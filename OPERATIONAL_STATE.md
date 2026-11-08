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
