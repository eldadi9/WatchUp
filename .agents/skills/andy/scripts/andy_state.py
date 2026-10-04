#!/usr/bin/env python3
"""
Andy state helper — atomic read/write/verify for .ai/andy/current.json.

Usage:
  python andy_state.py init <project_root>
  python andy_state.py read <project_root>
  python andy_state.py write <project_root> <json_patch_file_or_->
  python andy_state.py verify <project_root>
  python andy_state.py archive <project_root> [slug]
  python andy_state.py migrate-worktrees <project_root>
  python andy_state.py compact <project_root>
  python andy_state.py resume <project_root>
  python andy_state.py adopt-manual <project_root> <reason>   (emergency: audit a direct edit)

State root: `continuity_root` in an ancestor DREAM_TEAM_EXECUTION_PLAN.md (same repo,
not Git-ignored) wins; otherwise the Git common-dir root; otherwise project_root.

No third-party dependencies. Safe to run from any tool (Claude, Codex, Cursor, ...).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ANDY_DIR = os.path.join(".ai", "andy")
CURRENT_FILE = "current.json"
SESSIONS_DIR = "sessions"
HISTORY_DIR = "history"
# sha256 of the last current.json written by this tool; a mismatch means an unrecorded direct edit.
WRITE_DIGEST_FILE = "current.json.sha256"
CONTINUITY_PLAN_FILE = "DREAM_TEAM_EXECUTION_PLAN.md"
CONTINUITY_KEY = "continuity_root"
# a lock older than this belongs to a dead writer (checkpoint writes take milliseconds)
STALE_LOCK_SECONDS = 60
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.json"

# Token governance (dream-team/policies/governance.json resource_governance.checkpoint):
# current.json is a continuation packet, not a transcript.
CHECKPOINT_MAX_BYTES = 6144
MAX_TEXT_CHARS = 400
# list field -> (items kept at first, minimum kept); oldest entries move to history.
COMPACT_LISTS = {
    "last_completed": (6, 2),
    "decisions": (8, 3),
    "tests": (4, 1),
    "validation": (4, 1),
    "errors": (4, 1),
    "restrictions": (8, 4),
    "open_tasks": (10, 5),
    "files_touched": (30, 10),
    "files_created": (20, 5),
    "files_deleted": (20, 5),
    "source_of_truth": (6, 3),
}

DEFAULT_STATE = {
    "andy_version": "1.1",
    "project": "",
    "workstream": "",
    "goal": "",
    "status": "new",
    "current_phase": "",
    "current_task": "",
    "last_completed": [],
    "open_tasks": [],
    "next_action": "",
    "decisions": [],
    "restrictions": [],
    "files_touched": [],
    "files_created": [],
    "files_deleted": [],
    "tests": [],
    "validation": [],
    "errors": [],
    "blockers": [],
    "source_of_truth": [],
    "workspace_root": "",
    "git": {"branch": "", "head": "", "dirty": False},
    "last_worker": "",
    "last_session": "",
    "checkpoint_health": {
        "last_checkpoint": "",
        "turns_since_checkpoint": 0,
        "dirty_since_checkpoint": False,
    },
    "updated_at": "",
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")


def load_schema():
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_value(value, schema, path="$", errors=None):
    if errors is None:
        errors = []
    expected = schema.get("type")
    type_checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    }
    if expected in type_checks and not type_checks[expected](value):
        errors.append(f"{path}: expected {expected}")
        return errors
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if expected == "integer" and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: must be >= {schema['minimum']}")
    if expected == "array":
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            validate_value(item, item_schema, f"{path}[{index}]", errors)
    if expected == "object":
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required field {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unknown field {key!r}")
        for key, item in value.items():
            if key in properties:
                validate_value(item, properties[key], f"{path}.{key}", errors)
    return errors


def validate_state(data):
    return validate_value(data, load_schema())


def backup_corrupt(path):
    base = path + ".corrupt." + now_iso()
    backup = base
    counter = 1
    while os.path.exists(backup):
        backup = f"{base}.{counter}"
        counter += 1
    shutil.copy2(path, backup)
    return backup


def read_json(path, backup_on_corrupt=False):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        backup = backup_corrupt(path) if backup_on_corrupt else None
        return None, {"error": str(e), "backup": backup}


def deep_merge(base, patch):
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def run_git(project_root, args):
    try:
        out = subprocess.run(
            ["git"] + args,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except Exception:
        return None


def git_common_dir(project_root):
    raw = run_git(project_root, ["rev-parse", "--git-common-dir"])
    if not raw:
        return None
    return os.path.realpath(raw if os.path.isabs(raw) else os.path.join(project_root, raw))


def read_continuity_root(plan_path):
    """`continuity_root:` from the plan's machine-readable YAML block, or None."""
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    in_yaml = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_yaml = (not in_yaml) and line.strip() == "```yaml"
            continue
        if in_yaml and line.startswith(CONTINUITY_KEY + ":"):
            value = line.split(":", 1)[1].split("#", 1)[0].strip().strip("\"'")
            return value or None
    return None


def configured_state_root(project_root):
    return continuity_config(project_root)["state_root"]


def continuity_config(project_root):
    """Canonical continuity configuration (the Execution Plan) wins over Git-root inference.

    Applies only when project_root is in the same repository as the plan and is not a
    Git-ignored path, so nested external repositories never resolve to the Core Andy root.
    Returns {state_root, plan_dir, unparsed}: `unparsed` names a plan that mentions
    continuity_root but could not be read (verify/write stop instead of falling back).
    """
    found = {"state_root": None, "plan_dir": None, "unparsed": None}
    root = os.path.realpath(project_root)
    root_common = git_common_dir(root)
    directory = root
    while True:
        plan = os.path.join(directory, CONTINUITY_PLAN_FILE)
        value = read_continuity_root(plan) if os.path.isfile(plan) else None
        if not value and os.path.isfile(plan) and found["unparsed"] is None:
            try:
                with open(plan, "r", encoding="utf-8", errors="replace") as f:
                    if CONTINUITY_KEY + ":" in f.read():
                        found["unparsed"] = plan
            except OSError:
                pass
        if value:
            target = os.path.realpath(os.path.join(directory, value))
            parts = os.path.normcase(target).split(os.sep)[-3:]
            expected = [os.path.normcase(p) for p in (".ai", "andy", CURRENT_FILE)]
            state_root = os.path.dirname(os.path.dirname(os.path.dirname(target)))
            if parts != expected or not os.path.isdir(state_root):
                return found
            try:
                if os.path.commonpath([directory, state_root]) != directory:
                    return found
            except ValueError:
                return found
            if git_common_dir(directory) != root_common:
                return found
            if root_common and root != directory and run_git(directory, ["check-ignore", "-q", root]) is not None:
                return found
            found.update(state_root=state_root, plan_dir=directory, unparsed=None)
            return found
        parent = os.path.dirname(directory)
        if parent == directory:
            return found
        directory = parent


def canonical_project_root(project_root):
    configured = configured_state_root(project_root)
    if configured:
        return configured
    root = os.path.realpath(project_root)
    common = git_common_dir(root)
    if common and os.path.basename(common).lower() == ".git":
        return os.path.dirname(common)
    return root


def same_git_project(first, second):
    first_common = git_common_dir(first)
    second_common = git_common_dir(second)
    return bool(first_common and second_common and first_common == second_common)


def same_project(first, second):
    first_common = git_common_dir(first)
    second_common = git_common_dir(second)
    if first_common or second_common:
        return bool(first_common and second_common and first_common == second_common)
    return os.path.realpath(first) == os.path.realpath(second)


def andy_paths(project_root):
    config = continuity_config(project_root)
    configured = config["state_root"]
    state_root = configured or canonical_project_root(project_root)
    base = os.path.join(state_root, ANDY_DIR)
    return {
        "state_root": state_root,
        # configured roots keep file references relative to the Core project, whatever the cwd
        "workspace_root": state_root if configured else os.path.realpath(project_root),
        "configured": bool(configured),
        "plan_dir": config["plan_dir"],
        "unparsed_plan": config["unparsed"],
        "base": base,
        "current": os.path.join(base, CURRENT_FILE),
        "digest": os.path.join(base, WRITE_DIGEST_FILE),
        "sessions": os.path.join(base, SESSIONS_DIR),
        "history": os.path.join(base, HISTORY_DIR),
    }


def effective_workspace_root(data, paths):
    """A configured root is portable: never trust a stored absolute path (it may point at another clone)."""
    if paths["configured"]:
        return paths["workspace_root"]
    return data.get("workspace_root") or paths["workspace_root"]


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def record_write_digest(paths):
    with open(paths["digest"], "w", encoding="utf-8", newline="\n") as f:
        f.write(file_sha256(paths["current"]) + "\n")


def write_integrity(paths):
    """RECORDED (tool write), UNRECORDED_EDIT (direct edit since last tool write) or UNVERIFIED (no digest)."""
    if not os.path.exists(paths["digest"]):
        return "UNVERIFIED"
    with open(paths["digest"], "r", encoding="utf-8") as f:
        recorded = f.read().strip()
    return "RECORDED" if recorded == file_sha256(paths["current"]) else "UNRECORDED_EDIT"


def duplicate_states(project_root, paths):
    """Other current.json files that could be mistaken for the canonical checkpoint."""
    candidates = set()
    common = git_common_dir(os.path.realpath(project_root))
    boundary = paths.get("plan_dir")
    if common and os.path.basename(common).lower() == ".git":
        boundary = os.path.dirname(common)
    # every directory between project_root / state_root and the repository (or plan) boundary
    for start in (os.path.realpath(project_root), paths["state_root"]):
        directory = start
        while True:
            candidates.add(directory)
            if not boundary or os.path.normcase(directory) == os.path.normcase(boundary):
                break
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
    found = []
    for root in sorted(candidates):
        candidate = os.path.join(root, ANDY_DIR, CURRENT_FILE)
        if os.path.exists(candidate) and os.path.normcase(os.path.realpath(candidate)) != os.path.normcase(
                os.path.realpath(paths["current"])):
            found.append(candidate)
    return found


def atomic_write_json(path, data, validate=True):
    errors = validate_state(data) if validate else []
    if errors:
        raise ValueError("Invalid Andy state: " + "; ".join(errors))
    text = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(text)
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_andy_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


@contextmanager
def state_lock(base_dir, timeout_seconds=5):
    """Serialize checkpoint updates across AI tools and linked worktrees."""
    os.makedirs(base_dir, exist_ok=True)
    lock_path = os.path.join(base_dir, ".current.lock")
    deadline = time.monotonic() + timeout_seconds
    fd = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > STALE_LOCK_SECONDS:
                    os.remove(lock_path)  # the holder died mid-write
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Another Andy checkpoint write is still in progress")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass


def cmd_init(project_root):
    paths = andy_paths(project_root)
    os.makedirs(paths["sessions"], exist_ok=True)
    os.makedirs(paths["history"], exist_ok=True)
    if os.path.exists(paths["current"]):
        print(json.dumps({"status": "exists", "path": paths["current"]}))
        return
    state = json.loads(json.dumps(DEFAULT_STATE))
    state["project"] = os.path.basename(os.path.normpath(paths["state_root"]))
    state["workspace_root"] = paths["workspace_root"]
    timestamp = now_iso()
    state["updated_at"] = timestamp
    state["last_session"] = timestamp
    state["checkpoint_health"]["last_checkpoint"] = timestamp
    atomic_write_json(paths["current"], state)
    record_write_digest(paths)
    print(json.dumps({"status": "created", "path": paths["current"]}))


def cmd_read(project_root):
    paths = andy_paths(project_root)
    if not os.path.exists(paths["current"]):
        print(json.dumps({"status": "missing", "path": paths["current"]}))
        return
    data, problem = read_json(paths["current"], backup_on_corrupt=True)
    if problem:
        print(json.dumps({"status": "corrupt", **problem}))
        return 1
    errors = validate_state(data)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}))
        return 1
    print(json.dumps({
        "status": "ok",
        "state_root": paths["state_root"],
        "workspace_root": effective_workspace_root(data, paths),
        "data": data,
    }))
    return 0


def _cmd_write_unlocked(project_root, json_source):
    paths = andy_paths(project_root)
    if paths["unparsed_plan"]:
        print(json.dumps({"status": "continuity_config_unparsed", "plan": paths["unparsed_plan"],
                          "error": "continuity_root exists but cannot be read; fix the plan instead of writing elsewhere"}))
        return 1
    os.makedirs(paths["base"], exist_ok=True)
    if json_source == "-":
        raw = sys.stdin.read()
    else:
        with open(json_source, "r", encoding="utf-8") as f:
            raw = f.read()
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "invalid_input", "error": str(e)}))
        return 1
    if not isinstance(patch, dict):
        print(json.dumps({"status": "invalid_input", "error": "Patch must be a JSON object"}))
        return 1
    base_updated_at = patch.pop("_base_updated_at", None)
    if os.path.exists(paths["current"]):
        current, problem = read_json(paths["current"], backup_on_corrupt=True)
        if problem:
            print(json.dumps({"status": "corrupt", **problem}))
            return 1
        current_errors = validate_state(current)
        if current_errors:
            print(json.dumps({"status": "invalid", "errors": current_errors}))
            return 1
        if not base_updated_at:
            print(json.dumps({
                "status": "missing_precondition",
                "error": "Patch must include _base_updated_at from a fresh read",
                "current_updated_at": current.get("updated_at"),
            }))
            return 1
        if base_updated_at != current.get("updated_at"):
            print(json.dumps({
                "status": "stale_checkpoint",
                "error": "A newer Andy checkpoint already exists; read again before writing",
                "expected": base_updated_at,
                "current_updated_at": current.get("updated_at"),
                "last_worker": current.get("last_worker", ""),
            }))
            return 1
    else:
        current = json.loads(json.dumps(DEFAULT_STATE))
        current["project"] = os.path.basename(os.path.normpath(paths["state_root"]))
    data = deep_merge(current, patch)
    data["andy_version"] = "1.1"
    data["workspace_root"] = paths["workspace_root"]
    timestamp = now_iso()
    data["updated_at"] = timestamp
    data["last_session"] = timestamp
    data["checkpoint_health"] = deep_merge(
        data.get("checkpoint_health", {}),
        {
            "last_checkpoint": timestamp,
            "turns_since_checkpoint": 0,
            "dirty_since_checkpoint": False,
        },
    )
    live_git = git_state(project_root)
    if live_git is not None:
        data["git"] = live_git
    errors = validate_state(data)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}))
        return 1
    atomic_write_json(paths["current"], data)
    record_write_digest(paths)
    print(json.dumps({"status": "written", "path": paths["current"]}))
    return 0


def cmd_write(project_root, json_source):
    paths = andy_paths(project_root)
    if paths["unparsed_plan"]:
        return _cmd_write_unlocked(project_root, json_source)  # refuses before any directory or lock is created
    try:
        with state_lock(paths["base"]):
            return _cmd_write_unlocked(project_root, json_source)
    except TimeoutError as error:
        print(json.dumps({"status": "busy", "error": str(error)}))
        return 1


def checkpoint(project_root, patch, *, include_git=False, paths=None):
    """In-process automatic checkpoint for runtimes (no stdin, no manual save).

    Reads the current state under the same lock the CLI uses, so no
    _base_updated_at precondition is needed. Callers that checkpoint often
    pass `paths` from one andy_paths() call to skip the git lookup each time.
    Returns the written state.
    """
    paths = paths or andy_paths(project_root)
    if paths.get("unparsed_plan"):
        raise ValueError("continuity_root exists but cannot be read: " + paths["unparsed_plan"])
    with state_lock(paths["base"]):
        if os.path.exists(paths["current"]):
            current, problem = read_json(paths["current"], backup_on_corrupt=True)
            if problem or validate_state(current):
                current = json.loads(json.dumps(DEFAULT_STATE))
        else:
            current = json.loads(json.dumps(DEFAULT_STATE))
            current["project"] = os.path.basename(os.path.normpath(paths["state_root"]))
        data = deep_merge(current, dict(patch))
        data["andy_version"] = "1.1"
        data["workspace_root"] = paths["workspace_root"]
        timestamp = now_iso()
        data["updated_at"] = timestamp
        data["last_session"] = timestamp
        data["checkpoint_health"] = {
            "last_checkpoint": timestamp,
            "turns_since_checkpoint": 0,
            "dirty_since_checkpoint": False,
        }
        if include_git:
            live_git = git_state(project_root)
            if live_git is not None:
                data["git"] = live_git
        atomic_write_json(paths["current"], data)
        record_write_digest(paths)
        return data


def git_state(project_root):
    branch = run_git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None:
        return None
    head = run_git(project_root, ["rev-parse", "--short", "HEAD"])
    status = run_git(project_root, ["status", "--porcelain"])
    dirty = bool(status)
    return {"branch": branch, "head": head or "", "dirty": dirty}


def cmd_verify(project_root):
    paths = andy_paths(project_root)
    result = {"project_root": project_root, "state_root": paths["state_root"]}
    if paths["unparsed_plan"]:
        result.update(state="continuity_config_unparsed", continuity_config_unparsed=paths["unparsed_plan"])
        print(json.dumps(result))
        return 1
    if not os.path.exists(paths["current"]):
        result["state"] = "missing"
        print(json.dumps(result))
        return
    data, problem = read_json(paths["current"], backup_on_corrupt=True)
    if problem:
        result["state"] = "corrupt"
        result.update(problem)
        print(json.dumps(result))
        return 1

    schema_errors = validate_state(data)
    result["state"] = "invalid" if schema_errors else "ok"
    result["schema_errors"] = schema_errors
    if not isinstance(data, dict):
        print(json.dumps(result))
        return 1
    result["stored_git"] = data.get("git", {})
    workspace_root = effective_workspace_root(data, paths)
    result["workspace_root"] = workspace_root
    if not os.path.isdir(workspace_root) or not same_project(paths["state_root"], workspace_root):
        result["unsafe_workspace"] = workspace_root
        print(json.dumps(result))
        return 1
    live_git = git_state(workspace_root)
    result["live_git"] = live_git
    if live_git is not None:
        stored = data.get("git", {})
        result["git_drift"] = (
            stored.get("branch") != live_git.get("branch")
            or stored.get("head") != live_git.get("head")
            or stored.get("dirty") != live_git.get("dirty")
        )
    else:
        result["git_drift"] = False

    missing_files = []
    unsafe_paths = []
    deleted = set(data.get("files_deleted", []))
    checked = set()
    for key in ("files_touched", "files_created"):
        for rel in data.get(key, []):
            if rel in checked or rel in deleted:
                continue
            checked.add(rel)
            if not is_safe_project_relative(workspace_root, rel):
                unsafe_paths.append(rel)
                continue
            full = os.path.join(workspace_root, rel)
            if not os.path.exists(full):
                missing_files.append(rel)
    result["missing_files"] = missing_files
    result["unsafe_paths"] = unsafe_paths
    result["configured_root"] = paths["configured"]
    try:
        with state_lock(paths["base"]):
            result["write_integrity"] = write_integrity(paths)
    except TimeoutError:
        result["write_integrity"] = "BUSY"
    result["stale_duplicates"] = duplicate_states(project_root, paths)
    if paths["unparsed_plan"]:
        result["continuity_config_unparsed"] = paths["unparsed_plan"]
    # the canonical (configured) root must carry a write digest; legacy project roots may not yet
    integrity_blocks = result["write_integrity"] == "UNRECORDED_EDIT" or (
        paths["configured"] and result["write_integrity"] == "UNVERIFIED")
    print(json.dumps(result))
    blocked = (schema_errors or unsafe_paths or result["stale_duplicates"] or integrity_blocks
               or paths["unparsed_plan"])
    return 1 if blocked else 0


def cmd_adopt_manual(project_root, reason):
    """Emergency recovery: accept a direct edit of current.json explicitly and leave an audit record."""
    paths = andy_paths(project_root)
    if not reason or not reason.strip():
        print(json.dumps({"status": "invalid_input", "error": "adopt-manual requires a reason"}))
        return 1
    if not os.path.exists(paths["current"]):
        print(json.dumps({"status": "missing", "path": paths["current"]}))
        return 1
    with state_lock(paths["base"]):
        data, problem = read_json(paths["current"])
        if problem:
            print(json.dumps({"status": "corrupt", **problem}))
            return 1
        errors = validate_state(data)
        if errors:
            print(json.dumps({"status": "invalid", "errors": errors}))
            return 1
        before = write_integrity(paths)
        os.makedirs(paths["history"], exist_ok=True)
        audit = os.path.join(paths["history"], f"{now_iso()}_manual-edit-adopted.json")
        atomic_write_json(audit, {"adopted_at": now_iso(), "reason": reason.strip(), "integrity_before": before,
                                  "sha256": file_sha256(paths["current"]), "updated_at": data.get("updated_at")},
                          validate=False)
        record_write_digest(paths)
    print(json.dumps({"status": "adopted", "integrity_before": before, "audit": audit}))
    return 0


def is_safe_project_relative(project_root, rel):
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        return False
    root = os.path.realpath(project_root)
    candidate = os.path.realpath(os.path.join(root, rel))
    try:
        return os.path.commonpath([root, candidate]) == root
    except ValueError:
        return False


def safe_slug(value):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "workstream"


def worktree_roots(project_root):
    raw = run_git(project_root, ["worktree", "list", "--porcelain"])
    if not raw:
        return [os.path.realpath(project_root)]
    roots = []
    for line in raw.splitlines():
        if line.startswith("worktree "):
            candidate = os.path.realpath(line[len("worktree "):])
            if same_git_project(project_root, candidate):
                roots.append(candidate)
    return roots or [os.path.realpath(project_root)]


def timestamp_key(value):
    raw = str(value or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def resolve_workspace_root(data, roots, source_root):
    referenced = set(data.get("files_touched", []) + data.get("files_created", []))
    deleted = set(data.get("files_deleted", []))
    referenced = [path for path in referenced if path not in deleted]
    stored_git = data.get("git", {})
    preferred = data.get("workspace_root")

    def score(root):
        existing = sum(
            1 for rel in referenced
            if is_safe_project_relative(root, rel) and os.path.exists(os.path.join(root, rel))
        )
        live = git_state(root) or {}
        git_matches = int(
            bool(stored_git.get("branch"))
            and stored_git.get("branch") == live.get("branch")
            and stored_git.get("head") == live.get("head")
        )
        preferred_match = int(bool(preferred) and os.path.realpath(root) == os.path.realpath(preferred))
        source_match = int(os.path.realpath(root) == os.path.realpath(source_root))
        return existing, git_matches, preferred_match, source_match

    return max(roots, key=score)


def cmd_migrate_worktrees(project_root):
    paths = andy_paths(project_root)
    roots = worktree_roots(project_root)
    candidates = []
    for root in roots:
        candidate = os.path.join(root, ANDY_DIR, CURRENT_FILE)
        if not os.path.exists(candidate):
            continue
        data, problem = read_json(candidate)
        if problem or validate_state(data):
            continue
        candidates.append((str(data.get("updated_at") or ""), root, candidate, data))
    if not candidates:
        print(json.dumps({"status": "missing", "state_root": paths["state_root"]}))
        return 1
    _, source_root, source_path, latest = max(candidates, key=lambda item: timestamp_key(item[0]))
    latest = json.loads(json.dumps(latest))
    latest["andy_version"] = "1.1"
    latest["project"] = os.path.basename(os.path.normpath(paths["state_root"]))
    latest["workspace_root"] = resolve_workspace_root(latest, roots, source_root)
    os.makedirs(paths["base"], exist_ok=True)
    backup = None
    if os.path.exists(paths["current"]) and os.path.realpath(source_path) != os.path.realpath(paths["current"]):
        current, problem = read_json(paths["current"])
        if not problem and not validate_state(current):
            os.makedirs(paths["history"], exist_ok=True)
            backup = os.path.join(
                paths["history"],
                f"{now_iso()}_pre-worktree-migration.json",
            )
            atomic_write_json(backup, current)
    atomic_write_json(paths["current"], latest)
    record_write_digest(paths)
    print(json.dumps({
        "status": "migrated",
        "source": source_path,
        "target": paths["current"],
        "backup": backup,
        "updated_at": latest.get("updated_at"),
        "workspace_root": latest["workspace_root"],
        "candidates": len(candidates),
    }))
    return 0


def cmd_archive(project_root, slug=None):
    paths = andy_paths(project_root)
    if not os.path.exists(paths["current"]):
        print(json.dumps({"status": "missing", "path": paths["current"]}))
        return 1
    data, problem = read_json(paths["current"], backup_on_corrupt=True)
    if problem:
        print(json.dumps({"status": "corrupt", **problem}))
        return 1
    errors = validate_state(data)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}))
        return 1
    if data.get("status") != "completed":
        print(json.dumps({"status": "not_completed", "error": "Set status to completed before archiving"}))
        return 1
    os.makedirs(paths["history"], exist_ok=True)
    label = safe_slug(slug or data.get("workstream") or data.get("project") or "workstream")
    target = os.path.join(paths["history"], f"{now_iso()}_{label}.json")
    counter = 1
    while os.path.exists(target):
        target = os.path.join(paths["history"], f"{now_iso()}_{label}_{counter}.json")
        counter += 1
    atomic_write_json(target, data)
    print(json.dumps({"status": "archived", "path": target}))
    return 0


def _state_bytes(data):
    return len(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def compact_state(data, max_bytes=CHECKPOINT_MAX_BYTES):
    """Return (compacted, overflow). Keeps the newest list items; never drops required keys."""
    compacted = json.loads(json.dumps(data))
    overflow = {}

    def clip(value):
        if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
            return value[: MAX_TEXT_CHARS - 3] + "..."
        return value

    for key, value in list(compacted.items()):
        if isinstance(value, str):
            if len(value) > MAX_TEXT_CHARS:
                overflow.setdefault(key, value)
            compacted[key] = clip(value)
        elif isinstance(value, list):
            compacted[key] = [clip(v) for v in value]
    keep = {key: first for key, (first, _minimum) in COMPACT_LISTS.items()}
    while True:
        for key, count in keep.items():
            items = data.get(key)
            if isinstance(items, list) and len(items) > count:
                overflow[key] = items[: len(items) - count]
                compacted[key] = [clip(v) for v in items[len(items) - count:]]
        if _state_bytes(compacted) <= max_bytes:
            break
        shrinkable = [k for k, (_first, minimum) in COMPACT_LISTS.items() if keep[k] > minimum]
        if not shrinkable:
            break
        for key in shrinkable:
            keep[key] -= 1
    return compacted, overflow


def resume_packet(data):
    """The token-efficient continuation view (resource_governance.checkpoint.resume_fields)."""
    return {
        "objective": data.get("goal"),
        "completed": list(data.get("last_completed") or [])[-COMPACT_LISTS["last_completed"][0]:],
        "active": {"phase": data.get("current_phase"), "task": data.get("current_task"), "open_tasks": data.get("open_tasks") or []},
        "blocked": data.get("blockers") or [],
        "changed_files": sorted(set((data.get("files_touched") or []) + (data.get("files_created") or []))),
        "validation_state": list(data.get("validation") or [])[-2:],
        "next_exact_action": data.get("next_action"),
        "essential_decisions": list(data.get("decisions") or [])[-COMPACT_LISTS["decisions"][0]:],
    }


def cmd_compact(project_root):
    paths = andy_paths(project_root)
    if not os.path.exists(paths["current"]):
        print(json.dumps({"status": "missing", "path": paths["current"]}))
        return 1
    with state_lock(paths["base"]):
        data, problem = read_json(paths["current"], backup_on_corrupt=True)
        if problem:
            print(json.dumps({"status": "corrupt", **problem}))
            return 1
        before = _state_bytes(data)
        compacted, overflow = compact_state(data)
        errors = validate_state(compacted)
        if errors:
            print(json.dumps({"status": "invalid", "errors": errors}))
            return 1
        archived = None
        if overflow:
            os.makedirs(paths["history"], exist_ok=True)
            archived = os.path.join(paths["history"], f"{now_iso().replace(':', '')}_compact-overflow.json")
            atomic_write_json(archived, {"compacted_at": now_iso(), "workstream": data.get("workstream"), "overflow": overflow},
                              validate=False)
        atomic_write_json(paths["current"], compacted)
        record_write_digest(paths)
    print(json.dumps({"status": "compacted", "bytes_before": before, "bytes_after": _state_bytes(compacted),
                      "max_bytes": CHECKPOINT_MAX_BYTES, "overflow": archived}))
    return 0


def cmd_resume(project_root):
    paths = andy_paths(project_root)
    data, problem = read_json(paths["current"]) if os.path.exists(paths["current"]) else (None, {"error": "missing"})
    if problem or data is None:
        print(json.dumps({"status": "unavailable", **(problem or {})}))
        return 1
    print(json.dumps(resume_packet(data), ensure_ascii=False, indent=2))
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    action = sys.argv[1]
    project_root = os.path.abspath(sys.argv[2])
    result = 0
    if action == "init":
        result = cmd_init(project_root) or 0
    elif action == "read":
        result = cmd_read(project_root) or 0
    elif action == "write":
        if len(sys.argv) < 4:
            print("write requires a json file path or -")
            sys.exit(1)
        result = cmd_write(project_root, sys.argv[3]) or 0
    elif action == "verify":
        result = cmd_verify(project_root) or 0
    elif action == "archive":
        result = cmd_archive(project_root, sys.argv[3] if len(sys.argv) > 3 else None) or 0
    elif action == "migrate-worktrees":
        result = cmd_migrate_worktrees(project_root) or 0
    elif action == "compact":
        result = cmd_compact(project_root) or 0
    elif action == "resume":
        result = cmd_resume(project_root) or 0
    elif action == "adopt-manual":
        result = cmd_adopt_manual(project_root, " ".join(sys.argv[3:])) or 0
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
    sys.exit(result)


if __name__ == "__main__":
    main()
