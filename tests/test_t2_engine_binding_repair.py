"""T2 — a stored key for another engine is a guided repair instead of a dead start.

`~/.ephe/engine.key` is bound to one provider/model/endpoint. A start whose
engine.json names a different one used to exit 1, which the desktop shell can
only read as "backend unreachable": the window opened with no engine and no way
to fix it. The loopback start now enters setup mode and names the repair, the
chat guard refuses until the binding is rewritten, and both re-read the binding
on every call, so the key the user enters on the setup page clears the state for
the running process. A LAN start still exits — an unconfigured network surface
is not a repair.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

from core import engine_config as ec


#: The engine the stored key was entered for (and is bound to).
CHOICE = ec.EngineChoice(
    provider="openai_compatible",
    model="deepseek-chat",
    api_url="https://api.deepseek.com/v1",
)
#: The engine engine.json names now — same key file, different engine.
ACTIVE = replace(CHOICE, model="another-model")

#: Everything `EngineChoice.apply_env` writes plus the flags this module reads.
#: The values are restored by hand because apply_env writes to os.environ directly.
_ENV_KEYS = (
    "EPHE_MODEL_PROVIDER",
    "EPHE_MODEL",
    "EPHE_OPENAI_COMPAT_MODEL",
    "EPHE_OPENAI_COMPAT_BASE_URL",
    "EPHE_OPENAI_COMPAT_API_KEY",
    "EPHE_ENGINE_KEY_SOURCE",
    "EPHE_SETUP_MODE",
    "EPHE_ENGINE_KEY_REPAIR",
    "EPHE_LAN",
    "EPHE_HOST",
)


@pytest.fixture(autouse=True)
def _clean_engine_env():
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def mismatched_key(monkeypatch, empty_ephe_home):
    """The key belongs to CHOICE; engine.json names ACTIVE.

    One key file, one valid binding, two engines — the state a user reaches by
    switching the model after entering the key.
    """
    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")
    key_path = ec.key_file_path()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text("key-b\n", encoding="utf-8")
    key_path.chmod(0o600)
    binding = ec.key_binding_path()
    binding.write_text(
        json.dumps(
            {
                "version": 1,
                "provider": CHOICE.provider,
                "model": CHOICE.model,
                "api_url": CHOICE.api_url,
                "key_fingerprint": ec.engine_key_fingerprint("key-b"),
            }
        ),
        encoding="utf-8",
    )
    binding.chmod(0o600)
    ec.save_engine_config(ACTIVE)
    monkeypatch.setattr(ec, "resolve_engine_choice", lambda **_kw: ACTIVE)
    return ACTIVE


def _argv(monkeypatch, *args: str) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", ["run_server.py", *args])


def test_a_mismatched_key_enters_setup_mode_instead_of_exiting(
    mismatched_key, monkeypatch, capsys
):
    import run_server

    _argv(monkeypatch, "--port", "8765")

    assert run_server._bootstrap_engine_choice() is None
    out = capsys.readouterr().out
    assert "SETUP MODE" in out
    assert os.environ.get("EPHE_SETUP_MODE") == "1"
    assert os.environ.get("EPHE_ENGINE_KEY_REPAIR") == ec.REPAIR_ENGINE_KEY_MISMATCH


def test_the_same_mismatch_on_a_lan_start_still_exits(mismatched_key, monkeypatch, capsys):
    import run_server

    _argv(monkeypatch, "--lan")

    with pytest.raises(SystemExit) as excinfo:
        run_server._bootstrap_engine_choice()

    assert excinfo.value.code == 1
    assert "SETUP MODE" not in capsys.readouterr().out


def test_a_bound_key_still_starts_normally(monkeypatch, empty_ephe_home):
    import run_server

    monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")
    ec.save_engine_config(CHOICE)
    ec.store_engine_api_key("key-b", engine=CHOICE)
    monkeypatch.setattr(ec, "resolve_engine_choice", lambda **_kw: CHOICE)
    _argv(monkeypatch, "--port", "8765")

    assert run_server._bootstrap_engine_choice() == CHOICE
    assert "EPHE_ENGINE_KEY_REPAIR" not in os.environ


def test_setup_status_names_the_repair_and_clears_after_a_rebind(mismatched_key, monkeypatch):
    monkeypatch.setenv("EPHE_ENGINE_KEY_REPAIR", ec.REPAIR_ENGINE_KEY_MISMATCH)
    from server.routes import settings as setup_settings

    monkeypatch.setattr(setup_settings, "_probe_memoised", lambda provider, url: (False, []))

    payload = setup_settings._setup_provider_dict()
    assert payload["configured"] is False
    repair = payload["repair"]
    assert repair["code"] == ec.REPAIR_ENGINE_KEY_MISMATCH
    assert repair["active"] == {
        "provider": ACTIVE.provider,
        "model": ACTIVE.model,
        "url": ACTIVE.api_url,
    }
    assert repair["bound"] == {
        "provider": CHOICE.provider,
        "model": CHOICE.model,
        "url": CHOICE.api_url,
    }
    assert repair["key_source"] == "file"
    assert repair["choices"] == ["keep_bound_engine", "replace_key", "choose_provider", "cancel"]
    assert "key-b" not in json.dumps(payload)

    # Choice 2: keep the active engine and re-enter the key for it.
    ec.store_engine_api_key("key-b", engine=ACTIVE)

    payload = setup_settings._setup_provider_dict()
    assert payload["repair"] is None
    assert payload["configured"] is True


def test_restoring_the_bound_engine_clears_the_repair(mismatched_key, monkeypatch):
    """Choice 1 of four: keep the key and go back to the engine it was entered for."""
    monkeypatch.setenv("EPHE_ENGINE_KEY_REPAIR", ec.REPAIR_ENGINE_KEY_MISMATCH)
    from server.routes import settings as setup_settings

    monkeypatch.setattr(setup_settings, "_probe_memoised", lambda provider, url: (False, []))
    assert setup_settings._setup_provider_dict()["repair"] is not None

    import asyncio

    request = setup_settings.SettingsRequest(
        provider=setup_settings.ProviderSettings(
            type=CHOICE.provider,
            model=CHOICE.model,
            endpoint=CHOICE.api_url,
        )
    )
    # Choice 1: the engine the key is bound to, and no key in the request.
    asyncio.run(setup_settings.update_settings(request))

    payload = setup_settings._setup_provider_dict()
    assert payload["repair"] is None
    assert payload["configured"] is True


def test_a_replaced_key_file_drops_the_keep_option(mismatched_key, monkeypatch):
    """A key written after its binding: restoring the bound engine cannot repair it."""
    monkeypatch.setenv("EPHE_ENGINE_KEY_REPAIR", ec.REPAIR_ENGINE_KEY_MISMATCH)
    key_path = ec.key_file_path()
    key_path.write_text("key-replaced\n", encoding="utf-8")
    key_path.chmod(0o600)

    state = ec.engine_key_repair_state()

    assert state is not None
    assert "does not match its binding" in state["problem"]
    assert state["active"]["model"] == ACTIVE.model
    assert state["bound"] is None
    assert state["choices"] == ["replace_key", "choose_provider", "cancel"]
    assert "key-replaced" not in json.dumps(state)


def test_the_cli_verdict_names_the_key_source_and_the_choices(mismatched_key):
    """The CLI/TUI print the exception and its hint; both are the same verdict the page
    shows, with the source named and no key material."""
    with pytest.raises(ec.EngineKeyMismatch) as excinfo:
        ec.assert_engine_key_binding(ACTIVE)

    message = str(excinfo.value)
    hint = excinfo.value.hint
    assert "bound to" in message and "active engine is" in message
    assert "the stored key file" in hint
    assert "restore the engine it is bound to" in hint
    assert "re-enter the key" in hint
    assert "pick another engine" in hint
    assert "key-b" not in message and "key-b" not in hint


def test_chat_refuses_until_the_binding_is_rewritten(mismatched_key, monkeypatch):
    monkeypatch.setenv("EPHE_ENGINE_KEY_REPAIR", ec.REPAIR_ENGINE_KEY_MISMATCH)
    from fastapi import HTTPException

    from server.routes import chat

    with pytest.raises(HTTPException) as excinfo:
        chat._ensure_engine_ready()

    assert excinfo.value.status_code == 409
    assert "bound to" in str(excinfo.value.detail)

    ec.store_engine_api_key("key-b", engine=ACTIVE)

    assert chat._ensure_engine_ready() is None
