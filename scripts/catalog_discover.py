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
from catalog_fetch import fetch

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
    parser.add_argument("--out", required=True, type=Path, help="run-scoped report path")
    parser.add_argument("--sources", default="ephe,app-market,mcp,oss-plugin", help="comma-separated adapters")
    parser.add_argument("--root", type=Path, default=ROOT, help="workshop root for the Ephe adapter")
    parser.add_argument("--no-archives", action="store_true", help="skip app-market archive downloads")
    args = parser.parse_args(argv)

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
