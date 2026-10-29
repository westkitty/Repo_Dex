# Repo_Dex

A public, read-only GitHub portfolio observatory inspired by **Project Constellation**.

## Open

GitHub Pages (after Pages is activated): https://westkitty.github.io/Repo_Dex/

## Current build

- Observatory: scan a public GitHub account from the browser.
- Atlas: search the loaded repository inventory.
- Discovery candidates: shared keyword/domain mentions supported by links to repository metadata or README files.
- Ledger: Investigate / Shelf / Reject, stored in browser localStorage.
- Export: download JSON discovery results.
- Dark/light theme and mobile-friendly layout.

**Evidence restriction:** A shared term is only a hypothesis. Nothing here implies that code was inspected, executed, verified, safely reusable, or legally transferable. The prototype has no private-repository access, no credentials, no server, and no automatic source mutations. GitHub unauthenticated rate limits apply. Repository pagination is capped at 1,000 and README sampling at 40 recently updated repositories.

## Deployment

The included GitHub Actions workflow uploads the `docs/` directory. In **Settings → Pages**, choose **GitHub Actions** as the build/deploy source if it is not already selected. The workflow can be started from the Actions tab, or it runs on pushes to `main`.

## Roadmap

1. Evidence-preserving indexed repository inventory and source snapshots.
2. Capability genome and need extraction with exact commit, path, and symbol provenance.
3. Seven source-grounded discovery engines and skeptical challenger.
4. Controlled approval gates, bounded experiments, and long-lived decision memory.
5. Resumable incremental scanning and meaningful discovery digests.

See `PROJECT_SPEC.md` for the product mandate and limitations. This is a **thin public-facing prototype**, not the completed seven-engine system.
