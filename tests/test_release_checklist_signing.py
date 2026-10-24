"""The signing-key line must not report a key the updater would reject.

The checklist used to pass on the mere existence of `~/.tauri/ephe.key`. On
2026-10-22 that file was present while its public half did not match
`plugins.updater.pubkey`; the matching key was `ephe2.key`. A release built
with the wrong private half produces a feed the client refuses, so "present"
without the comparison is a false green.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_checklist.py"


def _load():
    spec = importlib.util.spec_from_file_location("release_checklist_signing", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checklist = _load()
PUBKEY = "untrusted comment: minisign public key\nRWQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    conf = root / "app" / "src-tauri" / "tauri.conf.json"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        json.dumps({"plugins": {"updater": {"pubkey": PUBKEY, "endpoints": ["https://example.invalid/latest.json"]}}}),
        encoding="utf-8",
    )
    return root


def _key(tmp_path: Path, name: str = "ephe.key", public: str | None = PUBKEY) -> Path:
    path = tmp_path / "keys" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("private\n", encoding="utf-8")
    if public is not None:
        Path(f"{path}.pub").write_text(public, encoding="utf-8")
    return path


def test_a_matching_public_half_passes(tmp_path):
    item = checklist.check_signing_key(_root(tmp_path), str(_key(tmp_path)))
    assert item.status == "PASS"
    assert "matches" in item.detail


def test_a_mismatched_public_half_warns_and_names_the_match(tmp_path):
    root = _root(tmp_path)
    wrong = _key(tmp_path, "ephe.key", "a different public key\n")
    _key(tmp_path, "ephe2.key", PUBKEY)

    item = checklist.check_signing_key(root, str(wrong))
    assert item.status == "WARN"
    assert "does not match" in item.detail
    assert "ephe2.key.pub" in item.detail


def test_a_missing_public_half_is_not_a_pass(tmp_path):
    item = checklist.check_signing_key(_root(tmp_path), str(_key(tmp_path, public=None)))
    assert item.status == "WARN"
    assert "cannot be matched" in item.detail


def test_a_missing_private_key_warns(tmp_path):
    item = checklist.check_signing_key(_root(tmp_path), str(tmp_path / "keys" / "absent.key"))
    assert item.status == "WARN"
    assert "missing" in item.detail
