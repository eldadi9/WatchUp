#!/usr/bin/env python3
"""Dream Team agent governor: Claude Code PreToolUse / PostToolUse / SubagentStop hook.

Enforces dream-team/policies/governance.json -> resource_governance for
host-native Claude subagents (Agent / Task tool):

- concurrency: default 1, normal max 2, above 2 only with a recorded
  justification file AND an `authorize parallel` ledger record, never above
  hard_max;
- Yuli and Ori are main-thread logical stages, never spawned subagents;
- usage states GREEN / YELLOW / ORANGE / RED from a proxy work-unit ledger
  (Claude exposes no quota percentage: platform telemetry is UNAVAILABLE);
- HIGH / ESCALATED models need a `MODEL_WHY: <reason>` line in the prompt;
- the runtime authorization state (.ai/dream-team/) is protected by a guard
  hook; budget and parallelism can only be raised through the governor CLI;
- every decision is appended to .ai/dream-team/usage-ledger.jsonl; that
  append-only ledger is the ONLY authority: units, authorized budget/parallel
  values and the mission identity AND complexity (the latest main-thread
  MISSION_SET entry) are re-derived from it on every call. mission.json is an
  informational pointer only; mission-budget.json may only LOWER the budget;
  an old usage-counters.json is ignored. Non-finite / negative ledger numbers
  are ignored and ledgered as LEDGER_VALUE_MALFORMED; a NaN ratio is RED;
- each PreToolUse ledger entry records policy_sha256 / policy_path of the
  governance file actually loaded;
- resource hotfix (ALIGN-3 WP-3a incident): agent admission (installed dt-* or a bounded
  DT_AGENT_CONTRACT compatibility worker; unknown types denied), mission / work-package / agent
  budgets that survive respawns (AGENT_USAGE ledger entries), a runtime watchdog that reads the
  host subagent transcript (model turns, per-call context, HTTP 429) and denies every further
  tool call at RED, a quota hold after a 429, single writer, no background shells in subagents;
- the hook fails closed: a governor error denies the spawn (pre), never
  blocks finished work (post / stop).

Usage (from .claude/settings.json):
  python .claude/hooks/dream-team-agent-governor.py pre     # PreToolUse, matcher Agent|Task
  python .claude/hooks/dream-team-agent-governor.py post    # PostToolUse, matcher Agent|Task
  python .claude/hooks/dream-team-agent-governor.py stop    # SubagentStop
  python .claude/hooks/dream-team-agent-governor.py guard   # PreToolUse, matcher * (state guard on Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell;
                                                            # runtime watchdog on every subagent tool call)
  python agent_governor.py quota-clear --reason TEXT          (main thread, after a provider quota reset)
  python agent_governor.py wp <wp_id>                         (main thread: Ori registers a WP of the active mission; unregistered wp_ids are denied)
  (PostToolUseFailure may also be routed to `post`: it releases the slot unconditionally.)
Main-thread CLI (audited in the ledger as authorized_by=main-thread-cli; subagents may only run `report`):
  python agent_governor.py mission <mission_id> [--complexity simple|normal|complex] [--project-dir P]
  python agent_governor.py authorize budget <work_units> --reason TEXT [--project-dir P]
  python agent_governor.py authorize parallel <max> --reason TEXT [--project-dir P]
  python agent_governor.py release <tool_use_id> | --stale [--project-dir P]
  python agent_governor.py report [--project-dir P]
Input is the hook JSON on stdin. A denial exits 2 with the reason on stderr.
Break-glass (Owner only, audited, blocks Gate GO): DREAM_TEAM_GOVERNOR_BREAK_GLASS=1; if the
break-glass audit record cannot be written the call is denied (exit 2): no unaudited bypass.

PARTIAL platform limitation (documented residual): the guard is a text/path filter on hook
payloads, not an OS sandbox. A main-thread or subagent command that builds the state path
dynamically (python -c, variable or environment expansion, encoded strings, a script written
elsewhere and executed) is not recognised by the guard. Real isolation of .ai/dream-team needs
OS-level permissions (separate account / read-only mount), which Claude Code does not provide.
Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import shlex
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_FILES = (HERE / "dream-team-governor-policy.json", HERE / "governor-policy.json")
CANONICAL_POLICY = HERE.parent / "policies" / "governance.json"
STATE_DIR = Path(".ai") / "dream-team"
ACTIVE_FILE = "active-agents.json"
LEDGER_FILE = "usage-ledger.jsonl"
BUDGET_FILE = "mission-budget.json"
JUSTIFICATION_FILE = "parallel-justification.json"
MISSION_FILE = "mission.json"
SLOT_EVENTS_FILE = "slot-events.json"
LOCK_FILE = "active-agents.lock"
STALE_SECONDS = 90 * 60
LOCK_STALE_SECONDS = 30
LOCK_TIMEOUT = 3.0
STOPPED_KEEP = 50
COORDINATOR_TYPES = {"yuli", "ori", "dt-yuli-chief-of-staff", "yuli-ceo", "uri-orchestrator", "dt-ori"}
COMPLEXITIES = ("simple", "normal", "complex")
STATE_ORDER = ("GREEN", "YELLOW", "ORANGE", "RED")
SHELL_TOOLS = {"Bash", "PowerShell"}
# Subagent shells must not start unmetered model calls or processes that outlive the agent (CHAOS C05/C06).
# Text heuristics (PROVEN_PROXY): a dynamically built command is not recognised (documented PARTIAL).
NESTED_LLM_RE = re.compile(
    r"(?:^|[;&|(`]|\$\(|\b(?:npx|exec|call|xargs|cmd(?:\.exe)?\s+/[ck]|(?:powershell|pwsh)(?:\.exe)?\s+-c(?:ommand)?)\s)"
    r"\s*[\"']?(?:[^\s\"']*[\\/])?(?:claude|codex|gemini|cursor-agent|aider|ollama)(?:\.exe|\.cmd|\.ps1)?[\"']?(?=\s|$|[;&|)`])"
    r"|anthropic-ai/claude-code|\b(import|from)\s+(anthropic|openai)\b|api\.(anthropic|openai)\.com|api\.x\.ai"
    r"|generativelanguage\.googleapis\.com", re.IGNORECASE)
DETACH_RE = re.compile(
    r"\b(nohup|setsid|disown|schtasks|start-process|start-job|start-threadjob|invoke-wmimethod)\b"
    r"|\bwmic\s+process\s+call\s+create\b|(^|[\s;&|(])start\s+(/b|/min|\"\")", re.IGNORECASE)
BASH_BACKGROUND_RE = re.compile(r"(?<![&>|])&(?![&>\d])")
GUARD_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"} | SHELL_TOOLS
PROTECTED_B = (".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/", ".claude/agents/")
PROTECTED_B_FILES = ("settings.json", "settings.local.json")
PROTECTED_B_DIRS = ("hooks", "agents")
SENSITIVE_STATE_FILES = (BUDGET_FILE, JUSTIFICATION_FILE, MISSION_FILE, "usage-counters.json")
STATE_FILE_NAMES = ("usage-ledger", "mission-budget", "parallel-justification", "usage-counters", "active-agents",
                    "slot-events", "mission.json", "agent-usage")
AGENT_USAGE_DIR = "agent-usage"
CONTRACT_RE = re.compile(r"DT_AGENT_CONTRACT:[ \t]*(\{[^\r\n]*\})")
WP_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,48}$")
# 429 as number or string, and the provider's rate_limit_error type (CHAOS C08)
QUOTA_MARKER = re.compile(rb'"apiErrorStatus"\s*:\s*"?429(?!\d)|"type"\s*:\s*"rate_limit_error"')
QUOTA_SCAN_BYTES = 256 * 1024
WRITE_TOOLS = ("write", "edit", "multiedit", "notebookedit")
WRITE_FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
MODEL_WHY_RE = re.compile(r"MODEL_WHY:[ \t]*(.{10,})")
AGENT_ID_RE = re.compile(r"agentId:\s*([A-Za-z0-9_-]+)")
GOVERNOR_CALL_RE = re.compile(r"agent[_-]governor\.py(?:\s+(\S+))?")
SHELL_META_RE = re.compile(r"[;&|<>`$()\r\n]")
GOVERNOR_TOKEN_RE = re.compile(r"^[^a-z0-9]*(dream-team-)?agent[_-]?gov")
CLI_ARG_RE = re.compile(r"^[A-Za-z0-9_.:=/\\ -]+$")
CLI_INTERPRETERS = {"python", "python3", "py", "python.exe", "python3.exe"}
CLI_SCRIPTS = {"agent_governor.py", "dream-team-agent-governor.py"}
CLI_MODES = ("mission", "authorize", "report", "release", "quota-clear", "wp")
CLI_AUTHORIZER = "main-thread-cli"
POLICY_META = {"path": "", "sha256": ""}
# WP-1 AUTHORITY LOCK: Main = Host. Implementation writes belong to Workers; Main plumbing (state, evidence, plan, hashes) stays possible.
MAIN_PLUMBING_DEFAULT = (".ai/**", "**/.ai/**", "**/evidence/**", "**/DREAM_TEAM_EXECUTION_PLAN.md", "**/*.sha256", ".claude/settings*.json")
MAIN_SHELL_WRITE_RE = re.compile(
    r"(?<![&>])>{1,2}\s*(?!/dev/null|&|nul\b)\S|\bsed\s+(-[a-z]*i|--in-place)|\btee\b|\b(set|add)-content\b|\bout-file\b"
    r"|\bgit\s+(?:(?:apply|am|restore|stash|reset|clean|commit)\b|checkout\s+--)|\btouch\b|\bpatch\s+-|\b(cp|mv|copy|move|move-item|copy-item|rm|del|remove-item|new-item)\b",
    re.IGNORECASE)
INLINE_INTERPRETER_RE = re.compile(r"\b(?:python3?|py|node|deno|bun|ruby|perl|php|powershell|pwsh)(?:\.exe)?\b", re.IGNORECASE)
INLINE_MARKER_RE = re.compile(r"<<|\s-(?:c|e|command|encodedcommand)\b|\s-(?:\s|$)|@['\"]", re.IGNORECASE)
INLINE_WRITE_CALL_RE = re.compile(
    r"\bopen\s*\([^()]*?,\s*(?:mode\s*=\s*)?['\"][rbtU]*[wax+]|\.write_(?:text|bytes)\s*\(|\bwriteFile(?:Sync)?\s*\(|\bappendFile(?:Sync)?\s*\("
    r"|\bcreateWriteStream\s*\(|\bshutil\.(?:copy\w*|move|rmtree)\s*\(|\bos\.(?:replace|rename|remove|unlink|makedirs)\s*\("
    r"|\.(?:unlink|rmdir|touch|mkdir)\s*\(|\bWriteAll(?:Text|Lines|Bytes)\b|\bFile\.(?:write|open)\b|\b(?:set|add)-content\b|\bout-file\b"
    r"|\b(?:new|remove|copy|move)-item\b|\bsubprocess\.\w+\s*\(", re.IGNORECASE)
INLINE_PATH_TOKEN_RE = re.compile(
    r"[\w.\-~]+(?:/[\w.\-~]+)+|[\w\-]+\.(?:py|js|mjs|cjs|ts|tsx|jsx|json|md|txt|ya?ml|toml|cfg|ini|html?|css|sh|ps1|bat|cmd|cs|java|go|rs|rb|php|sql|csv|xml|lock|env)\b",
    re.IGNORECASE)


def _load_policy_file(path: Path, unwrap: bool) -> dict:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    POLICY_META["path"], POLICY_META["sha256"] = str(path), hashlib.sha256(raw).hexdigest()
    return data["resource_governance"] if unwrap else data


def load_policy() -> dict:
    """Policy source order: env override, canonical install, generated sibling snapshot. Errors raise."""
    override = os.environ.get("DREAM_TEAM_GOVERNANCE_PATH")
    if override:
        return _load_policy_file(Path(override), True)
    if CANONICAL_POLICY.is_file():
        return _load_policy_file(CANONICAL_POLICY, True)
    for path in POLICY_FILES:
        if path.is_file():
            return _load_policy_file(path, False)
    raise FileNotFoundError("no Dream Team governor policy found (canonical governance.json or sibling snapshot)")


def project_root(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _read_json_sha(path: Path):
    """(parsed JSON or None, sha256 of the raw bytes) of a state file."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None, ""
    sha = hashlib.sha256(raw).hexdigest()
    try:
        return json.loads(raw.decode("utf-8")), sha
    except ValueError:
        return None, sha


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _ledger(state_dir: Path, entry: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    path = state_dir / LEDGER_FILE
    prefix = b""
    try:
        if path.stat().st_size:
            with path.open("rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    prefix = b"\n"
    except OSError:
        pass
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("ab") as fh:
        fh.write(prefix + line.encode("utf-8"))


@contextmanager
def _state_lock(state_dir: Path, timeout: float = LOCK_TIMEOUT):
    """Serialize read-decide-write of the slot file across parallel hook processes."""
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / LOCK_FILE
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError(f"governor state lock busy: {lock}")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock.unlink()
        except OSError:
            pass


def _agent_default_model(root: Path, agent_type: str) -> str:
    """The `model:` frontmatter of .claude/agents/<agent_type>.md, used when the spawn omits a model."""
    path = root / ".claude" / "agents" / f"{agent_type}.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    models = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        if key.strip() == "model":
            models.append(value.strip().strip("'\"").lower())
    if len(models) > 1:
        raise ValueError("duplicate model key")
    return models[0] if models else ""


def model_class_of(model: str) -> str:
    """Conservative model classification: any unrecognised non-empty model (incl. 'inherit') is HIGH."""
    name = str(model or "").lower()
    if not name:
        return "STANDARD"
    if "fable" in name:
        return "ESCALATED"
    if "opus" in name:
        return "HIGH"
    if "sonnet" in name:
        return "STANDARD"
    if "haiku" in name:
        return "FAST"
    return "HIGH"


def _read_active(state_dir: Path) -> list[dict]:
    """The raw slot list. A missing file is empty; an unparsable or non-list file raises (fail-closed)."""
    path = state_dir / ACTIVE_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(s, dict) for s in data):
        raise ValueError(f"{ACTIVE_FILE} is not a JSON list of slots")
    return data


def _active(state_dir: Path, now: float) -> list[dict]:
    return [s for s in _read_active(state_dir) if now - float(s.get("started", 0)) < STALE_SECONDS]


def _work_units(policy: dict, model_class: str, reasoning: str) -> float:
    usage = policy["usage_governor"]
    weight = float(usage["work_unit_weights"].get(model_class, usage["work_unit_weights"]["STANDARD"]))
    return weight * float(usage["reasoning_multipliers"].get(reasoning, 1.5))


def _usage_key(mission, session: str) -> str:
    return str(mission["mission_id"]) if mission else f"session:{session}"


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _ledger_number(value):
    """A ledger numeric: a real (non-bool) finite number >= 0, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _derive(state_dir: Path) -> dict:
    """Everything the governor trusts, re-derived from the append-only ledger on every call."""
    d = {"units": {}, "mission": None, "budget": {}, "parallel": {}, "model_calls": {}, "seen_self_auth": set(), "malformed": [],
         "seen_malformed": set(), "wps": set(), "wp_attempts": {}, "wp_prompts": {}, "wp_calls": {}, "mission_calls": {},
         "usage_agents": set(), "quota_hold": None, "quota_seen": set()}
    try:
        data = (state_dir / LEDGER_FILE).read_bytes()
    except OSError:
        return d
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        event = entry.get("event")
        cli = str(entry.get("authorized_by") or "").startswith("main-thread")
        bad = None
        if event == "PreToolUse" and entry.get("decision") == "allow":
            key = entry.get("mission") or (f"session:{entry['session']}" if entry.get("session") else None)
            if key:
                if "work_units" in entry and _ledger_number(entry["work_units"]) is None:
                    bad = "work_units"
                else:
                    d["units"][key] = float(d["units"].get(key, 0.0)) + float(_ledger_number(entry.get("work_units")) or 0.0)
                if entry.get("wp"):
                    wp_key = f"{key}/{entry['wp']}"
                    d["wp_attempts"][wp_key] = d["wp_attempts"].get(wp_key, 0) + 1
                    d["wp_prompts"].setdefault(wp_key, set()).add(str(entry.get("prompt_sha256") or ""))
        elif event == "AGENT_USAGE" and entry.get("agent_id") and str(entry["agent_id"]) not in d["usage_agents"]:
            calls = _ledger_number(entry.get("model_calls"))
            if calls is None and entry.get("model_calls") is not None:
                bad = "model_calls"
            else:
                d["usage_agents"].add(str(entry["agent_id"]))
                key = str(entry.get("mission") or "unknown")
                d["mission_calls"][key] = d["mission_calls"].get(key, 0.0) + (calls or 0.0)
                if entry.get("wp"):
                    wp_key = f"{key}/{entry['wp']}"
                    d["wp_calls"][wp_key] = d["wp_calls"].get(wp_key, 0.0) + (calls or 0.0)
        elif event == "QUOTA_EVENT":
            d["quota_hold"] = entry
            if entry.get("line_sha256"):
                d["quota_seen"].add(entry["line_sha256"])
        elif event == "QUOTA_CLEAR" and cli:
            d["quota_hold"] = None
        elif event == "MISSION_SET" and cli and str(entry.get("mission") or "").strip():
            complexity = str(entry.get("complexity") or "normal").lower()
            d["mission"] = {"mission_id": str(entry["mission"]).strip(),
                            "complexity": complexity if complexity in COMPLEXITIES else "normal",
                            "host_only": entry.get("host_only") is True}
        elif event == "WP_REGISTERED" and cli and str(entry.get("mission") or "").strip() and str(entry.get("wp") or "").strip():
            d["wps"].add(f"{entry['mission']}/{entry['wp']}")
        elif event == "AUTHORIZE" and cli and entry.get("mission") and entry.get("kind") in ("budget", "parallel", "model_calls"):
            raw_value = entry.get("value", entry.get("max_parallel", entry.get("work_units")))
            value = _ledger_number(raw_value)
            if value is None:
                bad = "value"
            else:
                book = d[entry["kind"]]
                book[entry["mission"]] = max(float(book.get(entry["mission"], 0)), value)
        elif event == "SELF_AUTH_ATTEMPT" and entry.get("kind") in ("budget", "parallel") and entry.get("file_sha256"):
            d["seen_self_auth"].add(f"{entry['kind']}:{entry['file_sha256']}")
        elif event == "LEDGER_VALUE_MALFORMED" and entry.get("line_sha256"):
            d["seen_malformed"].add(entry["line_sha256"])
        if bad:
            d["malformed"].append({"line_sha256": hashlib.sha256(raw).hexdigest(), "field": bad, "source_event": event})
    return d


def _ledger_malformed(state_dir: Path, derived: dict) -> None:
    for item in derived["malformed"]:
        if item["line_sha256"] not in derived["seen_malformed"]:
            derived["seen_malformed"].add(item["line_sha256"])
            _ledger(state_dir, {"event": "LEDGER_VALUE_MALFORMED", **item})


def _self_auth_attempt(state_dir: Path, derived: dict, kind: str, sha: str, **fields) -> None:
    tag = f"{kind}:{sha}"
    if tag in derived["seen_self_auth"]:
        return
    derived["seen_self_auth"].add(tag)
    _ledger(state_dir, {"event": "SELF_AUTH_ATTEMPT", "kind": kind, "file_sha256": sha, **fields})


def budget_state(policy: dict, used: float, budget: float) -> str:
    try:
        ratio = used / budget if budget else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return "RED"
    if math.isnan(ratio):
        return "RED"
    state = "GREEN"
    for name in STATE_ORDER[1:]:
        if ratio >= float(policy["usage_governor"]["states"][name]["from"]):
            state = name
    return state


# --- runtime watchdog (resource governance hotfix) ---------------------------
def _frontmatter(root: Path, agent_type: str) -> dict | None:
    """Frontmatter key/values of .claude/agents/<agent_type>.md; None when no definition is installed."""
    path = root / ".claude" / "agents" / f"{agent_type}.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    fields: dict = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("'\"")
    return fields


def _parse_contract(prompt) -> tuple[dict | None, str]:
    match = CONTRACT_RE.search(prompt) if isinstance(prompt, str) else None
    if not match:
        return None, "missing DT_AGENT_CONTRACT line"
    try:
        contract = json.loads(match.group(1))
    except ValueError:
        return None, "DT_AGENT_CONTRACT is not valid one-line JSON"
    if not isinstance(contract, dict):
        return None, "DT_AGENT_CONTRACT is not a JSON object"
    return contract, ""


def admit(root: Path, agent_type: str, tool_input: dict, wd: dict, mission, model: str, wps=frozenset()) -> dict:
    """Agent admission. Returns {ok, reason, wp, access, max_turns, role, kind}."""
    adm, agent_cfg = wd["admission"], wd["agent"]
    hard = int(agent_cfg["max_turns_hard"])
    prompt = tool_input.get("prompt")
    contract, why = _parse_contract(prompt)
    if agent_type.startswith(adm["registered_prefix"]):
        fm = _frontmatter(root, agent_type)
        if fm is None:
            return {"ok": False, "reason": f"'{agent_type}' is not installed (no .claude/agents/{agent_type}.md); unregistered agents are denied"}
        tools = fm.get("tools", "")
        access = "write" if (not tools or any(t in tools.lower() for t in WRITE_TOOLS)) else "read"
        max_turns = min(int(_num(fm.get("maxTurns"), hard) or hard), hard)
        info = {"ok": True, "reason": "", "kind": "registered", "access": access, "max_turns": max_turns, "wp": None,
                "role": agent_type}
        if contract is None:
            return info
    elif agent_type in set(adm["compat_types"]):
        if contract is None:
            return {"ok": False, "reason": (f"'{agent_type}' is an unrestricted host agent: {why}. Use an installed dt-* agent, or a bounded "
                                            "compatibility worker with one line `DT_AGENT_CONTRACT: {json}` carrying "
                                            + ", ".join(adm["contract_required_fields"]))}
        info = {"ok": True, "reason": "", "kind": "compat", "role": None}
    else:
        return {"ok": False, "reason": f"unknown agent type '{agent_type}' (not dt-* and not a governed compatibility type): denied"}
    missing = [f for f in adm["contract_required_fields"] if contract.get(f) in (None, "", [], {})]
    if missing:
        return {"ok": False, "reason": f"DT_AGENT_CONTRACT missing fields: {', '.join(missing)}"}
    if not mission:
        return {"ok": False, "reason": "DT_AGENT_CONTRACT needs an active mission: run `agent_governor.py mission <id>` in the main thread"}
    if str(contract["mission_id"]) != str(mission["mission_id"]):
        return {"ok": False, "reason": f"DT_AGENT_CONTRACT mission_id '{contract['mission_id']}' is not the active mission '{mission['mission_id']}'"}
    if not WP_ID_RE.match(str(contract["wp_id"])):
        return {"ok": False, "reason": "DT_AGENT_CONTRACT wp_id must match [A-Za-z0-9._-]{1,48}"}
    if f"{mission['mission_id']}/{contract['wp_id']}" not in wps:
        return {"ok": False, "reason": (f"DT_AGENT_CONTRACT wp_id '{contract['wp_id']}' is not registered for mission "
                                        f"'{mission['mission_id']}': Ori registers it from the main thread with `agent_governor.py wp <wp_id>`")}
    if str(contract["access"]) not in ("read", "write"):
        return {"ok": False, "reason": "DT_AGENT_CONTRACT access must be read or write"}
    turns = _num(contract["max_turns"])
    if isinstance(contract["max_turns"], bool) or turns is None or turns < 1 or turns > hard or int(turns) != turns:
        return {"ok": False, "reason": f"DT_AGENT_CONTRACT max_turns must be an integer 1..{hard}"}
    if info["kind"] == "compat" and model_class_of(str(contract["model"])) != model_class_of(model):
        return {"ok": False, "reason": "DT_AGENT_CONTRACT model must match the explicit spawn model"}
    if not isinstance(contract["files"], list) or not isinstance(contract["tools"], list):
        return {"ok": False, "reason": "DT_AGENT_CONTRACT files and tools must be lists"}
    max_turns = min(int(turns), info.get("max_turns") or hard)
    access = "write" if "write" in (str(contract["access"]), info.get("access")) else "read"
    if info["kind"] == "registered":
        access = info["access"] if info["access"] == "write" else str(contract["access"])
    return {**info, "wp": str(contract["wp_id"]), "access": access, "max_turns": max_turns, "role": str(contract["role"]),
            "files": [str(f) for f in contract["files"]]}


def _transcript_candidates(event: dict, agent_id: str) -> list[Path]:
    out = []
    for key in ("agent_transcript_path", "transcript_path"):
        raw = event.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        if path.name == f"agent-{agent_id}.jsonl":
            out.append(path)
        elif key == "transcript_path":
            session = str(event.get("session_id") or path.stem)
            out.append(path.parent / session / "subagents" / f"agent-{agent_id}.jsonl")
            out.append(path.parent / "subagents" / f"agent-{agent_id}.jsonl")
    return out


def _find_transcript(event: dict, agent_id: str) -> Path | None:
    return next((p for p in _transcript_candidates(event, agent_id) if p.is_file()), None)


def _scan_transcript(path: Path, usage: dict) -> None:
    """Incremental read from usage['offset']: counts distinct model calls and per-call context; flags 429."""
    with path.open("rb") as fh:
        fh.seek(int(usage.get("offset", 0)))
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return
    usage["offset"] = int(usage.get("offset", 0)) + end + 1
    seen = usage.setdefault("model_ids", [])
    for raw in data[:end].split(b"\n"):
        if QUOTA_MARKER.search(raw):
            usage["quota_429"] = True
            usage["quota_line_sha256"] = hashlib.sha256(raw).hexdigest()
        if b'"assistant"' not in raw:
            continue
        try:
            entry = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(msg, dict) or entry.get("type") != "assistant" or msg.get("model") == "<synthetic>":
            continue
        mid = str(msg.get("id") or "")
        if not mid or mid in seen:
            continue
        seen.append(mid)
        u = msg.get("usage") or {}
        ctx = sum(int(_num(u.get(k), 0) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if ctx > 0:
            usage["ctx_first"] = usage.get("ctx_first") or ctx
            usage["ctx_last"] = ctx
            usage["ctx_peak"] = max(int(usage.get("ctx_peak") or 0), ctx)
    usage["model_calls"] = len(seen)


def _meta_tool_use_id(transcript: Path | None) -> str:
    if transcript is None:
        return ""
    meta = _read_json(transcript.with_name(transcript.name[:-len(".jsonl")] + ".meta.json"), {})
    return str(meta.get("toolUseId") or "") if isinstance(meta, dict) else ""


def _usage_path(state_dir: Path, agent_id: str) -> Path:
    return state_dir / AGENT_USAGE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", agent_id)[:80] + ".json")


def _rank(state: str) -> int:
    return STATE_ORDER.index(state)


def evaluate(usage: dict, wd: dict, derived: dict, mission_cap: float, now: float) -> tuple[str, list[str], str]:
    """Agent resource state, reasons, and the TURN_LIMIT label (ENFORCED or PROXY)."""
    cfg, wp_cfg = wd["agent"], wd["work_package"]
    reasons, state = [], "GREEN"

    def bump(level: str, reason: str):
        nonlocal state
        reasons.append(f"{level}: {reason}")
        if _rank(level) > _rank(state):
            state = level

    max_turns = int(usage.get("max_turns") or cfg["max_turns_hard"])
    calls = usage.get("model_calls")
    label = "ENFORCED" if usage.get("transcript") else "PROXY"
    if label == "ENFORCED" and calls is not None:
        ratio = calls / max_turns
        for level in ("RED", "ORANGE", "YELLOW"):
            if ratio >= float(cfg["turn_state_ratios"][level]):
                bump(level, f"model turns {calls}/{max_turns}")
                break
    else:
        tools = int(usage.get("tool_calls", 0))
        proxy = int(cfg["tool_calls_proxy_red"])
        if tools >= proxy:
            bump("RED", f"tool-call proxy {tools}/{proxy} (turn telemetry UNAVAILABLE)")
        elif tools >= 0.84 * proxy:
            bump("ORANGE", f"tool-call proxy {tools}/{proxy} (turn telemetry UNAVAILABLE)")
    peak, first, last = int(usage.get("ctx_peak") or 0), int(usage.get("ctx_first") or 0), int(usage.get("ctx_last") or 0)
    if peak >= int(cfg["context_peak_red_tokens"]):
        bump("RED", f"context peak {peak} >= {cfg['context_peak_red_tokens']}")
    if first and last:
        growth = last / first
        if growth >= float(cfg["context_growth_red_ratio"]):
            bump("RED", f"context grew x{growth:.1f} ({first} -> {last})")
        elif growth >= float(cfg["context_growth_orange_ratio"]):
            bump("ORANGE", f"context grew x{growth:.1f} ({first} -> {last})")
    elapsed = now - float(usage.get("first_seen") or now)
    if elapsed >= float(cfg["elapsed_red_seconds"]):
        bump("RED", f"elapsed {int(elapsed)}s")
    elif elapsed >= float(cfg["elapsed_orange_seconds"]):
        bump("ORANGE", f"elapsed {int(elapsed)}s")
    own = float(calls or 0)
    mission = str(usage.get("mission") or "unknown")
    live = derived.get("live", {"mission": {}, "wp": {}})
    if usage.get("wp"):
        wp_key = f"{mission}/{usage['wp']}"
        wp_total = float(derived["wp_calls"].get(wp_key, 0.0)) + float(live["wp"].get(wp_key, 0.0)) + own
        if wp_total >= float(wp_cfg["max_model_calls"]):
            bump("RED", f"work package {usage['wp']} model calls {int(wp_total)}/{wp_cfg['max_model_calls']} (across agents)")
    mission_total = float(derived["mission_calls"].get(mission, 0.0)) + float(live["mission"].get(mission, 0.0)) + own
    if mission_cap and mission_total >= mission_cap:
        bump("RED", f"mission {mission} subagent model calls {int(mission_total)}/{int(mission_cap)}")
    if usage.get("quota_429"):
        bump("RED", "provider HTTP 429 in the agent transcript (INTERRUPTED_BY_QUOTA)")
    return state, reasons, label


def live_usage(state_dir: Path, derived: dict, exclude: str = "") -> dict:
    """Model calls of agents not yet in the ledger (running siblings, or crashed agents that never stopped)."""
    out = {"mission": {}, "wp": {}}
    folder = state_dir / AGENT_USAGE_DIR
    if not folder.is_dir():
        return out
    for path in folder.glob("*.json"):
        usage = _read_json(path, None)
        if not isinstance(usage, dict) or not usage.get("agent_id"):
            continue
        agent = str(usage["agent_id"])
        if agent == exclude or agent in derived["usage_agents"]:
            continue
        calls = float(_ledger_number(usage.get("model_calls")) or 0.0)
        mission = str(usage.get("mission") or "unknown")
        out["mission"][mission] = out["mission"].get(mission, 0.0) + calls
        if usage.get("wp"):
            key = f"{mission}/{usage['wp']}"
            out["wp"][key] = out["wp"].get(key, 0.0) + calls
    return out


def _write_allowed(root: Path, value: str, patterns: list[str]) -> bool:
    target = os.path.normcase(os.path.abspath(os.path.join(str(root), str(value))))
    for pattern in patterns:
        full = os.path.normcase(os.path.abspath(os.path.join(str(root), pattern)))
        if fnmatch.fnmatch(target, full) or _inside(target, full):
            return True
    return False


def mission_call_cap(wd: dict, derived: dict, key: str) -> float:
    complexity = (derived.get("mission") or {}).get("complexity") or "normal"
    base = float(wd["mission"]["max_subagent_model_calls"].get(complexity, 250))
    return max(base, float(derived["model_calls"].get(key, 0.0)))


def watchdog(event: dict, policy: dict, now: float | None = None) -> tuple[int, str]:
    """Runtime watchdog for one subagent tool call. Returns (exit_code, message)."""
    now = time.time() if now is None else now
    wd = policy.get("runtime_watchdog")
    if not wd:
        return 0, ""
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    root = project_root(event)
    state_dir = root / STATE_DIR
    agent_id = str(event.get("agent_id") or "")
    if tool in SHELL_TOOLS and tool_input.get("run_in_background") is True and wd["agent"].get("background_shell") == "deny":
        _ledger(state_dir, {"event": "WATCHDOG_DENY", "agent_id": agent_id or None, "reason": "background_shell"})
        return 2, ("Dream Team watchdog: background shells are denied inside subagents (they outlive the agent). "
                   "Run the command in the foreground with a timeout.")
    session = str(event.get("session_id") or "unknown")
    synthetic = False
    if not agent_id:
        # agent_type without agent_id: meter under a synthetic identity instead of letting it run unmetered.
        agent_id, synthetic = f"type-{event.get('agent_type')}-{session}", True
    with _state_lock(state_dir):
        derived = _derive(state_dir)
        path = _usage_path(state_dir, agent_id)
        usage = _read_json(path, None) if path.exists() else {}
        if not isinstance(usage, dict):
            raise ValueError(f"agent usage state is corrupt: {path.name}")
        transcript = None if synthetic else _find_transcript(event, agent_id)
        if not usage:
            tool_use_id = _meta_tool_use_id(transcript)
            active = _read_active(state_dir)
            slot = next((s for s in active if tool_use_id and s.get("id") == tool_use_id), None)
            if slot is None:
                unattached = [s for s in active if not s.get("agent_id") and s.get("session") == session]
                slot = unattached[0] if len(unattached) == 1 else None
            mission = slot.get("mission") if slot else _usage_key(derived["mission"], session)
            usage = {"agent_id": agent_id, "first_seen": now, "tool_calls": 0, "offset": 0, "state": "GREEN",
                     "tool_use_id": tool_use_id or (slot or {}).get("id"), "mission": mission, "synthetic_id": synthetic,
                     "agent_type": str(event.get("agent_type") or (slot or {}).get("agent_type") or ""),
                     "wp": (slot or {}).get("wp"), "access": (slot or {}).get("access"), "files": (slot or {}).get("files"),
                     "wp_signal": "ENFORCED" if slot else "UNAVAILABLE",
                     "max_turns": (slot or {}).get("max_turns") or int(wd["agent"]["max_turns_hard"])}
            if agent_id in derived["usage_agents"]:
                usage["finished"] = True  # already ledgered as finished: never a fresh GREEN budget
        usage["tool_calls"] = int(usage.get("tool_calls", 0)) + 1
        usage["transcript"] = bool(transcript)
        if transcript:
            _scan_transcript(transcript, usage)
        access_denial = ""
        if tool in WRITE_FILE_TOOLS:
            values = [str(tool_input.get(k) or "") for k in ("file_path", "notebook_path", "path") if tool_input.get(k)]
            if usage.get("access") == "read":
                access_denial = f"{tool} denied: this agent was admitted read-only (contract access=read)"
            elif usage.get("files") and not all(_write_allowed(root, v, usage["files"]) for v in values):
                access_denial = f"{tool} denied: target is outside the contract files allowlist {usage['files']}"
        derived["live"] = live_usage(state_dir, derived, exclude=agent_id)
        cap = mission_call_cap(wd, derived, str(usage.get("mission") or ""))
        state, reasons, label = evaluate(usage, wd, derived, cap, now)
        if usage.get("finished"):
            state = "RED"
            reasons.append("RED: agent already finished (usage recorded); budget is not reset")
        previous = usage.get("state", "GREEN")
        usage["state"], usage["turn_limit"] = state, label
        handback_denial = ""
        if state == "RED" and tool == "SubagentHandback":
            cap = int(wd.get("final_handback_max_chars") or 2000)
            size = len(str(tool_input.get("message") if "message" in tool_input else json.dumps(tool_input, ensure_ascii=False)))
            if usage.get("final_handback") == "used":
                handback_denial = "the single final handback was already used"
            else:
                usage["final_handback"] = "used"
                over_cap = size > cap
                event_rec = {"event": "WATCHDOG_HANDBACK", "agent_id": agent_id, "message_chars": size,
                             "mission": usage.get("mission"), "wp": usage.get("wp")}
                if over_cap:
                    event_rec["over_cap"] = True
                    handback_denial = (f"handback is {size} chars, over the {cap}-char cap; the single final handback is now spent "
                                       "(no retry)")
                _ledger(state_dir, event_rec)
        _write_json(path, usage)
        if usage.get("quota_429") and usage.get("quota_line_sha256") not in derived["quota_seen"]:
            _ledger(state_dir, {"event": "QUOTA_EVENT", "source": "agent_transcript", "agent_id": agent_id,
                                "mission": usage.get("mission"), "wp": usage.get("wp"),
                                "line_sha256": usage.get("quota_line_sha256")})
        if _rank(state) > _rank(previous):
            _ledger(state_dir, {"event": "WATCHDOG_STATE", "agent_id": agent_id, "state": state, "previous": previous,
                                "reasons": reasons, "turn_limit": label, "model_calls": usage.get("model_calls"),
                                "tool_calls": usage["tool_calls"], "ctx_peak": usage.get("ctx_peak"),
                                "mission": usage.get("mission"), "wp": usage.get("wp"), "wp_signal": usage.get("wp_signal")})
        if access_denial:
            _ledger(state_dir, {"event": "WATCHDOG_DENY", "agent_id": agent_id, "reason": "access", "tool_name": tool,
                                "detail": access_denial, "mission": usage.get("mission"), "wp": usage.get("wp")})
    if access_denial and state != "RED":
        return 2, f"Dream Team watchdog: {access_denial}. Stay inside your contract or hand back to Ori."
    if state == "RED":
        if tool == "SubagentHandback" and not handback_denial:
            return 0, ""
        if handback_denial:
            return 2, f"Dream Team watchdog RED: SubagentHandback denied: {handback_denial}. Stop; no further tool calls are allowed."
        return 2, ("Dream Team watchdog RED: " + "; ".join(reasons) + ". STOP now: the ONLY permitted call is a single "
                   "SubagentHandback with a compact checkpoint (done / changed files / tests run / remaining work); every other "
                   "tool is denied and the budget is not reset.")
    if state in ("ORANGE", "YELLOW"):
        advice = ("finish the current safe atomic change, then hand back a checkpoint; do not start new work"
                  if state == "ORANGE" else "narrow your reads (grep / line ranges), avoid re-reading large files")
        return 0, f"Dream Team watchdog {state}: " + "; ".join(reasons) + f". {advice}."
    return 0, ""


def _reap_api_error_agents(event: dict, state_dir: Path, session: str, now: float) -> None:
    """An agent killed by a provider API error fires neither SubagentStop nor PostToolUseFailure. Before each spawn,
    scan the tails of this session's subagent transcripts: a 429 sets the quota hold; any agent whose transcript
    ends in an API error gets its usage ledgered (AGENT_USAGE) and its slot released, once."""
    folder = Path(str(event["transcript_path"])).parent / session / "subagents"
    if not folder.is_dir():
        return
    for path in folder.glob("agent-*.jsonl"):
        try:
            if now - path.stat().st_mtime > STALE_SECONDS * 4:
                continue
            with path.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 16384))
                lines = [l for l in fh.read().split(b"\n") if l.strip()]
        except OSError:
            continue
        if not lines or b'"isApiErrorMessage":true' not in lines[-1].replace(b" ", b""):
            continue
        agent_id = path.name[len("agent-"):-len(".jsonl")]
        derived = _derive(state_dir)
        if QUOTA_MARKER.search(lines[-1]):
            sha = hashlib.sha256(lines[-1]).hexdigest()
            if sha not in derived["quota_seen"]:
                _ledger(state_dir, {"event": "QUOTA_EVENT", "source": "subagent_transcript_tail", "agent_id": agent_id,
                                    "session": session, "line_sha256": sha})
        if agent_id in derived["usage_agents"]:
            continue
        tool_use_id = _meta_tool_use_id(path)
        active = _read_active(state_dir)
        slot = next((s for s in active if tool_use_id and s.get("id") == tool_use_id), None)
        _record_agent_usage({"session_id": session, "agent_id": agent_id, "agent_transcript_path": str(path)},
                            state_dir, agent_id, slot)
        if slot is not None:
            _write_json(state_dir / ACTIVE_FILE, [s for s in active if s is not slot])
            _ledger(state_dir, {"event": "SLOT_RELEASED_API_ERROR", "tool_use_id": tool_use_id, "agent_id": agent_id})


def _scan_quota_tail(path: Path) -> tuple[str, str] | None:
    """Last 429 line in the tail of a transcript: (line_sha256, timestamp) or None."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - QUOTA_SCAN_BYTES))
            data = fh.read()
    except OSError:
        return None
    found = None
    for raw in data.split(b"\n"):
        if QUOTA_MARKER.search(raw):
            ts = ""
            try:
                ts = str(json.loads(raw.decode("utf-8")).get("timestamp") or "")
            except ValueError:
                pass
            found = (hashlib.sha256(raw).hexdigest(), ts)
    return found


def decide(event: dict, policy: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    root = project_root(event)
    state_dir = root / STATE_DIR
    tool_input = event.get("tool_input") or {}
    agent_type = str(tool_input.get("subagent_type") or "general-purpose").lower()
    session = str(event.get("session_id") or "unknown")
    conc = policy["concurrency"]
    usage = policy["usage_governor"]
    active = _active(state_dir, now)

    derived = _derive(state_dir)
    _ledger_malformed(state_dir, derived)
    mission = derived["mission"]
    key = _usage_key(mission, session)
    used = float(derived["units"].get(key, 0.0))

    budget_cfg, budget_sha = _read_json_sha(state_dir / BUDGET_FILE)
    if not isinstance(budget_cfg, dict):
        budget_cfg = {}
    complexity = (mission or {}).get("complexity") or "normal"
    default_units = usage["default_mission_work_units"]
    base = float(default_units.get(complexity, 40))
    cap = max(base, float(derived["budget"].get(key, 0)))
    raised = {}
    file_complexity = str(budget_cfg.get("complexity") or "").lower()
    if file_complexity in COMPLEXITIES:
        file_base = float(default_units.get(file_complexity, 40))
        if file_base > base:
            raised["complexity"] = file_complexity
        else:
            cap = min(cap, file_base)
    requested = _num(budget_cfg.get("work_units"))
    budget = cap
    if requested is not None and requested > 0:
        budget = min(requested, cap)
        if requested > cap:
            raised["work_units"] = requested
    if raised:
        _self_auth_attempt(state_dir, derived, "budget", budget_sha, requested=raised.get("work_units", raised.get("complexity")),
                           raised=raised, granted=budget, mission=key)
    state = budget_state(policy, used, budget)
    state_limit = int(usage["states"][state]["max_concurrency"])

    limit = int(conc["normal_max"])
    justification, just_sha = _read_json_sha(state_dir / JUSTIFICATION_FILE)
    if isinstance(justification, dict):
        requested_parallel = int(_num(justification.get("max_parallel"), limit) or limit)
        if requested_parallel > limit:
            missing = [c for c in conc["above_normal_requires"] if not justification.get(c)]
            authorized_parallel = int(derived["parallel"].get(key, 0))
            if not missing and authorized_parallel >= requested_parallel:
                limit = min(requested_parallel, authorized_parallel, int(conc["hard_max"]))
            else:
                _self_auth_attempt(state_dir, derived, "parallel", just_sha, requested=requested_parallel,
                                   granted=limit, mission=key)
    limit = min(limit, state_limit) if state != "GREEN" else limit

    claude_cfg = (policy.get("provider_enforcement", {}) or {}).get("claude", {}) or {}
    model = str(tool_input.get("model") or "").lower()
    effective_model = (model or _agent_default_model(root, agent_type)
                       or str((claude_cfg.get("agent_default_models") or {}).get(agent_type) or "").lower())
    model_class = model_class_of(effective_model)
    units = _work_units(policy, model_class, "medium")
    prompt = tool_input.get("prompt")
    why = MODEL_WHY_RE.search(prompt) if isinstance(prompt, str) else None
    base_result = {"session": session, "agent_type": agent_type, "mission": key,
                   "model": model or f"agent-default:{effective_model or 'unknown'}",
                   "model_class": model_class,
                   "active_before": len(active), "limit": limit, "budget_state": state, "work_units_used": used,
                   "work_unit_budget": budget, "telemetry": {"platform": "UNAVAILABLE", "proxy": "work units"}}
    if why:
        base_result["model_why"] = why.group(1).strip()[:200]

    def done(decision: str, reason: str, **extra) -> dict:
        return {**base_result, "decision": decision, "reason": reason, **extra}

    if agent_type in COORDINATOR_TYPES:
        return done("deny", f"'{agent_type}' is a main-thread logical stage (Yuli/Ori). Run it in the main thread; do not spawn it as a subagent.")
    explicit = set(claude_cfg.get("explicit_model_required_for") or [])
    if agent_type in explicit and not model:
        return done("deny", (f"'{agent_type}' defaults to the parent session model. Pass model explicitly: haiku for FAST, "
                             "sonnet for STANDARD, opus only for HIGH with a recorded WHY."))
    if not effective_model:
        return done("deny", f"'{agent_type}' has no known default model; pass model explicitly (haiku FAST, sonnet STANDARD, opus HIGH with MODEL_WHY)")
    wd = policy.get("runtime_watchdog")
    if wd:
        if derived["quota_hold"]:
            return done("deny", ("provider quota hold (HTTP 429 recorded): no new agents until the main thread checks the durable state "
                                 "and runs `agent_governor.py quota-clear --reason ...` after the reset (INTERRUPTED_BY_QUOTA)."))
        adm = admit(root, agent_type, tool_input, wd, mission, effective_model, derived["wps"])
        live = live_usage(state_dir, derived)
        if not adm["ok"]:
            return done("deny", adm["reason"])
        base_result.update({"admission": adm["kind"], "wp": adm["wp"], "access": adm["access"], "max_turns": adm["max_turns"],
                            "role": adm["role"], "files": adm.get("files")})
        if isinstance(prompt, str):
            base_result["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if adm["wp"]:
            wp_key, wp_cfg = f"{key}/{adm['wp']}", wd["work_package"]
            wp_calls = float(derived["wp_calls"].get(wp_key, 0.0)) + float(live["wp"].get(wp_key, 0.0))
            if wp_calls >= float(wp_cfg["max_model_calls"]):
                return done("deny", f"work package {adm['wp']} already used {int(wp_calls)}/{wp_cfg['max_model_calls']} model calls across agents: split or re-plan")
            attempt = int(derived["wp_attempts"].get(wp_key, 0)) + 1
            base_result["wp_attempt"] = attempt
            if attempt > int(wp_cfg["max_agents"]):
                return done("deny", (f"work package {adm['wp']}: attempt {attempt} exceeds {wp_cfg['max_agents']} agents. STOP: Andy "
                                     "checkpoint, then Yuli/Ori re-plan (new scope = new WP with a recorded reason)."))
            if attempt >= int(wp_cfg["replan_marker_from_attempt"]):
                if wp_cfg["replan_marker"] not in str(prompt or ""):
                    return done("deny", f"work package {adm['wp']} attempt {attempt} is a REPLAN: add a '{wp_cfg['replan_marker']} <what changed>' line")
                if base_result.get("prompt_sha256") in derived["wp_prompts"].get(wp_key, set()):
                    return done("deny", f"work package {adm['wp']}: identical prompt re-dispatched; a re-plan must change scope, context, agent or model")
        cap = mission_call_cap(wd, derived, key)
        mission_calls = float(derived["mission_calls"].get(key, 0.0)) + float(live["mission"].get(key, 0.0))
        base_result["mission_model_calls"] = {"used": mission_calls, "cap": cap}
        if mission_calls >= cap:
            return done("deny", f"mission {key} used {int(mission_calls)}/{int(cap)} subagent model calls: RED. Checkpoint; raise only via `authorize model_calls`.")
    if state == "RED":
        return done("deny", f"usage governor RED ({used:.1f}/{budget:.0f} work units): stop spawning, write the Andy checkpoint and return a resumable state.")
    if state == "ORANGE" and model_class in {"HIGH", "ESCALATED"}:
        return done("deny", "usage governor ORANGE: no model escalation. Use the agent's default (cheaper) model or finish the bounded phase.")
    if model_class in set(claude_cfg.get("model_why_required_for") or ("HIGH", "ESCALATED")) and not why:
        return done("deny", "HIGH/ESCALATED model requires 'MODEL_WHY: <reason>' in the prompt")
    if len(active) >= limit:
        return done("deny", (f"concurrency limit {limit} reached ({len(active)} active, state {state}). Wait for a running agent to finish, "
                             "or continue in the current thread. More than 2 needs .ai/dream-team/parallel-justification.json with every "
                             "resource_governance.concurrency.above_normal_requires key plus an `authorize parallel` record."))
    if wd and wd.get("single_writer") and base_result.get("access") == "write" and any(s.get("access") == "write" for s in active):
        return done("deny", "single-writer rule: another writing agent is active. Wait for it, or dispatch this one read-only.")
    return done("allow", "admitted", work_units=units)


def _payload_keys(event: dict) -> list[str]:
    return sorted(str(k) for k in event)


def _policy_fields() -> dict:
    return {"policy_sha256": POLICY_META["sha256"], "policy_path": POLICY_META["path"]}


def handle_pre(event: dict, policy: dict) -> int:
    state_dir = project_root(event) / STATE_DIR
    tool_use_id = str(event.get("tool_use_id") or "")
    with _state_lock(state_dir):
        now = time.time()
        session = str(event.get("session_id") or "unknown")
        if not tool_use_id:
            result = {"decision": "deny", "reason": "missing tool_use_id", "session": session,
                      "mission": _usage_key(_derive(state_dir)["mission"], session)}
            _ledger(state_dir, {"event": "PreToolUse", **result, **_policy_fields(), "tool_use_id": None,
                                "payload_keys": _payload_keys(event)})
            print(f"Dream Team governor: {result['reason']}", file=sys.stderr)
            return 2
        if event.get("agent_id"):
            result = {"decision": "deny", "session": session, "mission": _usage_key(_derive(state_dir)["mission"], session),
                      "reason": "nested subagent spawn denied (resource_governance.concurrency.max_spawn_depth=1)",
                      "agent_id": str(event["agent_id"])}
            _ledger(state_dir, {"event": "PreToolUse", **result, **_policy_fields(), "tool_use_id": tool_use_id,
                                "payload_keys": _payload_keys(event)})
            print(f"Dream Team governor: {result['reason']}", file=sys.stderr)
            return 2
        active = _active(state_dir, now)
        if any(s.get("id") == tool_use_id for s in active):
            _ledger(state_dir, {"event": "DUPLICATE_INVOCATION", "tool_use_id": tool_use_id, "session": session,
                                "decision_replayed": "allow", "payload_keys": _payload_keys(event)})
            return 0
        if policy.get("runtime_watchdog") and event.get("transcript_path"):
            hit = _scan_quota_tail(Path(str(event["transcript_path"])))
            if hit and hit[0] not in _derive(state_dir)["quota_seen"]:
                _ledger(state_dir, {"event": "QUOTA_EVENT", "source": "session_transcript", "session": session,
                                    "line_sha256": hit[0], "observed_ts": hit[1]})
            _reap_api_error_agents(event, state_dir, session, now)
            active = _active(state_dir, now)
        result = decide(event, policy, now)
        _ledger(state_dir, {"event": "PreToolUse", **result, **_policy_fields(), "tool_use_id": tool_use_id,
                            "payload_keys": _payload_keys(event)})
        if result["decision"] == "allow":
            active.append({"id": tool_use_id, "agent_type": result["agent_type"],
                           "session": result["session"], "mission": result["mission"], "started": now, "agent_id": None,
                           "wp": result.get("wp"), "access": result.get("access"), "max_turns": result.get("max_turns"),
                           "files": result.get("files")})
            _write_json(state_dir / ACTIVE_FILE, active)
    if result["decision"] != "allow":
        print(f"Dream Team governor: {result['reason']}", file=sys.stderr)
        return 2
    return 0


def _find_agent_id(response) -> str:
    def walk(node, depth=0):
        if depth > 4:
            return ""
        if isinstance(node, dict):
            for name in ("agentId", "agent_id"):
                if isinstance(node.get(name), str) and node[name]:
                    return node[name]
            for value in node.values():
                found = walk(value, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value, depth + 1)
                if found:
                    return found
        return ""

    found = walk(response)
    if found:
        return found
    match = AGENT_ID_RE.search(str(response))
    return match.group(1) if match else ""


def _release(active: list[dict], predicate):
    for i, slot in enumerate(active):
        if predicate(slot):
            return active.pop(i)
    return None


def handle_post(event: dict, policy: dict | None = None) -> int:
    state_dir = project_root(event) / STATE_DIR
    tool_use_id = str(event.get("tool_use_id") or "")
    response = event.get("tool_response")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    with _state_lock(state_dir):
        active = _active(state_dir, time.time())
        if event.get("hook_event_name") == "PostToolUseFailure":
            released = _release(active, lambda s: bool(tool_use_id) and s.get("id") == tool_use_id)
            _write_json(state_dir / ACTIVE_FILE, active)
            _ledger(state_dir, {"event": "SLOT_RELEASED_FAILURE", "tool_use_id": tool_use_id or None,
                                "released": bool(released), "active_after": len(active), "payload_keys": _payload_keys(event)})
            return 0
        agent_id = _find_agent_id(response)
        events = _read_json(state_dir / SLOT_EVENTS_FILE, {})
        stopped = events.get("stopped", []) if isinstance(events, dict) else []
        action, released = "none", None
        if agent_id and agent_id not in stopped:
            slot = next((s for s in active if tool_use_id and s.get("id") == tool_use_id), None)
            if slot is not None:
                slot["agent_id"] = agent_id
                action = "attached"
        elif agent_id or tool_input.get("run_in_background") is not True:
            released = _release(active, lambda s: bool(tool_use_id) and s.get("id") == tool_use_id)
            action = "released" if released else "none"
        else:
            action = "kept_ambiguous"
            _ledger(state_dir, {"event": "SLOT_AMBIGUOUS", "tool_use_id": tool_use_id or None})
        _write_json(state_dir / ACTIVE_FILE, active)
        entry = {"event": "PostToolUse", "tool_use_id": tool_use_id or None, "agent_id": agent_id or None,
                 "action": action, "active_after": len(active), "payload_keys": _payload_keys(event),
                 "response_type": type(response).__name__}
        if isinstance(response, dict):
            entry["response_keys"] = sorted(str(k) for k in response)
        _ledger(state_dir, entry)
    return 0


def handle_stop(event: dict, policy: dict | None = None) -> int:
    state_dir = project_root(event) / STATE_DIR
    session = str(event.get("session_id") or "unknown")
    agent_id = str(event.get("agent_id") or "")
    with _state_lock(state_dir):
        active = _active(state_dir, time.time())
        released = None
        if agent_id:
            released = _release(active, lambda s: s.get("agent_id") == agent_id)
            if released is None:
                events = _read_json(state_dir / SLOT_EVENTS_FILE, {})
                stopped = events.get("stopped", []) if isinstance(events, dict) else []
                stopped.append(agent_id)
                _write_json(state_dir / SLOT_EVENTS_FILE, {"stopped": stopped[-STOPPED_KEEP:]})
            else:
                _write_json(state_dir / ACTIVE_FILE, active)
        _ledger(state_dir, {"event": "SubagentStop", "session": session, "agent_id": agent_id or None,
                            "released": released, "active_after": len(active), "payload_keys": _payload_keys(event)})
        if agent_id:
            _record_agent_usage(event, state_dir, agent_id, released)
    return 0


def _record_agent_usage(event: dict, state_dir: Path, agent_id: str, released) -> None:
    """Persist the agent's final usage in the ledger (WP / mission totals survive respawns), then drop its usage file."""
    derived = _derive(state_dir)
    if agent_id in derived["usage_agents"]:
        return
    path = _usage_path(state_dir, agent_id)
    usage = _read_json(path, {}) if path.exists() else {}
    usage = usage if isinstance(usage, dict) else {}
    transcript = _find_transcript(event, agent_id)
    if transcript:
        _scan_transcript(transcript, usage)
    slot = released if isinstance(released, dict) else {}
    if not usage.get("tool_use_id") and transcript:
        usage["tool_use_id"] = _meta_tool_use_id(transcript) or None
    if not slot and usage.get("tool_use_id"):
        slot = next((s for s in _read_active(state_dir) if s.get("id") == usage["tool_use_id"]), {})
    entry ={"event": "AGENT_USAGE", "agent_id": agent_id, "mission": usage.get("mission") or slot.get("mission"),
             "wp": usage.get("wp") or slot.get("wp"), "agent_type": usage.get("agent_type") or slot.get("agent_type") or event.get("agent_type"),
             "model_calls": usage.get("model_calls") if transcript or "model_calls" in usage else None,
             "tool_calls": usage.get("tool_calls"), "ctx_first": usage.get("ctx_first"), "ctx_peak": usage.get("ctx_peak"),
             "final_state": usage.get("state", "GREEN"), "turn_limit": "ENFORCED" if transcript else "PROXY",
             "telemetry": "transcript" if transcript else "UNAVAILABLE", "quota_429": bool(usage.get("quota_429")),
             "elapsed_seconds": int(time.time() - float(usage["first_seen"])) if usage.get("first_seen") else None}
    if entry["mission"] is None:
        entry["mission"] = _usage_key(derived["mission"], str(event.get("session_id") or "unknown"))
    _ledger(state_dir, entry)
    if usage.get("quota_429") and usage.get("quota_line_sha256") not in derived["quota_seen"]:
        _ledger(state_dir, {"event": "QUOTA_EVENT", "source": "agent_stop", "agent_id": agent_id, "mission": entry["mission"],
                            "wp": entry["wp"], "line_sha256": usage.get("quota_line_sha256")})
    try:
        path.unlink()
    except OSError:
        pass


def _squash(text: str) -> str:
    """Lowercase, unify separators, drop quotes/backticks, collapse // /./ and x/../ so path tricks cannot hide a match."""
    text = re.sub(r"\\+", "/", str(text).lower())
    text = re.sub(r"[\"'`]", "", text)
    while True:
        new = re.sub(r"/+", "/", text)
        new = new.replace("/./", "/")
        new = re.sub(r"[^/\s]+/\.\./", "", new)
        if new == text:
            return text
        text = new


def _is_exempt_cli(command: str) -> bool:
    """Strict structure: `<python> <path>/agent_governor.py <mission|authorize|report|release> <plain args>`, no shell metacharacters."""
    if not command or SHELL_META_RE.search(command):
        return False
    try:
        tokens = shlex.split(command.replace("\\", "/"), posix=True)
    except ValueError:
        return False
    if len(tokens) < 3:
        return False
    base = lambda value: os.path.basename(value.replace("\\", "/")).lower()
    if base(tokens[0]) not in CLI_INTERPRETERS or base(tokens[1]) not in CLI_SCRIPTS:
        return False
    if tokens[2] not in CLI_MODES:
        return False
    return all(CLI_ARG_RE.match(tok) for tok in tokens[3:])


def _squash_deleting_backslashes(text: str) -> str:
    return _squash(str(text).replace("\\", ""))


def _is_report_cli(command: str) -> bool:
    return _is_exempt_cli(command) and shlex.split(command.replace("\\", "/"), posix=True)[2] == "report"


def _subagent_forbidden_process(tool: str, command: str) -> str:
    """Reason when a subagent shell command would start a nested model call or a detached process."""
    if NESTED_LLM_RE.search(command):
        return "nested model call (LLM CLI / SDK / API) from a subagent is not metered by the governor"
    stripped = re.sub(r"\d*>&\d*|&&|&>|>&", " ", command)
    if DETACH_RE.search(command) or (tool == "Bash" and BASH_BACKGROUND_RE.search(stripped)):
        return "detached/background process from a subagent would outlive the agent and its watchdog"
    return ""


def _subagent_shell_evasion(command: str, text: str) -> bool:
    """Extra subagent-only shell heuristics: escaped separators, split paths, globs, 8.3 names, governor lookalikes."""
    if ".ai/dream-team" in _squash_deleting_backslashes(command):
        return True
    tokens = text.split()
    if "dream" in text and any(".ai" in tok for tok in tokens):
        return True
    if re.search(r"\.ai/\S*([*?\[]|~\d)", text):
        return True
    if any(GOVERNOR_TOKEN_RE.search(os.path.basename(tok)) or ("gov" in tok and re.search(r"[*?\[]", tok))
           for tok in tokens) and not _is_report_cli(command):
        return True
    return False


def _governor_subcommands(text: str) -> list[str]:
    return [m.group(1) or "" for m in GOVERNOR_CALL_RE.finditer(text)]


def _clean_path(root: Path, value: str) -> str:
    drive, rest = os.path.splitdrive(str(value))
    parts = []
    for comp in re.split(r"[\\/]+", rest):
        if comp not in ("", ".", ".."):
            comp = comp.rstrip(". ")
        if comp:
            parts.append(comp)
    joined = drive + (os.sep if rest[:1] in ("/", "\\") else "") + os.sep.join(parts)
    return os.path.abspath(os.path.join(str(root), joined))


def _inside(path: str, base: str) -> bool:
    p, b = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(base))
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def _file_targets(root: Path, values: list[str], subagent: bool) -> tuple[bool, bool]:
    root_abs = os.path.abspath(str(root))
    state_dir = os.path.join(root_abs, *STATE_DIR.parts)
    claude = os.path.join(root_abs, ".claude")
    b_files = [os.path.join(claude, name) for name in PROTECTED_B_FILES]
    b_dirs = [os.path.join(claude, name) for name in PROTECTED_B_DIRS]
    protected_a = protected_b = False
    for value in values:
        if not value:
            continue
        squashed = _squash(value)
        forms = {_clean_path(root, value), os.path.realpath(_clean_path(root, value))}
        if re.search(r"\.ai/dream-team(/|$)", squashed) or any(_inside(f, state_dir) or _inside(f, os.path.realpath(state_dir)) for f in forms):
            protected_a = True
        if subagent and (any(p in squashed for p in PROTECTED_B)
                         or any(_inside(f, d) for f in forms for d in b_dirs)
                         or any(os.path.normcase(f) == os.path.normcase(b) for f in forms for b in b_files)):
            protected_b = True
    return protected_a, protected_b


def _is_implementation_path(root: Path, value: str, globs: list[str]) -> bool:
    """True when `value` is a repo path inside the project root that is not Main plumbing (state, evidence, plan, hashes)."""
    if not value:
        return False
    base = os.path.abspath(str(root))
    full = _clean_path(root, value)
    if not _inside(full, base):
        return False
    rel = os.path.relpath(full, base).replace(os.sep, "/").lower()
    if rel == ".":
        return False
    return not any(fnmatch.fnmatch(rel, g.lower()) or (g.startswith("**/") and fnmatch.fnmatch(rel, g[3:].lower())) for g in globs)


INLINE_UNRESOLVED = "<inline-interpreter-script>"
SHELL_REDIRECT_RE = re.compile(r"(?<![&>])\d?>{1,2}\s*(?!/dev/null|&|nul\b)(['\"]?[^\s'\";|&<>]+)", re.IGNORECASE)


def _inline_write_targets(command: str) -> list[str]:
    """Inline interpreter script (python - <<EOF, python -c, node -e, powershell here-string) with a write call: its path-like
    tokens, or [INLINE_UNRESOLVED] when no target can be resolved statically (conservative). PARTIAL heuristic."""
    if not (INLINE_INTERPRETER_RE.search(command) and INLINE_MARKER_RE.search(command) and INLINE_WRITE_CALL_RE.search(command)):
        return []
    text = command.replace("\\", "/")
    tokens = [t for t in INLINE_PATH_TOKEN_RE.findall(text) if not t.lower().startswith(("http", "/dev/")) and "//" not in t]
    return tokens or [INLINE_UNRESOLVED]


def _main_shell_targets(command: str) -> list[str]:
    """Path-like tokens of a Main shell command that has a write verb (text heuristic, PARTIAL like the rest of the guard)."""
    if _is_exempt_cli(command):
        return []
    inline = _inline_write_targets(command)
    if not MAIN_SHELL_WRITE_RE.search(command):
        return inline
    out = list(inline)
    for segment in re.split(r"\|\||&&|[;|\n]", command.replace("\\", "/")):
        out.extend(m.group(1).strip("'\"") for m in SHELL_REDIRECT_RE.finditer(segment))
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        out.extend(_segment_write_destinations(tokens))
    return out


def _git_repo_mutation(plain: list[str], args: list[str]) -> bool:
    """Repo-mutating git verbs that rewrite the working tree: reset --hard, clean (not dry-run), commit -a/--all, bare/push/save stash."""
    sub, rest = (plain[0] if plain else ""), plain[1:]
    flags = [a for a in args if a.startswith("-")]
    if sub == "reset":
        return "--hard" in flags
    if sub == "clean":
        return not any(f == "--dry-run" or re.fullmatch(r"-[a-z]*n[a-z]*", f) for f in flags)
    if sub == "commit":
        return "--all" in flags or any(re.fullmatch(r"-[a-z]*a[a-z]*", f) for f in flags)
    if sub == "stash":
        return not rest or rest[0] in ("push", "save")
    return False


def _segment_write_destinations(tokens: list[str]) -> list[str]:
    """Actual write destinations of one simple command (cd, git diff/status/log, sha256sum, cat, ls, pytest args are never targets)."""
    if not tokens:
        return []
    verb = os.path.basename(tokens[0]).lower()
    args = tokens[1:]
    plain = [a for a in args if not a.startswith("-") and not a.lower().startswith(("http:", "https:", "/dev/"))]
    if verb == "tee":
        return plain
    if verb in ("set-content", "add-content", "out-file", "new-item"):
        for i, a in enumerate(args[:-1]):
            if a.lower() in ("-path", "-filepath", "-literalpath"):
                return [args[i + 1]]
        return plain[:1]
    if verb == "sed" and any(re.fullmatch(r"-[a-z]*i\S*|--in-place\S*", a, re.IGNORECASE) for a in args):
        return plain[1:]
    if verb in ("cp", "copy", "copy-item"):
        return plain[-1:]
    if verb in ("mv", "move", "move-item", "rm", "del", "remove-item"):
        return plain
    if verb == "patch" or (verb == "git" and plain[:1] in (["apply"], ["am"]) or verb == "git" and plain[:2] == ["stash", "pop"]):
        return [INLINE_UNRESOLVED]
    if verb == "touch":
        return plain
    if verb == "git" and _git_repo_mutation(plain, args):
        return [INLINE_UNRESOLVED]
    if verb == "git" and plain[:1] in (["checkout"], ["restore"]) and (plain[0] == "restore" or "--" in args):
        return (args[args.index("--") + 1:] if "--" in args else plain[1:])
    return []


def _main_authority(event: dict, tool: str, tool_input: dict, root: Path) -> int:
    """WP-1: record (and, in a host-only mission, deny) Main-thread implementation writes. Workers are never touched here."""
    try:
        cfg = load_policy().get("main_authority") or {}
        if cfg.get("enabled") is False:
            return 0
        globs = [str(g) for g in cfg.get("plumbing_globs") or MAIN_PLUMBING_DEFAULT]
        if tool in WRITE_FILE_TOOLS:
            candidates = [str(tool_input.get(k) or "") for k in ("file_path", "notebook_path", "path")]
        else:
            candidates = _main_shell_targets(str(tool_input.get("command") or ""))
        hits = [c for c in candidates if c == INLINE_UNRESOLVED or _is_implementation_path(root, c, globs)]
        if not hits:
            return 0
        state_dir = root / STATE_DIR
        mission = _derive(state_dir)["mission"] or {}
        host_only = bool(mission.get("host_only"))
        _ledger(state_dir, {"event": "MAIN_IMPLEMENTATION_WRITE", "tool_name": tool, "paths": hits[:5],
                            "decision": "deny" if host_only else "record", "mission": mission.get("mission_id"),
                            "session": event.get("session_id")})
        if host_only:
            print(f"Dream Team authority lock: Main is Host only. {tool} to implementation path {hits[0]!r} is denied; "
                  "Ori must dispatch a scoped dt-* Worker for this change.", file=sys.stderr)
            return 2
    except Exception as exc:
        _error_ledger("main_authority", event, exc)
    return 0


def handle_guard(event: dict) -> int:
    tool = event.get("tool_name")
    subagent = bool(event.get("agent_id") or event.get("agent_type"))
    if subagent:
        try:
            code, message = watchdog(event, load_policy())
        except Exception as exc:
            _error_ledger("watchdog", event, exc)
            print(f"Dream Team watchdog error ({type(exc).__name__}): tool call denied (fail-closed for subagents). "
                  "Stop and hand back a checkpoint.", file=sys.stderr)
            return 2
        if code:
            print(message, file=sys.stderr)
            return code
        if message:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}}))
    if tool not in GUARD_TOOLS:
        return 0
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    root = project_root(event)
    if tool in SHELL_TOOLS:
        command = str(tool_input.get("command") or "")
        text = _squash(command)
        forbidden = _subagent_forbidden_process(tool, command) if subagent else ""
        if forbidden:
            try:
                _ledger(root / STATE_DIR, {"event": "GUARD_DENY", "tool_name": tool, "target_kind": "PROCESS", "subagent": True,
                                           "reason": forbidden})
            except Exception:
                pass
            print(f"Dream Team governor guard: {forbidden}. Run it from the main thread if it is really needed.", file=sys.stderr)
            return 2
        protected_a = ".ai/dream-team" in text and not _is_exempt_cli(command)
        protected_b = subagent and (any(p in text for p in PROTECTED_B)
                                    or any(sub != "report" for sub in _governor_subcommands(text))
                                    or any(name in text for name in STATE_FILE_NAMES)
                                    or _subagent_shell_evasion(command, text))
    else:
        values = [str(tool_input.get(k) or "") for k in ("file_path", "notebook_path", "path")]
        text = _squash(" ".join(values))
        protected_a, protected_b = _file_targets(root, values, subagent)
    if not (protected_a or protected_b):
        return 0 if subagent else _main_authority(event, tool, tool_input, root)
    kind = "A" if protected_a else "B"
    state_dir = root / STATE_DIR
    try:
        _ledger(state_dir, {"event": "GUARD_DENY", "tool_name": tool, "target_kind": kind, "subagent": subagent})
        if any(name in text for name in SENSITIVE_STATE_FILES):
            _ledger(state_dir, {"event": "SELF_AUTH_ATTEMPT", "kind": "guard", "tool_name": tool, "subagent": subagent})
    except Exception:
        pass
    print(f"Dream Team governor guard: {tool} to the Dream Team runtime authorization state is denied (target {kind}). "
          "Use the governor CLI from the main thread (mission / authorize / report / release).", file=sys.stderr)
    return 2


def _break_glass(mode: str, event: dict) -> int:
    state_dir = project_root(event) / STATE_DIR
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    session = str(event.get("session_id") or "unknown")
    print("Dream Team governor BREAK-GLASS used; this blocks Gate GO unless the Owner authorized it", file=sys.stderr)
    try:
        entry = {"event": "TEST_BREAK_GLASS" if os.environ.get("DREAM_TEAM_TEST_MODE") == "1" else "BREAK_GLASS_USED",
                 "reason": os.environ.get("DREAM_TEAM_BREAK_GLASS_REASON") or "unspecified", "mode": mode,
                 "tool_use_id": event.get("tool_use_id"), "session": session,
                 "mission": _usage_key(_derive(state_dir)["mission"], session), "initiating_context": "env"}
        if tool_input.get("subagent_type"):
            entry["agent_type"] = tool_input.get("subagent_type")
        if event.get("tool_name"):
            entry["tool_name"] = event.get("tool_name")
        _ledger(state_dir, entry)
    except Exception as exc:
        print(f"Dream Team governor: break-glass ledger write failed ({type(exc).__name__}); denied (exit 2): "
              "break-glass is never allowed unaudited", file=sys.stderr)
        return 2
    return 0


def _error_ledger(mode: str, event, exc: Exception) -> None:
    try:
        root = project_root(event if isinstance(event, dict) else {})
        _ledger(root / STATE_DIR, {"event": "GOVERNOR_ERROR", "mode": mode, "error_class": type(exc).__name__,
                                   "error": str(exc)[:200]})
    except Exception:
        pass


def _parse_event(raw: str) -> dict:
    event = json.loads(raw or "{}")
    if not isinstance(event, dict):
        raise ValueError("hook input is not a JSON object")
    return event


def _lenient_event(raw: str) -> dict:
    try:
        return _parse_event(raw)
    except ValueError:
        return {}


def _break_glass_on() -> bool:
    return os.environ.get("DREAM_TEAM_GOVERNOR_BREAK_GLASS") == "1"


# --- main-thread CLI ---------------------------------------------------------
def _cli(mode: str, args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"agent_governor.py {mode}")
    parser.add_argument("--project-dir")
    if mode == "mission":
        parser.add_argument("mission_id")
        parser.add_argument("--complexity", choices=COMPLEXITIES, default="normal")
        parser.add_argument("--host-only", action="store_true", help="WP-1: deny Main implementation writes for this mission")
    elif mode == "wp":
        parser.add_argument("wp_id")
    elif mode == "release":
        parser.add_argument("tool_use_id", nargs="?")
        parser.add_argument("--stale", action="store_true")
    elif mode == "authorize":
        parser.add_argument("kind", choices=("budget", "parallel", "model_calls"))
        parser.add_argument("value")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--session")
    elif mode == "quota-clear":
        parser.add_argument("--reason", required=True)
    ns = parser.parse_args(args)
    root = Path(ns.project_dir or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    state_dir = root / STATE_DIR
    if mode == "report":
        print(json.dumps(_report(state_dir), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if mode == "quota-clear":
        reason = ns.reason.strip()
        if len(reason) < 10:
            parser.error("--reason must be at least 10 characters")
        with _state_lock(state_dir):
            hold = _derive(state_dir)["quota_hold"]
            if not hold:
                print("no quota hold active")
                return 0
            _ledger(state_dir, {"event": "QUOTA_CLEAR", "reason": reason, "cleared": hold.get("line_sha256"),
                                "authorized_by": CLI_AUTHORIZER})
        print("quota hold cleared")
        return 0
    if mode == "mission":
        mission_id = ns.mission_id.strip()
        if not mission_id:
            parser.error("mission_id must not be empty")
        with _state_lock(state_dir):
            _write_json(state_dir / MISSION_FILE, {"mission_id": mission_id, "complexity": ns.complexity, "informational": True,
                                                   "set_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            _ledger(state_dir, {"event": "MISSION_SET", "mission": mission_id, "complexity": ns.complexity,
                                "authorized_by": CLI_AUTHORIZER, **({"host_only": True} if ns.host_only else {})})
        print(f"mission set: {mission_id} ({ns.complexity}){' host-only' if ns.host_only else ''}")
        return 0
    if mode == "wp":
        wp_id = ns.wp_id.strip()
        if not WP_ID_RE.match(wp_id):
            parser.error("wp_id must match [A-Za-z0-9._-]{1,48}")
        with _state_lock(state_dir):
            derived = _derive(state_dir)
            if not derived["mission"]:
                print("no mission set: run `agent_governor.py mission <mission_id>` first", file=sys.stderr)
                return 1
            mission_id = derived["mission"]["mission_id"]
            if f"{mission_id}/{wp_id}" not in derived["wps"]:
                _ledger(state_dir, {"event": "WP_REGISTERED", "mission": mission_id, "wp": wp_id, "authorized_by": CLI_AUTHORIZER})
        print(f"wp registered: {mission_id}/{wp_id}")
        return 0
    if mode == "release":
        if bool(ns.tool_use_id) == bool(ns.stale):
            parser.error("give exactly one of <tool_use_id> or --stale")
        now = time.time()
        with _state_lock(state_dir):
            slots = _read_active(state_dir)
            if ns.stale:
                gone = [s for s in slots if now - float(s.get("started", 0)) >= STALE_SECONDS]
            else:
                gone = [s for s in slots if s.get("id") == ns.tool_use_id]
            if gone:
                _write_json(state_dir / ACTIVE_FILE, [s for s in slots if not any(s is g for g in gone)])
            for slot in gone:
                _ledger(state_dir, {"event": "SLOT_RELEASED_MANUAL", "tool_use_id": slot.get("id"),
                                    "agent_type": slot.get("agent_type"), "mission": slot.get("mission"),
                                    "mode": "stale" if ns.stale else "id", "authorized_by": CLI_AUTHORIZER})
        print(f"released {len(gone)} slot(s)")
        return 0 if gone or ns.stale else 1
    reason = ns.reason.strip()
    if len(reason) < 10:
        parser.error("--reason must be at least 10 characters")
    value = _num(ns.value)
    if value is None or value <= 0:
        parser.error("value must be a positive number")
    mission = _derive(state_dir)["mission"]
    if mission:
        key = _usage_key(mission, "")
    elif ns.session:
        key = f"session:{ns.session}"
    else:
        print("no mission set: run `agent_governor.py mission <mission_id>` first (or pass --session)", file=sys.stderr)
        return 1
    value = int(value) if ns.kind == "parallel" else value
    with _state_lock(state_dir):
        _ledger(state_dir, {"event": "AUTHORIZE", "kind": ns.kind, "value": value, "reason": reason, "mission": key,
                            "authorized_by": CLI_AUTHORIZER})
    print(f"authorized {ns.kind} {value} for {key}")
    return 0


def _report(state_dir: Path) -> dict:
    counts: dict[str, int] = {}
    units: dict[str, float] = {}
    switches: list[dict] = []
    recent: list[dict] = []
    policy_shas: dict[str, set] = {}
    bad = 0
    main_denied = 0
    path = state_dir / LEDGER_FILE
    lines =path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not isinstance(entry, dict):
            bad += 1
            continue
        event = str(entry.get("event") or "unknown")
        counts[event] = counts.get(event, 0) + 1
        if event == "MAIN_IMPLEMENTATION_WRITE" and entry.get("decision") == "deny":
            main_denied += 1
        if event in ("AGENT_USAGE", "WATCHDOG_STATE", "WATCHDOG_DENY", "QUOTA_EVENT", "QUOTA_CLEAR"):
            recent.append({k: entry.get(k) for k in ("ts", "event", "agent_id", "mission", "wp", "agent_type", "model_calls",
                                                     "tool_calls", "ctx_first", "ctx_peak", "state", "final_state", "turn_limit",
                                                     "telemetry", "reasons", "reason") if entry.get(k) is not None})
        if event == "MISSION_SET":
            switches.append({"mission": entry.get("mission"), "complexity": entry.get("complexity"), "ts": entry.get("ts")})
        if event == "PreToolUse" and entry.get("policy_sha256"):
            policy_shas.setdefault(str(entry.get("mission") or "unknown"), set()).add(entry["policy_sha256"])
        if entry.get("decision") == "allow":
            key = entry.get("mission") or (f"session:{entry['session']}" if entry.get("session") else "unknown")
            units[key] = units.get(key, 0.0) + float(_num(entry.get("work_units"), 0.0) or 0.0)
    derived = _derive(state_dir)
    return {"ledger_lines": len(lines), "malformed_lines": bad, "events": counts,
            "quota_hold": bool(derived["quota_hold"]), "watchdog_states": counts.get("WATCHDOG_STATE", 0),
            "subagent_model_calls_by_mission": derived["mission_calls"], "model_calls_by_wp": derived["wp_calls"],
            "agents_by_wp": derived["wp_attempts"], "recent_resource_events": recent[-10:],
            "break_glass_used": counts.get("BREAK_GLASS_USED", 0), "test_break_glass": counts.get("TEST_BREAK_GLASS", 0),
            "governor_errors": counts.get("GOVERNOR_ERROR", 0),
            "slot_ambiguous": counts.get("SLOT_AMBIGUOUS", 0),
            "policy_sha256_by_mission": {k: sorted(v) for k, v in sorted(policy_shas.items())}, "self_auth_attempts": counts.get("SELF_AUTH_ATTEMPT", 0),
            "guard_denies": counts.get("GUARD_DENY", 0), "main_implementation_writes": counts.get("MAIN_IMPLEMENTATION_WRITE", 0),
            "main_implementation_writes_denied": main_denied, "mission_switches": switches, "units_by_mission": units}


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "pre"
    if mode in CLI_MODES:
        return _cli(mode, argv[2:])
    raw, event = "", {}
    if mode == "pre":
        try:
            raw = sys.stdin.read()
            if _break_glass_on():
                return _break_glass("pre", _lenient_event(raw))
            event = _parse_event(raw)
            if event.get("tool_name") not in (None, "Agent", "Task"):
                return 0
            return handle_pre(event, load_policy())
        except Exception as exc:
            _error_ledger("pre", event, exc)
            print(f"Dream Team governor error ({type(exc).__name__}): spawn denied (fail-closed). "
                  "Continue in the main thread; see .ai/dream-team/usage-ledger.jsonl", file=sys.stderr)
            return 2
    if mode in ("post", "stop"):
        try:
            event = _parse_event(sys.stdin.read())
            return (handle_post if mode == "post" else handle_stop)(event, None)
        except Exception as exc:
            _error_ledger(mode, event, exc)
            return 0
    if mode == "guard":
        try:
            raw = sys.stdin.read()
            if _break_glass_on():
                lenient = _lenient_event(raw)
                if lenient.get("tool_name") not in GUARD_TOOLS and not lenient.get("agent_id"):
                    return 0
                return _break_glass("guard", lenient)
            return handle_guard(_parse_event(raw))
        except Exception as exc:
            _error_ledger("guard", event, exc)
            # subagents fail closed (CHAOS C09); the main thread stays usable on a governor bug
            subagent_payload = '"agent_id"' in raw or '"agent_type"' in raw
            return 2 if (".ai/dream-team" in _squash(raw) or subagent_payload) else 0
    print(f"Dream Team governor: unknown mode {mode!r} (pre|post|stop|guard|mission|authorize|report)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
