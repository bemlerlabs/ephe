"""How a language and a key become a string in this interface.

Scope: the two shipped bundles under ``app/src/locales`` and the resolver config in
``app/src/i18n.ts``. The vitest suite beside the app covers the call sites (every
``t()`` literal exists, the dead-key ratchet, the guarded leak files); the TS
``i18n-keys`` spec compares key sets but cannot check how a region tag, a fallback,
an interpolation name or a plural form resolves, because it never sees the config.

The checks here are the ones a shipped string can fail while both bundles still parse:
a language that is offered but has no bundle, a ``de-DE`` request that never collapses
to ``de``, a translation whose ``{{name}}`` the other locale does not carry (the value
then renders the literal braces), a plural pair that exists on one side only, and a
value that resolves to an empty label. None of these is visible in a key census.

Read-only: the bundles and the config are the inputs, nothing is written.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "app" / "src" / "locales"
I18N_CONFIG = ROOT / "app" / "src" / "i18n.ts"

# i18next substitutes only the double-brace form; a lone ``{name}`` reaches the user
# verbatim. The lookarounds keep ``{{x}}`` out of the single-brace net.
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w]*)\s*\}\}")
SINGLE_BRACE = re.compile(r"(?<!\{)\{\s*[A-Za-z_][\w]*\s*\}(?!\})")
PLURAL_SUFFIX = re.compile(r"_(one|two|few|many|other|zero)$")


def _bundle(locale: str) -> dict:
    return json.loads((LOCALES / f"{locale}.json").read_text(encoding="utf-8"))


def _leaves(node: object, prefix: str = "", out: dict | None = None) -> dict:
    """Every leaf as a dotted path, the shape a lookup walks."""
    if out is None:
        out = {}
    for key, value in node.items():  # type: ignore[union-attr]
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _leaves(value, path, out)
        else:
            out[path] = value
    return out


def _config() -> str:
    return I18N_CONFIG.read_text(encoding="utf-8")


# WD-33 splits the catalogs per language, and the language is decided *before* `init` (the
# preloaded chunk has to be the one the detected language needs). That is why `fallbackLng`
# and `supportedLngs` name module-level constants instead of carrying the literal inside the
# init object. The shipped *values* are what these checks are about, so the read follows the
# name; an inline literal is still read as before, and a changed constant fails here too.
_NAMED = re.compile(r"[A-Za-z_$][\w$]*")
_ENTRY = re.compile(r"'([^']*)'|\.\.\.([A-Za-z_$][\w$]*)")


def _constant(text: str, name: str) -> str:
    """What a module-level `const NAME[: Type] = <value>` in i18n.ts holds."""
    match = re.search(rf"^const {name}\s*(?::[^=]+)?=\s*(.+)$", text, re.M)
    assert match, f"{I18N_CONFIG.name} declares no const {name}"
    return match.group(1).strip()


def _entry(body: str, text: str) -> list[str]:
    """The entries of an array literal, with a `...NAME` splice expanded where it stands."""
    out: list[str] = []
    for found in _ENTRY.finditer(body):
        if found.group(1) is not None:
            out.append(found.group(1))
        else:
            literals = re.findall(r"'([^']*)'", _constant(text, found.group(2)))
            assert literals, f"{I18N_CONFIG.name}: const {found.group(2)} is empty"
            out.extend(literals)
    return out


def _quoted_list(text: str, field: str) -> list[str]:
    match = re.search(rf"{field}:\s*\[([^\]]*)\]", text)
    assert match, f"{field} is not declared in {I18N_CONFIG.name}"
    return _entry(match.group(1), text)


def _string_field(text: str, field: str) -> str:
    match = re.search(rf"{field}:\s*([^,\n}}]+)", text)
    assert match, f"{field} is not declared in {I18N_CONFIG.name}"
    raw = match.group(1).strip()
    if _NAMED.fullmatch(raw):  # the init object names the constant the split hoisted
        literals = re.findall(r"'([^']*)'", _constant(text, raw))
        assert literals, f"{I18N_CONFIG.name}: const {raw} carries no string literal"
        return literals[0]
    quoted = re.fullmatch(r"'([^']*)'", raw)
    assert quoted, f"{field} in {I18N_CONFIG.name} is neither a literal nor a constant"
    return quoted.group(1)


def _detection_block(text: str) -> str:
    """The detector options, so ``order`` is read from that block and not from a key
    of the same name elsewhere."""
    start = text.index("detection:")
    open_brace = text.index("{", start)
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace : index + 1]
    raise AssertionError("the detection block in i18n.ts is not closed")


@pytest.fixture(scope="module")
def supported() -> list[str]:
    return _quoted_list(_config(), "supportedLngs")


def test_every_offered_language_ships_a_readable_bundle(supported):
    """A language in ``supportedLngs`` with no bundle resolves to raw keys."""
    text = _config()
    # The fallback is the boot language, decided before init (browser on a first
    # start); its catalog is the one preloaded, so no offered language may miss one.
    assert "fallbackLng: activeLanguage" in text
    assert "function languageFrom" in text and "navigator.language" in text
    assert supported, "supportedLngs is empty"
    for locale in supported:
        assert (LOCALES / f"{locale}.json").is_file(), f"no bundle shipped for {locale}"
        assert _bundle(locale), f"the {locale} bundle has no entries"


def test_region_tags_collapse_to_the_base_bundle(supported):
    """``load: 'languageOnly'`` is what makes ``de-DE`` find ``de``; a region-tagged
    choice otherwise lands on the fallback while a bundle for it is sitting there."""
    assert _string_field(_config(), "load") == "languageOnly"
    for locale in supported:
        for region in ("DE", "AT", f"{locale.upper()}-LATN"):
            tag = f"{locale}-{region}"
            base = tag.replace("_", "-").split("-")[0].lower()
            assert base in supported, f"{tag} does not collapse onto an offered language"
            assert _bundle(base), f"{tag} collapses onto {base} with no entries"


def test_an_unknown_detected_language_resolves_to_the_fallback(supported):
    """A stored choice pointing at an unshipped language still has to get strings."""
    text = _config()
    fallback = re.search(r"^const FALLBACK_LANGUAGE[^=]*=\s*'([^']+)'", text, re.M)
    assert fallback is not None, "i18n.ts declares no FALLBACK_LANGUAGE literal"
    unknown = "fr"
    assert unknown not in supported
    assert fallback.group(1) in supported
    assert _bundle(fallback.group(1)), "the fallback language ships no bundle"
    assert "return FALLBACK_LANGUAGE" in text, "languageFrom no longer ends on the fallback"


def test_detection_reads_the_stored_choice_only():
    """The documented decision: without a stored choice the navigator language is never
    guessed. A detector that reads the navigator reintroduces the mixed first screen."""
    block = _detection_block(_config())
    order = _quoted_list(block, "order")
    assert order == ["localStorage"], f"detection order is {order}"
    assert "localStorage" in _quoted_list(block, "caches")


def test_flat_dotted_keys_do_not_shadow_a_nested_branch():
    """The bundles mix nested objects with flat dotted keys (``settings.plugins.orphans``
    sits as a literal key beside ``settings.plugins.public``). i18next resolves both, but
    when a parent carries a nested branch of the same name as a flat key's first token,
    which one wins is i18next's precedence and not the caller's — so the two may not
    coexist under one parent."""
    for locale in ("de", "en"):
        for parent, key, path in _flat_dotted(_bundle(locale)):
            first = key.split(".")[0]
            assert not isinstance(parent.get(first), dict), (
                f"{locale}: {path} is both a flat key and a nested branch"
            )


def _flat_dotted(node: object, prefix: str = ""):
    """Every dict key that itself carries a dot, with its parent and dotted path."""
    out = []
    for key, value in node.items():  # type: ignore[union-attr]
        path = f"{prefix}.{key}" if prefix else key
        if "." in key:
            out.append((node, key, path))
        if isinstance(value, dict):
            out.extend(_flat_dotted(value, path))
    return out


def _container_shape(value: object) -> str:
    if isinstance(value, list):
        return "list[" + ",".join(sorted(_container_shape(item) for item in value)) + "]"
    if isinstance(value, dict):
        return "dict{" + ",".join(f"{k}:{_container_shape(v)}" for k, v in sorted(value.items())) + "}"
    return type(value).__name__


def test_object_valued_entries_stay_symmetric():
    """``settings.modelOptions`` holds an array of option objects rather than a string,
    so i18next hands it back only under ``returnObjects``. Both locales have to carry
    the same shape, or a consumer reads a different number of rows per language."""
    shapes = {
        locale: {p: _container_shape(v) for p, v in _leaves(_bundle(locale)).items() if not isinstance(v, str)}
        for locale in ("de", "en")
    }
    assert shapes["de"] == shapes["en"], f"object-valued keys differ: {shapes}"


def test_no_scalar_translation_resolves_to_a_blank_string():
    for locale in ("de", "en"):
        blank = [
            path
            for path, value in _leaves(_bundle(locale)).items()
            if isinstance(value, str) and not value.strip()
        ]
        assert blank == [], f"{locale}: {len(blank)} key(s) render nothing, first {blank[:3]}"


def test_interpolation_names_agree_in_both_locales():
    """A name carried on one side only leaves the other rendering ``{{name}}``."""
    de, en = _leaves(_bundle("de")), _leaves(_bundle("en"))
    mismatched = [
        key
        for key in set(de) & set(en)
        if isinstance(de[key], str)
        and isinstance(en[key], str)
        and set(PLACEHOLDER.findall(de[key])) != set(PLACEHOLDER.findall(en[key]))
    ]
    assert mismatched == [], f"{len(mismatched)} key(s) with unequal placeholders: {mismatched[:5]}"


def test_placeholders_use_the_double_brace_syntax():
    for locale in ("de", "en"):
        offenders = [
            k
            for k, v in _leaves(_bundle(locale)).items()
            if isinstance(v, str) and SINGLE_BRACE.search(v)
        ]
        assert offenders == [], f"{locale}: single-brace placeholder in {offenders[:5]}"


def _plural_families(bundle: dict) -> dict[str, set[str]]:
    families: dict[str, set[str]] = {}
    for key in _leaves(bundle):
        match = PLURAL_SUFFIX.search(key)
        if match:
            families.setdefault(PLURAL_SUFFIX.sub("", key), set()).add(match.group(1))
    return families


def test_plural_families_carry_the_same_forms_in_both_locales():
    de, en = _plural_families(_bundle("de")), _plural_families(_bundle("en"))
    assert de, "no plural keys found; the check would be vacuous"
    mismatched = [(base, de.get(base), en.get(base)) for base in set(de) | set(en) if de.get(base) != en.get(base)]
    assert mismatched == [], f"{len(mismatched)} plural famil(y/ies) differ: {mismatched[:5]}"
