"""The chromadb removal is a reading of this tree, and a reading needs a reader.

Nothing above 1.5.9 ever closed the advisories that sat on chromadb (Dependabot,
2026-10-14). The owner's rule is that a finding which cannot be closed by a version must not
ship at all, so the package left the product instead of being argued away: `pyproject.toml`
and `uv.lock` no longer carry it, `core/memory_chroma.py` is gone, and both the memory store
and the vision store run on `core/memory_kepta.py`.

That closes those rows by removing the ground they stood on, and a later commit can put
the ground back by accident. This file is the reader for the state, where
`tests/test_chroma_server_fence.py` used to be the reader for the acceptance. It holds three
things: the dependency is absent from both lockfiles, no shipped module imports it, and the
server surface those advisories are about stays absent too — because an import is how the
acceptance would come back.

`scripts/import_legacy_store.py` is the one exception and it is marked: the lines that name
the package carry `# gate:legacy`, and the read runs under `uv run --with …` in an
environment of its own, so the vulnerable library is never installed beside the app. The
migration itself is covered by `tests/test_import_legacy_store.py`.

The fifth alert is glib (GHSA-wrw7-89jp-8q8g) and it stays open, measured on 2026-10-14:
`cargo update -p glib --precise 0.20.0` is refused because `gtk v0.18.2` requires
`glib = "^0.18"`, `tauri 2.12.3` pins that `gtk`, and the `gtk` release that would carry a
glib 0.20 — `gtk` 0.20 — does not exist on crates.io at all (newest is 0.19.0). So the last
test here holds our own Rust sources instead: they never name `glib::VariantStrIter`, the
unsound type that record is about.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.toml_compat import tomllib

ROOT = Path(__file__).resolve().parents[1]

RETIRED = "chromadb"

#: Where the product could stand a reachable Chroma server up, or wire its authorization in.
#: The shell scripts are listed because `chroma run` is a command, not an import.
PY_ROOTS = ("core", "server", "scripts", "ui")
PY_FILES = ("run_server.py", "ephe.py", "ephe_cli.py")

#: The one file allowed to name the retired package, and only on a marked line.
LEGACY_READER = ROOT / "scripts" / "import_legacy_store.py"

#: Each entry is (the name a failure prints, the pattern that must never match). The first six
#: are the surface the four removed rows were about; the last three are the Settings route to
#: a server host that the six do not spell out.
FORBIDDEN = (
    (f"{RETIRED}.HttpClient",
     re.compile(rf"{RETIRED}\s*\.\s*HttpClient\b|from\s+{RETIRED}\s+import\s+[^\n]*\bHttpClient\b")),
    (f"{RETIRED}.app",
     re.compile(rf"{RETIRED}\s*\.\s*app\b|from\s+{RETIRED}\s+import\s+[^\n]*\bapp\b")),
    ("chroma run",
     re.compile(r"\bchroma\s+run\b")),
    ("trust_remote_code",
     re.compile(r"\btrust_remote_code\b")),
    ("AuthorizationProvider",
     re.compile(r"\bAuthorizationProvider\b")),
    ("SimpleRBAC",
     re.compile(r"\bSimpleRBAC\w*\b")),
    ("chroma_api_impl",
     re.compile(r"\bchroma_api_impl\b")),
    ("chroma_server_host",
     re.compile(r"\bchroma_server_host\b")),
    (f"{RETIRED}.api.fastapi",
     re.compile(rf"{RETIRED}\s*\.\s*api\s*\.\s*fastapi\b")),
)

#: Every way an import of the retired package can be written.
IMPORT_RE = re.compile(
    rf"^\s*(?:import\s+{RETIRED}\b|from\s+{RETIRED}(?:\.[\w.]+)?\s+import\b)"
)

GLIB_SOURCES = ROOT / "app" / "src-tauri" / "src"


def _scanned_files() -> list[Path]:
    """Every shipped file the product could stand a Chroma server up from."""
    files = [p for root in PY_ROOTS for p in sorted((ROOT / root).rglob("*.py"))]
    files += [ROOT / name for name in PY_FILES]
    files += sorted(ROOT.glob("*.sh"))
    files += sorted((ROOT / "scripts").glob("*.sh"))
    return [p for p in files if p.is_file()]


def _hits() -> list[str]:
    """`path:line: name` for every forbidden name found in the shipped tree."""
    found: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in FORBIDDEN:
                if pattern.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    return found


def _imports_of_retired() -> list[str]:
    """`path:line` for every import of the retired package, marked lines excepted."""
    found: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if IMPORT_RE.search(line) and "# gate:legacy" not in line:
                found.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:80]}")
    return found


def test_the_declared_dependencies_carry_no_trace_of_the_retired_package():
    """`pyproject.toml` is the promise the lock is resolved from."""
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = list(manifest["project"]["dependencies"])
    declared += list(manifest["project"].get("optional-dependencies", {}).get("dev", []))
    named = [d for d in declared if RETIRED in d.lower()]
    assert not named, f"pyproject.toml still declares {named}"
    constraints = manifest.get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
    assert not [c for c in constraints if RETIRED in c.lower()], constraints


def test_the_lock_resolves_no_package_whose_name_carries_the_retired_one():
    """The lock is what CI installs, so an absent dependency has to be absent here."""
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    blocks = lock.split("[[package]]")[1:]
    names = [re.search(r'name = "([^"]+)"', b).group(1) for b in blocks
             if re.search(r'name = "([^"]+)"', b)]
    assert names, "uv.lock parsed to no package blocks"
    named = [n for n in names if RETIRED in n]
    assert not named, f"uv.lock still resolves {named}"
    manifest = re.search(r"^\[manifest\]\s*$(.*?)(?=^\[\[package\]\])", lock, re.S | re.M)
    assert manifest, "uv.lock has no [manifest] block before its first [[package]]"
    assert RETIRED not in manifest.group(1), "uv.lock's [manifest] still names the package"


def test_no_shipped_module_imports_the_retired_package():
    hits = _imports_of_retired()
    assert not hits, (
        "the retired package is imported again. It left the product because advisories on it "
        "had no release to move to; the one read that still needs it belongs in "
        "scripts/import_legacy_store.py behind a `# gate:legacy` marker:\n  " + "\n  ".join(hits)
    )


def test_the_legacy_reader_is_the_only_marked_exception():
    """The exception is a file, its lines are marked, and it fails closed without the package."""
    assert LEGACY_READER.is_file(), f"missing {LEGACY_READER.relative_to(ROOT)}"
    text = LEGACY_READER.read_text(encoding="utf-8")
    importing = [line.strip() for line in text.splitlines() if IMPORT_RE.search(line)]
    assert importing, "the legacy reader no longer imports the package it reads"
    unmarked = [line for line in importing if "# gate:legacy" not in line]
    assert not unmarked, f"unmarked imports in the legacy reader: {unmarked}"
    assert "SystemExit" in text, (
        "the legacy reader must refuse loudly when the package is absent, which is its "
        "normal state in this venv"
    )


def test_the_scan_still_reads_the_shipped_files_it_names():
    """A moved store or launch script would leave the fence scanning nothing."""
    scanned = _scanned_files()
    names = {str(p.relative_to(ROOT)) for p in scanned}
    for needed in ("core/vision_memory.py", "core/memory.py", "core/memory_provider.py",
                   "scripts/import_legacy_store.py", "run_server.py", "setup.sh", "dev.sh"):
        assert needed in names, f"the scan no longer reads {needed}"
    # Every root that exists has to contribute, or a rename quietly shrank the fence.
    for root in PY_ROOTS:
        directory = ROOT / root
        if directory.is_dir():
            assert any(n.startswith(f"{root}/") for n in names), f"{root}/ contributes nothing"


def test_no_chroma_server_surface_is_built_in_the_shipped_tree():
    hits = _hits()
    assert not hits, (
        "a reachable Chroma server surface appeared in the product. The advisories that "
        "left .github/advisories-ignore.txt on 2026-10-14 are about that surface, and the "
        "removal is what closed them:\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize(
    ("name", "plant"),
    [
        (f"{RETIRED}.HttpClient", f"client = {RETIRED}.HttpClient(host='localhost', port=8000)"),
        (f"{RETIRED}.app", f"from {RETIRED} import app"),
        ("chroma run", "chroma run --path /tmp/chroma-db --port 8000"),
        ("trust_remote_code", "model = AutoModel.from_pretrained(repo, trust_remote_code=True)"),
        ("AuthorizationProvider", "class BasicAuthorizationProvider(AuthorizationProvider): ..."),
        ("SimpleRBAC", "provider = SimpleRBACAuthorizationProvider()"),
        ("chroma_api_impl", f'Settings(chroma_api_impl="{RETIRED}.api.fastapi.FastAPI")'),
        ("chroma_server_host", "Settings(chroma_server_host=host)"),
        (f"{RETIRED}.api.fastapi", f"import {RETIRED}.api.fastapi"),
    ],
)
def test_each_forbidden_name_fires_on_its_own_plant(name, plant):
    matched = [label for label, pattern in FORBIDDEN
               if any(pattern.search(line) for line in plant.splitlines())]
    assert name in matched, f"planting {name} would not trip the fence: matched {matched}"


@pytest.mark.parametrize(
    "plant",
    [
        f"import {RETIRED}",
        f"    import {RETIRED}  # noqa",
        f"import {RETIRED}.api",
        f"from {RETIRED} import PersistentClient",
        f"from {RETIRED}.utils.embedding_functions import DefaultEmbeddingFunction",
    ],
)
def test_every_spelling_of_the_import_trips_the_import_fence(plant):
    assert IMPORT_RE.search(plant), f"this import would slip past: {plant!r}"


def test_glib_unsoundness_has_no_call_site_in_our_rust_sources():
    """GHSA-wrw7-89jp-8q8g names glib::VariantStrIter; our Rust tree must never use it."""
    assert GLIB_SOURCES.is_dir(), (
        "app/src-tauri/src moved, so the glib not_affected reading is no longer measured here"
    )
    offenders = [
        f"{path.relative_to(ROOT)}:{lineno}"
        for path in sorted(GLIB_SOURCES.rglob("*.rs"))
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if "VariantStrIter" in line
    ]
    assert not offenders, (
        "our own Rust code now names glib::VariantStrIter, the type GHSA-wrw7-89jp-8q8g is "
        "about, so the alert can no longer be dismissed as not_affected:\n  " + "\n  ".join(offenders)
    )
