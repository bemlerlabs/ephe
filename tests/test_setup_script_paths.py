"""setup.sh / install.sh must only reference paths that exist in this repo.

Why this file exists: ``setup.sh`` carried a whole generation of stale paths at
once — ``SCRIPT_DIR="$(...)/v2"``, ``cd dashboard``, ``node server/index.js``,
port 5173 — none of which exist since the app moved into ``app/``. With
``set -e`` the script died on its third line, so the documented one-command
install (AGENTS.md: a first-class product surface) could not run on any machine,
and no test noticed because nothing checked the script against the tree.

Two rules, in this order:

1. ROOT ANCHOR — the first segment of every repo-relative path the script
   mentions has to be a real entry of the repository root. This is what
   ``v2/`` and ``dashboard/`` violated.
2. TARGET EXISTS — the path itself has to exist, unless it is something the
   script (or a build) creates: ``.venv/``, ``app/dist/``, ``$HOME/...``,
   ``/tmp/...``. This is what ``server/index.js`` violated — ``server/`` is
   real, that file never was.

Plus explicit pins for the historic defects, so a future "cleanup" cannot
restore them by accident.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["setup.sh", "install.sh"]

# Paths a script is allowed to create; they cannot be expected on disk.
GENERATED_PREFIXES = (".venv", "app/dist", "app/node_modules", "node_modules", "dist")

# A path segment shorter than this (e.g. the "Y" of a "[Y/n]" prompt) is not a
# path.
MIN_SEGMENT_LEN = 2

# File extensions that mark a real file reference in a shell script.
KNOWN_EXT = r"(?:py|sh|json|ya?ml|toml|html|md|js|mjs|tsx|ps1)"

# Where a path can actually be used in these scripts. Prose is never inspected:
# a quoted sentence with a slash in it ("Desktop/PWA") is not a path operand,
# and comments are dropped before extraction.
#
# POSITIONAL patterns yield a path by grammar alone: the argument of `cd` or of
# a `-d` test IS a directory, so a bare name like `dashboard` still counts —
# that is exactly the shape of the bug this file exists to catch.
POSITIONAL = (
    # [[ -d "x" ]], [[ ! -d $HOME/y ]], [ -d z ]
    re.compile(r"\[\[?\s*!?\s*-d\s+\"?([^\]\"\s]+)"),
    # cd x / cd "x"
    re.compile(r"(?<![\w-])cd\s+\"?([^\s;&|\"#]+)"),
    # pnpm --dir "x" / npm --prefix x
    re.compile(r"--(?:dir|prefix)\s+\"?([^\s;&|\"#]+)"),
)

# SHAPE patterns only count when the token itself looks like a path.
SHAPE = (
    # [[ -f "x" ]] / [[ -e x ]]
    re.compile(r"\[\[?\s*!?\s*-[fe]\s+\"?([^\]\"\s]+)"),
    # a quoted string that is nothing but a path
    re.compile(r"\"([\w.$@{}/+-]+)\""),
    # an unquoted command argument that names a file with a known extension
    re.compile(r"(?<![\w./-])([\w.$@{}/+-]+\.(?:%s))(?![\w-])" % KNOWN_EXT),
)


def _scripts() -> list[Path]:
    missing = [s for s in SCRIPTS if not (REPO_ROOT / s).is_file()]
    assert not missing, f"installer script(s) missing from the repository root: {missing}"
    return [REPO_ROOT / s for s in SCRIPTS]


def _looks_like_path(token: str) -> bool:
    # A leading `-` is a flag (`cd -- "$dir"`), never a path.
    if "://" in token or token.startswith(("~", "/", "-")):
        return False
    if any(ch in token for ch in "*?[]"):
        return False
    return bool(re.fullmatch(r"[\w.$@{}/+-]+", token))


def _normalise(token: str) -> str:
    out = token.strip().strip('"').strip("'")
    while out.startswith("./"):
        out = out[2:]
    return out


# Which variable a path is anchored to decides whether the rest is a repository
# path at all: $HOME/... is the user's machine, $PROJECT_DIR/... is the checkout,
# and an unknown variable ($PORT) carries no information about the tree.
HOME_VARS = {"HOME", "HOME_DIR"}
ROOT_VARS = {"PROJECT_DIR", "SCRIPT_DIR", "INSTALL_DIR", "EPHE_INSTALL_DIR", "REPO_ROOT"}
VAR_AT_START = re.compile(
    r"^\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))(?P<rest>/.*)?$"
)


def _resolve_vars(token: str) -> str | None:
    """Repository-relative view of a token, or None when it is not one."""
    match = VAR_AT_START.match(token)
    if not match:
        return token
    name = match.group(1) or match.group(2)
    rest = match.group("rest")
    if name in HOME_VARS:
        return None
    if name in ROOT_VARS:
        return (rest or "").lstrip("/")
    return None


def _candidate_paths(text: str) -> list[str]:
    out: set[str] = set()
    quoted = re.compile(r'"[^"]*"|\'[^\']*\'')
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        positional = [m.group(1) for p in POSITIONAL for m in p.finditer(line)]
        shape = [m.group(1) for p in SHAPE[:2] for m in p.finditer(line)]
        # The extension rule only sees the bare line: `Node.js` inside a quoted
        # message is prose, not a file the script touches.
        shape += [m.group(1) for m in SHAPE[2].finditer(quoted.sub(" ", line))]
        for token, by_position in [(t, True) for t in positional] + [
            (t, False) for t in shape
        ]:
            resolved = _normalise(token)
            if not _looks_like_path(resolved):
                continue
            resolved = _normalise(_resolve_vars(resolved) or "")
            if not resolved or resolved == "..":
                continue
            if not by_position and "/" not in resolved:
                if not re.search(rf"\.{KNOWN_EXT}$", resolved):
                    continue
            if not all(len(seg) >= MIN_SEGMENT_LEN for seg in resolved.split("/")):
                continue
            out.add(resolved)
    return sorted(out)


def _is_generated(path: str) -> bool:
    return any(
        path == prefix or path.startswith(prefix + "/") for prefix in GENERATED_PREFIXES
    )


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_every_referenced_repo_path_exists(script: Path) -> None:
    """GIVEN an installer script  WHEN its path references are resolved
    THEN each one is anchored in the repository root and points at a real
    target (or at something the script itself creates)."""
    text = script.read_text(encoding="utf-8")
    root_entries = {p.name for p in REPO_ROOT.iterdir()}

    broken_anchor: list[str] = []
    missing_target: list[str] = []
    for ref in _candidate_paths(text):
        # Anything the script or a build creates cannot be expected on disk —
        # neither its root anchor nor its target.
        if _is_generated(ref):
            continue
        first = ref.split("/")[0]
        if first not in root_entries:
            broken_anchor.append(ref)
            continue
        if not (REPO_ROOT / ref).exists():
            missing_target.append(ref)

    assert not broken_anchor, (
        f"{script.name} references paths whose first segment is not in the "
        f"repository root: {sorted(broken_anchor)}"
    )
    assert not missing_target, f"{script.name} references paths that do not exist: {sorted(missing_target)}"


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_no_pre_move_layout_survives(script: Path) -> None:
    """The generation of paths from before the app moved into ``app/``."""
    text = script.read_text(encoding="utf-8")
    forbidden = {
        "v2/": "the old subdirectory the whole script used to cd into",
        "dashboard": "the old frontend directory (it is app/ now)",
        "server/index.js": "there was never a Node backend; it is run_server.py",
        "localhost:5173": "5173 is the Vite dev server, not the product server",
        "hostname -I": "Linux-only flag; it prints an empty host on macOS",
    }
    hits = [label for needle, label in forbidden.items() if needle in text]
    assert not hits, f"{script.name} reintroduced stale assumptions: {hits}"


def test_setup_sh_targets_the_real_product_surface() -> None:
    """setup.sh has to install, build and start the things that exist."""
    text = (REPO_ROOT / "setup.sh").read_text(encoding="utf-8")
    assert "run_server.py" in text, "setup.sh must start the Python product server"
    assert "app/dist" in text, "setup.sh must build the PWA the server serves"
    assert "8765" in text, "setup.sh must name the product port"
    # The frontend install has to happen inside app/ — a `pnpm --dir`/`npm
    # --prefix` call from the repository root makes corepack ignore the pinned
    # packageManager in app/package.json.
    assert re.search(r"cd\s+\"?[^\n]*/app\"?\b", text), (
        "setup.sh must change into app/ for the frontend install and build"
    )
    assert re.search(r"(pnpm|npm)\s+install", text), "setup.sh must install frontend deps"
    assert re.search(r"(pnpm|npm)\s+(--\S+\s+)*run\s+build", text), "setup.sh must build the PWA"


def test_the_detector_catches_the_script_that_started_this() -> None:
    """Audit of the instrument: the stale lines setup.sh actually shipped with
    have to be reported by the rules above. A guard that cannot see the bug it
    was written for is decoration."""
    historic = "\n".join(
        [
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/v2"',
            'cd "$SCRIPT_DIR"',
            "npm install --silent",
            "cd dashboard && npm install --silent",
            "npm run build --silent",
            "cd ..",
            "node server/index.js &",
            'echo "  Öffne im Browser:  http://localhost:5173"',
        ]
    )
    found = _candidate_paths(historic)
    assert "dashboard" in found, f"`cd dashboard` must be reported, got {found}"
    assert "server/index.js" in found, f"the Node backend must be reported, got {found}"

    root_entries = {p.name for p in REPO_ROOT.iterdir()}
    broken = [p for p in found if p.split("/")[0] not in root_entries]
    missing = [
        p
        for p in found
        if p.split("/")[0] in root_entries and not _is_generated(p)
        and not (REPO_ROOT / p).exists()
    ]
    assert broken == ["dashboard"], broken
    assert missing == ["server/index.js"], missing


def test_the_detector_actually_finds_the_live_paths() -> None:
    """The other direction: on the current scripts the rules must still see the
    paths that matter, or the guard is vacuous."""
    seen = set()
    for script in _scripts():
        seen.update(_candidate_paths(script.read_text(encoding="utf-8")))
    for expected in ("app/package.json", "app/pnpm-lock.yaml", "run_server.py", "pyproject.toml"):
        assert expected in seen, f"the detector stopped seeing {expected} (found: {sorted(seen)})"


def test_the_layout_the_installers_assume_is_still_there() -> None:
    """If this fails, both installers went stale at once — the exact situation
    setup.sh was in: the app moved into ``app/`` and nothing said so."""
    for entry in ("app", "app/package.json", "run_server.py", "pyproject.toml", "server"):
        assert (REPO_ROOT / entry).exists(), f"repository layout changed: {entry} is gone"


def test_setup_sh_does_not_choose_an_engine() -> None:
    """Fail-closed / offline-first guard: the installer never installs an AI and
    never pulls a model — the engine is the user's decision (AGENTS.md)."""
    text = (REPO_ROOT / "setup.sh").read_text(encoding="utf-8")
    assert "ollama pull" not in text, "the installer must not download a model"
    assert not re.search(r"curl[^\n]*ollama[^\n]*\|\s*sh", text), (
        "the installer must not pipe a vendor script into a shell"
    )
    for invented in ("EPHE_MODEL_PROVIDER", "EPHE_OPENAI_COMPAT_API_KEY", "EPHE_OPENAI_COMPAT_BASE_URL"):
        assert invented not in text, f"setup.sh must not set {invented} — no silent engine default"
