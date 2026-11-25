"""The settings surface must not lie (wave I1, counter I3).

A field in the deep schema is a control only if somebody reads the value. The
live audit against our own seam found 55 of 87 fields with no consumer at all —
including six under 'Sicherheit', two of them defaulting to True with names like  # language-gate: ignore (quoted German setting names as shipped)
"Skripte automatisch freigeben". The surface promised an approval policy the  # language-gate: ignore (quoted German setting names as shipped)
code never exercised. That is not a single-field problem, it is a capital error
in a surface whose purpose is building trust.

I3 exposed the counter itself: it searched the *last name component* as a
substring in the corpus. That let 28 fields count as wired although they never
were — `kanban.board` matched 'onboarding', `zeit.timezone` matched the Python
module import, `engine.top_k` matched the retrieval vocabulary of core/memory.py,
`advanced.fuel_budget` matched an env function of the same name. So what got
counted was a possible reader, not a real one.

New standard: a field is wired when a consumer calls it by its full key through
the accessor line — `deep_bool("appearance.update_check")` (Python) or
`deepValue('appearance.theme')` (client). A substring in a name, a comment or a
foreign domain no longer counts. An unknown key raises inside the line itself, so
a typo cannot stay silent.

Hence two rules:
1. 'safety.*' no longer leads the register — the approval policy lives in
   security.json and has its real control in the privacy section.
2. For the rest a measured debt list applies that may only shrink: existing debt
   stays visible, new debt fails the test (frozen-baseline pattern, the way the
   architecture wall does it for file sizes).
"""
from __future__ import annotations

import re
from pathlib import Path

from core.settings_schema import SCHEMA

from tests.support import shipped_copy

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("core", "server", "app/src")
SOURCE_FILES = ("ephe_cli.py", "ephe.py")
SKIP_PARTS = {"node_modules", "dist", "__pycache__", ".venv", "tests"}
# The register itself and its description texts cannot be readers.
SKIP_FILES = {"settings_schema.py", "settings_hints.py"}

# deep_value/deep_bool/... (Python, snake_case) and deepValue/... (client) with
# the full field key as first argument — that is the read in use.
ACCESSOR_CALL = re.compile(
    r"""deep(?:_|)?(?:value|bool|number|select|text)\s*\(\s*['"]([a-z_]+\.[a-z_0-9]+)['"]""",
    re.IGNORECASE,
)


def _is_corpus_file(path: Path) -> bool:
    if path.suffix not in {".py", ".ts", ".tsx"}:
        return False
    # Test files under app/src call the line without any user benefiting from it
    # — a field counts as a control only once production code reads it (the
    # Python side excludes tests/ through SKIP_PARTS).
    name = path.name
    return not (
        name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or "__tests__" in path.parts
    )


def _corpus() -> str:
    """The bulk text of every place that can read a value — without the schema itself."""
    chunks: list[str] = []
    for rel in (*SOURCE_DIRS, *SOURCE_FILES):
        base = ROOT / rel
        paths = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in paths:
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.name in SKIP_FILES or not _is_corpus_file(path):
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(chunks)


CORPUS = _corpus()


def _read_keys() -> set[str]:
    return {match.group(1) for match in ACCESSOR_CALL.finditer(CORPUS)}


def _fields_without_consumer() -> set[str]:
    return set(SCHEMA) - _read_keys()


# I3-6: the debt list is empty. The register carries only fields a consumer
# calls through the line — 71 fields without a reader were struck instead of
# being dragged along. The list stays as a mechanism: a new field without a
# reader turns this test red, and a field that has long been read must not stay
# here as debt.
REGISTERED_DEBT: frozenset[str] = frozenset()


def test_the_register_is_the_yardstick() -> None:
    """The counter must not run against a field the register does not know."""
    assert _read_keys() <= set(SCHEMA), sorted(_read_keys() - set(SCHEMA))[:5]


def test_safety_is_not_a_second_approval_switch() -> None:
    """The approval policy has exactly one source (security.json + privacy section)."""
    doppelt = sorted(k for k in SCHEMA if k.startswith("safety."))
    assert not doppelt, f"safety fields in the expert register write past security.json: {doppelt}"


def test_a_new_field_without_a_reader_fails() -> None:
    """New control = new reader. Growing the debt is a failure case."""
    added_fields = sorted(_fields_without_consumer() - set(REGISTERED_DEBT))
    assert not added_fields, (
        f"new controls without a consumer — wire them or delete them, never leave them standing: {added_fields}"
    )


def test_the_debt_list_does_not_go_stale() -> None:
    """A field that is long since wired must not keep running here as debt."""
    veraltet = sorted(set(REGISTERED_DEBT) - _fields_without_consumer())
    assert not veraltet, (
        f"REGISTERED_DEBT contains wired fields — shorten the list: {veraltet}"
    )


def test_the_three_real_readers_are_covered() -> None:
    """What actually feeds the line is fixed — the three domain readers of I1/I2."""
    assert _read_keys() >= {
        "appearance.update_check",
        "plugins.plugin_autorun",
        "plugins.plugin_signature_check",
    }


def test_a_sentence_about_a_switched_off_field_names_the_control_by_its_label() -> None:
    """The update dialog explains a state the register owns, so it uses the register's name.

    The leaf is shown when the check answers `enabled: false` (app/src/lib/updateCheckRun.ts
    turns that into phase `unsupported`, app/src/lib/useUpdateCheck.ts picks the leaf), which
    is one field of this register. The sentence used to state that the settings offered no
    control for it while the panel had been rendering one for waves. Reading the locale
    bundles is the allowed exception in tests/AGENTS.md: a locale is data the product loads,
    the way the plist and the bundle are read elsewhere.
    """
    title_key = SCHEMA["appearance.update_check"]["labelKey"]
    for bundle in ("de", "en"):
        text = shipped_copy.shipped(bundle)
        leaf = text["update"]["disabledHint"]
        # The sentence has to name the control the reader sees in this language, and that
        # title is the same leaf the panel resolves — a copy of it in the update namespace
        # would be a second source that can go stale against the one it claims to name.
        title = shipped_copy.resolve(bundle, title_key)
        assert title in leaf, f"{bundle}: the hint does not name the control ({title!r}): {leaf}"
