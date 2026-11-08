import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("scanner_safe",ROOT/"scripts"/"scan_public.py")
scanner=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=scanner
spec.loader.exec_module(scanner)
other=importlib.util.spec_from_file_location("scanner_base_test",ROOT/"tests"/"test_scan_public.py")
base=importlib.util.module_from_spec(other)
sys.modules[other.name]=base
other.loader.exec_module(base)

class SafetyContract(unittest.TestCase):
    def test_rate_limit_is_fatal_not_partial(self):
        api=base.FakeGitHub()
        real_get=api.get
        def limited(path):
            if "/contents/" in path:
                raise scanner.FatalScanFailure("rate limit reached")
            return real_get(path)
        api.get=limited
        with self.assertRaises(scanner.FatalScanFailure):
            scanner.build_feed(api,"westkitty",max_source_repos=3)

    def test_rename_does_not_reuse_stale_urls(self):
        api=base.FakeGitHub()
        old=scanner.build_feed(api,"westkitty",max_source_repos=3)
        api.repos[1]["name"]="RenamedViewer"
        api.heads["RenamedViewer"]=base.SHA_B
        api.files[("RenamedViewer","README.md")]=api.files[("ModelViewer","README.md")]
        api.files[("RenamedViewer","package.json")]=api.files[("ModelViewer","package.json")]
        cur=scanner.build_feed(api,"westkitty",prior=old,max_source_repos=3)
        item=next(r for r in cur["repositories"] if r["id"]==102)
        self.assertTrue(all("/RenamedViewer/blob/" in x["url"] for x in item["inspection"]["sources"].values()))

    def test_abrupt_inventory_loss_requires_operator_review(self):
        api=base.FakeGitHub()
        api.repos=[base.repo(i,f"Public_{i}") for i in range(100,121)]
        old=scanner.build_feed(api,"westkitty",max_source_repos=0)
        api.repos=api.repos[:2]
        with self.assertRaisesRegex(scanner.ScanFailure,"dropped sharply"):
            scanner.build_feed(api,"westkitty",prior=old,max_source_repos=0)

    def test_malicious_previous_source_not_reused(self):
        api=base.FakeGitHub()
        old=scanner.build_feed(api,"westkitty",max_source_repos=3)
        bad=copy.deepcopy(old)
        bad["repositories"][0]["visibility"]="private"
        with self.assertRaises(scanner.ScanFailure):
            scanner.validate_feed(bad)

    def test_readme_link_trailing_punctuation(self):
        class A:
            def get(self,path):
                return {"type":"file","encoding":"base64","sha":"e"*40,"content":"U2VlIGh0dHBzOi8vZ2l0aHViLmNvbS93ZXN0a2l0dHkvTW9kZWxWaWV3ZXIu"}
        d=scanner.source_at(A(),"westkitty","Planner",base.SHA_C,"README.md")
        self.assertIn("ModelViewer",d["referenced_repositories"])
        self.assertNotIn("ModelViewer.",d["referenced_repositories"])

    def test_large_portfolio_parses_without_claiming_inspections(self):
        # Synthetic 201-repo regression, runnable identically in GitHub Actions.
        api=base.FakeGitHub()
        api.repos=[base.repo(i+10000,f"Public_Project_{i}") for i in range(201)]
        feed=scanner.build_feed(api,"westkitty",max_source_repos=0)
        self.assertEqual(len(feed["repositories"]),201)
        self.assertEqual(feed["inventory"]["inspected_repositories"],0)
        self.assertFalse(feed["relationships"])

if __name__=="__main__":unittest.main()

class AccumulatedEvidence(unittest.TestCase):
    def test_unchanged_unselected_source_is_retained_but_historical(self):
        api=base.FakeGitHub()
        initial=scanner.build_feed(api,"westkitty",max_source_repos=3)
        # A new public repo arrives and takes a prioritized source slot, while
        # ModelViewer is still unchanged and may be unselected this run.
        api.repos.append(base.repo(104,"NewImportant",pushed="2026-11-08T23:55:00Z"))
        api.heads["NewImportant"]="f"*40
        api.files[("NewImportant","README.md")]="# NewImportant\n"
        current=scanner.build_feed(api,"westkitty",prior=initial,max_source_repos=1)
        historical=[r for r in current["repositories"] if r["inspection"]["state"]=="cached"]
        self.assertTrue(historical)
        self.assertTrue(all(r["inspection"]["current_head_verified"] is False for r in historical))
        self.assertEqual(current["inventory"]["historical_cached_repositories"],len(historical))
        self.assertTrue(all(e.get("freshness") in ("sampled-head","historical") for e in current["relationships"]))

class DurableLedger(unittest.TestCase):
    def test_sqlite_persists_immutable_snapshot_and_evidence(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"history.sqlite"
            api=base.FakeGitHub()
            feed=scanner.build_feed(api,"westkitty",max_source_repos=3,now="2026-11-08T11:12:13Z")
            scanner.record_sqlite(path,feed)
            scanner.record_sqlite(path,feed)
            with __import__("contextlib").closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM repository_snapshots").fetchone()[0],3)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM observed_evidence").fetchone()[0],0)
                self.assertGreater(db.execute("SELECT COUNT(*) FROM discovery_snapshots").fetchone()[0],0)
                preserved=db.execute("SELECT payload_json FROM snapshots").fetchone()[0]
                self.assertEqual(__import__("json").loads(preserved)["content_sha256"],feed["content_sha256"])
