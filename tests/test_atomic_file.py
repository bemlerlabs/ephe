"""E3: an adopted artifact lands whole or not at all.

`shutil.copyfile` truncates the destination first, so a crash mid-copy left a
half-written file under the reader's own name. `publish_file` writes beside the
target and renames it into place.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.atomic_file import publish_file


def test_the_destination_receives_every_byte(tmp_path: Path) -> None:
    source = tmp_path / "cell" / "report.md"
    source.parent.mkdir()
    source.write_bytes(b"# report\nline two\n")
    dest = tmp_path / "shelf" / "report.md"
    dest.parent.mkdir()

    published = publish_file(source, dest)

    assert published == dest
    assert dest.read_bytes() == source.read_bytes()


def test_an_existing_destination_is_replaced_without_leftovers(tmp_path: Path) -> None:
    source = tmp_path / "new.txt"
    source.write_text("new", encoding="utf-8")
    dest = tmp_path / "keep.txt"
    dest.write_text("old", encoding="utf-8")

    publish_file(source, dest)

    assert dest.read_text(encoding="utf-8") == "new"
    parts = [p.name for p in tmp_path.iterdir() if p.name.startswith(".keep.txt.")]
    assert parts == []


def test_a_missing_source_leaves_the_destination_untouched(tmp_path: Path) -> None:
    dest = tmp_path / "keep.txt"
    dest.write_text("old", encoding="utf-8")

    with pytest.raises(OSError):
        publish_file(tmp_path / "absent.txt", dest)

    assert dest.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".part")] == []


def test_the_adopt_route_publishes_through_the_same_door() -> None:
    body = Path("server/routes/artifacts.py").read_text(encoding="utf-8")
    assert "publish_file(source, dest)" in body
    assert "shutil.copyfile(source, dest)" not in body
