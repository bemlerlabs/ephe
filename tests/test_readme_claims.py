"""The catalogue numbers in the READMEs come from the catalogue itself.

A user cannot check a count that only lives in prose. The index is the source
of truth; when it gains a third-party entry, the sentences that said there is
none and that nothing has an install button stop being true.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

NUMBER_WORD = {
    "en": {1: "one", 5: "five", 7: "seven", 9: "nine"},
    "zh": {1: "一", 5: "五", 7: "七", 9: "九"},
    "es": {1: "un", 5: "cinco", 7: "siete", 9: "nueve"},
}


def catalogue_counts() -> dict[str, int]:
    index = json.loads((ROOT / "marketplace/index.json").read_text(encoding="utf-8"))
    plugins = index["plugins"]
    return {
        "plugins": sum(
            1
            for item in plugins
            if item.get("kind", "plugin") == "plugin"
            and item.get("quality_label", "plugin") == "plugin"
            and item.get("provenance") == "first-party"
        ),
        "presets": sum(
            1 for item in plugins if item.get("quality_label") == "capability-preset"
        ),
        "packs": sum(
            1
            for item in plugins
            if item.get("kind") == "skill-pack" and item.get("provenance") == "first-party"
        ),
        "third_party": sum(
            1 for item in plugins if item.get("provenance") == "third-party"
        ),
    }


def expected_phrases(counts: dict[str, int], language: str) -> list[str]:
    word = NUMBER_WORD[language]
    if language == "en":
        return [
            f"{word[counts['plugins']]} first-party plugins",
            f"{word[counts['presets']]} capability presets",
            f"{word[counts['packs']]} first-party skill packs",
            f"{word[counts['third_party']]} bundled third-party skill pack",
        ]
    if language == "zh":
        return [
            f"{word[counts['plugins']]}个第一方插件",
            f"{word[counts['presets']]}个能力预设",
            f"{word[counts['packs']]}个第一方技能包",
            f"{word[counts['third_party']]}个随附的第三方技能包",
        ]
    return [
        f"{word[counts['plugins']]} plugins propios",
        f"{word[counts['presets']]} preajustes de capacidades",
        f"{word[counts['packs']]} paquetes de habilidades propios",
        f"{word[counts['third_party']]} paquete de habilidades de terceros incluido",
    ]


def test_the_four_documents_state_the_catalogue_counts():
    counts = catalogue_counts()
    for number in counts.values():
        assert number in NUMBER_WORD["en"], f"no number word for {number}"
    documents = {
        "README.md": "en",
        "README.zh-CN.md": "zh",
        "README.es.md": "es",
    }
    for name, language in documents.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        for phrase in expected_phrases(counts, language):
            assert phrase in text, f"{name} does not state {phrase!r}"

    overview = (ROOT / "docs/PLUGINS_OVERVIEW.md").read_text(encoding="utf-8")
    word = NUMBER_WORD["en"]
    for phrase in (
        f"{word[counts['plugins']]} plugins",
        f"{word[counts['presets']]} presets",
        f"{word[counts['packs']]} first-party skill packs",
        f"{word[counts['third_party']]} bundled third-party pack",
    ):
        assert phrase in overview, f"PLUGINS_OVERVIEW does not state {phrase!r}"


def test_a_third_party_entry_retires_the_old_claims():
    if catalogue_counts()["third_party"] == 0:
        pytest.skip("no third-party entry to install")
    retired = {
        "README.md": [
            "no install button",
            "No one-click installation of external plugins",
            "No third-party plugin catalogue",
            "marketplace installation is planned",
        ],
        "README.zh-CN.md": [
            "没有安装按钮",
            "暂无外部插件或 MCP 服务器的一键安装功能",
            "暂无第三方插件目录",
            "通过市场安装的功能仍在计划中",
        ],
        "README.es.md": [
            "no tienen botón de instalación",
            "No hay instalación con un clic de plugins externos",
            "No hay catálogo de plugins de terceros",
            "Está prevista la instalación con un clic",
        ],
    }
    for name, claims in retired.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        present = [claim for claim in claims if claim in text]
        assert not present, f"{name} still claims {present!r}"
