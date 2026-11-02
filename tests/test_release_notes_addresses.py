"""The release body a person reads is the changelog block with the register's addresses off.

`scripts/release_notes.py` cuts the `## [version]` block out of CHANGELOG.md and hands it to the
release, and the desktop update window renders it as the notes of the version it is about to
install. Every entry in the changelog ends with the commit it was landed by — (`86521560`), or
three of them across a wrapped line — because the register is read as an address book. In the
update window those hex digits stand where a sentence ended and say nothing to the person
deciding whether to install, so the body is printed without them. `--addresses` still prints the
block as written, which is what the register's own tools read.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"

_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

BLOCK = """## [0.5.5] - 2026-11-02

### Fixed

- server: The audio route describes its upload in the shelf language (`86521560`)
- desktop: The update names which of the three outcomes it reached — refreshed, still
  running, refused with its reason — and ends in a restart the surface offers instead of a
  sentence about one (`1228a4c6`,
  `dd51da76`, `13b259ea`)
- settings: The page keeps `dist` as the folder it means (`1234567`)
"""


def test_the_addresses_leave_and_the_words_stay():
    body = mod.strip_addresses(mod.section_body(BLOCK, "0.5.5"))
    assert "(`" not in body
    assert "86521560" not in body
    assert "dd51da76" not in body
    assert "shelf language" in body
    assert "sentence about one" in body
    # An inline code word that is not an address is not touched.
    assert "`dist`" in body


def test_no_line_is_left_hanging_where_an_address_stood():
    body = mod.strip_addresses(mod.section_body(BLOCK, "0.5.5"))
    for line in body.splitlines():
        assert line == line.rstrip(), line


def test_the_block_keeps_its_own_shape():
    body = mod.strip_addresses(mod.section_body(BLOCK, "0.5.5"))
    assert body.startswith("### Fixed")
    assert body.count("- ") == 3


def test_the_register_rendering_is_untouched():
    raw = mod.section_body(BLOCK, "0.5.5")
    assert "(`86521560`)" in raw
