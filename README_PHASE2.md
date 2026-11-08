# Repo_Dex / Constellation — five bounded improvements

Release candidate from the November 8, 2026 **COOL-20261108-ATLAS-05** review. The same public-only scanner remains the authoritative evidence producer. No scanned repository is ever modified.

1. **Progressive source frontier (C01).** The scanner still limits source inspections to 36 by default, but reserves one-third of the slots for never-inspected projects when there is an unreviewed backlog. Changed projects keep priority in the remaining slots. Previously inspected but unchanged sources are retained as historical, with cumulative source coverage shown separately from current scan coverage. Progress is not equivalent to a full source-code audit.
2. **Opportunity Laboratory (C02).** Published `capability_genomes` contain commit-pinned README import/export mentions and package manifest declarations only. Hypotheses receive an explicit skeptical review, named beneficiary, counterarguments, acceptance criterion and rank by evidence readiness rather than claimed commercial value. None is marked as proven usable.
3. **Two-clock truth (C03).** `scripts/publish_feed.py` writes `docs/feed/status.json` after each successful scan, even when `latest.json` is unchanged. The receipt distinguishes `last_successful_scan` from `feed_generated_at`, verifies the digest and records public coverage. Failed scans never advance success state. The workflow publishes both in the same Pages deployment. Use `docs/feed/status-schema-v1.json` for the receipt contract.
4. **Rename continuity (C04).** Repo records carry stable GitHub numeric IDs and bounded historical name aliases; the Atlas consumer preserves original curated ID and links across renames. New graph nodes are keyed by numeric ID to prevent rebirth under another name.
5. **Shared private discovery memory (C05).** `docs/laboratory.html` presents the published evidence feed, capability counts, skeptical findings, Investigate/Shelve/Reject decisions and manual export/import. `docs/shared-decisions.js` shares a schema and browser-local storage key with the Atlas. Both paths are served under the same `westkitty.github.io` origin. Decisions are never uploaded or included in public JSON; cross-device transfer requires an explicit file exchange.

## Review and test

```sh
python3 -m unittest discover -s tests -v
python3 scripts/scan_public.py --owner westkitty --previous docs/feed/latest.json --max-source-repos 36 --dry-run
```

The network scan command is read-only, may exhaust a GitHub Actions token budget and cannot run in this isolated container. The browser integration tests run in the corresponding Atlas release workbench with a real prior public snapshot and mocked fetch responses. Passing tests do not prove live GitHub Pages navigation or cross-device synchronization.

## Preservation and security

- Existing Repo_Dex homepage (`docs/index.html`) remains the legacy browser-scanner prototype; **do not confuse its local legacy decision store with the new shared ledger**. The [Opportunity Laboratory](https://westkitty.github.io/Repo_Dex/laboratory.html) is the shared review surface.
- Public feed stays `repo-dex-feed/v1`; the new fields are additive. Existing v1 consumers can ignore them safely.
- Browser decisions are same-origin **and per-browser/profile**. Do not place exported private decisions or local SQLite databases under `docs/`.
- No third-party library, cloud LLM, private repository, paid service or telemetry is introduced.
- Pages must be verified after an authorized push. The existing published feed is not overwritten by this local package until deployment.

## Recovery

If the new scanner fails validation, the prior public feed remains unchanged; the successful-scan receipt does not advance. If the Laboratory fails, the original `docs/index.html` remains available. If the Atlas feed or status endpoint is unavailable, its packaged data continues to work offline. Rollback the bounded commits, not scanned projects.
