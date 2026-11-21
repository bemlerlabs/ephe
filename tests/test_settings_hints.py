"""Description duty: every real control belongs with a text (wave I3).

The settings surface should explain what a value changes — but an explained button
without a reader sells false depth. Both directions are therefore errors: wired
without a text (unexplained) and a text without wiring (decoration). The same
detector as in tests/test_settings_surface_is_real.py sets the standard: a field
counts as a control when a consumer calls it through the accessor line by its full
key.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings_hints import HINTS  # noqa: E402
from core.settings_schema import SCHEMA, deep_view  # noqa: E402
from tests.test_settings_surface_is_real import _read_keys  # noqa: E402

MIN_LEN = 24
MAX_LEN = 240


def _normal(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(".!?")


# Both directions of the duty

def _row_keys() -> list[str]:
    """Wired fields that render as a register row.

    A multiline field has no row: it is edited in a full-width card whose title and
    explanation come from the locale files (the de/en pair HINTS carries would be a
    second copy of the same sentence). The duty below is about rows, so those fields
    are the one shape it does not cover.
    """
    return [k for k in _read_keys() if not SCHEMA.get(k, {}).get("multiline")]


def test_every_control_carries_a_text() -> None:
    # A field may carry its explanation as a locale key when the text belongs to
    # the product surface rather than to this German-annotated register.
    missing = sorted(
        k
        for k in _row_keys()
        if k not in HINTS and not SCHEMA.get(k, {}).get("hintKey")
    )
    assert not missing, f"verdrahtete Felder ohne Erklaerung: {missing}"


def test_no_text_for_a_field_without_a_reader() -> None:
    dekoriert = sorted(k for k in HINTS if k not in _read_keys())
    assert not dekoriert, (
        "Beschreibungstexte fuer Felder ohne Leser — ein toter Knopf mit "
        f"schoenem Text ist eine Falschaussage: {dekoriert}"
    )


def test_no_hint_for_a_field_the_register_lacks() -> None:
    fremde = sorted(k for k in HINTS if k not in SCHEMA)
    assert not fremde, f"HINTS kennt Felder, die das Register nicht hat: {fremde}"


# Shape of the texts

@pytest.mark.parametrize("key", sorted(HINTS))
def test_each_hint_has_both_languages_in_good_form(key: str) -> None:
    pair = HINTS[key]
    assert isinstance(pair, tuple) and len(pair) == 2, key
    de, en = pair
    for text in (de, en):
        assert MIN_LEN <= len(text) <= MAX_LEN, f"{key}: {len(text)} Zeichen"
    assert de != en, f"{key}: de und en sind identisch"
    # An echo of the label explains nothing.
    meta = SCHEMA[key]
    assert _normal(de) != _normal(meta["label"]), f"{key}: de wiederholt nur das Label"
    assert _normal(en) != _normal(meta["labelEn"]), f"{key}: en wiederholt nur das Label"


@pytest.mark.parametrize("key", sorted(HINTS))
def test_no_hint_is_a_placeholder(key: str) -> None:
    for text in HINTS[key]:
        for word in ("TODO", "tbd", "XXX", "lorem"):
            assert word.lower() not in text.lower(), f"{key}: Platzhalter {word!r}"


# The channel up into the API view

def test_deep_view_passes_both_languages_through(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    wired = _read_keys()
    for key, (de, en) in HINTS.items():
        assert entries[key]["hint"] == de
        assert entries[key]["hintEn"] == en
    for key in entries:
        if key not in wired:
            assert "hint" not in entries[key], f"{key}: Feld ohne Leser traegt Text"


def test_deep_view_never_carries_half_a_hint_channel(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the read without the write (or the other way round) leaves the client idling."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    for entry in (f for s in deep_view() for f in s["fields"]):
        assert ("hint" in entry) == ("hintEn" in entry), entry["key"]


def test_a_hint_key_reaches_the_view_without_a_second_copy(tmp_path, monkeypatch) -> None:
    """A product-copy hint lives in the locale, not as a second HINTS pair."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core.settings_schema import deep_view

    entries = {field["key"]: field for section in deep_view() for field in section["fields"]}
    entry = entries["plugins.plugin_lifecycle_read_only"]

    assert entry["labelKey"] == "settings.pluginReadOnly"
    assert entry["hintKey"] == "settings.pluginReadOnlyHint"
    assert "hint" not in entry and "hintEn" not in entry
    assert entry["label"] and entry["labelEn"]


# The numbers a text is allowed to name

def test_a_hint_names_only_numbers_the_register_itself_decides() -> None:
    """The percentage dial sold 14 px while the interface base is 15 px.

    That number was copied out of the front end (`UI_FONT_SIZE_BASE_PX` in
    `app/src/lib/deepSettings.ts`, the `--ui-font-size` in `globals.css`), and a copy is the
    version that goes stale: the base moved up on 2026-10-17, pinned since in
    `src/lib/deepSettings.test.ts`, and the panel kept offering the old figure. A hint may
    name a number the register decides from its own data, which for a select is its options.
    """
    for language in (0, 1):
        assert " px" not in HINTS["appearance.font_scale"][language]

    base = "appearance.base_font_px"
    named = {digit for text in HINTS[base] for digit in re.findall(r"\d+", text)}
    assert named == set(SCHEMA[base]["options"])


def _dial_keys_with_a_span() -> list[str]:
    return [
        key
        for key, spec in sorted(SCHEMA.items())
        if spec.get("type") == "number"
        and spec.get("min") is not None
        and spec.get("max") is not None
        and key in HINTS
    ]


def _spellings(bound: float | int) -> set[str]:
    """Every form one bound legitimately takes in these sentences.

    The same 2000 is written 2.000 in German and 2,000 in English, and a threshold under
    one is 0.5 there and 0,5 here. The rule is about the register's numbers, so the
    spelling stays out of it.
    """
    if isinstance(bound, float) and bound.is_integer():
        bound = int(bound)
    if isinstance(bound, int):
        return {str(bound), f"{bound:,}", f"{bound:,}".replace(",", ".")}
    return {str(bound), str(bound).replace(".", ",")}


@pytest.mark.parametrize("key", _dial_keys_with_a_span())
def test_a_dial_with_a_span_tells_that_span(key: str) -> None:
    """The row shows the hint and nothing else about how far the number may go.

    `deepFields.tsx` renders `hint`/`hintEn` and never the `min`/`max` that
    `deep_view` sends along, so a dial whose text names no bounds leaves the reader
    guessing where the field stops. Seventeen of twenty named theirs; the three that did
    not were filled in with the figure this file already decides.
    """
    spec = SCHEMA[key]
    for text in HINTS[key]:
        for bound in (spec["min"], spec["max"]):
            assert any(form in text for form in _spellings(bound)), (key, bound, text)


def test_a_hint_that_quotes_another_bound_is_pinned_to_its_owner() -> None:
    """Two texts name a number another module decides, and say whose it is.

    `advanced.api_timeout` quotes the streaming path's own read bound and
    `memory.capture_min_answer_chars` the length a question has to clear. Both read true
    today: `core/model_provider.py` sets read=300 s on `STREAM_TIMEOUT`, which the
    streaming client takes at :642 and the non-streaming path never sees, and
    `core/auto_memory.py` sets `_MIN_QUESTION_CHARS`. A sentence quoting a figure it does
    not own is the version that goes stale, which is how the font dial ended up selling
    14 px, so the pair is tied to the modules that decide it: move a constant and this
    case is the one that goes red.
    """
    from core import auto_memory, model_provider

    read_seconds = model_provider.OpenAICompatibleAsyncClient.STREAM_TIMEOUT.read
    for text in HINTS["advanced.api_timeout"]:
        assert str(int(read_seconds)) in text, text

    question_floor = auto_memory._MIN_QUESTION_CHARS
    for text in HINTS["memory.capture_min_answer_chars"]:
        assert str(question_floor) in text, text


# The second home of register copy: the locale bundles

LOCALES = ROOT / "app" / "src" / "locales"

# A label that is legitimately the same word in both languages: a name, an
# acronym, a model tag. Every entry states why the German surface shows that word.
SAME_BY_DESIGN: dict[str, str] = {}


def _leaf(bundle: dict, dotted: str) -> str:
    node: object = bundle
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    assert isinstance(node, str), f"{dotted} is no string"
    return node


def _both_bundles() -> tuple[dict, dict]:
    return tuple(  # type: ignore[return-value]
        json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in ("de", "en")
    )


def _keyed_fields(channel: str) -> list[tuple[str, str]]:
    return [(k, spec[channel]) for k, spec in sorted(SCHEMA.items()) if spec.get(channel)]


def test_a_key_into_the_locale_bundle_resolves_in_both_languages() -> None:
    """Every `labelKey` and `hintKey` in the register names a leaf that answers.

    i18next hands an unknown key back untouched: a typo in `hintKey` does not fall
    back to `hint`, the reader sees `settings.agentTeamEnabledHint` in the place a
    sentence belongs. The app-side gate (`app/src/locales/completeness.test.ts`)
    scans the app's own sources for call forms and `*Key:` fields; these two key
    homes are Python, so nothing over them but this case.
    """
    de, en = _both_bundles()
    for channel in ("labelKey", "hintKey"):
        for key, dotted in _keyed_fields(channel):
            for lang, bundle in (("de", de), ("en", en)):
                try:
                    text = _leaf(bundle, dotted)
                except KeyError:
                    raise AssertionError(f"{key}: {channel} {dotted!r} fehlt in {lang}.json") from None
                assert text.strip(), f"{key}: {channel} {dotted!r} ist leer in {lang}.json"
                for word in ("TODO", "tbd", "XXX", "lorem"):
                    assert word.lower() not in text.lower(), f"{key}: Platzhalter {word!r}"


def test_no_german_label_and_no_german_hint_carry_the_english_copy() -> None:
    """The German surface shows German, whichever of its two homes the text lives in.

    Two shapes carry register copy: `label`/`labelEn` (and a HINTS pair) in Python,
    a `labelKey`/`hintKey` into the locale bundles. A field that ships one string
    for both languages hands the German reader English, which is why the locale
    bundles have their own version of this rule
    (`app/src/locales/germanSurface.test.ts`) and the register had none.
    """
    de, en = _both_bundles()
    offenders: list[str] = []

    for key, spec in sorted(SCHEMA.items()):
        if not spec.get("labelKey"):
            if spec["label"] == spec["labelEn"] and key not in SAME_BY_DESIGN:
                offenders.append(f"{key}: label {spec['label']!r}")

    for channel, other in (("labelKey", "label"), ("hintKey", "hintEn")):
        for key, dotted in _keyed_fields(channel):
            if key in SAME_BY_DESIGN:
                continue
            de_text = _leaf(de, dotted)
            en_text = _leaf(en, dotted)
            if de_text == en_text:
                offenders.append(f"{key}: {channel} {dotted!r} in beiden Sprachen gleich")

    assert not offenders, f"the German surface shows English copy: {offenders}"


def test_the_memory_texts_quote_the_numbers_other_modules_decide() -> None:
    """Four memory texts name figures they do not own, so each is tied to its owner.

    `memory.embedder` quotes both embedders' dimensions, `memory.embedder_allow_download`
    the artifact's size and `memory.dedupe_score_threshold` the duplicate check's own
    bounds. All of them read true today — 542 is what `core/memory_embed_gemma.py` ships,
    after the text had sold 540 for as long as anyone read it — and a constant that moves
    has to make this the case that goes red rather than leave a stale figure on the row.
    """
    from core import auto_memory, memory_embed_gemma, memory_embed_onnx

    for text in HINTS["memory.embedder"]:
        for figure in (memory_embed_gemma.NATIVE_DIM, memory_embed_gemma.EMBED_DIM,
                       memory_embed_onnx.EMBED_DIM):
            assert str(figure) in text, text

    for text in HINTS["memory.embedder_allow_download"]:
        assert str(memory_embed_gemma.MODEL_SIZE_MB) in text, text

    for text in HINTS["memory.dedupe_score_threshold"]:
        for figure in (auto_memory._TWIN_TOPK, auto_memory._DEDUPE_QUERY_CHARS):
            assert str(figure) in text, text
