"""Sprint2-F2 regression tests: venv/CI Python parity + PWA hygiene.

DoD (SPECK, CTO-pinned):
  1. venv on Python >=3.10, all tests green inside the venv.
  2. CI Python parity: tests.yml runs the same Python as locally (the matrix/
     lower bound covers requires-python, and the local venv version sits inside
     the CI matrix).
  3. PWA hygiene: app/public/llms.txt + robots.txt present (Lighthouse
     llms-txt/robots-txt audits -> 1.0); color-contrast fix in the
     Tailwind config (globals.css @theme) -> color-contrast audit 1.0.
  5. TDD: these tests exist BEFORE the implementation.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "app" / "public"
GLOBALS_CSS = ROOT / "app" / "src" / "styles" / "globals.css"
PYPROJECT = ROOT / "pyproject.toml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
VENV_CFG = ROOT / ".venv" / "pyvenv.cfg"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

#: `.venv` is a gitignored developer artifact and CI's interpreter comes from
#: actions/setup-python, so the two venv probes below can only run where a venv was
#: really built. The half of the same promise that CI can check is
#: `test_running_interpreter_satisfies_requires_python` — skipping the venv cases must
#: not skip the guarantee.
_HAS_LOCAL_VENV = VENV_PYTHON.exists()

WCAG_NORMAL_TEXT_RATIO = 4.5


# Helpers

def _hsl_to_srgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    """h in deg, s/l in percent -> srgb 0..1."""
    s /= 100.0
    l /= 100.0
    c = (1 - abs(2 * l - 1)) * s
    hp = h % 360 / 60
    x = c * (1 - abs(hp % 2 - 1))
    if hp < 1:
        r, g, b = c, x, 0.0
    elif hp < 2:
        r, g, b = x, c, 0.0
    elif hp < 3:
        r, g, b = 0.0, c, x
    elif hp < 4:
        r, g, b = 0.0, x, c
    elif hp < 5:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    m = l - c / 2
    return (r + m, g + m, b + m)


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def chan(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hsl_a: str, hsl_b: str) -> float:
    def parse(hsl: str) -> tuple[float, float, float]:
        # accepts both notations: the bare triplet "0 0% 100%" (gradient stops)
        # and the wrapped "hsl(0 0% 100%)" (@theme tokens since the hsl() switch,
        # needed so that color-mix(in oklab, var(--color-*), transparent) works).
        m = re.match(
            r"\s*(?:hsl\(\s*)?(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s*\)?",
            hsl,
        )
        assert m, f"unparsable hsl: {hsl!r}"
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    la = _relative_luminance(_hsl_to_srgb(*parse(hsl_a)))
    lb = _relative_luminance(_hsl_to_srgb(*parse(hsl_b)))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _theme_tokens() -> dict[str, str]:
    """Only the --color-* tokens inside the @theme block of globals.css."""
    text = GLOBALS_CSS.read_text(encoding="utf-8")
    m = re.search(r"@theme\s*\{(.*?)\n\}", text, re.DOTALL)
    assert m, "no @theme block found in globals.css"
    tokens: dict[str, str] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"\s*--([a-z0-9-]+):\s*([^/;]+)", line)
        if mm and mm.group(1).startswith("color-"):
            tokens[mm.group(1)[6:]] = mm.group(2).strip()
    return tokens


def _requires_python_min() -> tuple[int, int]:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*">=([\d.]+)"', text)
    assert m, "requires-python not found in pyproject.toml"
    parts = m.group(1).split(".")
    return int(parts[0]), int(parts[1])


def _supported_python_versions() -> list[tuple[int, int]]:
    """The 'Programming Language :: Python :: 3.X' classifiers are the
    officially supported versions. Parity target: venv & CI matrix ⊆ this set."""
    text = PYPROJECT.read_text(encoding="utf-8")
    out = set()
    for v in re.findall(r"Programming Language :: Python :: (3\.\d+)", text):
        a, b = v.split(".")
        out.add((int(a), int(b)))
    assert out, "keine Python-Klassifizierer in pyproject.toml gefunden"
    return sorted(out)


def _ci_python_matrix() -> list[tuple[int, int]]:
    text = TESTS_WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"python-version:\s*\[([^\]]+)\]", text)
    assert m, "python-version matrix not found in tests.yml"
    out = []
    for entry in re.findall(r"'(\d+)\.(\d+)'", m.group(1)):
        out.append((int(entry[0]), int(entry[1])))
    assert out, "no python versions parsed from CI matrix"
    return out


def _venv_python() -> tuple[int, int]:
    """Version of the REAL venv Python binary — not just pyvenv.cfg.

    Root-cause defence (Sprint2 fix, DEFECT 2): pyvenv.cfg is a STALE artefact
    (after a rebuild/replacement it keeps the old version), so it is not the
    single source of truth. We query the actual binary with a subprocess and
    ASSERT that it matches pyvenv.cfg. If the two differ, this helper FAILS —
    and with it every parity test that uses it — in exactly the state that was
    just discovered (cfg=3.13.5 stale, binary=3.12.13). A STALE cfg is now
    caught by the test itself.
    """
    # (1) REAL binary — source of truth
    result = subprocess.run(
        [
            str(VENV_PYTHON), "-c",
            "import sys; print(sys.version_info[0], sys.version_info[1])",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f".venv/bin/python lieferte Exit {result.returncode}: "
        f"{result.stderr.strip()}"
    )
    out = result.stdout.strip().split()
    assert len(out) == 2 and out[0].isdigit() and out[1].isdigit(), (
        f"unerwartete Versions-Output von .venv/bin/python: "
        f"{result.stdout.strip()!r}"
    )
    binary = (int(out[0]), int(out[1]))

    # (2) pyvenv.cfg — has to agree (STALE cfg = the root-cause state -> FAIL)
    cfg = _venv_cfg_python()
    assert binary == cfg, (
        f".venv inkonsistent: reale Python-Binary ist {binary[0]}.{binary[1]} "
        f"aber pyvenv.cfg sagt {cfg[0]}.{cfg[1]} (STALE-Artefakt — venv wurde "
        f"rebuildet/ersetzt, ohne pyvenv.cfg zu regenerieren). venv "
        f"konsistent neu bauen: python3.{binary[1]} -m venv .venv"
    )
    return binary


def _venv_cfg_python() -> tuple[int, int]:
    """Version from .venv/pyvenv.cfg (the cfg value alone — for cross-checking)."""
    text = VENV_CFG.read_text(encoding="utf-8")
    # Cover both legitimate venv generators: the `venv` module writes
    # `version = 3.13.xfinal...`, `uv` writes `version_info = 3.13.5`.
    m = re.search(r"^version(?:_info)?\s*=\s*(\d+)\.(\d+)", text, re.MULTILINE)
    assert m, "version not found in .venv/pyvenv.cfg"
    return int(m.group(1)), int(m.group(2))


# DoD 1 — venv on Python >=3.10

@pytest.mark.skipif(not _HAS_LOCAL_VENV, reason="no local .venv on this machine (gitignored dev artifact)")
def test_venv_python_satisfies_requires_python() -> None:
    """Skipped without a local .venv — see _running_interpreter_satisfies_requires_python
    for the version of this claim that CI can check (its interpreter comes from
    actions/setup-python; `.venv` is gitignored, so on CI the binary simply is not
    there and the FileNotFoundError was reported as a broken release gate)."""
    venv = _venv_python()
    req = _requires_python_min()
    assert venv >= req, (
        f".venv Python {venv[0]}.{venv[1]} < requires-python >= {req[0]}.{req[1]}"
    )


def test_running_interpreter_satisfies_requires_python() -> None:
    """The guarantee the venv cases aim at, measured on the interpreter in use.

    Skipping the two `.venv` cases on CI must not skip the promise: whatever Python
    runs the suite has to satisfy requires-python, or the package is being tested on
    an environment it does not claim to support.
    """
    req = _requires_python_min()
    current = (sys.version_info.major, sys.version_info.minor)
    assert current >= req, (
        f"interpreter {current[0]}.{current[1]} < requires-python "
        f">= {req[0]}.{req[1]}"
    )


# DoD 2 — CI Python parity

def test_ci_matrix_lower_bound_matches_requires_python() -> None:
    """CI may not test below requires-python (that environment does not exist
    for the package), and the matrix lower bound must match the declared lower
    bound (no dead test window)."""
    matrix = _ci_python_matrix()
    req = _requires_python_min()
    assert min(matrix) >= req, (
        f"CI-Matrix-Minimum {min(matrix)} liegt unter requires-python "
        f">= {req[0]}.{req[1]} — CI testet eine nicht unterstützte Python"
    )


@pytest.mark.skipif(not _HAS_LOCAL_VENV, reason="no local .venv on this machine (gitignored dev artifact)")
def test_local_venv_python_in_ci_matrix() -> None:
    """Parity: the venv Python used locally must come from the official supported
    set (the classifiers) and sit in the CI matrix (when CI tests only one
    version per minor, 'supported' is the yardstick — CI runs the same minor
    version as locally)."""
    venv = _venv_python()
    matrix = _ci_python_matrix()
    supported = _supported_python_versions()
    assert venv in supported, (
        f"lokale venv Python {venv[0]}.{venv[1]} nicht in den "
        f"unterstützten Versionen {supported}"
    )
    assert venv in matrix, (
        f"lokale venv Python {venv[0]}.{venv[1]} fehlt in CI-Matrix {matrix} "
        f"— CI testet dieselbe Python nicht (Parity verletzt)"
    )
    assert set(matrix) <= set(supported), (
        f"CI-Matrix {matrix} enthält Versionen außerhalb des "
        f"unterstützten Sets {supported}"
    )


# DoD 3a — llms.txt

def test_llms_txt_exists_and_valid() -> None:
    f = PUBLIC_DIR / "llms.txt"
    assert f.is_file(), "app/public/llms.txt fehlt (Lighthouse llms-txt-Audit)"
    text = f.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines, "llms.txt ist leer"
    assert lines[0].startswith("#"), "llms.txt muss mit H1-Header beginnen"
    assert any("ephe" in ln.lower() for ln in lines), (
        "llms.txt identifiziert das Projekt nicht (Ephe)"
    )
    assert len(text) >= 200, "llms.txt zu dünn (<200 chars) — kein nützlicher Kontext"
    # Lighthouse llms-txt audit: needs at least one Markdown link
    assert re.search(r"\[[^\]]+\]\(https?://[^)\s]+[)\s]", text), (
        "llms.txt muss mindestens einen Markdown-Link [text](https://...) "
        "enthalten (Lighthouse: 'File does not appear to contain any links.')"
    )


# DoD 3b — robots.txt

def test_robots_txt_exists_and_valid() -> None:
    f = PUBLIC_DIR / "robots.txt"
    assert f.is_file(), "app/public/robots.txt fehlt (Lighthouse robots-txt-Audit)"
    text = f.read_text(encoding="utf-8")
    assert re.search(r"^User-agent:\s*\*", text, re.MULTILINE | re.IGNORECASE), (
        "robots.txt braucht eine User-agent-*-Regel"
    )
    assert re.search(r"^(Allow|Disallow):", text, re.MULTILINE | re.IGNORECASE), (
        "robots.txt braucht Allow/Disallow"
    )
    # Lighthouse validates sitemap URLs strictly — http(s) only, otherwise score 0
    for m in re.finditer(r"^Sitemap:\s*(\S+)", text, re.MULTILINE | re.IGNORECASE):
        assert m.group(1).startswith(("http://", "https://")), (
            f"ungültige Sitemap-URL in robots.txt: {m.group(1)}"
        )


# DoD 3c — color contrast (Tailwind v4 @theme tokens in globals.css)

# (foreground-token, background-token) — every text/background combination the
# UI really uses from the @theme tokens. WCAG 2.1 AA: 4.5:1 for normal text.
# Finding 2026-10-01 (Ephemora redesign): the primary/accent/destructive tokens
# are shadcn compatibility shims — text-/bg-primary are not consumed anywhere in
# the UI (rg evidence), so the pairs here were removed. No single red can satisfy
# BOTH sides of 4.5:1 against the 7% background; the pairs therefore documented a
# usage that does not exist.
CONTRAST_PAIRS: list[tuple[str, str]] = [
    ("foreground", "background"),
    ("stone", "background"),
    ("mist", "background"),
    ("mist", "card"),
    ("muted-foreground", "background"),
    ("muted-foreground", "card"),
    ("firefly", "background"),
    ("firefly-glow", "background"),
    ("secondary-foreground", "secondary"),
    # (accent-foreground/destructive-foreground on accent/destructive: tokens
    #  used as a button background are not used — shadcn shims, see above.)
    ("card-foreground", "card"),
    ("foreground", "muted"),
]


@pytest.mark.parametrize("fg,bg", CONTRAST_PAIRS)
def test_token_contrast_meets_wcag_aa(fg: str, bg: str) -> None:
    tokens = _theme_tokens()
    assert fg in tokens, f"@theme-Token --color-{fg} fehlt"
    assert bg in tokens, f"@theme-Token --color-{bg} fehlt"
    ratio = _contrast_ratio(tokens[fg], tokens[bg])
    assert ratio >= WCAG_NORMAL_TEXT_RATIO, (
        f"--color-{fg} auf --color-{bg}: Kontrast {ratio:.2f}:1 "
        f"< {WCAG_NORMAL_TEXT_RATIO}:1 (WCAG AA Normaltext)"
    )


def test_no_low_contrast_gradient_text() -> None:
    """The text-gradient utility: the lightness of every gradient stop must stay
    readable as text on the main background (Lighthouse checks the achievable
    minimum contrast across the gradient)."""
    text = GLOBALS_CSS.read_text(encoding="utf-8")
    m = re.search(r"\.text-gradient\s*\{[^}]*\}", text, re.DOTALL)
    assert m, ".text-gradient Utility fehlt"
    block = re.sub(r"/\*.*?\*/", "", m.group(0), flags=re.DOTALL)  # drop comments
    stops = re.findall(r"hsl\((\d+(?:\.\d+)?) (\d+(?:\.\d+)?)% (\d+(?:\.\d+)?)%\)",
                       block)
    assert stops, "keine hsl()-Stops in .text-gradient gefunden"
    tokens = _theme_tokens()
    bg = tokens["background"]
    for stop in stops:
        hsl = f"{stop[0]} {stop[1]}% {stop[2]}%"
        ratio = _contrast_ratio(hsl, bg)
        assert ratio >= WCAG_NORMAL_TEXT_RATIO, (
            f"text-gradient-Stop {hsl} auf background: {ratio:.2f}:1 "
            f"< {WCAG_NORMAL_TEXT_RATIO}:1"
        )


# I2-1a: the CI import steps must name modules that actually exist

_IMPORT_CMD = re.compile(r"python[^\n]*-c\s*\\?\"([^\"\\]*)\"")


def _import_check_commands() -> list[str]:
    """The one-liners with which tests.yml checks the package by importing it
    ('Verify package import' locally and 'Verify installed package' in Docker)."""
    text = TESTS_WORKFLOW.read_text(encoding="utf-8")
    return [m.group(1) for m in _IMPORT_CMD.finditer(text)]


def test_ci_import_commands_exist() -> None:
    """Sanity: the parser really hits the import steps — otherwise this file
    silently checks nothing."""
    assert _import_check_commands(), "keine python -c Import-Pruefung in tests.yml"


def test_ci_imports_only_modules_that_exist() -> None:
    """I2-1a: every name inside a CI import check has to exist.

    Finding: the steps named a legacy module of this project under its former
    package name. That module does not exist (the repo holds ephe.py,
    ephe_cli.py and run_server.py), so the step could only ever fail — broken
    CI, not a matter of taste. The assertion prints the concrete name at runtime;
    it is not written literally here (the naming gate scans this file too).
    """
    offenders: list[str] = []
    for cmd in _import_check_commands():
        # only the real import statement, not the prose word in print('... import OK')
        for dotted in re.findall(r"(?:^|[;\n])\s*import\s+([A-Za-z_][\w.]*)", cmd):
            top = dotted.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            if (ROOT / f"{top}.py").exists() or (ROOT / top / "__init__.py").exists():
                continue
            offenders.append(dotted)
    assert not offenders, (
        "tests.yml importiert Module, die es im Repo nicht gibt: " + ", ".join(sorted(set(offenders)))
    )


def test_ci_docker_tag_matches_project_name() -> None:
    """The built Docker tag is named like the project (pyproject [project].name),
    and never after a legacy brand; the same name builds and tests the image."""
    text = TESTS_WORKFLOW.read_text(encoding="utf-8")
    tags = set(re.findall(r"docker build\s+-t\s+([A-Za-z0-9_.:/-]+)", text))
    assert tags, "kein docker build -t in tests.yml gefunden"
    name = re.search(r'^name\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert name, "pyproject.toml hat keinen [project].name"
    for tag in tags:
        assert tag.split(":")[0] == name.group(1), f"Docker-Tag {tag} != Projektname {name.group(1)}"
