# Review focus and History — regression proof

Date: 2026-11-08. Target baselines: `Repo_Dex/e9dda2b6` and `Westkitty_Atlas/240b8e31`.

## Confirmed failures before correction

1. Both Laboratory and Atlas recreated review cards after Investigate / Shelve / Reject, leaving `document.activeElement` at `<body>` after a decision and breaking sequential keyboard review.
2. Laboratory's "Open this review" History link reset its status filter but not pagination/search, leaving previously reviewed experiments beyond the first eight invisible.
3. Pagination buttons rebuilding the current result list lost their focus handoff (or focused an about-to-be-hidden control).

## Narrow repair

- Preserve focus by public experiment ID + control role/name after DOM replacement, including a filter fallback when an action removes the candidate from the current list.
- Make historical review navigation reveal the indexed experiment, clear conflicting filters, focus the destination and preserve source evidence.
- Give newly displayed review, capability and textual-index entries an intentional keyboard focus target on "Show more".
- Keep browser-private decision data in localStorage; no private choice or reason is added to a URL, public feed or repository.
- No change to Atlas Canvas renderer, public Github source scanner, graph import/export, scheduled workflow or source-evidence semantics.

## Verification commands

- `python3 -m unittest discover -s tests -q` in Repo_Dex (dependency-free Python suite).
- `python3 qa/replay_review_keyboard.py --atlas ../Westkitty_Atlas/index.html` in Repo_Dex after installing Python Playwright and Chromium; defaults to `docs/feed/latest.json` (or `--feed PATH`). Read-only; test-only in-memory feed responses, no external requests. Chromium executable may be set with `CHROMIUM_PATH`.
- `python3 qa/verify_ui.py` in Westkitty_Atlas.
- Legacy offline graph/import/export and live-feed simulation regression suites from the OMNI UX v3 release workbench, plus JavaScript syntax checks and narrow mobile viewport tests.

## Proof limits

Local Chromium exercises the exact source HTML but cannot navigate the hosted GitHub Pages URL in this sandbox. GitHub Actions deployment success proves publication, **not** physical mobile or screen-reader success. No automatic cross-device private decision synchronization is claimed.
