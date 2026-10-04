import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "andy_state.py"


def run(*args, check=True):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result, json.loads(result.stdout)


class AndyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "andy@example.test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Andy Test"], cwd=self.root, check=True)
        (self.root / "tracked.txt").write_text("base", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.root, check=True, capture_output=True)
        run("init", self.root)

    def tearDown(self):
        self.temp.cleanup()

    def checkpoint(self, root, base, check=True, **changes):
        patch = Path(self.temp.name) / "patch.json"
        patch.write_text(json.dumps({"_base_updated_at": base, **changes}), encoding="utf-8")
        return run("write", root, patch, check=check)

    def test_rejects_stale_checkpoint(self):
        _, first = run("read", self.root)
        old = first["data"]["updated_at"]
        self.checkpoint(self.root, old, current_task="new task")
        result, payload = self.checkpoint(self.root, old, check=False, current_task="stale task")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(payload["status"], "stale_checkpoint")

    def test_compact_archives_overflow_and_fits_budget(self):
        _, first = run("read", self.root)
        self.checkpoint(self.root, first["data"]["updated_at"],
                        decisions=[f"decision {i} " + "x" * 200 for i in range(40)],
                        tests=[f"test {i} " + "y" * 200 for i in range(40)])
        _, result = run("compact", self.root)
        self.assertEqual(result["status"], "compacted")
        self.assertLessEqual(result["bytes_after"], result["max_bytes"])
        overflow = json.loads(Path(result["overflow"]).read_text(encoding="utf-8"))
        self.assertTrue(overflow["overflow"])
        run("verify", self.root)

    def test_concurrent_writes_cannot_both_replace_the_same_checkpoint(self):
        _, first = run("read", self.root)
        base = first["data"]["updated_at"]
        barrier = threading.Barrier(3)
        results = []

        def writer(name):
            patch = Path(self.temp.name) / f"patch-{name}.json"
            patch.write_text(
                json.dumps({"_base_updated_at": base, "current_task": name}),
                encoding="utf-8",
            )
            barrier.wait()
            results.append(run("write", self.root, patch, check=False))

        threads = [threading.Thread(target=writer, args=(name,)) for name in ("one", "two")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        statuses = sorted(payload["status"] for _, payload in results)
        self.assertEqual(statuses, ["stale_checkpoint", "written"])

    def test_worktrees_share_canonical_state_and_verify_active_workspace(self):
        linked = Path(self.temp.name) / "linked"
        subprocess.run(["git", "worktree", "add", "-b", "feature", str(linked)], cwd=self.root, check=True, capture_output=True)
        (linked / "new.txt").write_text("worktree", encoding="utf-8")
        _, first = run("read", linked)
        base = first["data"]["updated_at"]
        self.checkpoint(linked, base, current_task="linked task", files_created=["new.txt"])

        _, primary_read = run("read", self.root)
        self.assertEqual(primary_read["data"]["current_task"], "linked task")
        self.assertEqual(Path(primary_read["data"]["workspace_root"]), linked.resolve())
        self.assertFalse((linked / ".ai" / "andy" / "current.json").exists())
        _, verified = run("verify", self.root)
        self.assertEqual(verified["missing_files"], [])
        self.assertFalse(verified["git_drift"])

    def test_migration_finds_legacy_workspace_from_referenced_files(self):
        linked = Path(self.temp.name) / "linked"
        subprocess.run(["git", "worktree", "add", "-b", "feature", str(linked)], cwd=self.root, check=True, capture_output=True)
        (linked / "worktree-only.txt").write_text("worktree", encoding="utf-8")

        current_path = self.root / ".ai" / "andy" / "current.json"
        state = json.loads(current_path.read_text(encoding="utf-8"))
        state["andy_version"] = "1.0"
        state.pop("workspace_root", None)
        state["files_created"] = ["worktree-only.txt"]
        current_path.write_text(json.dumps(state), encoding="utf-8")

        _, migrated = run("migrate-worktrees", self.root)
        self.assertEqual(Path(migrated["workspace_root"]), linked.resolve())
        _, verified = run("verify", self.root)
        self.assertEqual(verified["missing_files"], [])


PLAN_TEXT = "# plan\n\n```yaml\nprogram: test\ncontinuity_root: Skills IL/Core Dir/.ai/andy/current.json\n```\n"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class ConfiguredRootTests(unittest.TestCase):
    """Continuity configuration (plan continuity_root) wins over Git-root inference."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "outer repo"
        self.core = self.repo / "Skills IL" / "Core Dir"
        (self.core / "sub dir").mkdir(parents=True)
        (self.repo / "DREAM_TEAM_EXECUTION_PLAN.md").write_text(PLAN_TEXT, encoding="utf-8")
        (self.core / "tracked.txt").write_text("base", encoding="utf-8")
        (self.repo / ".gitignore").write_text("/External/\n", encoding="utf-8")
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "andy@example.test")
        git(self.repo, "config", "user.name", "Andy Test")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "base")
        run("init", self.core)
        self.canonical = self.core / ".ai" / "andy" / "current.json"

    def tearDown(self):
        self.temp.cleanup()

    def state_root(self, where, cwd=None):
        result = subprocess.run([sys.executable, str(SCRIPT), "read", str(where)], capture_output=True, text=True,
                                cwd=cwd)
        data = json.loads(result.stdout)
        if "state_root" in data:
            return Path(data["state_root"]).resolve()
        return Path(data["path"]).parents[2].resolve()

    def write(self, where, **changes):
        _, current = run("read", where)
        patch = Path(self.temp.name) / "patch.json"
        patch.write_text(json.dumps({"_base_updated_at": current["data"]["updated_at"], **changes}), encoding="utf-8")
        return run("write", where, patch)

    def all_current_files(self):
        return sorted(p.resolve() for p in Path(self.temp.name).rglob("current.json"))

    def test_resolves_canonical_root_from_repo_root_nested_core_and_other_cwd(self):
        for where in (self.repo, self.core, self.core / "sub dir", self.repo / "Skills IL"):
            self.assertEqual(self.state_root(where), self.core.resolve(), where)
        self.assertEqual(self.state_root(self.repo, cwd=tempfile.gettempdir()), self.core.resolve())

    def test_write_from_repo_root_targets_canonical_only(self):
        self.write(self.repo, current_task="from root", files_touched=["tracked.txt"])
        self.assertEqual(self.all_current_files(), [self.canonical.resolve()])
        _, data = run("read", self.core)
        self.assertEqual(data["data"]["current_task"], "from root")
        self.assertEqual(Path(data["data"]["workspace_root"]).resolve(), self.core.resolve())
        _, verified = run("verify", self.repo)
        self.assertEqual((verified["missing_files"], verified["write_integrity"]), ([], "RECORDED"))

    def test_git_absent_fallback_uses_configuration(self):
        shutil.rmtree(self.repo / ".git", onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
        self.assertEqual(self.state_root(self.repo), self.core.resolve())
        self.assertEqual(self.state_root(self.core / "sub dir"), self.core.resolve())

    def test_clean_clone_resolves_inside_clone(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "andy")
        clone = Path(self.temp.name) / "clone dir"
        git(self.temp.name, "clone", "-q", str(self.repo), str(clone))
        clone_core = (clone / "Skills IL" / "Core Dir").resolve()
        self.assertEqual(self.state_root(clone), clone_core)
        # the stored workspace_root still names the original tree; the clone must never use it
        _, data = run("read", clone)
        self.assertEqual(Path(data["workspace_root"]).resolve(), clone_core)
        _, verified = run("verify", clone)
        self.assertNotIn("unsafe_workspace", verified)
        self.assertEqual(Path(verified["workspace_root"]).resolve(), clone_core)

    def test_nested_external_repo_and_ignored_dir_never_resolve_to_canonical(self):
        nested = self.repo / "Nested Repo"
        nested.mkdir()
        git(nested, "init", "-b", "main")
        ignored = self.repo / "External" / "thing"
        ignored.mkdir(parents=True)
        self.assertEqual(self.state_root(nested), nested.resolve())
        self.assertNotEqual(self.state_root(ignored), self.core.resolve())

    def test_plan_without_key_or_with_traversal_does_not_hijack(self):
        (self.core / "sub dir" / "DREAM_TEAM_EXECUTION_PLAN.md").write_text("# pointer copy\n", encoding="utf-8")
        self.assertEqual(self.state_root(self.core / "sub dir"), self.core.resolve())
        (self.repo / "DREAM_TEAM_EXECUTION_PLAN.md").write_text(
            "```yaml\ncontinuity_root: ../../evil/.ai/andy/current.json\n```\n", encoding="utf-8")
        self.assertEqual(self.state_root(self.core), self.repo.resolve())

    def test_stale_duplicate_is_detected_and_never_authoritative(self):
        duplicate = self.repo / ".ai" / "andy" / "current.json"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(self.canonical.read_text(encoding="utf-8").replace('"status": "new"', '"status": "active"'),
                             encoding="utf-8")
        _, data = run("read", self.repo)
        self.assertEqual(data["data"]["status"], "new")
        result, verified = run("verify", self.repo, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([Path(p).resolve() for p in verified["stale_duplicates"]], [duplicate.resolve()])

    def test_direct_edit_is_detected_and_emergency_adoption_is_audited(self):
        state = json.loads(self.canonical.read_text(encoding="utf-8"))
        state["current_task"] = "edited by hand"
        self.canonical.write_text(json.dumps(state), encoding="utf-8")
        result, verified = run("verify", self.core, check=False)
        self.assertEqual((result.returncode, verified["write_integrity"]), (1, "UNRECORDED_EDIT"))
        failed, _ = run("adopt-manual", self.core, check=False)
        self.assertEqual(failed.returncode, 1)
        _, adopted = run("adopt-manual", self.core, "tooling", "broken")
        self.assertEqual(adopted["integrity_before"], "UNRECORDED_EDIT")
        self.assertTrue(Path(adopted["audit"]).exists())
        _, verified = run("verify", self.core)
        self.assertEqual(verified["write_integrity"], "RECORDED")

    def test_deleting_the_digest_before_a_direct_edit_still_blocks_verify(self):
        (self.canonical.parent / "current.json.sha256").unlink()
        self.canonical.write_text(self.canonical.read_text(encoding="utf-8").replace('"status": "new"', '"status": "active"'),
                                  encoding="utf-8")
        result, verified = run("verify", self.core, check=False)
        self.assertEqual((result.returncode, verified["write_integrity"]), (1, "UNVERIFIED"))

    def test_stale_lock_from_a_dead_writer_is_recovered(self):
        lock = self.canonical.parent / ".current.lock"
        lock.write_text("99999\n", encoding="ascii")
        old = lock.stat().st_mtime - 3600
        os.utime(lock, (old, old))
        self.write(self.repo, current_task="after crash")
        self.assertFalse(lock.exists())

    def test_unreadable_continuity_config_stops_instead_of_falling_back(self):
        (self.repo / "DREAM_TEAM_EXECUTION_PLAN.md").write_text(
            "# plan\n\n```yml\n  continuity_root: Skills IL/Core Dir/.ai/andy/current.json\n```\n", encoding="utf-8")
        result, verified = run("verify", self.core, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("continuity_config_unparsed", verified)
        patch = Path(self.temp.name) / "patch.json"
        patch.write_text(json.dumps({"current_task": "x"}), encoding="utf-8")
        failed, data = run("write", self.repo, patch, check=False)
        self.assertEqual((failed.returncode, data["status"]), (1, "continuity_config_unparsed"))
        self.assertFalse((self.repo / ".ai").exists())

    def test_duplicate_in_an_intermediate_directory_is_flagged(self):
        duplicate = self.repo / "Skills IL" / ".ai" / "andy" / "current.json"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(self.canonical.read_text(encoding="utf-8"), encoding="utf-8")
        result, verified = run("verify", self.core / "sub dir", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn(duplicate.resolve(), [Path(p).resolve() for p in verified["stale_duplicates"]])

    def test_resume_after_session_restart(self):
        self.write(self.repo, next_action="continue X", current_phase="P1")
        result = subprocess.run([sys.executable, str(SCRIPT), "resume", str(self.core / "sub dir")],
                                capture_output=True, text=True)
        packet = json.loads(result.stdout)
        self.assertEqual((packet["next_exact_action"], packet["active"]["phase"]), ("continue X", "P1"))


if __name__ == "__main__":
    unittest.main()
