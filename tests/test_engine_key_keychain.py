"""Where the engine key lives now: the OS keychain first, the 0600 key file as fallback.

`core/channels/pairing.py` stores the channel bot token in the OS keyring and falls back to
an owner-only file when no backend is importable. The engine key moves to the same shape
(P0-1): `core/engine_config.py` reads `EPHE_OPENAI_COMPAT_API_KEY`, then the keychain entry
`ephe/engine_api_key`, then `~/.ephe/engine.key`. The env stays on top so CI and a terminal
export still decide the token, and the file stays the last resort for an icon-launched app.

`keyring` is an optional import, exactly as in the channel vault: these tests inject a fake
backend into `sys.modules` rather than depend on the host having one. No test reads or prints
a real token — the values here are literals written by the test itself.
"""
from __future__ import annotations

import ast
import os
import re
import stat
import sys
import types
from pathlib import Path

import pytest

from core import engine_config as ec
from core.channels import pairing as channel_vault

ROOT = Path(__file__).resolve().parents[1]


def _fake_keyring(monkeypatch, *, store_ok: bool = True, stored: str | None = None):
    """A stand-in `keyring` module recording the calls the engine vault makes."""
    seen: dict[str, tuple] = {}
    backend = types.ModuleType("keyring")

    def set_password(service: str, username: str, value: str) -> None:
        if not store_ok:
            raise RuntimeError("no backend")
        seen["set"] = (service, username, value)

    def get_password(service: str, username: str) -> str | None:
        seen["get"] = (service, username)
        return stored

    def delete_password(service: str, username: str) -> None:
        seen["delete"] = (service, username)

    setattr(backend, "set_password", set_password)
    setattr(backend, "get_password", get_password)
    setattr(backend, "delete_password", delete_password)
    monkeypatch.setitem(sys.modules, "keyring", backend)
    return seen


def _write_key_file(home: Path, value: str) -> None:
    """The user's file, as `_key_file` demands it: one line, owner-only, a regular file."""
    target = home / ".ephe" / "engine.key"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value + "\n", encoding="utf-8")
    target.chmod(0o600)


def test_the_engine_entry_shares_the_service_the_channel_vault_uses():
    """One keyring service, one entry per secret — a rename on either side has to fail here."""
    assert ec.ENGINE_KEYRING_SERVICE == channel_vault.KEYRING_SERVICE == "ephe"
    assert ec.ENGINE_KEYRING_USERNAME != channel_vault.KEYRING_USERNAME


def test_the_backend_receives_the_declared_service_and_entry(monkeypatch):
    """The import path is the real one; only the backend is a double."""
    seen = _fake_keyring(monkeypatch, stored="loaded-value")
    assert ec._store_engine_keyring("written-value") is True
    assert seen["set"] == ("ephe", "engine_api_key", "written-value")
    assert ec._load_engine_keyring() == "loaded-value"
    assert seen["get"] == ("ephe", "engine_api_key")
    ec._delete_engine_keyring()
    assert seen["delete"] == ("ephe", "engine_api_key")


def test_a_backend_that_refuses_degrades_to_empty(monkeypatch):
    """A locked or missing entry is no token, never an exception on the resolver path."""
    _fake_keyring(monkeypatch, store_ok=False)
    assert ec._store_engine_keyring("v") is False
    ec._delete_engine_keyring()


def test_store_prefers_the_keychain_and_writes_no_file(tmp_path, monkeypatch):
    """A working keyring means the token never touches the disk."""
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: True)
    home = tmp_path / "home"
    assert ec.store_engine_api_key("tok-value", home=home) == "keyring"
    assert not (home / ".ephe" / "engine.key").exists()


def test_store_falls_back_to_an_owner_only_file(tmp_path, monkeypatch):
    """With no backend the fallback is the file `_key_file` reads back, and nothing looser."""
    if os.name == "nt":
        pytest.skip("mode assertions hold on POSIX")
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    home = tmp_path / "home"
    assert ec.store_engine_api_key("  tok-value  ", home=home) == "file_0600"
    path = home / ".ephe" / "engine.key"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, "the fallback must be owner-only"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.read_text(encoding="utf-8") == "tok-value\n"
    assert ec._key_file(home=home) == "tok-value"


def test_the_fallback_file_is_owner_only_before_it_is_renamed_into_place(tmp_path, monkeypatch):
    """The mode belongs to the open, not to a chmod after the write.

    A file written first and narrowed afterwards is readable by group and other for as
    long as the write takes, and a crash in between leaves that readable file behind.
    The check runs on the temporary name, the only moment where a wrong mode is still
    observable.
    """
    if os.name == "nt":
        pytest.skip("mode assertions hold on POSIX")
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    home = tmp_path / "home"
    seen: list[int] = []
    real_replace = os.replace

    def watch(source, target):
        seen.append(stat.S_IMODE(Path(source).stat().st_mode))
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", watch)
    assert ec.store_engine_api_key("tok-value", home=home) == "file_0600"
    assert seen == [0o600], "the key was readable by group or other before the rename"
    assert ec._key_file(home=home) == "tok-value"


def test_the_env_wins_over_the_keychain_and_the_file(tmp_path, monkeypatch):
    """An inherited variable is what the process was started with, so it decides alone."""
    home = tmp_path / "home"
    _write_key_file(home, "file-value")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "env-value")
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "keychain-value")
    assert ec.engine_api_key_for("http://engine/v1", home=home) == "env-value"


def test_the_keychain_wins_over_the_file(tmp_path, monkeypatch):
    """A stored secret outranks the leftover file on disk."""
    home = tmp_path / "home"
    _write_key_file(home, "file-value")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "keychain-value")
    assert ec.engine_api_key_for("http://engine/v1", home=home) == "keychain-value"


def test_the_file_is_the_last_resort(tmp_path, monkeypatch):
    """No env and no keychain leaves the owner-only file the desktop spawn also reads."""
    home = tmp_path / "home"
    _write_key_file(home, "file-value")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")
    assert ec.engine_api_key_for("http://engine/v1", home=home) == "file-value"


def test_delete_clears_the_keychain_and_the_file(tmp_path, monkeypatch):
    """Revoke has to reach both stores, or one of them answers the next start."""
    home = tmp_path / "home"
    _write_key_file(home, "file-value")
    called = []
    monkeypatch.setattr(ec, "_delete_engine_keyring", lambda: called.append(True))
    ec.delete_engine_api_key(home=home)
    assert called == [True]
    assert not (home / ".ephe" / "engine.key").exists()


def test_an_empty_token_is_refused(tmp_path):
    """An empty write would clear a stored key, so the store stops before it can."""
    home = tmp_path / "home"
    with pytest.raises(ValueError):
        ec.store_engine_api_key("", home=home)
    with pytest.raises(ValueError):
        ec.store_engine_api_key("   \n", home=home)
    assert not (home / ".ephe" / "engine.key").exists()


def test_a_multi_line_token_is_refused_before_it_reaches_a_file(tmp_path, monkeypatch):
    """`_key_file` refuses a two-line file, so the store has to refuse the token up front.

    Otherwise the fallback reports ``file_0600`` while the resolver reads nothing back —
    a success the next start never sees.
    """
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)
    home = tmp_path / "home"
    with pytest.raises(ValueError):
        ec.store_engine_api_key("line-one\nline-two", home=home)
    assert not (home / ".ephe" / "engine.key").exists()


def test_a_key_file_that_cannot_be_decoded_is_empty(tmp_path):
    """A binary blob in the key file is not a token: an unreadable read fails closed to nothing."""
    home = tmp_path / "home"
    path = home / ".ephe" / "engine.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe not utf-8\n")
    path.chmod(0o600)
    assert ec._key_file(home=home) == ""


def _raising_keyring(monkeypatch) -> None:
    """A backend whose every call fails — a locked wallet or a dropped entry."""
    backend = types.ModuleType("keyring")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("backend unavailable")

    setattr(backend, "set_password", _boom)
    setattr(backend, "get_password", _boom)
    setattr(backend, "delete_password", _boom)
    monkeypatch.setitem(sys.modules, "keyring", backend)


def test_keyring_absent_degrades_without_raising(monkeypatch):
    """No importable backend is the normal headless state: each call degrades, none raises."""
    monkeypatch.setitem(sys.modules, "keyring", None)  # `import keyring` → ImportError
    assert ec._store_engine_keyring("v") is False
    assert ec._load_engine_keyring() == ""
    assert ec._delete_engine_keyring() is None


def test_a_keyring_that_refuses_the_read_and_delete_is_empty_and_silent(monkeypatch):
    """A backend that answers with an error is a missing token, never an exception on the path."""
    _raising_keyring(monkeypatch)
    assert ec._store_engine_keyring("v") is False
    assert ec._load_engine_keyring() == ""
    ec._delete_engine_keyring()  # raising through here would break revoke


def test_the_store_survives_a_mode_that_the_filesystem_refuses(tmp_path, monkeypatch):
    """The chmod is hardening; a filesystem that refuses it must not fail the store."""
    if os.name == "nt":
        pytest.skip("chmod semantics hold on POSIX")
    monkeypatch.setattr(ec, "_store_engine_keyring", lambda token: False)

    def _refuse_chmod(self, mode):
        raise OSError("chmod refused")

    monkeypatch.setattr(Path, "chmod", _refuse_chmod)
    home = tmp_path / "home"
    assert ec.store_engine_api_key("tok", home=home) == "file_0600"
    assert (home / ".ephe" / "engine.key").read_text(encoding="utf-8") == "tok\n"


def test_delete_survives_an_unlink_that_fails(tmp_path, monkeypatch):
    """Revoke is best effort on both stores: a busy file must not abort the keychain delete."""
    seen = []
    monkeypatch.setattr(ec, "_delete_engine_keyring", lambda: seen.append(True))

    def _refuse_unlink(self, *args, **kwargs):
        raise OSError("busy")

    monkeypatch.setattr(Path, "unlink", _refuse_unlink)
    ec.delete_engine_api_key(home=tmp_path / "home")  # must not raise
    assert seen == [True]


def test_engine_not_configured_carries_the_fixed_hint():
    """The fail-closed error and its actionable line are identical in CLI and server."""
    exc = ec.EngineNotConfigured()
    assert str(exc) == "No engine configured."
    assert exc.hint == ec.ENGINE_SETUP_HINT
    custom = ec.EngineNotConfigured("custom message", hint="do this")
    assert str(custom) == "custom message"
    assert custom.hint == "do this"



def _resolver_source() -> str:
    """The three functions the resolver is made of, read out of the module file."""
    text = (ROOT / "core" / "engine_config.py").read_text(encoding="utf-8")
    wanted = {"engine_api_key_for", "_key_file", "key_file_path"}
    tree = ast.parse(text)
    bodies = [
        ast.get_source_segment(text, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert len(bodies) == len(wanted), "the resolver is no longer these three functions"
    return "\n".join(b for b in bodies if b)


def test_the_resolver_consults_only_env_keychain_and_file():
    """The keychain is the third source, and it is the only one added.

    The env variable and the file stay exactly the two names the resolver carried before, so a
    fourth source cannot enter by renaming one of them: this fails and names the extra path.
    """
    source = _resolver_source()
    env_names = set(re.findall(r'environ(?:\.get\()?["\[]?(EPHE_[A-Z_]+)', source))
    files = set(re.findall(r'"([\w.]+\.(?:json|key))"', source))
    assert env_names == {"EPHE_OPENAI_COMPAT_API_KEY"}
    assert files == {"engine.key"}
    assert "_load_engine_keyring()" in source, "the resolver dropped the keychain source"


def test_the_module_records_where_the_third_source_stores():
    """A source the module reads has to be written down in the module, keychain included."""
    doc = ec.__doc__ or ""
    assert "engine_api_key" in doc
    assert "keychain" in doc.lower()
