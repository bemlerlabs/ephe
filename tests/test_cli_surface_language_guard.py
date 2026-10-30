"""The CLI's own prose is user-visible, so it is English.

`scripts/language_inventory.py` scores tracked lines against a marker vocabulary tuned
for German function words, plus a wide second net. Both miss the installer's surface
nouns: `install.sh` measured zero German lines while printing three, and
`core/_cli_onboarding.py` measured two while printing twelve. This gate extracts the
strings a user actually reads out of those two files and scores them with the
instrument's own two predicates plus the surface nouns it misses.

The vocabulary below is German, and the pragma says so on every line that the
instrument's own marker list would count — the same escape valve the instrument uses
for its lists in `scripts/language_inventory.py:27-34`.

Given / When / Then, strictly.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVENTORY_PATH = REPO / "scripts" / "language_inventory.py"
ONBOARDING_PATH = REPO / "core" / "_cli_onboarding.py"
INSTALLER_PATH = REPO / "install.sh"


def _load_inventory():
    spec = importlib.util.spec_from_file_location("language_inventory_under_test", INVENTORY_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Loaded once: the helpers below need the instrument's own lists, and a pytest
#: fixture cannot reach module-level code.
inventory = _load_inventory()

#: German the instrument's two nets cannot see. `auswahl` and `gefunden` are absent from
#: both lists; the rest are the nouns a translator finds first. One of the fourteen is
#: reached by the wide net through a substring containing a word it already carries — it
#: stays in the list so the union reads as the finding describes it.
SURFACE_NOUNS = (  # language-gate: ignore
    "auswahl", "wahl", "unbekannte", "gefunden", "gespeichert", "speichert",  # language-gate: ignore
    "erkannt", "lokale", "live-modelle", "basis-url", "nutzen", "willst",  # language-gate: ignore
    "oder", "vorhanden",  # language-gate: ignore
)

SURFACE = re.compile(
    # A hyphen is part of a German compound (`Engine-Basis-URL`), so it does not end a
    # word here; only a letter or digit does.
    r"(?<![A-Za-z0-9])("
    + "|".join(sorted(SURFACE_NOUNS, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

#: The German the two files carried before this wave, verbatim: the eleven distinct
#: literals `git show HEAD:core/_cli_onboarding.py` printed and the installer's three.
#: They are the positive control — the zero at the bottom of this file would mean
#: nothing if the union could not see the German that demonstrably was there.
PRE_WAVE_ONBOARDING = (
    '◑ Ephe – Engine-Auswahl (einmalig, wird gespeichert)',  # language-gate: ignore
    '  [4] OpenAI-kompatible Cloud-API (z.B. Mistral / OpenAI, mit Key)',  # language-gate: ignore
    'Modell: ',
    '  ✓ Lokale Ollama-Engine erkannt (',
    'Modell [Default ',
    '  → Engine gespeichert: ',
    'Engine-Basis-URL (z.B. ',
    'OpenAI-kompatible Basis-URL (z.B. ',
    'OpenAI-kompatible Basis-URL (z.B. https://api.mistral.ai/v1): ',
    '  ✓ Live-Modelle: ',
    '  Unbekannte Wahl: ',
)
PRE_WAVE_INSTALLER = (
    'Wie willst du Ephe nutzen? [D]esktop/PWA, [C]li (TUI), oder [S]kip-Start: ',
    " -c 'import sys; print(sys.version.split()[0])') gefunden",
    '${GREEN}${BOLD}Setup fertig.${NC}',
)

# `run_quiet` takes its label first and prints it through `ok` when the step passes,
# so its label is user surface like the six calls around it.
OUTPUT_CALL = re.compile(r"^\s*(?:echo|info|warn|ok|fail|step|read|run_quiet)\b")
SHELL_STRING = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def german_hits(text: str) -> list[str]:
    """The German this project's instrument finds, plus the nouns it is blind to.

    `inventory.WORD` is the gate's own marker predicate, applied the way `hits_in`
    applies it, with no false-friend filter. `inventory.WIDE` is the second net, applied
    the way `wide_prose_hits` applies it, with the English false friends dropped — a word
    that is both German and English is a measurement artefact, not a finding.
    """
    found = list(inventory.WORD.findall(text))
    found += [w for w in inventory.WIDE.findall(text) if w.lower() not in inventory.FALSE_FRIENDS]
    return found + SURFACE.findall(text)


def python_user_strings(path: Path) -> list[str]:
    """Every string literal a Python CLI module can put in front of a user.

    The module exists to talk to the user — a `print(...)` prompt, an `input_fn(...)`
    label, an `_ask_url(...)` question — so the whole AST is read rather than a list of
    call names that would go stale the first time a prompt moves.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _joined(lines: list[str]) -> list[str]:
    """Shell lines, with a trailing backslash folding into the next line."""
    out: list[str] = []
    for line in lines:
        if out and out[-1].endswith("\\"):
            out[-1] = out[-1][:-1] + " " + line
        else:
            out.append(line)
    return out


def shell_user_strings(path: Path) -> list[str]:
    """The quoted text install.sh hands to echo, read, info, warn, ok, fail or step.

    Those seven calls are the whole user surface of the script; a comment or a
    variable assignment is not shown to anyone.
    """
    strings: list[str] = []
    for line in _joined(path.read_text(encoding="utf-8").splitlines()):
        if not OUTPUT_CALL.match(line):
            continue
        strings += [double or single for single, double in SHELL_STRING.findall(line)]
    return strings


def offences(strings: list[str]) -> list[tuple[str, list[str]]]:
    """The strings that carry German, with the words that made them German."""
    return [(s, german_hits(s)) for s in strings if german_hits(s)]


def test_given_the_two_files_when_extracted_then_the_user_surface_is_not_empty():
    """
    GIVEN the guard reads the installer and the onboarding module
    WHEN it extracts their user-visible strings
    THEN both extractions hold the lines a reader sees, so an empty set can never
         pass the zero below by accident.
    """
    onboarding = python_user_strings(ONBOARDING_PATH)
    installer = shell_user_strings(INSTALLER_PATH)

    assert any("engine setup" in s for s in onboarding)
    assert any("ephe configure" in s for s in onboarding)
    assert any("Dependencies installed" in s for s in installer)
    assert any("Setup complete" in s for s in installer)
    assert len(installer) > 20, f"the installer extractor found only {len(installer)} strings"


def test_given_the_instruments_two_nets_alone_when_scored_then_the_surface_nouns_are_invisible():
    """
    GIVEN the marker list and the wide net `scripts/language_inventory.py` ships
    WHEN the surface nouns are scored with them
    THEN twelve of the fourteen come back clean — which is why this guard adds them,
         and why the installer measured zero German lines while printing three.
    """
    seen = {n for n in SURFACE_NOUNS if inventory.WORD.search(n) or inventory.WIDE.search(n)}
    invisible = set(SURFACE_NOUNS) - seen

    # The wide net reaches two of them through a substring: `modelle` inside  # language-gate: ignore
    # `live-modelle`, and `speichert`.  # language-gate: ignore
    assert {"live-modelle", "speichert"} <= seen, f"the nets lost a word they used to have: {sorted(seen)}"
    assert invisible >= {
        "auswahl", "wahl", "unbekannte", "gefunden", "gespeichert", "erkannt",
        "lokale", "basis-url", "nutzen", "willst", "oder", "vorhanden",
    }, f"the instrument now sees most of the vocabulary: {sorted(seen)}"


def test_given_the_pre_wave_german_when_scored_then_the_union_flags_every_line():
    """
    GIVEN the German the two files carried before this wave
    WHEN the union scores it
    THEN every line is a finding — the counter-proof that the zero below is a
         measurement and not an empty vocabulary.
    """
    missed = [s for s in (*PRE_WAVE_ONBOARDING, *PRE_WAVE_INSTALLER) if not german_hits(s)]

    assert missed == [], f"the union cannot see the German this gate exists for: {missed}"


def test_given_core_cli_onboarding_when_scored_then_no_user_visible_string_is_german():
    """
    GIVEN the first screen a CLI user meets (`ephe configure`, `ephe tui`)
    WHEN every string literal in `core/_cli_onboarding.py` is scored
    THEN none of them is German.
    """
    found = offences(python_user_strings(ONBOARDING_PATH))

    assert found == [], "German in the CLI's own onboarding output: " + "; ".join(
        f"{words} in {text!r}" for text, words in found
    )


def test_given_install_sh_when_scored_then_no_user_visible_string_is_german():
    """
    GIVEN the installer a newcomer runs first
    WHEN every string it echoes or prompts with is scored
    THEN none of them is German.
    """
    found = offences(shell_user_strings(INSTALLER_PATH))

    assert found == [], "German in the installer's own output: " + "; ".join(
        f"{words} in {text!r}" for text, words in found
    )
