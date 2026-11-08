# Repo_Dex → Project Constellation: phase 1 scanner

**Status:** Tested locally against offline fixtures. No live GitHub API scan, repository write, scheduled job activation or Pages deployment is claimed. This is a **file overlay** for the existing `westkitty/Repo_Dex` repository, not a replacement for its browser prototype. Files in this packet are new paths; no existing file must be overwritten.

## Purpose

Produce a conservative, versioned public GitHub portfolio feed that Project Constellation can eventually consume. It lists all returned public repositories, inspects at most a bounded set of current source heads, anchors its evidence to commit/blob hashes and keeps possible integrations explicitly hypothetical.

## Overlay installation (after approval)

Place these files in the existing `Repo_Dex` repository at the same relative paths:

| File | Role |
| --- | --- |
| `scripts/scan_public.py` | Python standard-library CLI, scanner and optional SQLite evidence ledger |
| `tests/test_scan_public.py` | Offline unit tests; no network calls |
| `docs/feed/schema-v1.json` | v1 contract for consumers |
| `.github/workflows/public-scan-preview.yml` | Read-only scheduled/manual *preview* scan; Actions artifact only |

**Do not delete** `docs/index.html`, existing `README.md`, `PROJECT_SPEC.md`, or `.github/workflows/pages.yml`. Existing Pages behavior is untouched. The preview workflow does **not** push commits, publish new Pages data or modify any analyzed repository.

## Commands

```sh
python3 -m unittest discover -s tests -v
GITHUB_TOKEN="$GITHUB_TOKEN" python3 scripts/scan_public.py --owner westkitty --max-source-repos 36 --dry-run
GITHUB_TOKEN="$GITHUB_TOKEN" python3 scripts/scan_public.py --owner westkitty --max-source-repos 36 --previous docs/feed/latest.json --output docs/feed/latest.json --database "${TMPDIR:-/tmp}/repo-dex-history.sqlite" --snapshot-dir "${TMPDIR:-/tmp}/repo-dex-history"
```

Omit `--previous` on the very first run when `docs/feed/latest.json` does not yet exist. For local use, a GitHub token is optional, but anonymous API quota may be insufficient for source inspection. Never put a token in the feed or commit it to Git. Python 3.11+ only; no pip install needed. `--database` writes local SQLite snapshots, scan records, repository identities and pinned evidence with append-only digest history; keep this file outside public `docs/`. The output is the first fully validated read-only *public* feed candidate. Review it before publishing.

## Contract and semantics

- `schema`: `repo-dex-feed/v1`; `content_sha256`: digest of canonical scan substance excluding timestamps.
- `repositories`: one identity per numeric GitHub repository ID (allows rename detection); includes **only public** metadata. Repo descriptions and topics are public and not independently verified.
- `inspection`: `inspected`, `partial`, `error`, `cached`, or `not-selected`; pin all evidence to a commit SHA and source blob/digest. Raw README content and dependency version strings are never included in the public feed. Cached evidence is pinned but marked historical until HEAD is checked again.
- `relationships`: `documented` is limited to actual source claims, such as two package manifests naming the same package or a README explicitly linking another repository. It does **not** prove shared code, runtime dependencies, successful integration or transitive imports.
- `opportunities`: all `hypothesis`. Format exchange proposals are only tests to consider, not production-ready integrations.
- `delta`: `baseline` on first run; later diffs use stable repository IDs. A scan aborted by a rate limit or incomplete pagination never writes the output file. Archivals/renames are not confused with deletions.
- `observations`: facts about source inventory changes and explicit limitations. The separate skeptical decision ledger remains user-owned and is not modified by this scanner.

## Data coverage and cost

The metadata inventory paginates up to 2,000 public repositories (20 pages × 100); exceeding that limit blocks publication. Source inspection is capped at 36 repositories by default and at 80 maximum, chosen from changed/recent projects. It attempts `README.md`, `package.json`, `pyproject.toml`, and `Cargo.toml` at their pinned commits. Source errors remain visible and cannot be upgraded into affirmative evidence. This is **selective source inspection**, not a code audit of every repository. The run is read-only, and does not send source content to an LLM or paid service.

## Artifact vs live release

The optional scheduled workflow creates a **downloadable GitHub Actions artifact**; it does **not** publish it into Pages or Project Constellation. That deliberate boundary prevents a preview scan from silently changing a public product. A later approved phase can validate the feed against the schema, compare to the last accepted snapshot, publish it to the Repo_Dex public feed, refresh an embedded offline Constellation snapshot and deploy Pages in the **same workflow** (avoiding the `GITHUB_TOKEN` re-trigger trap).

## Next phase acceptance

- A real authenticated read-only GitHub scan successfully enumerates the public account and emits the v1 schema; no private repository names or source bodies appear.
- A second run using a saved prior feed detects actual new/changed/renamed/archived public repositories without inventing losses from partial pagination.
- The source evidence links resolve to pinned public file revisions.
- A sample Constellation adapter loads this feed without downgrading user-imported data, interrupting camera controls or exceeding the 30% permanent chrome budget.
- Offline fallback displays an accurate snapshot date. No changes are made to other repositories.

## Rollback

Because the overlay only adds new paths, removing those files fully reverses the feature without changing the existing Repo_Dex site or its behavior. If a future workflow is deployed, disable it before deleting its source files.
