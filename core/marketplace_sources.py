"""Marketplace sources: bundled, a local file, or an HTTPS index.

A source is explicit. The bundled index is always present and cannot be
removed; an HTTPS source needs a signed index and a trusted key, and a refresh
is always the user's action. The last good index stays cached, so a broken
source degrades to "stale" instead of an empty catalog.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import guarded_fetch, marketplace_index, path_guard, plugin_signing
from core.plugin_store import config_root

SCHEMA_VERSION = 1
MAX_INDEX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_S = 10
REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_ID = "bundled"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class SourceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def sources_path() -> Path:
    return config_root() / "marketplaces.json"


def cache_dir() -> Path:
    return config_root() / "marketplace-cache"


def cache_path(source_id: str) -> Path:
    target = path_guard.child(cache_dir(), source_id, pattern=_ID, suffix=".json")
    if target is None:
        raise SourceError("invalid_source_id", source_id)
    return target


def bundled_index_path() -> Path:
    override = os.environ.get("EPHE_MARKETPLACE_INDEX")
    return Path(override) if override else REPO_ROOT / "marketplace" / "index.json"


def bundled_revocations_path() -> Path:
    override = os.environ.get("EPHE_MARKETPLACE_REVOCATIONS")
    return Path(override) if override else REPO_ROOT / "marketplace" / "revocations.json"


def _bundled_descriptions() -> dict[str, dict[str, str]]:
    path = Path(os.environ.get("EPHE_MARKETPLACE_METADATA") or REPO_ROOT / "ephe-marketplace.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, str]] = {}
    for entry in raw.get("plugins", []) if isinstance(raw, dict) else []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        i18n = entry.get("description_i18n")
        if isinstance(i18n, dict):
            out[str(entry["name"])] = {
                str(key): str(value) for key, value in i18n.items() if isinstance(value, str)
            }
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def bundled_source() -> dict[str, Any]:
    return {
        "id": BUNDLED_ID,
        "title": "Ephe bundled",
        "kind": "bundled",
        "url": str(bundled_index_path()),
        "trust": "bundled",
        "removable": False,
    }


def _normalize_source(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    source_id = str(raw.get("id") or "")
    kind = str(raw.get("kind") or "")
    if not _ID.match(source_id) or kind not in {"local", "https"}:
        return None
    url = str(raw.get("url") or "")
    if not url:
        return None
    return {
        "id": source_id,
        "title": str(raw.get("title") or source_id)[:80],
        "kind": kind,
        "url": url,
        "trust": "local" if kind == "local" else "community",
        "removable": True,
    }


def load_sources() -> dict[str, Any]:
    try:
        raw = json.loads(sources_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    sources: list[dict[str, Any]] = [bundled_source()]
    seen = {BUNDLED_ID}
    for item in raw.get("sources", []) if isinstance(raw, dict) else []:
        source = _normalize_source(item)
        if source is None or source["id"] in seen:
            continue
        seen.add(source["id"])
        sources.append(source)
    return {
        "version": SCHEMA_VERSION,
        "sources": sources,
        "last_read": raw.get("last_read") if isinstance(raw.get("last_read"), dict) else {},
        "last_error": raw.get("last_error") if isinstance(raw.get("last_error"), dict) else {},
    }


def save_sources(data: dict[str, Any]) -> None:
    target = sources_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _source_id(url: str) -> str:
    return "src-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _local_index(value: str) -> Path:
    # The owner names an index file on their own machine, so the path is theirs to choose:
    # the guards below keep it a JSON index and out of the credential stores and this app's
    # own state, which is all a source reader may ever be pointed at.
    # codeql[py/path-injection]
    candidate = Path(str(value or "")).expanduser()
    if not candidate.is_absolute():
        raise SourceError("invalid_url", "a local source needs an absolute path")
    resolved = candidate.resolve()
    if resolved.suffix != ".json":
        raise SourceError("invalid_url", "a local source needs a .json index")
    if path_guard.denied(resolved):
        raise SourceError("refused_path", "this file is not readable as a source")
    if not resolved.is_file():
        raise SourceError("not_found", "the index file does not exist")
    return resolved


def add_source(kind: str, title: str, url: str) -> dict[str, Any]:
    kind = str(kind or "").strip().lower()
    title = str(title or "").strip()
    if not title:
        raise SourceError("title_required", "a source needs a title")
    if kind == "local":
        path = _local_index(url)
        url = str(path)
        trust = "local"
    elif kind == "https":
        parsed = urllib.parse.urlsplit(str(url or ""))
        if parsed.scheme != "https" or not parsed.hostname:
            raise SourceError("invalid_url", "an HTTPS source needs an https URL")
        if parsed.username or parsed.password:
            raise SourceError("invalid_url", "credentials in a source URL are refused")
        if parsed.fragment:
            raise SourceError("invalid_url", "a fragment is not part of a source URL")
        url = urllib.parse.urlunsplit(parsed)
        trust = "community"
    else:
        raise SourceError("invalid_kind", "local or https expected")

    data = load_sources()
    source_id = _source_id(url)
    for existing in data["sources"]:
        if existing["id"] == source_id:
            return existing
    source = {
        "id": source_id,
        "title": title[:80],
        "kind": kind,
        "url": url,
        "trust": trust,
        "removable": True,
    }
    data["sources"].append(source)
    save_sources(data)
    return source


def remove_source(source_id: str) -> bool:
    if source_id == BUNDLED_ID:
        return False
    data = load_sources()
    before = len(data["sources"])
    data["sources"] = [s for s in data["sources"] if s["id"] != source_id]
    if len(data["sources"]) == before:
        return False
    data["last_read"].pop(source_id, None)
    data["last_error"].pop(source_id, None)
    save_sources(data)
    try:
        cache_path(source_id).unlink(missing_ok=True)
    except SourceError:
        return False
    return True


def _write_cache(source_id: str, index: dict[str, Any]) -> None:
    target = cache_path(source_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    body = json.dumps(
        {"source": source_id, "read_at": _now(), "index": index},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    os.chmod(target, 0o600)


def cached_index(source_id: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(cache_path(source_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, SourceError):
        return None
    index = raw.get("index") if isinstance(raw, dict) else None
    return index if isinstance(index, dict) else None


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceError("unreadable_index", str(exc)) from exc


def _fetch_https(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SourceError("invalid_url", "https expected")
    try:
        return guarded_fetch.fetch_https(
            url, max_bytes=MAX_INDEX_BYTES, timeout=FETCH_TIMEOUT_S
        )
    except guarded_fetch.GuardedFetchError as exc:
        raise SourceError(exc.code, exc.detail) from exc


def _revocations_for(source: dict[str, Any], raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        bundled = _read_json_file(bundled_revocations_path())
        if isinstance(bundled, dict) and isinstance(bundled.get("revoked"), list):
            items.extend(item for item in bundled["revoked"] if isinstance(item, dict))
    except SourceError:
        pass
    if source["kind"] in {"local", "bundled"}:
        local_path = Path(source["url"]).parent / "revocations.json"
        if local_path.is_file():
            try:
                local = _read_json_file(local_path)
            except SourceError:
                local = {}
            if isinstance(local, dict) and isinstance(local.get("revoked"), list):
                items.extend(item for item in local["revoked"] if isinstance(item, dict))
    elif isinstance(raw, dict) and isinstance(raw.get("revocations"), list):
        items.extend(item for item in raw["revocations"] if isinstance(item, dict))
    return items


def _fail(data: dict[str, Any], source: dict[str, Any], message: str) -> dict[str, Any]:
    data["last_error"][source["id"]] = message[:200]
    save_sources(data)
    return {
        "status": "error",
        "source": source,
        "error": message[:300],
        "index": cached_index(source["id"]),
    }


def read_source(
    source: dict[str, Any], fetcher: Callable[[str], bytes] | None = None
) -> dict[str, Any]:
    data = load_sources()
    kind = source.get("kind")
    try:
        if kind in {"local", "bundled"}:
            path = _local_index(str(source.get("url") or ""))
            raw = _read_json_file(path)
        elif kind == "https":
            url = str(source.get("url") or "")
            payload = (fetcher or _fetch_https)(url)
            if len(payload) > MAX_INDEX_BYTES:
                raise SourceError("too_large", "the index exceeds the size cap")
            try:
                raw = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise SourceError("unreadable_index", str(exc)) from exc
            cls = plugin_signing.FIRST_PARTY if kind == "bundled" else plugin_signing.USER
            ok, reason = marketplace_index.verify_index_signature(
                raw, plugin_signing.trusted_pems_for_class(cls),
            )
            if not ok:
                raise SourceError("index_untrusted", reason)
        else:
            raise SourceError("invalid_kind", str(kind))
        index = marketplace_index.validate_index(raw, source_kind=kind)
        if kind == "bundled":
            descriptions = _bundled_descriptions()
            for plugin in index["plugins"]:
                extra = descriptions.get(plugin["name"])
                if extra and isinstance(plugin["description"], dict):
                    plugin["description"].update(extra)
        marketplace_index.apply_revocations(index, _revocations_for(source, raw))
    except (SourceError, marketplace_index.IndexError) as exc:
        # The response and the persisted last_error carry the stable code only: a
        # source detail can name a local path or an exception, and a public surface
        # must not echo either. The full text stays in the audit trail.
        code = getattr(exc, "code", "source_error")
        return _fail(data, source, str(code))

    _write_cache(source["id"], index)
    data["last_read"][source["id"]] = _now()
    data["last_error"].pop(source["id"], None)
    save_sources(data)
    digest = hashlib.sha256(
        json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "status": "ok",
        "source": source,
        "index": index,
        "error": "",
        "digest": digest,
    }


def refresh_all(fetcher: Callable[[str], bytes] | None = None) -> list[dict[str, Any]]:
    return [read_source(source, fetcher=fetcher) for source in load_sources()["sources"]]
