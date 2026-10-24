"""The v2 marketplace index: validate one document, resolve one version.

The index is user-readable evidence, not an authority: the installer still
verifies the artifact hash and its signature. This module decides which exact,
compatible, non-revoked version a name refers to and refuses a malformed index
as a whole, naming the field that failed.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from typing import Any, NoReturn

from core import plugin_signing

FORMAT = 2
TRUST_CLASSES = ("official", "verified", "community", "local", "bundled")
SIGNED_TRUST = ("official", "verified", "community")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class IndexError(ValueError):
    def __init__(self, code: str, path: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.path = path
        self.detail = detail


def _fail(code: str, path: str, detail: str = "") -> NoReturn:
    raise IndexError(code, path, detail)


def parse_semver(value: Any) -> tuple[int, int, int] | None:
    match = _SEMVER.match(str(value or ""))
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _at_least(version: tuple[int, int, int], floor: tuple[int, int, int]) -> bool:
    return version >= floor


def compatible(range_text: str, version: str) -> bool:
    """A small AND-range parser; an unsupported range is incompatible."""
    current = parse_semver(version)
    if current is None:
        return False
    spec = str(range_text or "").strip()
    if spec == "*":
        return True
    predicates = [part for part in re.split(r"[\s,]+", spec) if part]
    if not predicates:
        return False
    for predicate in predicates:
        if predicate.startswith(">="):
            floor = parse_semver(predicate[2:])
            ok = floor is not None and current >= floor
        elif predicate.startswith("<="):
            ceil = parse_semver(predicate[2:])
            ok = ceil is not None and current <= ceil
        elif predicate.startswith(">"):
            floor = parse_semver(predicate[1:])
            ok = floor is not None and current > floor
        elif predicate.startswith("<"):
            ceil = parse_semver(predicate[1:])
            ok = ceil is not None and current < ceil
        elif predicate.startswith("^"):
            floor = parse_semver(predicate[1:])
            if floor is None:
                return False
            upper = (floor[0] + 1, 0, 0) if floor[0] else (0, floor[1] + 1, 0)
            ok = floor <= current < upper
        elif predicate.startswith("~"):
            floor = parse_semver(predicate[1:])
            if floor is None:
                return False
            upper = (floor[0], floor[1] + 1, 0)
            ok = floor <= current < upper
        elif predicate.startswith("=="):
            exact = parse_semver(predicate[2:])
            ok = exact is not None and current == exact
        elif predicate.startswith("="):
            exact = parse_semver(predicate[1:])
            ok = exact is not None and current == exact
        else:
            exact = parse_semver(predicate)
            ok = exact is not None and current == exact
        if not ok:
            return False
    return True


def _description(value: Any, path: str) -> str | dict[str, str]:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict) and isinstance(value.get("en"), str) and value["en"].strip():
        return {str(key): str(text) for key, text in value.items() if isinstance(text, str)}
    _fail("description", path)


def _version_entry(raw: Any, path: str, trust: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail("bad_version_entry", path)
    number = str(raw.get("version") or "")
    if parse_semver(number) is None:
        _fail("bad_version", f"{path}.version")
    source = raw.get("source")
    if not isinstance(source, dict) or source.get("type") != "zip":
        _fail("unsupported_source", f"{path}.source")
    url = str(source.get("url") or "")
    if not url:
        _fail("missing_url", f"{path}.source.url")
    if "latest" in url.lower():
        _fail("mutable_url", f"{path}.source.url", "the artifact URL names a moving target")
    digest = str(source.get("sha256") or "").lower()
    if not _HEX64.match(digest):
        _fail("missing_hash", f"{path}.source.sha256")
    signature = source.get("signature")
    if signature is not None and not isinstance(signature, dict):
        _fail("bad_signature", f"{path}.source.signature")
    if trust in SIGNED_TRUST and not isinstance(signature, dict):
        _fail("signature_required", f"{path}.source.signature")
    engines = raw.get("engines")
    if not isinstance(engines, dict) or not isinstance(engines.get("ephe"), str):
        _fail("missing_engine", f"{path}.engines.ephe")
    components = raw.get("components", [])
    if not isinstance(components, list) or any(not isinstance(c, str) for c in components):
        _fail("bad_components", f"{path}.components")
    return {
        "version": number,
        "publishTimestamp": int(raw.get("publishTimestamp") or 0),
        "source": {
            "type": "zip",
            "url": url,
            "sha256": digest,
            **({"signature": signature} if isinstance(signature, dict) else {}),
        },
        "engines": {"ephe": str(engines["ephe"])},
        "permissions": raw.get("permissions") if isinstance(raw.get("permissions"), dict) else {},
        "components": list(components),
        "changelog": raw.get("changelog") if isinstance(raw.get("changelog"), str) else "",
        "revoked": False,
    }


def validate_index(raw: Any, *, source_kind: str = "bundled") -> dict[str, Any]:
    """Validate the whole document; one bad field refuses the index by path."""
    if not isinstance(raw, dict):
        _fail("format", "index", "an object is expected")
    if raw.get("format") != FORMAT:
        _fail("format", "format", f"format {FORMAT} expected")
    name = str(raw.get("name") or "").strip()
    if not name:
        _fail("name", "name")
    owner = raw.get("owner")
    if not isinstance(owner, dict) or not str(owner.get("name") or "").strip():
        _fail("owner", "owner.name")
    plugins = raw.get("plugins")
    if not isinstance(plugins, list):
        _fail("plugins", "plugins")

    seen: set[str] = set()
    out_plugins: list[dict[str, Any]] = []
    default_trust = "bundled" if source_kind == "bundled" else "community"
    for index, plugin in enumerate(plugins):
        path = f"plugins[{index}]"
        if not isinstance(plugin, dict):
            _fail("plugin", path)
        plugin_name = str(plugin.get("name") or "")
        if not _SLUG.match(plugin_name):
            _fail("bad_name", f"{path}.name")
        if plugin_name in seen:
            _fail("duplicate_name", f"{path}.name", plugin_name)
        seen.add(plugin_name)
        publisher = plugin.get("publisher")
        if not isinstance(publisher, dict) or not str(publisher.get("name") or "").strip():
            _fail("publisher", f"{path}.publisher.name")
        trust = str(plugin.get("trust") or default_trust).strip().lower()
        if trust not in TRUST_CLASSES:
            _fail("trust", f"{path}.trust", trust)
        kind = str(plugin.get("kind") or "plugin").strip().lower()
        if kind not in {"plugin", "skill-pack"}:
            _fail("kind", f"{path}.kind", kind)
        quality = str(
            plugin.get("quality_label") or ("bundled" if kind == "skill-pack" else "plugin")
        ).strip().lower()
        if quality not in {"plugin", "capability-preset", "bundled"}:
            _fail("quality_label", f"{path}.quality_label", quality)
        measurement = plugin.get("measurement")
        if measurement is not None and not isinstance(measurement, dict):
            _fail("measurement", f"{path}.measurement")
        tiers = plugin.get("tiers")
        if tiers is not None and (
            not isinstance(tiers, dict)
            or any(type(value) is not int or value < 0 for value in tiers.values())
        ):
            _fail("tiers", f"{path}.tiers")
        versions_raw = plugin.get("versions")
        if not isinstance(versions_raw, list) or not versions_raw:
            _fail("versions", f"{path}.versions")
        versions: list[dict[str, Any]] = []
        numbers: set[str] = set()
        for position, entry in enumerate(versions_raw):
            parsed = _version_entry(entry, f"{path}.versions[{position}]", trust)
            if parsed["version"] in numbers:
                _fail(
                    "duplicate_version",
                    f"{path}.versions[{position}].version",
                    parsed["version"],
                )
            numbers.add(parsed["version"])
            versions.append(parsed)
        categories = plugin.get("categories", [])
        if not isinstance(categories, list) or any(not isinstance(c, str) for c in categories):
            _fail("categories", f"{path}.categories")
        out_plugins.append(
            {
                "name": plugin_name,
                "displayName": str(plugin.get("displayName") or plugin_name),
                "description": _description(plugin.get("description"), f"{path}.description"),
                "publisher": {
                    "name": str(publisher["name"]),
                    "verified": bool(publisher.get("verified", False)),
                },
                "trust": trust,
                "kind": kind,
                "quality_label": quality,
                "provenance": str(plugin.get("provenance") or "first-party"),
                "categories": list(categories),
                "icon": plugin.get("icon") if isinstance(plugin.get("icon"), dict) else {},
                "versions": versions,
                **({"measurement": measurement} if measurement is not None else {}),
                **({"tiers": tiers} if tiers is not None else {}),
            }
        )
    return {
        "format": FORMAT,
        "name": name,
        "owner": {"name": str(owner["name"])},
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
        "plugins": out_plugins,
    }


def _find(index: dict[str, Any], name: str) -> dict[str, Any]:
    for plugin in index.get("plugins", []):
        if plugin.get("name") == name:
            return plugin
    _fail("unknown_plugin", "plugins", name)


def resolve_version(
    index: dict[str, Any],
    name: str,
    version: str = "",
    *,
    ephe_version: str = "0.0.0",
) -> dict[str, Any]:
    plugin = _find(index, name)
    all_versions = plugin["versions"]
    if version:
        for entry in all_versions:
            if entry["version"] == version and entry.get("revoked"):
                _fail(
                    "revoked",
                    f"plugins.{name}.versions[{version}]",
                    str(entry.get("revocation_reason") or "revoked"),
                )
    versions = [entry for entry in all_versions if not entry.get("revoked")]
    if not versions:
        _fail("revoked", f"plugins.{name}.versions", "every version is revoked")
    if version:
        for entry in versions:
            if entry["version"] == version:
                if not compatible(entry["engines"]["ephe"], ephe_version):
                    _fail(
                        "incompatible",
                        f"plugins.{name}.versions[{version}]",
                        f"needs Ephe {entry['engines']['ephe']}, this is {ephe_version}",
                    )
                return {**entry, "plugin": plugin}
        _fail("unknown_version", f"plugins.{name}.versions", version)
    candidates = [
        entry
        for entry in versions
        if compatible(entry["engines"]["ephe"], ephe_version)
    ]
    if not candidates:
        _fail(
            "no_compatible_version",
            f"plugins.{name}.versions",
            f"none fits Ephe {ephe_version}",
        )
    best = max(candidates, key=lambda entry: parse_semver(entry["version"]) or (0, 0, 0))
    return {**best, "plugin": plugin}


def apply_revocations(index: dict[str, Any], revoked: list[dict[str, Any]]) -> dict[str, Any]:
    table = {
        (str(item.get("name")), str(item.get("version"))): str(item.get("reason") or "")
        for item in revoked
        if isinstance(item, dict) and item.get("name") and item.get("version")
    }
    for plugin in index.get("plugins", []):
        for entry in plugin.get("versions", []):
            key = (plugin.get("name"), entry.get("version"))
            if key in table:
                entry["revoked"] = True
                entry["revocation_reason"] = table[key]
    return index


def is_revoked(name: str, version: str, revoked: list[dict[str, Any]]) -> bool:
    return any(
        str(item.get("name")) == name and str(item.get("version")) == version
        for item in revoked
        if isinstance(item, dict)
    )


def verify_index_signature(
    raw: dict[str, Any], trusted_pems: list[bytes]
) -> tuple[bool, str]:
    signature = raw.get("signature")
    if not isinstance(signature, dict) or not signature.get("signature"):
        return False, "the index is not signed"
    if signature.get("alg") != plugin_signing.SIG_ALG:
        return False, "unsupported signature algorithm"
    if not trusted_pems:
        return False, "no trusted key is configured"
    body = {key: value for key, value in raw.items() if key != "signature"}
    for pem in trusted_pems:
        if plugin_signing.verify(body, str(signature["signature"]), pem):
            return True, ""
    return False, "the index signature is not from a trusted key"
