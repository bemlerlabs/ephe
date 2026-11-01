"""Ephe — MCP catalog (E3c, docs/EXTENSIONS_V2_PLAN.md).
core/mcp_catalog.py

Curated starter catalog of known, open MCP servers for the MCP page.
Described vendor-neutral; links go to the official docs only. Entries are
pure data — no network call, no installation, no secrets.
`spec` is set only when the server can be registered directly as an
Ephe engine (PUT contract: http://, https://, stdio:); otherwise
`install_hint` describes the local start and the user adds the endpoint
by hand.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: The one slug rule for `/discover/icon/{slug}`: a lower-case file name we can
#: resolve under the providers directory. Kept beside the loaders so curated
#: rows and the route answer for the same shape.
ICON_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")

_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "marketplace" / "registry-snapshot.json"
)
_CURATED_PATH = (
    Path(__file__).resolve().parent.parent / "marketplace" / "registry-curated.json"
)
_FEATURED_PATH = (
    Path(__file__).resolve().parent.parent / "marketplace" / "featured.json"
)


def _load_entries(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else None
    return [dict(entry) for entry in entries] if isinstance(entries, list) else []

CATALOG: list[dict] = [
    {
        "id": "mcp-everything",
        "name": "Everything Server",
        "description": "Offizieller Test-Server des MCP-Projekts: Echo, Addition, "
        "Ressourcen und Prompts — ideal, um die eigene Anbindung zu prüfen.",
        "description_en": "Official test server from the MCP project: echo, addition, "
        "resources and prompts — ideal for checking your own connection.",
        "category": "testing",
        "install_hint": "npx -y @modelcontextprotocol/server-everything (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-filesystem",
        "name": "Filesystem Server",
        "description": "Dateizugriff auf freigegebene Ordner (lesen/schreiben/"
        "suchen) über das Model Context Protocol.",
        "description_en": "File access to shared folders (read/write/search) "
        "over the Model Context Protocol.",
        "category": "files",
        "install_hint": "npx -y @modelcontextprotocol/server-filesystem <folder> (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-fetch",
        "name": "Fetch Server",
        "description": "Webseiten abrufen und in Markdown konvertieren — der "
        "schlanke Weg zu aktuellen Informationen.",
        "description_en": "Fetch websites and convert them to Markdown — the "
        "lean way to current information.",
        "category": "web",
        "install_hint": "uvx mcp-server-fetch (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-memory",
        "name": "Memory Server",
        "description": "Wissensgraph als dauerhaftes Gedächtnis (Entitäten, "
        "Relationen, Beobachtungen).",
        "description_en": "Knowledge graph as a durable memory (entities, "
        "relations, observations).",
        "category": "memory",
        "install_hint": "npx -y @modelcontextprotocol/server-memory (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-git",
        "name": "Git Server",
        "description": "Repositories lesen und verändern: Status, Diffs, "
        "Commits, Branches — lokal über Git.",
        "description_en": "Read and change repositories: status, diffs, commits, "
        "branches — locally through Git.",
        "category": "code",
        "install_hint": "uvx mcp-server-git --repository <path> (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-time",
        "name": "Time Server",
        "description": "Aktuelle Zeit und Zeitzonenrechnung — klein, schnell, "
        "nützlich für jede Agenten-Sitzung.",
        "description_en": "Current time and timezone maths — small, fast, useful "
        "in any agent session.",
        "category": "utility",
        "install_hint": "uvx mcp-server-time (stdio)",
        "docs": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "id": "mcp-ephemora-cell",
        "name": "Ephemora Cell Server",
        "description": "Der Käfig selbst: Ephemora Cell bringt eine eigene "
        "MCP-Seite mit (Meta-Tool get-policy, gedeckelte Python-Ausführung in "
        "einer WASI-Cell). Ephe fährt seine Cell nativ und braucht diesen Server "
        "nicht — der Eintrag ist für fremde MCP-Clients, die denselben Käfig "
        "nutzen wollen. Lizenzgrenze wie in Ephe: >=1.0.4.3,<1.0.5 (1.0.5 ist "
        "BUSL-1.1).",
        "description_en": "The cage itself: Ephemora Cell ships its own MCP page "
        "(meta-tool get-policy, capped Python execution in a WASI cell). Ephe runs "
        "its cell natively and does not need this server — the entry is for other "
        "MCP clients that want the same cage. Same license fence as Ephe: "
        ">=1.0.4.3,<1.0.5 (1.0.5 is BUSL-1.1).",
        "category": "sandbox",
        "install_hint": "uvx --from \"ephemora-cell>=1.0.4.3,<1.0.5\" ephemora-cell-mcp (stdio)",
        "docs": "https://pypi.org/project/ephemora-cell/",
    },
]


def catalog_entries() -> list[dict]:
    """Copy of the catalog (route output; deterministic, without secrets)."""
    return [dict(e) for e in CATALOG]


def registry_entries() -> list[dict]:
    """The public registry mirror written by `catalog_discover.py --mirror`.

    Metadata only (CC0), English descriptions from the publishers themselves,
    served without a network call — the breadth answer for the connector area."""
    return _load_entries(_SNAPSHOT_PATH)


def curated_entries() -> list[dict]:
    """The tier the connector area shows by default: named picks plus the most
    recently published entries per category, derived from the mirror.

    A row may carry an optional `icon` slug for `/discover/icon/<slug>`; a
    value the icon route could never resolve is dropped at load, so the frame
    stays deterministic and offline whatever the data file holds."""
    entries = _load_entries(_CURATED_PATH)
    for entry in entries:
        slug = str(entry.get("icon") or "")
        if ICON_SLUG.fullmatch(slug):
            entry["icon"] = slug
        else:
            entry.pop("icon", None)
    return entries


def featured_entries() -> list[dict]:
    """The editorial tier: publishers and installation paths verified by hand.

    Each entry carries its own evidence links and a verified transport, so the
    shelf can put a known-good server above the long tail. Ranked by `rank`."""
    entries = _load_entries(_FEATURED_PATH)
    for entry in entries:
        entry["source"] = "featured"
        entry["description"] = entry.get("summary") or ""
    return sorted(entries, key=lambda one: (int(one.get("rank") or 999), str(one.get("name") or "")))
