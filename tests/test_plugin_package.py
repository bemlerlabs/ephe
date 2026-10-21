"""PKG-01..03 — archive limits before anything is extracted.

A plugin archive is bounded by member count, uncompressed bytes and compression
ratio, and may contain only regular files and directories within the staging
root. Symlinks, hardlinks, absolute members and traversal are refused.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_market
from core.plugin_store import sha256_hex

MANIFEST = {
    "manifest_version": 1,
    "name": "my-tool",
    "version": "1.2.3",
    "description": "A bundled tool",
    "permissions": {"tool_families": [], "data_roots": []},
    "components": {"skills": [], "commands": [], "tools": []},
}


def _payload(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return buf.getvalue()


def _install(tmp_path, monkeypatch, payload: bytes) -> dict:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    entry = {
        "name": "my-tool",
        "version": "1.2.3",
        "sha256": sha256_hex(payload),
        "url": "https://artifact.invalid/my-tool.zip",
        "trust": "local",
    }
    return plugin_market.install_from_marketplace(
        "my-tool",
        marketplace={"plugins": [entry]},
        fetcher=lambda url: payload,
        allow_local_trust=True,
    )


def _valid_members() -> dict[str, bytes]:
    return {"my-tool/ephe-plugin.json": json.dumps(MANIFEST).encode()}


def test_member_containment_and_regular_files_only(tmp_path, monkeypatch) -> None:
    traversal = _payload({**_valid_members(), "../escape.sh": b"rm -rf /"})
    assert _install(tmp_path, monkeypatch, traversal)["status"] == "unsafe_archive"

    absolute = _payload({"/etc/ephe-escape": b"x"})
    assert _install(tmp_path, monkeypatch, absolute)["status"] == "unsafe_archive"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("my-tool/link")
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "my-tool/ephe-plugin.json")
        archive.writestr("my-tool/ephe-plugin.json", json.dumps(MANIFEST))
    assert _install(tmp_path, monkeypatch, buf.getvalue())["status"] == "unsafe_archive"


def test_member_count_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(plugin_market, "MAX_ARCHIVE_MEMBERS", 2)
    members = {**_valid_members(), "my-tool/a": b"a", "my-tool/b": b"b"}
    status = _install(tmp_path, monkeypatch, _payload(members))
    assert status["status"] == "unsafe_archive"
    assert "members" in status["error"]


def test_uncompressed_bytes_and_ratio_caps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(plugin_market, "MAX_ARCHIVE_BYTES", 200)
    status = _install(
        tmp_path,
        monkeypatch,
        _payload({**_valid_members(), "my-tool/big": b"x" * 500}),
    )
    assert status["status"] == "unsafe_archive"
    assert "bytes" in status["error"]

    monkeypatch.setattr(plugin_market, "MAX_ARCHIVE_BYTES", 10_000_000)
    monkeypatch.setattr(plugin_market, "MAX_ARCHIVE_RATIO", 2)
    status = _install(
        tmp_path,
        monkeypatch,
        _payload({**_valid_members(), "my-tool/zeros": b"\0" * 100_000}),
    )
    assert status["status"] == "unsafe_archive"
    assert "ratio" in status["error"]
