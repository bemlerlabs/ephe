"""W4-30 / row R25: the head's plain description speaks English, like the tags beside it.

`app/index.html` ships `lang="en"` and describes Ephe in English in its `og:` and
`twitter:` tags. The `<meta name="description">` was the one German sentence in that head
until W4-30, and it carried the private claim `docs/BRAND.md` ("Claim boundary") keeps out
of the product — on the line a crawler and a link preview read before any script runs.

The value is pinned exactly. A check that only hunts German words passes on the next
English sentence somebody writes here, and this row was opened because the head drifted
into two languages once already.

The German reader keeps the German wording of the same pitch in `app/src/locales/de.json`
(`welcome.heroSub`). Both locale files are asserted below, so a later sweep that aligns the
head with the German file fails here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "app" / "index.html"
EN_JSON = ROOT / "app" / "src" / "locales" / "en.json"
DE_JSON = ROOT / "app" / "src" / "locales" / "de.json"

DESCRIPTION = (
    "Ephe — Ephemeral SI Agent. Give it a task; it researches, builds and "
    "delivers while you watch. Runs locally on the engine you choose."
)

# The pitch every English description surface repeats, and its German counterpart in the
# German locale. `welcome.heroSub` is the app's own sentence for what Ephe does.
PITCH_EN = "researches, builds and delivers"
PITCH_DE = ("recherchiert", "baut", "liefert")

# German words the retired description carried. `SI-Agent` is the hyphenated German form;
# the English head writes `SI Agent` (og:title).
GERMAN_MARKERS = ("dein", "lokaler", "lokal", "privat", "si-agent", "während")
GERMAN_RE = re.compile(r"\b(?:" + "|".join(GERMAN_MARKERS) + r")\b", re.I)

# `docs/BRAND.md` "Claim boundary": sayable is what is countable or provable. Web search,
# a foreign engine and the Telegram link are opt-in paths.
FORBIDDEN_CLAIMS = ("private", "never", "without a trace", "no data leaves")


def meta_content(attr: str, name: str) -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    pattern = rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"'
    hit = re.search(pattern, html)
    assert hit, f"app/index.html carries no <meta {attr}={name}>"
    return hit.group(1)


def locale_value(path: Path, *keys: str) -> str:
    node: object = json.loads(path.read_text(encoding="utf-8"))
    for key in keys:
        node = node[key]
    assert isinstance(node, str)
    return node


def description_metas() -> list[str]:
    return [
        meta_content("name", "description"),
        meta_content("property", "og:description"),
        meta_content("name", "twitter:description"),
    ]


def test_the_document_language_is_the_description_language() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<html lang="en">' in html


def test_the_static_description_is_the_pinned_english_line() -> None:
    assert meta_content("name", "description") == DESCRIPTION


def test_the_static_description_names_the_product_and_fits_a_result_snippet() -> None:
    value = meta_content("name", "description")
    assert value.startswith("Ephe")
    assert len(value) <= 160


def test_the_static_description_carries_no_german_word() -> None:
    hit = GERMAN_RE.search(meta_content("name", "description"))
    assert hit is None, f"German word in the English head: {hit and hit.group(0)}"


def test_every_english_description_surface_repeats_the_one_pitch() -> None:
    english = description_metas() + [locale_value(EN_JSON, "welcome", "heroSub")]
    for value in english:
        assert PITCH_EN in value


def test_no_description_claim_leaves_the_brand_boundary() -> None:
    for value in description_metas():
        lowered = value.lower()
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in lowered, f"claim register in a description: {claim}"


def test_the_german_locale_keeps_the_german_pitch() -> None:
    hero_sub = locale_value(DE_JSON, "welcome", "heroSub")
    assert "Aufgabe" in hero_sub
    for word in PITCH_DE:
        assert word in hero_sub
    assert PITCH_EN not in hero_sub
