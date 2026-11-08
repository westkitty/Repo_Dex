# Operational State — Repo_Dex

Project ID: westkitty/Repo_Dex
Baseline: main fc13b146d61a89dacbafa0225abb7e6606a42bd5 (observed November 8, 2026)
Active candidate: COOL-20261108-ATLAS-05 / five bounded improvements

## Protected capabilities

- Public-only GitHub data. No inspection or mutation of private or analyzed repositories.
- Pinned evidence and historical freshness states are not claims of runtime interoperability.
- Legacy `docs/index.html` observatory remains accessible.
- Validated feed publication must fail closed. No publication of local user decisions.

## Verification states

- Verified locally: 35 Python tests and deterministic synthetic multi-scan progression.
- Verified locally: browser preview with intercepted prior real GitHub public feed for separate Laboratory interface.
- Implemented unverified: live GitHub API scan against the new scheduler, complete Pages deployment, cross-device storage; local-only decisions are intentional.

## Pending release gates

- Verify `main` baseline matches before writing and do not alter unrelated paths.
- Run GitHub Actions scanner and confirm the public feed, status receipt and Pages outputs.
- Treat failures as blocking; preserve previous verified feed and offline Atlas fallback.

## 2026-11-08 -- OMNI UX v3: task-centered interface

- Source baseline: Repo_Dex main `49e33a0a587fabc71b9868f707ebf2cfb11f700c`. Candidate changes are limited to `docs/laboratory.html`, `docs/shared-decisions.js`, `tests/test_omni_ux_contract.py`, documents and this ledger. The older `docs/index.html`, scanner scripts and publishing workflow remain authoritative and unchanged.
- Protected journeys: original public-only scanner and scheduled feed, commit-pinned citations, no automatic source mutation, local-only review decisions, portable ledger and original schema. Browser Lab now offers task navigation, paginated searchable capability records, compact review queue, evidence comparisons, a private decision history, Undo and a public-ID-only Atlas deep link.
- Verification: baseline scanner 35 tests; extended suite 40 tests. New Lab and cross-Atlas journeys exercised in headless Chromium with source-pinned feed fixture and controlled in-memory response. Static JavaScript syntax checks passed.
- Unknown: direct hosted-browser transport and live cross-origin navigation are blocked in this test runtime. Physical touch, screen-reader end-to-end testing and cross-device decision persistence are not verified. Same-origin storage is private; there is no automatic sync.
- Release gate: verify remote branch before pushing, prove workflow and Pages deployment separately and do not change unrelated repositories or claim actual integration tests from described source documents.
