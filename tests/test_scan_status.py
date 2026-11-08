"""C03: distinct last successful scan and latest content-change times."""
import copy
import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
import sys
from test_scan_public import scan, FakeGitHub
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('publisher',ROOT/'scripts'/'publish_feed.py')
pub=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class ScanStatus(unittest.TestCase):
    def test_changed_unchanged_and_changed_again(self):
        api=FakeGitHub()
        a=scan.build_feed(api,'westkitty',max_source_repos=3,now='2026-11-08T12:00:00Z')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            candidate=root/'candidate.json'; published=root/'latest.json'; status=root/'status.json'
            candidate.write_text(json.dumps(a))
            first=pub.publish(candidate,published,status,'135','https://github.com/westkitty/Repo_Dex/actions/runs/135')
            self.assertTrue(first['evidence_changed'])
            prior_bytes=published.read_bytes()
            b=copy.deepcopy(a);b['generated_at']='2026-11-09T12:00:00Z'
            candidate.write_text(json.dumps(b))
            second=pub.publish(candidate,published,status,'136')
            self.assertFalse(second['evidence_changed'])
            self.assertEqual(second['last_successful_scan'],'2026-11-09T12:00:00Z')
            self.assertEqual(second['feed_generated_at'],'2026-11-08T12:00:00Z')
            self.assertEqual(published.read_bytes(),prior_bytes)
            self.assertEqual(json.loads(status.read_text())['latest_feed_digest'],a['content_sha256'])
            api.repos[0]['description']='changed verified metadata'
            c=scan.build_feed(api,'westkitty',prior=a,max_source_repos=3,now='2026-11-10T12:00:00Z')
            candidate.write_text(json.dumps(c))
            third=pub.publish(candidate,published,status,'137')
            self.assertTrue(third['evidence_changed'])
            self.assertEqual(third['feed_generated_at'],'2026-11-10T12:00:00Z')

    def test_failed_candidate_cannot_advance_success_clock(self):
        api=FakeGitHub()
        good=scan.build_feed(api,'westkitty')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/'candidate.json'; latest=root/'latest.json'; status=root/'status.json'
            p.write_text(json.dumps(good));pub.publish(p,latest,status)
            old_bytes=(latest.read_bytes(),status.read_bytes())
            malformed=copy.deepcopy(good);malformed['repositories'][0]['visibility']='private'
            p.write_text(json.dumps(malformed))
            with self.assertRaises(pub.ScanFailure):pub.publish(p,latest,status)
            self.assertEqual((latest.read_bytes(),status.read_bytes()),old_bytes)

    def test_status_schema_is_valid_json(self):
        schema=json.loads((ROOT/'docs'/'feed'/'status-schema-v1.json').read_text())
        self.assertIn('last_successful_scan',schema['required'])
        self.assertEqual(schema['properties']['owner']['const'],'westkitty')

if __name__ == '__main__': unittest.main()
