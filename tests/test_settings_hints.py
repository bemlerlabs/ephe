"""Description duty: every real control belongs with a text (wave I3).

The settings surface should explain what a value changes — but an explained button
without a reader sells false depth. Both directions are therefore errors: wired
without a text (unexplained) and a text without wiring (decoration). The same
detector as in tests/test_settings_surface_is_real.py sets the standard: a field
counts as a control when a consumer calls it through the accessor line by its full
key.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings_hints import HINTS, hint_key, label_key, option_key  # noqa: E402
from core.settings_schema import SCHEMA, deep_view  # noqa: E402
from tests.support import shipped_copy  # noqa: E402
from tests.test_settings_surface_is_real import _read_keys  # noqa: E402

MIN_LEN = 24
MAX_LEN = 240


def _normal(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(".!?")


def _german_hint(key: str) -> str:
    """The German half of a register text, read where it now lives: the German bundle."""
    de, _ = _both_bundles()
    return _leaf(de, hint_key(key))


def _row_title(key: str) -> tuple[str, str]:
    """The row title as the German surface shows it and as the register carries it.

    Since wave L the title is a leaf in both bundles and `label` holds the English the
    panel falls back to, so the German half has exactly one place to be read from.
    """
    de, _ = _both_bundles()
    return _leaf(de, SCHEMA[key].get("labelKey") or label_key(key)), SCHEMA[key]["label"]


def both_halves(key: str) -> list[str]:
    """The one sentence a row shows, in both of the two places its languages live.

    Since wave L the register carries the English fallback and the German is a leaf in
    `app/src/locales/de.json` under `hint_key(key)`. A rule about these texts holds for
    both halves or it holds for the German reader by accident.
    """
    return [HINTS[key], _german_hint(key)]


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
    assert not missing, f"wired fields without an explanation: {missing}"


def test_no_text_for_a_field_without_a_reader() -> None:
    dekoriert = sorted(k for k in HINTS if k not in _read_keys())
    assert not dekoriert, (
        "description texts for fields without a reader — a dead button with nice text is a false claim: " f"{dekoriert}"
    )


def test_no_hint_for_a_field_the_register_lacks() -> None:
    fremde = sorted(k for k in HINTS if k not in SCHEMA)
    assert not fremde, f"HINTS knows fields the register does not have: {fremde}"


# Shape of the texts

@pytest.mark.parametrize("key", sorted(HINTS))
def test_each_hint_has_both_languages_in_good_form(key: str) -> None:
    de, en = _german_hint(key), HINTS[key]
    for text in (de, en):
        assert MIN_LEN <= len(text) <= MAX_LEN, f"{key}: {len(text)} Zeichen"
    assert de != en, f"{key}: de and en are identical"
    # An echo of the title explains nothing.
    meta = SCHEMA[key]
    german_title, _ = _row_title(key)
    assert _normal(de) != _normal(german_title), f"{key}: de only repeats the row title"
    assert _normal(en) != _normal(meta["labelEn"]), f"{key}: en only repeats the label"


@pytest.mark.parametrize("key", sorted(HINTS))
def test_no_hint_is_a_placeholder(key: str) -> None:
    for text in both_halves(key):
        for word in ("TODO", "tbd", "XXX", "lorem"):
            assert word.lower() not in text.lower(), f"{key}: Platzhalter {word!r}"


# The channel up into the API view

def test_deep_view_passes_both_languages_through(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The register hands the page one key and one English fallback, both halves intact.

    The German reaches the reader through `hintKey` and the bundle, never through this
    table, so the case asserts the key is the derived one and the two strings are the
    fallback rather than half a pair each.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    wired = _read_keys()
    for key in HINTS:
        assert entries[key]["hint"] == HINTS[key]
        assert entries[key]["hintEn"] == HINTS[key]
        assert entries[key]["hintKey"] == hint_key(key)
    for key in entries:
        if key not in wired:
            assert "hint" not in entries[key], f"{key}: a field without a reader carries text"


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
    for text in both_halves("appearance.font_scale"):
        assert " px" not in text

    base = "appearance.base_font_px"
    named = {digit for text in both_halves(base) for digit in re.findall(r"\d+", text)}
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
    for text in both_halves(key):
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
    for text in both_halves("advanced.api_timeout"):
        assert str(int(read_seconds)) in text, text

    question_floor = auto_memory._MIN_QUESTION_CHARS
    for text in both_halves("memory.capture_min_answer_chars"):
        assert str(question_floor) in text, text


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


def _boot_bundles() -> tuple[dict, dict]:
    # Read once per run: every parametrized hint case asks for both halves, and the
    # bundles are 190 kB each.
    global _BUNDLES
    if "_BUNDLES" not in globals():
        _BUNDLES = (shipped_copy.boot("de"), shipped_copy.boot("en"))
    return _BUNDLES  # type: ignore[return-value]


def _both_bundles() -> tuple[dict, dict]:
    """What a reader's client can resolve: the boot bundle plus the register copy it loads on demand.

    A row asks i18next for one dotted leaf and does not care which of the two files carried it —
    `addResourceBundle` merges the register copy into the same namespace before the panel paints.
    `test_a_leaf_sits_in_exactly_one_of_the_two_halves` pins which half holds which leaf, so the
    merge here cannot hide a leaf that drifted back into the boot bundle.
    """
    return shipped_copy.shipped("de"), shipped_copy.shipped("en")


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
                    raise AssertionError(f"{key}: {channel} {dotted!r} is missing from {lang}.json") from None
                assert text.strip(), f"{key}: {channel} {dotted!r} is empty in {lang}.json"
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

    for text in both_halves("memory.embedder"):
        for figure in (memory_embed_gemma.NATIVE_DIM, memory_embed_gemma.EMBED_DIM,
                       memory_embed_onnx.EMBED_DIM):
            assert str(figure) in text, text

    for text in both_halves("memory.embedder_allow_download"):
        assert str(memory_embed_gemma.MODEL_SIZE_MB) in text, text

    for text in both_halves("memory.dedupe_score_threshold"):
        for figure in (auto_memory._TWIN_TOPK, auto_memory._DEDUPE_QUERY_CHARS):
            assert str(figure) in text, text


def test_the_german_sentence_arrives_from_the_bundle_not_from_python(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half the German reader sees is a bundle leaf; comparing the two Python strings proves nothing.

    `deepFields.tsx` answers `field.hintKey ? t(field.hintKey) : …`, so the row's German is
    whatever `de.json` holds under the key the register sent. This walks the seam end to end:
    the key out of `deep_view`, the leaf out of the German bundle, and the assertion that the
    register's own two strings are the English fallback — a field whose German had been
    "translated away" into the fallback would fail here rather than read English to a German.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    de, en = _both_bundles()
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}

    for key in sorted(HINTS):
        entry = entries[key]
        german = _leaf(de, entry["hintKey"])
        assert german == _german_hint(key), f"{key}: the view's key and the tested leaf disagree"
        assert german != entry["hint"], f"{key}: the German row would show the fallback"
        assert german != entry["hintEn"], f"{key}: hintEn carries the German, the pairs collapsed"
        assert _leaf(en, entry["hintKey"]) == entry["hint"], f"{key}: the English leaf and the fallback differ"


# The row titles: the second half of what a German reader reads on a row

# The three cards are not register rows; they name their leaf by hand (r58 holds that list).
CARD_FIELDS = {"chat.custom_instructions", "plugins.plugin_lifecycle_read_only",
               "advanced.agent_team_enabled"}


def test_no_register_row_keeps_a_german_title_in_code() -> None:
    """A row title is product text: the code holds the key and the English, never the German.

    Before wave L, 49 of the 52 rows carried their German title as a Python string, which
    meant a German reader's title was written in a file the language gate reads as
    developer prose. `label` is the fallback the panel shows when it does not know the key.
    """
    german = sorted(k for k, meta in SCHEMA.items() if meta["label"] != meta["labelEn"])
    assert not german, f"rows whose German title still sits in the code: {german}"


@pytest.mark.parametrize("key", sorted(SCHEMA))
def test_every_row_title_resolves_in_both_bundles(key: str) -> None:
    meta = SCHEMA[key]
    dotted = meta.get("labelKey")
    assert dotted, f"{key}: a row without a title key and without a language of its own"
    if key not in CARD_FIELDS:
        assert dotted == label_key(key), f"{key}: the leaf and the rule disagree"
    de, en = _both_bundles()
    german, english = _leaf(de, dotted), _leaf(en, dotted)
    assert german.strip() and english.strip(), key
    assert english == meta["labelEn"], f"{key}: the English leaf and the register differ"
    if key not in SAME_BY_DESIGN:
        assert german != english, f"{key}: the German surface shows the English title"


def _register_copy() -> dict[str, dict[str, str]]:
    """The two halves of the lazy register copy, keyed by the dotted leaf a client asks for.

    The asset holds one object per language nested under `settings`, which is the shape
    i18next merges into its `translation` namespace; flattening it here gives the same
    spelling `optionKeys` and `hintKey` carry.
    """
    return {language: shipped_copy.register_leaves(language) for language in ("de", "en")}


def test_every_option_carries_its_leaf_and_keeps_its_label() -> None:
    """Given a select in the register, When its view is built, Then the leaf arrived and the label stayed.

    `optionKeys` came in additive, the way `hintKey` did: a client that has not read the
    register copy still paints `optionLabels`. Both halves are asserted here because the
    label text now lives twice — in the register for that client and in the copy for the
    leaf — and a copy that is allowed to differ is a second truth.
    """
    entries = {field["key"]: field for section in deep_view() for field in section["fields"]}
    leaves = _register_copy()
    with_keys = [k for k, entry in entries.items() if entry.get("optionKeys")]
    with_labels = [k for k, entry in entries.items() if entry.get("optionLabels")]
    assert with_keys == with_labels, "an option list arrived without its keys, or the reverse"
    assert with_keys, "the register carries no labelled option any more"
    for key in with_keys:
        entry = entries[key]
        assert [o["value"] for o in entry["optionKeys"]] == [o["value"] for o in entry["optionLabels"]]
        # `SettingControl` reads option, label and key by the map index, so the three lists
        # are one list here — a value that moved in one of them and not the others is the bug.
        assert [o["value"] for o in entry["optionLabels"]] == entry["options"], (
            f"{key}: options, optionLabels and optionKeys went out of step"
        )
        for label, keyed in zip(entry["optionLabels"], entry["optionKeys"]):
            assert keyed["key"] == option_key(key, keyed["value"]), f"{key}/{keyed['value']}"
            for language, text in (("de", label["label"]), ("en", label["labelEn"])):
                assert leaves[language].get(keyed["key"]) == text, (
                    f"{keyed['key']}: the {language} copy and the register differ"
                )


def test_an_option_key_moves_with_its_value() -> None:
    """Given two values of one field, When their leaves are named, Then each value is part of its leaf."""
    assert option_key("appearance.base_font_px", "13") != option_key("appearance.base_font_px", "14")
    assert option_key("appearance.companion_species", "paper_moth").endswith("OptionPaperMoth")
    assert option_key("appearance.base_font_px", "13").startswith("settings.appearanceBaseFontPxOption")


# Which half holds which leaf, now that the register copy is a file of its own

#: Rows whose title and hint stayed in the boot bundle: three cards the panel writes by hand,
#: two of which carry keys at all. Everything the register itself sends reads the asset.
CATALOG_HELD_ROWS = {"advanced.agent_team_enabled", "plugins.plugin_lifecycle_read_only"}


def test_a_leaf_sits_in_exactly_one_of_the_two_halves() -> None:
    """Given the split of 2026-11-24, When both halves are read, Then no leaf stands in both and each row's copy sits where its reader finds it.

    A leaf present twice would mean the boot bundle ships register text again — the bytes the
    split took out of the first paint, back on it. A leaf in neither half would paint a key path
    in the panel. The partition is asserted per row, so a leaf that walks from one file to the
    other fails by name.
    """
    copy = _register_copy()
    for language, boot in zip(("de", "en"), _boot_bundles()):
        both = sorted(set(boot.get("settings", {})) & {k.split(".", 1)[1] for k in copy[language]})
        assert not both, f"{language}: {both[:3]} stands in the boot bundle and in the register copy"
    entries = {field["key"]: field for section in deep_view() for field in section["fields"]}
    for key in sorted(SCHEMA):
        in_asset = key not in CATALOG_HELD_ROWS
        for channel in ("labelKey", "hintKey"):
            dotted = entries[key].get(channel) or SCHEMA[key].get(channel)
            if not dotted:
                continue
            assert (dotted in copy["de"]) == in_asset, f"{key}.{channel}: wrong half ({dotted})"
            assert (dotted in copy["en"]) == in_asset, f"{key}.{channel}: the halves disagree ({dotted})"
