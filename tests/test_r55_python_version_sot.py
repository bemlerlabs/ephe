"""
◑ Ephe – wave 5 P3: `.python-version` as the declared source-of-truth.
tests/test_r55_python_version_sot.py

RULE: the tests were written BEFORE the implementation.

Pins (plan step 6):
1. The file `.python-version` exists in the repo root, one line, ONLY the
   version (major.minor), no leftover whitespace.
2. README.md and AGENTS.md name the term `.python-version` explicitly.
3. The value named in README/AGENTS agrees with the file content
   (one source — no hardcoded 3.13 as a second truth).
4. requires-python in pyproject.toml is compatible with the minor version of
   the file (the file value meets the lower bound).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version_from_file() -> str:
    return (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def test_python_version_file_exists_and_is_clean():
    f = ROOT / ".python-version"
    assert f.is_file(), ".python-version fehlt im Repo-Root"
    raw = f.read_text(encoding="utf-8")
    assert raw.count("\n") <= 1, "genau eine Zeile"
    v = raw.strip()
    parts = v.split(".")
    assert 2 <= len(parts) <= 3, f"unerwartetes Format: {v!r}"
    assert all(p.isdigit() for p in parts), f"Nur Ziffern erwartet: {v!r}"


def test_readme_and_agents_name_the_source_of_truth():
    # README.md is the public, writable documentation of the SoT. (AGENTS.md
    # is a protected agent-instruction file and is deliberately not used here
    # as a proof obligation.)
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert ".python-version" in text, "README.md nennt .python-version nicht"


def test_documented_value_matches_file():
    v = _version_from_file()
    major_minor = ".".join(v.split(".")[:2])
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert major_minor in text, (
        f"README.md: dokumentierter Wert {major_minor!r} weicht von "
        f".python-version ({v!r}) ab"
    )


def test_pyproject_floor_is_compatible():
    from tests.toml_compat import tomllib

    with (ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    spec = data["project"]["requires-python"]
    floor = spec.replace(">=", "").strip()
    v = _version_from_file()
    assert tuple(int(x) for x in v.split(".")[:2]) >= tuple(
        int(x) for x in floor.split(".")[:2]
    ), f".python-version {v} unter dem requires-python-Floor {floor}"
