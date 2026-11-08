# OMNI UX v3 — Repo_Dex Opportunity Laboratory

**Implemented:** November 8, 2026. **Source baseline:** `49e33a0a587fabc71b9868f707ebf2cfb11f700c`. This is a bounded UX implementation, not a new scanner or evidence source.

## What changed

- The Laboratory now uses task-first navigation: **Explore map → Discover → Review → Decisions**. The legacy Repo_Dex scanner remains linked and untouched.
- The original read-only published `repo-dex-feed/v1` and successful-scan receipt contracts remain authoritative. Scan freshness is shown only when the receipt matches both feed digest **and feed generated timestamp**.
- The formerly count-only `capability_genomes` surface is a searchable, paged, source-pinned declaration index with explicit evidence levels and freshness.
- A compact, paged review queue shows review rank, named beneficiary, evidence level and unverified status. Details retain source citations, two-project comparison, skeptical objections and falsifiable acceptance/rejection criteria.
- Review links point into the Atlas by **public opportunity ID only**, never by private decision or reason.
- Investigate / Shelve / Reject preserve the existing `repo-dex-decisions/v1` file and localStorage schema. Session-only **Undo** restores the prior decision, and the private decision history remains visible, exportable and importable.
- Buttons and navigation have keyboard focus indicators, at least 44 px-height primary touch targets and reduced-motion support. No framework, external UI dependency, background telemetry or network endpoint was introduced.

## Original product boundaries

The original Repo_Dex browser scanner (`docs/index.html`), source scanner (`scripts/scan_public.py`), publishing workflow, public evidence feed, private decision schema and import/export remain intact. Browsing the Laboratory never changes scanned repositories or writes user decisions to Pages. Decisions share browser storage with the Atlas **only on the same origin and browser profile**, and must be manually exported/imported for other devices.

The opportunity ordering is a bounded, deterministic evidence-readiness heuristic. **It is not a utility prediction or proof of compatible runtime interfaces.** Capabilities are declarations and textual evidence, not demonstrated working software.

## Evidence and verification

- Dependency-free scanner unit suite: `python3 -m unittest discover -s tests -q`.
- New Lab contract checks: `tests/test_omni_ux_contract.py`.
- Browser checks run from the release workbench using headless Chromium with mock-fed, source-pinned public fixture records. The hosted origin and localhost navigation are blocked by sandbox policy; browser QA therefore injects test-only feed transport and does not assert production network success.
- The original legacy browser scanner remains unchanged; direct deployed site and physical device tests must be confirmed after publication.

**Rollback:** revert only the Laboratory HTML, shared decision runtime and this documentation. Do not revert the scanner or public feed. The Atlas contains an inlined copy of the shared decision runtime and must be kept in sync with the same JavaScript contract.
