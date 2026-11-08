#!/usr/bin/env python3
"""Publish validated Repo_Dex snapshots and scan receipts without false freshness claims.

Intended for GitHub Actions after a successful source scan. No API calls, tokens,
network clients, or writes outside explicitly supplied output paths.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from scan_public import validate_feed, ScanFailure, canonical, write_atomically

STATUS_SCHEMA = 'repo-dex-scan-status/v1'
HEX = re.compile(r'^[0-9a-f]{64}$')


def publish(candidate: Path, published: Path, status: Path, run_id: str = '', run_url: str = '') -> dict:
    if not candidate.is_file():
        raise ScanFailure('Validated candidate file missing')
    data = json.loads(candidate.read_text(encoding='utf-8'))
    validate_feed(data)
    if data.get('owner') != 'westkitty' or data.get('source', {}).get('visibility') != 'public-only':
        raise ScanFailure('Invalid owner or public-only contract')
    digest = data.get('content_sha256')
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise ScanFailure('Invalid feed digest')
    old = json.loads(published.read_text(encoding='utf-8')) if published.is_file() else None
    if old is not None:
        validate_feed(old)
    changed = old is None or old.get('content_sha256') != digest
    report = {
        'schema': STATUS_SCHEMA,
        'owner': 'westkitty',
        'state': 'success',  # This file is never updated after a failed scan.
        'last_successful_scan': data['generated_at'],
        'latest_feed_digest': digest,
        'feed_generated_at': data['generated_at'] if changed else old['generated_at'],
        'evidence_changed': changed,
        'run_id': run_id if re.fullmatch(r'\d{1,20}', run_id) else '',
        'run_url': run_url if re.fullmatch(r'https://github\.com/westkitty/Repo_Dex/actions/runs/\d{1,20}', run_url) else '',
        'public_repositories': data['inventory']['public_repositories'],
        'source_inspected_this_run': data['inventory']['inspected_repositories'],
        'cumulative_source_repositories': data['inventory'].get('cumulative_source_repositories', data['inventory']['inspected_repositories'] + data['inventory']['historical_cached_repositories']),
    }
    if status == published or status == candidate or published == candidate:
        raise ScanFailure('Outputs must not overlap candidate source')
    # Publish only after both new inputs validated. Keep immutable old evidence
    # when the semantic digest is unchanged; update the independent scan clock.
    if changed:
        write_atomically(published, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    write_atomically(status, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--published', type=Path, required=True)
    p.add_argument('--status', type=Path, required=True)
    p.add_argument('--run-id', default='')
    p.add_argument('--run-url', default='')
    a = p.parse_args(argv)
    try:
        receipt = publish(a.candidate, a.published, a.status, a.run_id, a.run_url)
    except (ValueError, OSError, ScanFailure) as e:
        print('SCAN_PUBLICATION_BLOCKED: ' + str(e)[:160], file=sys.stderr)
        return 2
    print(canonical(receipt))
    return 0


if __name__ == '__main__': raise SystemExit(main())
