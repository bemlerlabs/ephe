"""◑ Ephe — marketplace generator (Extensions v2, E3).
scripts/generate_marketplace.py

Builds ephe-marketplace.json (repo root) from plugins/ — the bundled
marketplace manifest in our own schema (pattern: multi-source marketplaces:
name/version/description/description_i18n/owner + plugin entries with
icon/category/keywords/origin). Vendor-neutral, no third-party logos: `icon`
points at the bundled icon.svg inside each plugin dir.

Run:  .venv/bin/python scripts/generate_marketplace.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # core.* is not importable when run by path


from core.plugin_manifest import load_manifest

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"

CATEGORIES = {
    "web-research": "research",
    "memory": "memory",
    "documents": "documents",
    "spreadsheets": "documents",
    "presentations": "documents",
    "browser-use": "browser",
    "vision": "vision",
    "image-studio": "image",
    "voice": "audio",
    "code-shell": "code",
    "mcp-connector": "mcp",
    "plugin-creator": "meta",
    "skill-creator": "meta",
    "guide": "meta",
}

DESCRIPTION_I18N = {
    "web-research": {"en": "Live web research for the agent (opt-in, needs an API key).",
                      "de": "Live-Websuche für den Agenten (Opt-in, braucht einen API-Key)."},
    "memory": {"en": "Short- and long-term memory across sessions.",
                "de": "Kurz- und Langzeitgedächtnis über Sitzungen hinweg."},
    "documents": {"en": "Real document production: PDF, DOCX, QR codes, notebooks, briefs.",
                   "de": "Echte Dokument-Produktion: PDF, DOCX, QR-Codes, Notebooks, Briefe."},
    "spreadsheets": {"en": "Real spreadsheet production: formatted XLSX workbooks and charts.",
                      "de": "Echte Tabellen-Produktion: formatierte XLSX-Arbeitsmappen und Charts."},
    "presentations": {"en": "Real deck production: PPTX presentations, pitch decks, diagrams.",
                       "de": "Echte Deck-Produktion: PPTX-Präsentationen, Pitch-Decks, Diagramme."},
    "browser-use": {"en": "Real browser automation: navigate, click, type, screenshot — approval-gated.",
                     "de": "Echte Browser-Automatisierung: navigieren, klicken, tippen, Screenshot — approval-gated."},
    "vision": {"en": "Vision-capable model reads screenshots and images.",
                "de": "Vision-fähiges Modell liest Screenshots und Bilder."},
    "image-studio": {"en": "Image generation for posters, illustrations and concepts.",
                      "de": "Bildgenerierung für Poster, Illustrationen und Konzepte."},
    "voice": {"en": "Text-to-speech for answers and read-aloud.",
               "de": "Sprachausgabe für Antworten und Vorlesen."},
    "code-shell": {"en": "Coding loop: read, edit, patch, run tests, format and analyze code.",
                    "de": "Coding-Loop: lesen, editieren, patchen, Tests laufen lassen, formatieren, analysieren."},
    "mcp-connector": {"en": "External tools via Model Context Protocol servers.",
                       "de": "Externe Werkzeuge über Model-Context-Protocol-Server."},
    "plugin-creator": {"en": "Create and validate Ephe plugins: scaffolds, permissions, signing.",
                        "de": "Ephe-Plugins erstellen und validieren: Gerüste, Permissions, Signierung."},
    "skill-creator": {"en": "Create and grade Ephe skill packs with rubric and golden gates.",
                       "de": "Ephe-Skill-Packs erstellen und benoten — mit Rubrik und Golden-Gates."},
    "guide": {"en": "Ephe usage and self-diagnosis guide: engines, plugins, hooks, doctor flows.",
               "de": "Ephe-Gebrauchs- und Diagnose-Guide: Engines, Plugins, Hooks, Doctor-Flows."},
}


def main() -> None:
    plugins = []
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        manifest, err = load_manifest(plugin_dir)
        if manifest is None:
            print(f"SKIP {plugin_dir.name}: {err}")
            continue
        slug = str(manifest["name"])
        de = str(manifest["description"])
        plugins.append(
            {
                "name": slug,
                "source": f"plugins/{slug}",
                "description": DESCRIPTION_I18N.get(slug, {}).get("en", de),
                "description_i18n": DESCRIPTION_I18N.get(slug, {"en": de, "de": de}),
                "version": str(manifest["version"]),
                "author": "Ephe",
                "icon": f"plugins/{slug}/icon.svg",
                "category": CATEGORIES.get(slug, "meta"),
                "keywords": [slug.replace("-", " "), "ephe", "local-first"],
                "origin": str(manifest.get("origin", "first-party")),
            }
        )

    out = {
        "name": "ephe-plugins-official",
        "version": 1,
        "description": "Official Ephe plugins: built-in product plugins for Ephe Agent.",
        "description_i18n": {
            "en": "Official Ephe plugins: built-in product plugins for Ephe Agent.",
            "de": "Offizielle Ephe-Plugins: eingebaute Produkt-Plugins für den Ephe Agent.",
        },
        "owner": "Ephe",
        "plugins": plugins,
    }
    target = ROOT / "ephe-marketplace.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ephe-marketplace.json written: {len(plugins)} plugins")


if __name__ == "__main__":
    main()
