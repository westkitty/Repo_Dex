"""Additive preservation tests for the Repo_Dex Laboratory and shared private ledger."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LAB=(ROOT/'docs/laboratory.html').read_text(encoding='utf-8')
DECISIONS=(ROOT/'docs/shared-decisions.js').read_text(encoding='utf-8')

class TestOmniUXContract(unittest.TestCase):
    def test_existing_public_feed_contract(self):
        self.assertIn("repo-dex-feed/v1",LAB)
        self.assertIn("repo-dex-scan-status/v1",LAB)
        self.assertIn("f.source?.visibility!=='public-only'",LAB)
        self.assertIn("r.feed_generated_at===f.generated_at",LAB)
        self.assertIn('feed/latest.json',LAB)
        self.assertIn('feed/status.json',LAB)

    def test_public_review_surface_and_recovery(self):
        for id_ in ('reload','scan-summary','caps','capSearch','capFreshness','cap-list','capMore','review-count','findings','reviewMore','filter','query','export','import','undo','decision-history','ledger-status'):
            self.assertIn(f'id="{id_}"',LAB)
        self.assertIn('No results match',LAB)
        self.assertIn('existing findings retained',LAB)
        self.assertIn('No source-pinned capability records',LAB)

    def test_cross_product_navigation(self):
        for url in ('../Westkitty_Atlas/','./','../Westkitty_Atlas/?op='):
            self.assertIn(url,LAB)
        self.assertIn('Legacy Repo_Dex',LAB)
        self.assertIn('evidence-compare',LAB)
        self.assertIn('displayRank(op)',LAB)

    def test_private_decision_contract_is_local_only(self):
        for token in ('repo-dex-decisions/v1','westkitty.repoDex.decisions.v1','function undoLast()','function canUndo()','function importJSON(raw)','function exportJSON()','evidence_signature'):
            self.assertIn(token,DECISIONS)
        self.assertIn("localStorage.setItem",DECISIONS)
        self.assertNotIn('fetch(',DECISIONS)
        self.assertNotIn('navigator.sendBeacon',DECISIONS)
        self.assertNotIn('XMLHttpRequest',DECISIONS)
        self.assertNotIn('https://',DECISIONS)

    def test_mobile_and_reduced_motion(self):
        self.assertIn('min-height:44px',LAB)
        self.assertIn('prefers-reduced-motion:reduce',LAB)
        self.assertIn('aria-label="Portfolio workspaces"',LAB)
        self.assertIn('aria-live="polite"',LAB)

if __name__=='__main__':unittest.main()
