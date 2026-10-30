#!/usr/bin/env python3
"""Discover catalogue candidates from Ephe, two third-party plugin
marketplaces, and the MCP Registry. The adapters are named for the manifest shape
they read; the vendors they read stay in the cited URLs only.

Read-only by construction: every download is https-only and capped, archives
are read in memory and hashed against the index, and nothing is written except
the run-scoped report passed with --out. Review and publication are separate
steps; this script never publishes an entry.

    python3 scripts/catalog_discover.py --out out/catalog/<run>/candidates.json
    python3 scripts/catalog_discover.py --sources ephe --out /tmp/candidates.json

The candidate shape and the licence gates are documented in
docs/CATALOG_ACQUISITION_PLAN_2026-10-22.md.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.parse
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from catalog_fetch import fetch  # noqa: E402
from core.discover_intent import keys as intent_keys, tags_for  # noqa: E402

APP_MARKET_INDEX = "https://qoder.com/apphub/api/v1/marketplace/marketplace.json"
OSS_PLUGIN_INDEX = "https://raw.githubusercontent.com/anthropics/claude-code/main/.claude-plugin/marketplace.json"
MCP_REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
MANIFEST_BYTES = 256_000
ALLOWED_LICENSES = {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC"}
MCP_QUERIES = [
    "filesystem", "fetch", "git", "memory", "sequential thinking", "time",
    "everything", "github", "playwright", "context7", "chrome devtools",
    "postgres", "notion", "slack", "linear",
]
MIRROR_PAGE_LIMIT = 100
MIRROR_MAX_ENTRIES = 10_000

#: Facet buckets for the registry mirror; the map lives here so the snapshot
#: stays reproducible and the runtime serves pure data.
_CATEGORY_KEYWORDS = (
    ("files", ("filesystem", "file", "folder", "drive", "s3", "dropbox")),
    ("code", ("git", "github", "repository", "pull request", "code review")),
    ("database", ("postgres", "sql", "database", "redis", "vector", "mongo", "bigquery", "snowflake")),
    ("web", ("browser", "scraping", "search", "http", "url", "fetch")),
    ("memory", ("memory", "knowledge", "graph", "notes", "obsidian", "notion")),
    ("communication", ("slack", "email", "gmail", "telegram", "discord", "messaging")),
    ("security", ("security", "audit", "vulnerability", "auth", "identity")),
    ("cloud", ("aws", "azure", "gcp", "kubernetes", "docker", "serverless", "terraform")),
    ("media", ("image", "video", "audio", "music", "media")),
    ("productivity", ("calendar", "task", "todo", "project", "spreadsheet", "docs")),
    ("utility", ("time", "math", "calculator", "qr", "random", "weather")),
)


def _registry_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "other"


def _mirror_slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-") or "entry"


def _mirror_hint(server: dict[str, Any]) -> tuple[str, str]:
    """(install_hint, docs) for one registry server; the registry listing URL
    is the only locator the metadata guarantees."""
    quoted = urllib.parse.quote(str(server.get("name") or ""))
    docs = f"https://registry.modelcontextprotocol.io/v0/servers/{quoted}"
    for remote in server.get("remotes") or []:
        url = str(remote.get("url") or "")
        kind = str(remote.get("type") or "streamable-http")
        return f"{url} ({kind})", docs
    for package in server.get("packages") or []:
        transport = str((package.get("transport") or {}).get("type") or "stdio")
        command = str(package.get("runtimeHint") or package.get("identifier") or "")
        return f"{command} ({transport})", docs
    return "", docs


def _english_only(text: str) -> bool:
    # Reuse the language gate's marker regex: a line it flags as German is not committed.
    from language_inventory import WORD

    return WORD.search(text) is None


def _required_env(server: dict[str, Any]) -> list[dict[str, Any]]:
    """The names a publisher declares as required, as names only.

    Descriptions stay out: they are free prose, and what a surface needs is the
    variable name and whether its value is a secret."""
    found: dict[str, bool] = {}
    packages = server.get("packages")
    for package in packages if isinstance(packages, list) else []:
        if not isinstance(package, dict):
            continue
        variables = package.get("environmentVariables")
        for variable in variables if isinstance(variables, list) else []:
            if not isinstance(variable, dict) or not variable.get("isRequired"):
                continue
            name = str(variable.get("name") or "").strip()
            if not name or len(name) > 64:
                continue
            found.setdefault(name, bool(variable.get("isSecret")))
    return [{"name": name, "secret": secret} for name, secret in sorted(found.items())]


def mirror_registry() -> tuple[int, list[dict[str, Any]], list[str]]:
    """One full pass over the public registry: cursor pagination, dedupe by
    name (the newest version wins), ASCII-only descriptions, one entry per
    server. Returns (count, entries, errors). Metadata only — the registry
    data is CC0, its terms reserve nothing for read access."""
    entries: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    cursor = ""
    pages = 0
    while pages < 200:
        url = f"{MCP_REGISTRY}?limit={MIRROR_PAGE_LIMIT}"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
        try:
            payload = json.loads(fetch(url))
        except Exception as exc:  # noqa: BLE001 - a source failure is data
            errors.append(f"page {pages}: {type(exc).__name__}: {exc}")
            break
        servers = payload.get("servers") if isinstance(payload, dict) else None
        if not isinstance(servers, list):
            errors.append(f"page {pages}: no servers array")
            break
        for raw in servers:
            if not isinstance(raw, dict):
                continue
            server = raw.get("server")
            if not isinstance(server, dict):
                continue
            name = str(server.get("name") or "")
            description = " ".join(str(server.get("description") or "").split()).strip()
            if not name or not description or not description.isascii():
                continue
            hint, docs = _mirror_hint(server)
            if not all(
                _english_only(part)
                for part in (name, str(server.get("title") or ""), description, hint, docs)
                if part
            ):
                continue
            meta = raw.get("_meta")
            meta = meta if isinstance(meta, dict) else {}
            previous = entries.get(name)
            latest = bool(meta.get("isLatest"))
            if previous is not None and not latest:
                continue
            entries[name] = {
                "id": _mirror_slug(name),
                "name": str(server.get("title") or name),
                "description": description[:400],
                "category": _registry_category(description),
                "install_hint": hint,
                "docs": docs,
                "version": str(server.get("version") or ""),
                "published_at": str(meta.get("publishedAt") or ""),
                "source": "registry",
                "required_env": _required_env(server),
            }
            if len(entries) >= MIRROR_MAX_ENTRIES:
                break
        pages += 1
        cursor = ""
        if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
            cursor = str(payload["metadata"].get("nextCursor") or "")
        if not cursor or len(entries) >= MIRROR_MAX_ENTRIES:
            break
    return len(entries), sorted(entries.values(), key=lambda e: e["name"].lower()), errors


#: Well-known registry names the curated tier leads with; matched as substrings
#: against mirror names, so a pick that disappears from the registry stops
#: matching instead of resurrecting a dead entry.
PICKS = (
    "everything", "filesystem", "server-fetch", "server-git", "server-time",
    "server-memory", "sequential", "github", "gitlab", "slack", "notion",
    "linear", "postgres", "sqlite", "redis", "context7", "brave", "chrome",
    "playwright", "puppeteer", "firecrawl", "tavily", "figma", "sentry",
    "stripe", "supabase", "kubernetes", "docker", "terraform", "google-maps",
    "gmail", "jira", "confluence", "clickup", "airtable", "exa", "serper",
    "screenshot", "browserbase", "fetch", "memory", "search", "terminal",
    "obsidian", "notion", "youtube", "spotify", "weather", "math",
)
PICKS_PER_CATEGORY = 20


def curated_from_mirror(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tier the surface shows by default: named picks first, then the 30
    most recently published entries per category. Every row is a mirror entry
    plus its reason; nothing here is invented data."""
    picked: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = entry["name"].lower()
        if any(pick in name for pick in PICKS):
            picked[entry["id"]] = dict(entry, curated_reason="pick")
    by_category: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_category.setdefault(entry["category"], []).append(entry)
    for rows in by_category.values():
        rows.sort(key=lambda e: e.get("published_at") or "", reverse=True)
    for rows in by_category.values():
        for entry in rows[:PICKS_PER_CATEGORY]:
            row = picked.setdefault(entry["id"], dict(entry))
            row.setdefault("curated_reason", "recent")
    ordered = sorted(picked.values(), key=lambda e: (e["name"].lower(),))
    return ordered


def write_intent_index(entries: list[dict[str, Any]], target: Path) -> None:
    """The intent tags for the curated tier, computed once so a search is a lookup.

    Only the tags are precomputed; the ranking runs at read time in `core.discover_search`."""
    tagged = {}
    for entry in entries:
        entry_id = str(entry.get("id") or entry.get("name") or "")
        if not entry_id:
            continue
        tagged[entry_id] = tags_for(
            str(entry.get("name") or ""),
            str(entry.get("description") or ""),
            str(entry.get("category") or ""),
        )
    payload = {
        "format": 1,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "intents": list(intent_keys()),
        "entries": tagged,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"search-index: {len(tagged)} entry(ies) tagged into {target}")


def permissive(license_text: str) -> bool:
    return license_text.strip().upper().replace(" ", "-") in ALLOWED_LICENSES


def _candidate(
    *,
    kind: str,
    name: str,
    version: str,
    title: str,
    publisher: str,
    source: dict[str, Any],
    license_text: str,
    repository: str = "",
    components: list[str] | None = None,
    transport: str = "",
    env: list[dict[str, Any]] | None = None,
    compatibility: str = "requires_review",
    status: str = "discovered",
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "kind": kind,
        "name": name,
        "version": version,
        "title": title or name,
        "publisher": {"name": publisher},
        "source": source,
        "license": license_text,
        "repository": repository,
        "components": components or [],
        "transport": transport,
        "env": env or [],
        "auth": "none",
        "compatibility": compatibility,
        "status": status,
        "reason": reason,
    }
    if extra:
        row.update(extra)
    return row


def discover_ephe(root: Path) -> list[dict[str, Any]]:
    """First-party plugins and built-in skills, already owned by the project."""
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted((root / "plugins").glob("*/ephe-plugin.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        components = sorted((manifest.get("components") or {}).keys())
        rows.append(_candidate(
            kind="plugin",
            name=str(manifest.get("name") or manifest_path.parent.name),
            version=str(manifest.get("version") or ""),
            title=str(manifest.get("displayName") or manifest.get("name") or ""),
            publisher="Ephe",
            source={"type": "repo", "path": str(manifest_path.relative_to(root))},
            license_text="project",
            components=components,
            compatibility="native",
            status="published",
        ))
    pack_index = root / "skills" / "pack-index.json"
    try:
        packs = json.loads(pack_index.read_text(encoding="utf-8")).get("packs") or []
    except (OSError, ValueError):
        packs = []
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        rows.append(_candidate(
            kind="skill-pack",
            name=str(pack.get("id") or ""),
            version="1.0.0",
            title=str(pack.get("title") or pack.get("id") or ""),
            publisher="Ephe",
            source={"type": "repo", "path": str(pack_index.relative_to(root))},
            license_text="project",
            components=["skills"],
            compatibility="native",
            status="published",
            extra={"skills": [str(skill) for skill in pack.get("skills") or []]},
        ))
    return rows


def _app_market_manifest(archive: bytes) -> tuple[dict[str, Any], list[str]]:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = bundle.namelist()
        manifest_name = next(
            (name for name in names if name.endswith(".qoder-plugin/plugin.json")), ""
        )
        if not manifest_name:
            return {}, []
        info = bundle.getinfo(manifest_name)
        if info.file_size > MANIFEST_BYTES:
            raise ValueError("manifest above cap")
        manifest = json.loads(bundle.read(manifest_name))
        licenses = [
            name for name in names
            if Path(name).name.lower().startswith("license")
            and bundle.getinfo(name).file_size <= MANIFEST_BYTES
        ]
    return manifest, licenses


def discover_app_market(index: dict[str, Any], *, fetch_bytes: Callable[[str], bytes] = fetch,
                   read_archives: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for plugin in index.get("plugins", []):
        name = str(plugin.get("name") or "")
        source = plugin.get("source") if isinstance(plugin.get("source"), dict) else {}
        url = str(source.get("url") or "")
        wanted = str(source.get("sha256") or "")
        license_text = ""
        repository = ""
        components: list[str] = []
        compatibility = "requires_review"
        reason = ""
        archive_read = False
        extra: dict[str, Any] = {"archive_sha256_ok": None}
        if read_archives and url:
            try:
                archive = fetch_bytes(url)
                extra["archive_sha256_ok"] = hashlib.sha256(archive).hexdigest() == wanted
                if not extra["archive_sha256_ok"]:
                    reason = "archive hash does not match the index"
                else:
                    manifest, licenses = _app_market_manifest(archive)
                    archive_read = True
                    license_text = str(manifest.get("license") or "")
                    repository = str(manifest.get("repository") or "")
                    components = [
                        key for key in ("skills", "commands", "agents", "hooks", "mcpServers", "mcp")
                        if manifest.get(key)
                    ]
                    if manifest.get("canvas") or any(manifest.get(k) for k in ("ui", "workflows")):
                        compatibility = "app-market-native"
                    elif components and set(components) <= {"skills", "commands"}:
                        compatibility = "skills-only"
                    if not license_text and licenses:
                        reason = f"licence file present ({licenses[0]}); manifest field empty"
            except Exception as exc:  # noqa: BLE001 - a source failure is data
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                reason = "archive not read"
        status = "discovered"
        if reason.startswith("archive hash"):
            status = "refused_hash"
        elif not archive_read:
            reason = reason or "metadata only; archive not read"
        elif compatibility == "app-market-native":
            status = "incompatible"
        elif not permissive(license_text):
            status = "refused_license"
            reason = reason or "no permissive licence declared"
        rows.append(_candidate(
            kind="plugin",
            name=name,
            version=str(plugin.get("version") or ""),
            title=name,
            publisher=str((plugin.get("author") or {}).get("name") or ""),
            source={"type": "archive", "url": url, "sha256": wanted},
            license_text=license_text,
            repository=repository,
            components=components,
            compatibility=compatibility,
            status=status,
            reason=reason,
            extra=extra,
        ))
    return rows, errors


def _mcp_transport(server: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    remotes = server.get("remotes") or []
    if remotes:
        remote = remotes[0]
        return str(remote.get("type") or "streamable-http"), str(remote.get("url") or ""), []
    packages = server.get("packages") or []
    if packages:
        package = packages[0]
        transport = (package.get("transport") or {}).get("type") or "stdio"
        command = package.get("runtimeHint") or package.get("identifier") or ""
        return str(transport), str(command), list(package.get("environmentVariables") or [])
    return "", "", []


def discover_mcp(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One candidate per registry server, preferring the latest version."""
    latest: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for item in payload.get("servers", []):
            server = item.get("server") if isinstance(item, dict) else None
            if not isinstance(server, dict):
                continue
            meta = (item.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
            if meta.get("isLatest") is False:
                continue
            name = str(server.get("name") or "")
            if name:
                latest[name] = server
    rows: list[dict[str, Any]] = []
    for name, server in sorted(latest.items()):
        transport, endpoint, env = _mcp_transport(server)
        repository = server.get("repository") or {}
        rows.append(_candidate(
            kind="connector",
            name=name,
            version=str(server.get("version") or ""),
            title=str(server.get("title") or name),
            publisher=name.split("/", 1)[0],
            source={"type": "registry", "url": f"{MCP_REGISTRY}?search={urllib.parse.quote(name)}"},
            license_text="metadata-only",
            repository=str(repository.get("url") or "") if isinstance(repository, dict) else "",
            components=["mcp"],
            transport=transport,
            env=env,
            compatibility="native",
            status="discovered",
            reason="endpoint metadata only; auth and terms need review",
            extra={"endpoint": endpoint},
        ))
    return rows


def discover_oss_plugin(index: dict[str, Any], *, fetch_bytes: Callable[[str], bytes] = fetch,
                    repo: str = "anthropics/claude-code") -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for plugin in index.get("plugins", []):
        name = str(plugin.get("name") or "")
        source = plugin.get("source")
        manifest_url = ""
        if isinstance(source, str) and source.startswith("./"):
            manifest_url = (
                f"https://raw.githubusercontent.com/{repo}/main/"
                f"{source.removeprefix('./')}/.claude-plugin/plugin.json"
            )
        license_text = ""
        components: list[str] = []
        if manifest_url:
            try:
                manifest = json.loads(fetch_bytes(manifest_url))
                license_text = str(manifest.get("license") or "")
                components = [
                    key for key in ("skills", "commands", "agents", "hooks", "mcpServers")
                    if manifest.get(key)
                ]
            except Exception as exc:  # noqa: BLE001 - a source failure is data
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        rows.append(_candidate(
            kind="plugin",
            name=name,
            version=str(plugin.get("version") or ""),
            title=name,
            publisher=str((index.get("owner") or {}).get("name") or ""),
            source={"type": "repo", "url": manifest_url},
            license_text=license_text,
            components=components,
            compatibility="requires_review",
            status="discovered" if permissive(license_text) else "refused_license",
            reason="" if license_text else "no licence in the plugin manifest or repository",
        ))
    return rows, errors


def summarize(rows: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {"kind": {}, "status": {}, "license": {}}
    for row in rows:
        for bucket, value in (
            ("kind", row["kind"]), ("status", row["status"]), ("license", row["license"] or "none"),
        ):
            counts[bucket][value] = counts[bucket].get(value, 0) + 1
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates": rows,
        "counts": {"total": len(rows), **counts},
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="run-scoped report path")
    parser.add_argument("--sources", default="ephe,app-market,mcp,oss-plugin", help="comma-separated adapters")
    parser.add_argument("--root", type=Path, default=ROOT, help="workshop root for the Ephe adapter")
    parser.add_argument("--no-archives", action="store_true", help="skip app-market archive downloads")
    parser.add_argument(
        "--mirror", type=Path, metavar="OUT",
        help="write the full registry mirror to OUT and exit (metadata only)",
    )
    parser.add_argument(
        "--curated", type=Path, metavar="OUT",
        help="write the curated tier to OUT and exit (picks plus recent per category)",
    )
    parser.add_argument(
        "--search-index", type=Path, metavar="OUT",
        help="write the precomputed intent tags for the curated tier to OUT",
    )
    args = parser.parse_args(argv)

    if args.mirror:
        count, entries, errors = mirror_registry()
        payload = {
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": MCP_REGISTRY,
            "count": count,
            "entries": entries,
        }
        args.mirror.parent.mkdir(parents=True, exist_ok=True)
        args.mirror.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"mirror: {count} entry(ies) written to {args.mirror}")
        for error in errors:
            print(f"  error: {error}")
        return 1 if errors else 0

    if args.curated:
        # The curated tier derives from the committed mirror, so the run is
        # deterministic and offline; --mirror refreshes the mirror first.
        snapshot = ROOT / "marketplace" / "registry-snapshot.json"
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"curated: {snapshot} unreadable: {exc}")
            return 1
        count = int(payload.get("count") or 0)
        entries = payload.get("entries") if isinstance(payload, dict) else None
        curated = curated_from_mirror(entries if isinstance(entries, list) else [])
        payload = {
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": MCP_REGISTRY,
            "count": len(curated),
            "entries": curated,
        }
        args.curated.parent.mkdir(parents=True, exist_ok=True)
        args.curated.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"curated: {len(curated)} of {count} entry(ies) written to {args.curated}")
        if args.search_index:
            write_intent_index(curated, args.search_index)
        return 0

    if args.search_index:
        snapshot = ROOT / "marketplace" / "registry-curated.json"
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"search-index: {snapshot} unreadable: {exc}")
            return 1
        entries = payload.get("entries") if isinstance(payload, dict) else None
        write_intent_index(entries if isinstance(entries, list) else [], args.search_index)
        return 0

    if args.out is None:
        parser.error("--out is required unless --mirror is given")

    sources = [part.strip() for part in args.sources.split(",") if part.strip()]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    used: list[str] = []
    if "ephe" in sources:
        used.append("ephe")
        rows += discover_ephe(args.root)
    if "app-market" in sources:
        used.append("app-market")
        try:
            index = json.loads(fetch(APP_MARKET_INDEX))
            found, failures = discover_app_market(index, read_archives=not args.no_archives)
            rows += found
            errors += failures
        except Exception as exc:  # noqa: BLE001 - a source failure is data
            errors.append(f"app-market index: {type(exc).__name__}: {exc}")
    if "mcp" in sources:
        used.append("mcp")
        payloads = []
        for query in MCP_QUERIES:
            try:
                payloads.append(json.loads(fetch(
                    f"{MCP_REGISTRY}?search={urllib.parse.quote(query)}&limit=10"
                )))
            except Exception as exc:  # noqa: BLE001 - a source failure is data
                errors.append(f"mcp {query}: {type(exc).__name__}: {exc}")
        rows += discover_mcp(payloads)
    if "oss-plugin" in sources:
        used.append("oss-plugin")
        try:
            index = json.loads(fetch(OSS_PLUGIN_INDEX))
            found, failures = discover_oss_plugin(index)
            rows += found
            errors += failures
        except Exception as exc:  # noqa: BLE001 - a source failure is data
            errors.append(f"oss-plugin index: {type(exc).__name__}: {exc}")

    report = summarize(rows, errors)
    report["sources"] = used
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = report["counts"]
    print(f"catalog-discover: {counts['total']} candidate(s) from {', '.join(used)}")
    print(f"  kind: {counts['kind']}")
    print(f"  status: {counts['status']}")
    print(f"  errors: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
