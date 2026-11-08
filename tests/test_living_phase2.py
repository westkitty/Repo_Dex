"""C01/C02/C04: strict read-only synthetic progression and evidence invariants."""
import unittest
import copy
from test_scan_public import scan, FakeGitHub, repo


class ProgressiveCoverage(unittest.TestCase):
    def test_uninspected_repos_rotate_without_claiming_fresh_inspection(self):
        api = FakeGitHub()
        api.repos = [repo(i, f"Repo_{i:03d}") for i in range(1, 8)]
        api.heads = {r['name']: 'a'*40 for r in api.repos}
        api.files = {(r['name'], 'README.md'): f"# {r['name']}\nExport GLB.\n" for r in api.repos}
        prior = None
        progression=[]
        for i in range(4):
            snap = scan.build_feed(api, 'westkitty', prior, max_source_repos=2, now=f'2026-11-0{i+1}T00:00:00Z')
            progression.append(snap['inventory']['cumulative_source_repositories'])
            self.assertLessEqual(snap['inventory']['inspected_repositories'], 2)
            self.assertTrue(all(item['visibility']=='public' for item in snap['repositories']))
            prior = snap
        self.assertEqual(progression, [2,4,6,7])
        self.assertEqual(sum(r['inspection']['state']=='cached' for r in prior['repositories']), 5)

    def test_changed_project_prioritized_over_backlog(self):
        api = FakeGitHub()
        old=scan.build_feed(api,'westkitty',max_source_repos=1)
        api.repos[0]['description']='new meaning'
        new=scan.build_feed(api,'westkitty',old,max_source_repos=1)
        got=[r['name'] for r in new['repositories'] if r['inspection']['state']=='inspected']
        self.assertEqual(got,['ExportStudio'])

    def test_genomes_source_pinned_and_transfers_still_unverified(self):
        f=scan.build_feed(FakeGitHub(),'westkitty',max_source_repos=3)
        self.assertGreater(len(f['capability_genomes']),0)
        assert any(c['kind']=='described-export' for c in f['capability_genomes'])
        assert any(c['kind']=='declared-package' for c in f['capability_genomes'])
        for c in f['capability_genomes']:
            self.assertIn('/blob/',c['source']['url'])
            self.assertIn('unverified',c['constraint'])
            self.assertIn(c['evidence_level'],('described','located'))
            self.assertFalse(c['evidence_level'] in ('transferred','verified'))
        for o in f['opportunities']:
            self.assertEqual(o['review']['confidence'],'untested-hypothesis')
            self.assertTrue(o['review']['skeptical_counterpoints'])
            self.assertEqual(o['review']['beneficiary_repository_id'],o['importer'])
            self.assertIn('round-trip',o['review']['acceptance_test'])

    def test_alias_survives_multiple_renames(self):
        api=FakeGitHub()
        a=scan.build_feed(api,'westkitty',max_source_repos=3)
        api.repos[1]['name']='Viewer2'
        api.heads['Viewer2']='b'*40
        b=scan.build_feed(api,'westkitty',a,max_source_repos=3)
        self.assertIn('ModelViewer', next(x for x in b['repositories'] if x['id']==102)['aliases'])
        api.repos[1]['name']='Viewer3'
        api.heads['Viewer3']='b'*40
        c=scan.build_feed(api,'westkitty',b,max_source_repos=3)
        self.assertEqual(set(next(x for x in c['repositories'] if x['id']==102)['aliases']), {'ModelViewer','Viewer2'})
        scan.validate_feed(c)

    def test_invalid_capability_provenance_fails_closed(self):
        f=scan.build_feed(FakeGitHub(),'westkitty',max_source_repos=3)
        f['capability_genomes'][0]['source']['commit_sha']='bogus'
        with self.assertRaises(scan.ScanFailure):
            scan.validate_feed(f)


if __name__ == '__main__': unittest.main()

class StarvationBoundary(unittest.TestCase):
    def test_noninspected_lane_survives_heavy_changed_activity(self):
        api=FakeGitHub()
        api.repos=[repo(i,f"Repo_{i:03d}") for i in range(1,61)]
        api.heads={r['name']:'a'*40 for r in api.repos}
        api.files={(r['name'],'README.md'):f"# {r['name']}\nExport JSON fixture.\n" for r in api.repos}
        old=scan.build_feed(api,'westkitty',max_source_repos=40)
        initially={r['id'] for r in old['repositories'] if r['inspection'].get('sources')}
        for r in api.repos:
            if r['id'] in initially:r['description']='Updated project feature'
        new=scan.build_feed(api,'westkitty',old,max_source_repos=12)
        new_ids={r['id'] for r in new['repositories'] if r['inspection'].get('sources')}
        self.assertGreaterEqual(len(new_ids-initially),4)
        self.assertLessEqual(new['inventory']['inspected_repositories'],12)
