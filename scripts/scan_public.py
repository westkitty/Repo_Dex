#!/usr/bin/env python3
"""Repo_Dex v1: read-only, evidence-preserving public GitHub portfolio scanner.

No non-stdlib dependencies. No repository writes. The public feed deliberately
excludes raw source text, repository secrets, private repository metadata and
unsupported claims about code reuse.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from contextlib import closing

SCHEMA = "repo-dex-feed/v1"
PARSER_VERSION = "1.0.0"
MAX_PAGES = 20
MAX_SOURCE_BYTES = 180_000
MAX_SOURCE_REPOS = 80
SOURCES = ("README.md", "package.json", "pyproject.toml", "Cargo.toml")
TECHNOLOGIES = (
    ("three", "Three.js"), ("@react-three/fiber", "React Three Fiber"),
    ("@react-three/drei", "Drei"), ("@react-three/rapier", "Rapier R3F"),
    ("react", "React"), ("vite", "Vite"), ("typescript", "TypeScript"),
    ("phaser", "Phaser"), ("dexie", "Dexie"), ("playwright", "Playwright"),
    ("vitest", "Vitest"), ("zod", "Zod"), ("fflate", "fflate"),
    ("sharp", "Sharp"), ("@vitejs/plugin-react", "Vite React plugin"),
)
FORMAT_NAMES = ("glb", "gltf", "obj", "stl", "svg", "json", "png", "webm", "mp4")
SAFE_OWNER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$")
SAFE_REPO = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class ScanFailure(RuntimeError):
    """No new snapshot may be published after this condition."""


class FatalScanFailure(ScanFailure):
    """Access or rate-limit failure: reject the entire run, not just one file."""


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def github_quote(s: str) -> str:
    return urllib.parse.quote(s, safe="")


class GitHubClient:
    """Fetch public GitHub REST JSON only. Credentials never leave headers."""

    def __init__(self, token: str | None = None, timeout: int = 20):
        self.token = token or None
        self.timeout = timeout
        self.requests = 0

    def get(self, path: str):
        if not path.startswith("/") or "//" in path or ".." in path or "#" in path:
            raise ScanFailure("Unsafe API path")
        url = "https://api.github.com" + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Repo-Dex-Public-Scanner/1.0",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        self.requests += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ScanFailure(f"Unexpected GitHub HTTP status {response.status}")
                payload = response.read(3_000_000)
                return json.loads(payload)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code in (401, 403, 429):
                # 403 may be a permission refusal, a secondary rate limit or an outage.
                raise FatalScanFailure(f"GitHub HTTP {exc.code}; credentials/rate limit/access must be checked") from None
            raise ScanFailure(f"GitHub HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ScanFailure("GitHub request failed or returned invalid JSON: " + str(exc)[:160]) from None


def _owner_repo(raw: dict, owner: str) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("owner"), dict) and str(raw["owner"].get("login", "")).casefold() == owner.casefold()


def public_inventory(api, owner: str) -> list[dict]:
    """Require a complete paginated inventory; never infer deletions from a partial run."""
    if not SAFE_OWNER.fullmatch(owner):
        raise ScanFailure("Invalid public GitHub owner")
    found = {}
    complete = False
    for page in range(1, MAX_PAGES + 1):
        rows = api.get(f"/users/{github_quote(owner)}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ScanFailure(f"Incomplete/invalid GitHub repository page {page}")
        for raw in rows:
            if not _owner_repo(raw, owner):
                continue
            if raw.get("private") is not False:
                continue
            if raw.get("visibility", "public") != "public":
                continue
            rid = raw.get("id")
            name = raw.get("name")
            if not isinstance(rid, int) or isinstance(rid, bool) or not isinstance(name, str) or not SAFE_REPO.fullmatch(name):
                raise ScanFailure("Public repository has invalid ID or name")
            base = {
                "id": rid,
                "name": name,
                "full_name": f"{owner}/{name}",
                "url": f"https://github.com/{owner}/{name}",
                "description": str(raw.get("description") or "")[:500],
                "default_branch": str(raw.get("default_branch") or "")[:150],
                "language": str(raw.get("language") or "")[:80],
                "topics": sorted({str(t)[:80] for t in (raw.get("topics") or []) if isinstance(t, str)})[:40],
                "archived": bool(raw.get("archived", False)),
                "fork": bool(raw.get("fork", False)),
                "pushed_at": str(raw.get("pushed_at") or "")[:40],
                "updated_at": str(raw.get("updated_at") or "")[:40],
            }
            base["metadata_sha256"] = sha256(canonical(base))
            if rid in found and found[rid]["name"] != name:
                raise ScanFailure("Conflicting identities in paginated inventory")
            found[rid] = base
        if len(rows) < 100:
            complete = True
            break
    if not complete:
        raise ScanFailure("Repository pagination cap reached; previous snapshot kept unchanged")
    # An empty account can be real, but for this known public portfolio it should
    # never quietly replace a healthy snapshot without operator intervention.
    return sorted(found.values(), key=lambda r: (r["name"].casefold(), r["id"]))


def read_previous(path: str | None, owner: str) -> dict | None:
    if not path or not Path(path).is_file():
        return None
    try:
        prior = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ScanFailure("Previous snapshot unreadable: " + str(exc)[:100]) from None
    if prior.get("schema") != SCHEMA or prior.get("owner", "").casefold() != owner.casefold():
        raise ScanFailure("Previous snapshot schema/owner mismatch; refusing unsafe diff")
    validate_feed(prior)
    return prior


def source_at(api, owner: str, name: str, commit: str, path: str) -> dict | None:
    if path not in SOURCES or not COMMIT_SHA.fullmatch(commit):
        raise ScanFailure("Invalid pinned source request")
    url = f"/repos/{github_quote(owner)}/{github_quote(name)}/contents/{path}?ref={commit}"
    item = api.get(url)
    if item is None:
        return None
    if not isinstance(item, dict) or item.get("type") != "file" or item.get("encoding") != "base64":
        raise ScanFailure("Unexpected source representation")
    encoded = item.get("content")
    if not isinstance(encoded, str) or len(encoded) > (MAX_SOURCE_BYTES * 2):
        raise ScanFailure("Source file too large or invalid")
    try:
        content = base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError):
        raise ScanFailure("Invalid source encoding") from None
    if len(content) > MAX_SOURCE_BYTES:
        raise ScanFailure("Source file above inspection cap")
    # We only emit bounded, structured information derived from source.
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ScanFailure("Source was not UTF-8") from None
    info = {
        "path": path,
        "commit_sha": commit,
        "blob_sha": str(item.get("sha") or "")[:40],
        "sha256": sha256(content),
        "url": f"https://github.com/{owner}/{name}/blob/{commit}/{path}",
        "level": "located" if path != "README.md" else "described",
    }
    if path == "package.json":
        try:
            data = json.loads(decoded)
            if not isinstance(data, dict):
                raise ValueError("package.json not an object")
            packages = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                obj = data.get(key, {})
                if isinstance(obj, dict):
                    for package in dict(TECHNOLOGIES):
                        if package in obj and isinstance(obj[package], str):
                            packages[package] = {"section": key}  # Never export raw dependency URLs or version strings; they may contain tokens.
            info["packages"] = packages
        except (ValueError, TypeError):
            info["parse_warning"] = "Manifest could not be parsed as JSON"
    elif path == "README.md":
        info["referenced_repositories"] = sorted(set(
            x.rstrip(".,);]") for x in re.findall(r"https?://github\.com/" + re.escape(owner) + r"/([a-zA-Z0-9_.-]+)", decoded, re.I)
            if SAFE_REPO.fullmatch(x.rstrip(".,);]"))
        ))[:35]
        info["formats"] = discover_formats(decoded)
    elif path in ("pyproject.toml", "Cargo.toml"):
        # Presence and digest are evidence. Deeper dependency parsers come later;
        # a TOML file alone does not prove an implementation capability.
        info["source_kind"] = "manifest-present"
    return info


def discover_formats(content: str) -> dict:
    """Textual import/export format mentions; not proof of working IO."""
    result = {}
    lower = content.lower()
    for fmt in FORMAT_NAMES:
        directions = []
        pattern = re.compile(r"\b(import|export|read|write|load|save)\b.{0,90}?\b" + re.escape(fmt) + r"\b", re.I | re.S)
        for match in pattern.finditer(lower):
            direction = match.group(1).lower()
            normalized = "import" if direction in ("import", "read", "load") else "export"
            directions.append(normalized)
            if len(directions) > 6:
                break
        if directions:
            result[fmt] = sorted(set(directions))
    return result


def inspect_selected(api, owner: str, repos: list[dict], prior: dict | None, max_source_repos: int) -> dict:
    old = {r["id"]: r for r in (prior or {}).get("repositories", []) if isinstance(r, dict)}
    eligible = [r for r in repos if not r["archived"] and not r["fork"] and r["default_branch"]]
    # Changed repos first, then most recently pushed; noninspected repos remain in inventory.
    eligible.sort(key=lambda r: (
        r["id"] in old and old[r["id"]].get("metadata_sha256") == r["metadata_sha256"],
        r.get("pushed_at", ""), r["name"].casefold()), reverse=False)
    # Use chronological sorting among changed/unchanged for incremental utility.
    changed = [r for r in eligible if r["id"] not in old or old[r["id"]].get("metadata_sha256") != r["metadata_sha256"]]
    unchanged = [r for r in eligible if r not in changed]
    changed.sort(key=lambda r: r["pushed_at"], reverse=True)
    unchanged.sort(key=lambda r: r["pushed_at"], reverse=True)
    selected = (changed + unchanged)[:max_source_repos]
    inspected = {}
    for repo in selected:
        name = repo["name"]
        try:
            branch = api.get(f"/repos/{github_quote(owner)}/{github_quote(name)}/branches/{github_quote(repo['default_branch'])}")
            if not isinstance(branch, dict) or not isinstance(branch.get("commit"), dict):
                raise ScanFailure("Branch unavailable")
            head = str(branch["commit"].get("sha") or "")
            if not COMMIT_SHA.fullmatch(head):
                raise ScanFailure("Unverified branch SHA")
            cache = old.get(repo["id"], {}).get("inspection") or {}
            if old.get(repo["id"], {}).get("name") == name and cache.get("commit_sha") == head and cache.get("state") == "inspected":
                inspection = cache
            else:
                sources = {}
                errs = []
                for path in SOURCES:
                    try:
                        item = source_at(api, owner, name, head, path)
                        if item:
                            sources[path] = item
                    except FatalScanFailure:
                        raise
                    except ScanFailure as exc:
                        # A single large/invalid source is a local limitation, not a
                        # reason to invent a relationship from it.
                        errs.append(f"{path}: {str(exc)[:100]}")
                inspection = {
                    "state": "inspected" if sources and not errs else "partial",
                    "commit_sha": head,
                    "sources": sources,
                    "errors": errs,
                    "inspected_at": utc_now(),
                }
            inspected[repo["id"]] = inspection
        except FatalScanFailure:
            raise
        except ScanFailure as exc:
            inspected[repo["id"]] = {"state": "error", "errors": [str(exc)[:140]]}
    return inspected


def evidence(repo: dict, item: dict, mechanism: str) -> dict:
    return {
        "repository_id": repo["id"], "repository": repo["name"],
        "path": item["path"], "commit_sha": item["commit_sha"],
        "blob_sha": item["blob_sha"], "sha256": item["sha256"],
        "url": item["url"], "level": item["level"],
        "mechanism": mechanism[:100],
    }


def _pair_id(kind: str, a: int, b: int, key: str) -> str:
    return sha256(f"{kind}:{min(a,b)}:{max(a,b)}:{key}")[:18]


def build_relationships(repos: list[dict]) -> tuple[list[dict], list[dict]]:
    sources = defaultdict(list)
    by_name = {r["name"].casefold(): r for r in repos}
    for r in repos:
        inspection = r.get("inspection") or {}
        if inspection.get("state") not in ("inspected", "partial", "cached"):
            continue
        files = inspection.get("sources", {})
        pkg = files.get("package.json")
        if pkg and "packages" in pkg:
            for name in pkg["packages"]:
                if name in dict(TECHNOLOGIES):
                    sources[name].append((r, pkg))
    edges, opportunities = [], []
    per_node = defaultdict(int)
    for tech, label in TECHNOLOGIES:
        rxs = sorted(sources.get(tech, []), key=lambda pair: pair[0]["name"].casefold())
        # Bound density; graph is a reader, not a complete dependency matrix.
        count = 0
        for i in range(len(rxs)):
            for j in range(i + 1, len(rxs)):
                a, af = rxs[i]
                b, bf = rxs[j]
                if per_node[a["id"]] >= 12 or per_node[b["id"]] >= 12 or count >= 15:
                    continue
                rid = _pair_id("shared-technology", a["id"], b["id"], tech)
                evid = [evidence(a, af, f"package {tech}"), evidence(b, bf, f"package {tech}")]
                edges.append({
                    "id": rid, "a": a["id"], "b": b["id"],
                    "type": "shared-technology", "status": "documented",
                    "evidence_level": "located", "mechanism": label,
                    "freshness": "historical" if (a["inspection"]["state"] == "cached" or b["inspection"]["state"] == "cached") else "sampled-head",
                    "explanation": f"Both pinned package.json manifests declare {tech}. This proves a shared package name, not code reuse, compatibility or a dependency between these projects. A historical-marked edge has at least one source whose current HEAD was not rechecked.",
                    "evidence": evid,
                })
                per_node[a["id"]] += 1
                per_node[b["id"]] += 1
                count += 1
    # A README link is documentary cross-reference only. Never call it a
    # runtime dependency or verified integration.
    seen = {e["id"] for e in edges}
    for r in repos:
        readme = (r.get("inspection") or {}).get("sources", {}).get("README.md")
        if not readme:
            continue
        for name in readme.get("referenced_repositories", []):
            other = by_name.get(name.casefold())
            if not other or other["id"] == r["id"]:
                continue
            rid = _pair_id("readme-reference", r["id"], other["id"], r["name"])
            if rid in seen:
                continue
            seen.add(rid)
            edges.append({
                "id": rid, "a": r["id"], "b": other["id"],
                "type": "readme-reference", "status": "documented",
                "evidence_level": "described", "mechanism": "explicit repository URL",
                "freshness": "historical" if r["inspection"]["state"] == "cached" else "sampled-head",
                "explanation": f"{r['name']} README links to {other['name']}. A documentation link does not establish a software dependency or approved integration.",
                "evidence": [evidence(r, readme, "explicit GitHub repository URL")],
            })
    # A very small, deterministic proposal lane: complementary, text-described
    # exchange formats. No implementation or version compatibility is assumed.
    format_index = defaultdict(lambda: {"import": [], "export": []})
    for r in repos:
        rd = (r.get("inspection") or {}).get("sources", {}).get("README.md")
        if not rd:
            continue
        for fmt, actions in rd.get("formats", {}).items():
            for action in actions:
                format_index[fmt][action].append((r, rd))
    for fmt, group in format_index.items():
        for exporter, ef in sorted(group["export"], key=lambda x:x[0]["name"]):
            for importer, inf in sorted(group["import"], key=lambda x:x[0]["name"]):
                if exporter["id"] == importer["id"]:
                    continue
                oid = _pair_id("format-experiment", exporter["id"], importer["id"], fmt)
                if any(x["id"] == oid for x in opportunities):
                    continue
                opportunities.append({
                    "id": oid, "status": "hypothesis", "evidence_level": "described",
                    "freshness": "historical" if (exporter["inspection"]["state"] == "cached" or importer["inspection"]["state"] == "cached") else "sampled-head",
                    "type": "data-exchange-opportunity", "format": fmt,
                    "exporter": exporter["id"], "importer": importer["id"],
                    "title": f"Test {fmt.upper()} exchange: {exporter['name']} → {importer['name']}",
                    "why": f"The two READMEs mention {fmt.upper()} export and import respectively. These are textual claims only. Actual input/output semantics, implementation, licensing and compatibility are unverified.",
                    "experiment": f"Export a non-sensitive example {fmt.upper()} from {exporter['name']}; import it into {importer['name']}; compare expected content and error handling without changing production data.",
                    "evidence": [evidence(exporter, ef, f"README mentions {fmt} export"), evidence(importer, inf, f"README mentions {fmt} import")],
                })
                if len(opportunities) >= 30:
                    break
            if len(opportunities) >= 30:
                break
        if len(opportunities) >= 30:
            break
    return sorted(edges, key=lambda x: x["id"]), sorted(opportunities, key=lambda x: x["id"])


def delta(old: dict | None, repos: list[dict]) -> dict:
    if not old:
        return {"kind": "baseline", "new": [], "removed": [], "renamed": [], "changed": [], "archived": [], "summary": "Initial public portfolio baseline, not a count of newly created projects."}
    prior = {r["id"]: r for r in old.get("repositories", [])}
    now = {r["id"]: r for r in repos}
    return {
        "kind": "incremental",
        "new": sorted((r["name"] for rid, r in now.items() if rid not in prior), key=str.casefold),
        "removed": sorted((r["name"] for rid, r in prior.items() if rid not in now), key=str.casefold),
        "renamed": [{"id": rid, "from": prior[rid]["name"], "to": r["name"]} for rid, r in sorted(now.items()) if rid in prior and prior[rid]["name"] != r["name"]],
        "changed": sorted((r["name"] for rid, r in now.items() if rid in prior and r["metadata_sha256"] != prior[rid].get("metadata_sha256")), key=str.casefold),
        "archived": sorted((r["name"] for rid, r in now.items() if rid in prior and r["archived"] and not prior[rid].get("archived")), key=str.casefold),
    }


def validate_feed(feed: dict) -> None:
    if feed.get("schema") != SCHEMA or not SAFE_OWNER.fullmatch(str(feed.get("owner", ""))):
        raise ScanFailure("Invalid feed header")
    repos = feed.get("repositories")
    if not isinstance(repos, list) or len({r["id"] for r in repos}) != len(repos):
        raise ScanFailure("Duplicate or invalid repository identity")
    if feed.get("inventory", {}).get("public_repositories") != len(repos):
        raise ScanFailure("Inconsistent public repository count")
    ids = {r["id"] for r in repos}
    for r in repos:
        if not isinstance(r.get("id"), int) or isinstance(r.get("id"), bool):
            raise ScanFailure("Repository ID invalid")
        if r.get("visibility") != "public" or not r["url"].startswith(f"https://github.com/{feed['owner']}/"):
            raise ScanFailure("Non-public or foreign repository leaked into feed")
        ins = r.get("inspection") or {}
        for path, item in ins.get("sources", {}).items():
            if path not in SOURCES or not COMMIT_SHA.fullmatch(str(item.get("commit_sha", ""))):
                raise ScanFailure("Unpinned source reference")
            if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
                raise ScanFailure("Invalid source digest")
            if not item["url"].startswith(f"https://github.com/{feed['owner']}/{r['name']}/blob/{item['commit_sha']}/"):
                raise ScanFailure("Cross-owner source reference")
    for e in feed.get("relationships", []):
        if e["a"] not in ids or e["b"] not in ids or e["status"] not in ("documented", "hypothesis"):
            raise ScanFailure("Invalid relationship endpoints/status")
        if e["status"] == "documented" and not e.get("evidence"):
            raise ScanFailure("Undocumented edge")
        for ev in e.get("evidence", []):
            if ev.get("repository_id") not in ids or not COMMIT_SHA.fullmatch(str(ev.get("commit_sha", ""))):
                raise ScanFailure("Relationship contains unverified evidence")
    for o in feed.get("opportunities", []):
        if o.get("status") != "hypothesis" or not o.get("evidence"):
            raise ScanFailure("Opportunity wrongly promoted or unsupported")
        for ev in o["evidence"]:
            if ev.get("repository_id") not in ids or not COMMIT_SHA.fullmatch(str(ev.get("commit_sha", ""))):
                raise ScanFailure("Opportunity evidence invalid")


def build_feed(api, owner: str, prior: dict | None = None, max_source_repos: int = 36, now: str | None = None) -> dict:
    if not isinstance(max_source_repos, int) or max_source_repos < 0 or max_source_repos > MAX_SOURCE_REPOS:
        raise ScanFailure("Invalid source sampling limit")
    inventory = public_inventory(api, owner)
    if prior and prior.get("repositories") and not inventory:
        raise ScanFailure("Empty scan following nonempty baseline; refusing deletion claims")
    if prior and len(prior.get("repositories", [])) >= 10:
        before = len(prior["repositories"])
        if len(inventory) < before * 0.8:
            raise ScanFailure("Public repository count dropped sharply; investigate pagination/account access before accepting removal claims")
    inspections = inspect_selected(api, owner, inventory, prior, max_source_repos)
    by_id = {r["id"]: r for r in (prior or {}).get("repositories", [])}
    repos = []
    for base in inventory:
        r = dict(base, visibility="public")
        if r["id"] in inspections:
            r["inspection"] = inspections[r["id"]]
        else:
            old_repo = by_id.get(r["id"], {})
            previous_inspection = old_repo.get("inspection") or {}
            # Preserve immutable source evidence only while the public metadata
            # stays unchanged; be explicit that HEAD was not re-checked.
            if (old_repo.get("name") == r["name"] and
                old_repo.get("metadata_sha256") == r["metadata_sha256"] and
                previous_inspection.get("state") in ("inspected", "partial", "cached") and
                previous_inspection.get("sources")):
                r["inspection"] = dict(previous_inspection, state="cached", current_head_verified=False)
            else:
                r["inspection"] = {
                    "state": "not-selected",
                    "historical_commit_sha": previous_inspection.get("commit_sha", ""),
                }
        repos.append(r)
    relations, opportunities = build_relationships(repos)
    d = delta(prior, repos)
    observations = [{"kind": "baseline", "severity": "info", "message": d["summary"]}] if d["kind"] == "baseline" else []
    for key, label in (("new", "New public repositories"), ("removed", "No longer in public inventory"), ("changed", "Repository metadata or push state changed"), ("archived", "Newly archived")):
        if d.get(key):
            observations.append({"kind": key, "severity": "review" if key == "removed" else "info", "message": label, "repositories": d[key]})
    if d.get("renamed"):
        observations.append({"kind": "renamed", "severity": "info", "message": "Repository identities retained across name changes", "repositories": d["renamed"]})
    inspected = sum(r["inspection"]["state"] in ("inspected", "partial") for r in repos)
    cached = sum(r["inspection"]["state"] == "cached" for r in repos)
    source_errors = [{"repository": r["name"], "errors": r["inspection"].get("errors", [])} for r in repos if r["inspection"].get("errors")]
    feed = {
        "schema": SCHEMA,
        "parser_version": PARSER_VERSION,
        "owner": owner,
        "generated_at": now or utc_now(),
        "source": {"provider": "github-public-rest", "base": f"https://github.com/{owner}", "visibility": "public-only", "read_only": True},
        "inventory": {"public_repositories": len(repos), "complete": True, "inspected_repositories": inspected, "historical_cached_repositories": cached, "sampling_limit": max_source_repos, "source_errors": source_errors},
        "delta": d,
        "repositories": repos,
        "relationships": relations,
        "opportunities": opportunities,
        "observations": observations,
        "evidence_ladder": ["described", "located", "exercised", "verified", "transferred"],
        "limitations": [
            "Only public repository metadata and explicitly inspected, commit-pinned source files are used.",
            "Uninspected repositories have no new source-grounded relationships; cached evidence remains pinned to historical commits and its current HEAD is not rechecked.",
            "Descriptions, language tags and matching packages are not evidence of reusable code or a working integration.",
            "Hypothetical opportunities require manual experimentation; rejection decisions are user-owned.",
        ],
    }
    # A content digest ignores scan time so unchanged snapshots can be reused.
    # Inspections' timestamps are also excluded from the comparison digest.
    stable = json.loads(canonical(feed))
    stable.pop("generated_at")
    for repo in stable["repositories"]:
        repo.get("inspection", {}).pop("inspected_at", None)
    feed["content_sha256"] = sha256(canonical(stable))
    validate_feed(feed)
    return feed


def write_atomically(path: Path, text_value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".repo-dex-", delete=False) as out:
        out.write(text_value)
        out.flush()
        os.fsync(out.fileno())
        temp = Path(out.name)
    temp.replace(path)


def record_sqlite(path: Path, feed: dict) -> None:
    """Local append-only evidence ledger; never placed in the public Pages tree.

    The full immutable snapshot is the recovery authority; the auxiliary index
    tables make source changes queryable without replacing prior history.
    """
    validate_feed(feed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=15)) as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ScanFailure("Unsupported Repo_Dex SQLite database version")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
          digest TEXT PRIMARY KEY, owner TEXT NOT NULL, first_seen TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_runs (
          scan_key TEXT PRIMARY KEY, digest TEXT NOT NULL REFERENCES snapshots(digest),
          generated_at TEXT NOT NULL, public_count INTEGER NOT NULL,
          inspected_count INTEGER NOT NULL, source_error_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS repository_snapshots (
          digest TEXT NOT NULL REFERENCES snapshots(digest), repository_id INTEGER NOT NULL,
          name TEXT NOT NULL, metadata_sha256 TEXT NOT NULL,
          inspection_state TEXT NOT NULL, pinned_commit TEXT NOT NULL,
          PRIMARY KEY (digest, repository_id)
        );
        CREATE TABLE IF NOT EXISTS observed_evidence (
          digest TEXT NOT NULL REFERENCES snapshots(digest), evidence_key TEXT NOT NULL,
          repository_id INTEGER NOT NULL, path TEXT NOT NULL,
          commit_sha TEXT NOT NULL, blob_sha TEXT NOT NULL, sha256 TEXT NOT NULL,
          PRIMARY KEY (digest, evidence_key)
        );
        CREATE TABLE IF NOT EXISTS discovery_snapshots (
          digest TEXT NOT NULL REFERENCES snapshots(digest), finding_id TEXT NOT NULL,
          category TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
          PRIMARY KEY (digest, finding_id)
        );
        """)
        db.execute("PRAGMA user_version=1")
        digest = feed["content_sha256"]
        serialized = canonical(feed)
        # No update to existing snapshot payload, even on identical rescans.
        db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?)", (digest, feed["owner"], feed["generated_at"], serialized))
        scan_key = sha256(feed["generated_at"] + ":" + digest)
        db.execute("INSERT OR IGNORE INTO scan_runs VALUES (?,?,?,?,?,?)", (
          scan_key, digest, feed["generated_at"], len(feed["repositories"]),
          feed["inventory"]["inspected_repositories"], len(feed["inventory"]["source_errors"]),
        ))
        for r in feed["repositories"]:
            ins = r["inspection"]
            db.execute("INSERT OR IGNORE INTO repository_snapshots VALUES (?,?,?,?,?,?)", (
                digest, r["id"], r["name"], r["metadata_sha256"], ins["state"], ins.get("commit_sha", ""),
            ))
            for source in ins.get("sources", {}).values():
                key = sha256(f"{r['id']}:{source['path']}:{source['commit_sha']}")
                db.execute("INSERT OR IGNORE INTO observed_evidence VALUES (?,?,?,?,?,?,?)", (
                    digest, key, r["id"], source["path"], source["commit_sha"], source["blob_sha"], source["sha256"],
                ))
        for kind, collection in (("relationship", feed["relationships"]), ("opportunity", feed["opportunities"])):
            for finding in collection:
                db.execute("INSERT OR IGNORE INTO discovery_snapshots VALUES (?,?,?,?,?)", (
                    digest, finding["id"], kind, finding["status"], canonical(finding),
                ))
        db.commit()


def cli(argv=None, api=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", default="westkitty", help="Public GitHub login to scan")
    p.add_argument("--previous", help="Prior validated v1 JSON snapshot")
    p.add_argument("--output", help="Write latest feed JSON here")
    p.add_argument("--snapshot-dir", help="Preserve immutable digest-named snapshots")
    p.add_argument("--database", help="Optional private/local append-only SQLite history")
    p.add_argument("--max-source-repos", type=int, default=36)
    p.add_argument("--dry-run", action="store_true", help="Validate and print metrics without writing")
    ns = p.parse_args(argv)
    try:
        prev = read_previous(ns.previous, ns.owner)
        feed = build_feed(api or GitHubClient(os.environ.get("GITHUB_TOKEN")), ns.owner, prev, ns.max_source_repos)
        data = json.dumps(feed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if not ns.dry_run:
            if ns.database:
                record_sqlite(Path(ns.database), feed)
            if ns.snapshot_dir:
                directory = Path(ns.snapshot_dir)
                immutable = directory / (feed["content_sha256"][:20] + ".json")
                if immutable.exists() and immutable.read_text(encoding="utf-8") != data:
                    # Same material snapshot with a different scan timestamp:
                    # the earlier immutable file is correct and should stay unchanged.
                    pass
                elif not immutable.exists():
                    write_atomically(immutable, data)
            if ns.output:
                write_atomically(Path(ns.output), data)
        print(json.dumps({"schema": feed["schema"], "owner": ns.owner, "public_repositories": feed["inventory"]["public_repositories"], "inspected": feed["inventory"]["inspected_repositories"], "relationships": len(feed["relationships"]), "hypotheses": len(feed["opportunities"]), "content_sha256": feed["content_sha256"], "dry_run": ns.dry_run}, sort_keys=True))
        return 0
    except (ScanFailure, OSError, sqlite3.Error) as exc:
        print("REPO_DEX_SCAN_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
