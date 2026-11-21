"""The sinks the release review named, held to their refusals.

One case per class: an artifact fetch that could reach a private address, a plugin
name that could leave its root, an error response that could echo a path or an
exception, and a key fingerprint in a password-hash shape.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from core import engine_config as ec
from core import marketplace_service, plugin_versions
from core.guarded_fetch import GuardedFetchError
from core.marketplace_planner import ServiceError
from core.plugin_install import _default_fetcher
from server.routes import marketplace as routes

_SECRET_TEXT = "/Users/someone/.ephe/engine.key: Traceback (most recent call last)"


def test_the_default_artifact_fetch_refuses_a_non_public_target():
    for url in (
        "http://example.com/a.zip",
        "https://127.0.0.1/a.zip",
        "https://10.0.0.1/a.zip",
        "https://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(GuardedFetchError) as caught:
            _default_fetcher(url)
        assert caught.value.code == "untrusted_target", url


def test_the_default_artifact_fetch_uses_the_guarded_reader(monkeypatch):
    seen: dict[str, object] = {}

    def fake(url: str, *, max_bytes: int, timeout: float, accept: str) -> bytes:
        seen.update(url=url, max_bytes=max_bytes, timeout=timeout, accept=accept)
        return b"zip-bytes"

    monkeypatch.setattr("core.plugin_install.fetch_https", fake)
    assert _default_fetcher("https://example.com/a.zip") == b"zip-bytes"
    assert seen["url"] == "https://example.com/a.zip"
    assert seen["max_bytes"] == 50 * 1024 * 1024


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/b", "/absolute", "", ".", "..", "Ä", "a b", "a\\b", "ALPHA"],
)
def test_plugin_dir_refuses_a_name_that_is_not_a_slug(tmp_path, name):
    with pytest.raises(ValueError):
        plugin_versions.plugin_dir(tmp_path, name)


def test_plugin_dir_names_the_backup_variants_of_a_slug(tmp_path):
    root = tmp_path / "plugins"
    root.mkdir()
    assert plugin_versions.plugin_dir(root, "alpha") == (root / "alpha").resolve()
    assert plugin_versions.plugin_dir(root, "alpha", prefix=".previous-") == (
        root / ".previous-alpha"
    ).resolve()


def test_plugin_dir_refuses_a_symlink_that_leaves_the_root(tmp_path):
    root = tmp_path / "plugins"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "alpha").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        plugin_versions.plugin_dir(root, "alpha")


def test_an_existing_installation_stays_reachable(tmp_path):
    root = tmp_path / "plugins"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "ephe-plugin.json").write_text("{}", encoding="utf-8")
    assert plugin_versions.plugin_dir(root, "alpha").is_dir()


def _refusal(monkeypatch, name: str, outcome) -> None:
    if isinstance(outcome, BaseException):
        def boom(*_args, **_kwargs):
            raise outcome

        monkeypatch.setattr(marketplace_service, name, boom)
    else:
        monkeypatch.setattr(marketplace_service, name, lambda *_a, **_k: outcome)


def test_plan_and_install_refusals_carry_a_code_without_service_text(monkeypatch):
    secret = "/Users/someone/ephe/core/plugin_install.py: Traceback (most recent call last)"
    for handler, body in (
        (routes.plan_install, {"source_id": "bundled", "name": "alpha"}),
        (routes.install_plan, {"plan": {"name": "alpha"}}),
    ):
        monkeypatch.undo()
        _refusal(monkeypatch, "plan" if handler is routes.plan_install else "install",
                 ServiceError("unknown_source", secret, 404))
        with pytest.raises(HTTPException) as caught:
            asyncio.run(handler(body))
        assert caught.value.detail == {
            "code": "unknown_source",
            "detail": routes._REFUSED,
        }


def test_rollback_and_remove_refusals_carry_only_the_code(monkeypatch):
    _refusal(
        monkeypatch,
        "rollback",
        {"status": "invalid_backup", "name": "../alpha", "error": _SECRET_TEXT},
    )
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.rollback({"name": "../alpha"}))
    assert caught.value.detail == {"code": "invalid_backup", "detail": routes._REFUSED}

    monkeypatch.undo()
    _refusal(monkeypatch, "remove", {"status": "not_installed", "name": "../alpha"})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.remove_plugin({"name": "../alpha"}))
    assert caught.value.detail == {"code": "not_installed", "detail": routes._REFUSED}


def test_a_permission_review_keeps_the_delta_and_drops_every_other_field(monkeypatch):
    plan = {
        "status": "permission_review",
        "code": "permission_review",
        "error": "/secret/path: boom",
        "name": "alpha",
        "delta": {"tool_families_added": ["read"], "digest": "abc"},
        "trust": "local",
    }
    _refusal(monkeypatch, "plan", plan)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.plan_install({"source_id": "bundled", "name": "alpha"}))
    detail = caught.value.detail
    assert detail["code"] == "permission_review"
    assert detail["delta"] == plan["delta"]
    assert "error" not in detail
    assert "boom" not in str(detail)


def test_the_key_fingerprint_is_hmac_with_a_context():
    value = ec.engine_key_fingerprint("tok-value")
    bare = "sha256:" + hashlib.sha256(b"tok-value").hexdigest()
    assert value.startswith("hmac-sha256:")
    assert value != bare


def test_a_legacy_binding_is_accepted_once_and_rewritten(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / ".ephe"))
    choice = ec.EngineChoice(
        provider="openai_compatible",
        model="deepseek-chat",
        api_url="https://api.deepseek.com/v1",
    )
    token = "tok-value"
    binding = ec.key_binding_path()
    binding.parent.mkdir(parents=True, exist_ok=True)
    binding.write_text(
        '{"version": 1, "provider": "openai_compatible", "model": "deepseek-chat", '
        '"api_url": "https://api.deepseek.com/v1", "key_fingerprint": '
        f'"{ec._legacy_key_fingerprint(token)}"}}\n',
        encoding="utf-8",
    )
    binding.chmod(0o600)

    assert ec.engine_key_binding_problem(choice, token, "file") is None
    rewritten = binding.read_text(encoding="utf-8")
    assert ec.engine_key_fingerprint(token) in rewritten
    assert ec._legacy_key_fingerprint(token) not in rewritten
