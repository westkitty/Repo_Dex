"""Isolated, offline scanner regressions; never request GitHub over network."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repo_dex_scanner", ROOT / "scripts" / "scan_public.py")
scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scan
spec.loader.exec_module(scan)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def repo(rid, name, private=False, owner="westkitty", archived=False, pushed="2026-11-05T00:00:00Z"):
    return {
        "id": rid, "name": name,
        "owner": {"login": owner}, "visibility": "private" if private else "public",
        "private": private, "description": f"Public {name} project",
        "default_branch": "main", "language": "TypeScript", "topics": ["offline", "tools"],
        "archived": archived, "fork": False, "pushed_at": pushed, "updated_at": pushed,
    }


class FakeGitHub:
    def __init__(self):
        self.repos = [repo(101, "ExportStudio"), repo(102, "ModelViewer"), repo(103, "Planner"), repo(999, "HiddenPrivate", private=True), repo(9999, "Alien", owner="intruder")]
        self.heads = {"ExportStudio": SHA_A, "ModelViewer": SHA_B, "Planner": SHA_C}
        self.files = {
            ("ExportStudio", "README.md"): "# ExportStudio\nExport GLB models for offline viewers.\n",
            ("ModelViewer", "README.md"): "# ModelViewer\nImport GLB assets.\n",
            ("Planner", "README.md"): "See https://github.com/westkitty/ModelViewer for other viewing examples.\n",
            ("ExportStudio", "package.json"): json.dumps({"dependencies": {"three": "^0.180.0"}}),
            ("ModelViewer", "package.json"): json.dumps({"dependencies": {"three": "^0.180.0"}}),
            ("Planner", "package.json"): json.dumps({"devDependencies": {"vite": "^8.0.0"}}),
        }
        self.calls = []
        self.fail_page = None
        self.bad_source = None

    def get(self, path):
        self.calls.append(path)
        if path.startswith("/users/"):
            page = int(path.split("page=")[-1])
            if self.fail_page == page:
                raise scan.ScanFailure("Synthetic API limit")
            return self.repos[(page - 1) * 100:page * 100]
        if "/branches/" in path:
            name = path.split("/")[3]
            return {"commit": {"sha": self.heads[name]}}
        if "/contents/" in path:
            name = path.split("/")[3]
            tail = path.split("/contents/", 1)[-1]
            name_file = tail.split("?", 1)[0]
            if self.bad_source == (name, name_file):
                raise scan.ScanFailure("Synthetic invalid source")
            content = self.files.get((name, name_file))
            if content is None:
                return None
            return {
                "type": "file", "encoding": "base64", "sha": "e" * 40,
                "content": base64.b64encode(content.encode()).decode(),
            }
        raise AssertionError("Unexpected call " + path)


class ScannerContract(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def feed(self, prior=None, sample=3):
        return scan.build_feed(self.api, "westkitty", prior=prior, max_source_repos=sample, now="2026-11-08T13:00:00Z")

    def test_public_only_no_foreign_or_secrets(self):
        f = self.feed()
        self.assertEqual(f["schema"], "repo-dex-feed/v1")
        self.assertEqual(f["inventory"]["public_repositories"], 3)
        self.assertEqual({r["name"] for r in f["repositories"]}, {"ExportStudio", "ModelViewer", "Planner"})
        serialized = json.dumps(f)
        self.assertNotIn("HiddenPrivate", serialized)
        self.assertNotIn("Alien", serialized)
        self.assertNotIn("# ExportStudio", serialized)  # raw README bodies not exported
        self.assertEqual(f["source"]["visibility"], "public-only")

    def test_manifest_shared_tech_has_pinned_evidence_not_reuse_claim(self):
        f = self.feed()
        e = next(e for e in f["relationships"] if e["type"] == "shared-technology")
        self.assertEqual(e["status"], "documented")
        self.assertEqual(e["evidence_level"], "located")
        self.assertEqual(len(e["evidence"]), 2)
        self.assertIn("not code reuse", e["explanation"])
        for source in e["evidence"]:
            self.assertEqual(len(source["commit_sha"]), 40)
            self.assertIn("/blob/", source["url"])
            self.assertEqual(source["path"], "package.json")
        self.assertFalse(any(e["type"] == "runtime-dependency" for e in f["relationships"]))

    def test_readme_reference_not_misclassified_as_dependency(self):
        f = self.feed()
        e = next(e for e in f["relationships"] if e["type"] == "readme-reference")
        self.assertEqual(e["status"], "documented")
        self.assertEqual(e["evidence_level"], "described")
        self.assertIn("does not establish a software dependency", e["explanation"])

    def test_exchange_opportunity_is_explicitly_hypothetical(self):
        f = self.feed()
        self.assertGreaterEqual(len(f["opportunities"]), 1)
        o = next(x for x in f["opportunities"] if x["format"] == "glb")
        self.assertEqual(o["status"], "hypothesis")
        self.assertEqual(o["evidence_level"], "described")
        self.assertIn("unverified", o["why"])
        self.assertEqual(len(o["evidence"]), 2)
        self.assertIn("Export a non-sensitive", o["experiment"])

    def test_baseline_not_new_repo_event(self):
        f = self.feed()
        self.assertEqual(f["delta"]["kind"], "baseline")
        self.assertFalse(f["delta"]["new"])
        self.assertEqual(f["observations"][0]["kind"], "baseline")

    def test_incremental_rename_and_archive_by_identity(self):
        previous = self.feed()
        self.api.repos[1]["name"] = "RenamedViewer"
        self.api.repos[1]["archived"] = True
        self.api.heads["RenamedViewer"] = SHA_B
        current = self.feed(previous)
        self.assertEqual(current["delta"]["kind"], "incremental")
        self.assertEqual(current["delta"]["renamed"], [{"id": 102, "from": "ModelViewer", "to": "RenamedViewer"}])
        self.assertEqual(current["delta"]["archived"], ["RenamedViewer"])
        self.assertNotIn("ModelViewer", current["delta"]["removed"])

    def test_published_feed_handles_actual_deletion_only_when_complete(self):
        old = self.feed()
        self.api.repos = self.api.repos[:1]
        new = self.feed(old)
        self.assertEqual(new["delta"]["removed"], ["ModelViewer", "Planner"])
        self.assertEqual(new["inventory"]["public_repositories"], 1)

    def test_incomplete_pagination_fails_closed(self):
        self.api.repos = [repo(i, f"Repo_{i}") for i in range(1, 102)]
        self.api.fail_page = 2
        with self.assertRaises(scan.ScanFailure):
            self.feed(sample=0)

    def test_pagination_over_100_and_all_public_counted(self):
        self.api.repos = [repo(i, f"Repo_{i}") for i in range(1, 202)]
        f = self.feed(sample=0)
        self.assertEqual(f["inventory"]["public_repositories"], 201)
        self.assertEqual(f["inventory"]["inspected_repositories"], 0)
        self.assertEqual(len(f["relationships"]), 0)
        self.assertEqual(len(f["opportunities"]), 0)
        self.assertTrue(any("page=3" in path for path in self.api.calls))

    def test_missing_source_does_not_forge_evidence(self):
        self.api.bad_source = ("ModelViewer", "package.json")
        f = self.feed()
        self.assertFalse(any(e["type"] == "shared-technology" for e in f["relationships"]))
        self.assertTrue(f["inventory"]["source_errors"])
        self.assertTrue(all(o["status"] == "hypothesis" for o in f["opportunities"]))

    def test_unselected_projects_do_not_gain_claimed_inspections(self):
        f = self.feed(sample=1)
        self.assertEqual(f["inventory"]["inspected_repositories"], 1)
        self.assertEqual(sum(r["inspection"]["state"] == "not-selected" for r in f["repositories"]), 2)
        self.assertFalse(f["relationships"])

    def test_cache_unchanged_commit_skips_source_fetch(self):
        old = self.feed()
        self.api.calls.clear()
        new = self.feed(old)
        self.assertEqual(new["inventory"]["inspected_repositories"], 3)
        self.assertFalse(any("/contents/" in path for path in self.api.calls))
        self.assertEqual(new["delta"]["new"], [])

    def test_source_ref_is_pinned_on_new_head(self):
        old = self.feed()
        self.api.heads["ModelViewer"] = "d" * 40
        self.api.calls.clear()
        new = self.feed(old)
        moved = next(r for r in new["repositories"] if r["name"] == "ModelViewer")
        self.assertEqual(moved["inspection"]["commit_sha"], "d" * 40)
        self.assertTrue(any("ref=" + "d" * 40 in p for p in self.api.calls))

    def test_output_atomic_and_immutable_snapshot_not_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            out = t / "docs" / "feed" / "latest.json"
            archive = t / "snaps"
            with redirect_stdout(io.StringIO()):
                code = scan.cli(["--output", str(out), "--snapshot-dir", str(archive), "--max-source-repos", "3"], api=self.api)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.read_text())["inventory"]["public_repositories"], 3)
            snapshots = list(archive.iterdir())
            self.assertEqual(len(snapshots), 1)
            frozen = snapshots[0].read_bytes()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(scan.cli(["--output", str(out), "--snapshot-dir", str(archive), "--max-source-repos", "3"], api=self.api), 0)
            self.assertEqual(len(list(archive.iterdir())), 1)
            self.assertEqual(snapshots[0].read_bytes(), frozen)

    def test_failing_scan_does_not_erase_previous_file(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "latest.json"
            out.write_text("PREEXISTING")
            self.api.fail_page = 1
            with redirect_stderr(io.StringIO()):
                self.assertEqual(scan.cli(["--output", str(out)], api=self.api), 2)
            self.assertEqual(out.read_text(), "PREEXISTING")

    def test_dry_run_no_writes(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "latest.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(scan.cli(["--output", str(out), "--dry-run"], api=self.api), 0)
            self.assertFalse(out.exists())

    def test_reject_invalid_previous_schema(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "old.json"
            path.write_text('{"schema":"untrusted", "owner":"westkitty"}')
            with self.assertRaises(scan.ScanFailure):
                scan.read_previous(str(path), "westkitty")

    def test_invariant_guard_prevents_false_categorization(self):
        f = self.feed()
        f["repositories"][0]["visibility"] = "private"
        with self.assertRaises(scan.ScanFailure):
            scan.validate_feed(f)
        f = self.feed()
        f["opportunities"][0]["status"] = "verified"
        with self.assertRaises(scan.ScanFailure):
            scan.validate_feed(f)


if __name__ == "__main__":
    unittest.main()
