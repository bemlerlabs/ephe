"""Plugin artifact route: a generated file stays inside the mount that owns it."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULE = ROOT / "server" / "routes" / "plugin_artifacts.py"


def _route():
    spec = importlib.util.spec_from_file_location("ephe_plugin_artifacts_test", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_route_is_registered_in_the_frozen_contract():
    from tests.test_w3_68_api_contract_frozen import FROZEN_ROUTES

    assert "GET /api/plugin-artifacts/{plugin_id}/{nonce}/{artifact_id}/{path}" in FROZEN_ROUTES


def test_opaque_origin_gets_a_matching_allow_origin():
    mod = _route()

    class Request:
        headers = {"origin": "null"}

    headers = mod._opaque_origin_cors_headers(Request())
    assert headers["Access-Control-Allow-Origin"] == "null"
    assert headers["Vary"] == "Origin"


def test_other_origins_get_no_cors_header():
    mod = _route()

    class Request:
        headers = {"origin": "https://elsewhere.test"}

    assert mod._opaque_origin_cors_headers(Request()) == {}


def test_served_file_carries_closed_headers():
    mod = _route()
    response = mod._served(b"<p>x</p>", "text/html", "default-src 'self'")
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


#: The countdown bundle is the shipped surface with a UI and no tool behind it, so
#: it can be fetched without an engine and without a plugin that reaches the network.
PLUGIN = "countdown"
SERVED_HOST = "http://127.0.0.1:8765"


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def client(device):
    """A client on the host this server serves: the guard answers `untrusted_host` for
    `testserver`, and a surface fetch only exists on a served origin."""
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(
        create_app(),
        base_url=SERVED_HOST,
        headers={"Origin": SERVED_HOST, "X-Requested-With": "XMLHttpRequest"},
    ) as test_client:
        yield test_client


def _nonce(plugin_id: str = PLUGIN) -> str:
    from server import plugin_surface_nonce

    return plugin_surface_nonce.mint_surface_nonce(plugin_id).nonce


def _reason(response) -> str:
    return response.json()["error"]["reason_code"]


def test_a_contained_file_of_the_mount_arrives_sealed(client) -> None:
    response = client.get(f"/api/plugin-artifacts/{PLUGIN}/{_nonce()}/ui/index.html")
    assert response.status_code == 200, response.text
    on_disk = (ROOT / "plugins" / PLUGIN / "ui" / "index.html").read_bytes()
    assert response.content == on_disk
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_a_nonce_minted_for_another_plugin_is_refused(client) -> None:
    response = client.get(f"/api/plugin-artifacts/{PLUGIN}/{_nonce('memory')}/ui/app.css")
    assert response.status_code == 401, response.text
    assert _reason(response) == "plugin_ui_unauthorized"


def test_a_walk_out_of_the_plugin_directory_is_refused_before_a_byte_is_read(client) -> None:
    # Encoded so the client sends the traversal instead of normalising it away: the
    # containment walk, not the router, is the thing this asserts.
    response = client.get(
        f"/api/plugin-artifacts/{PLUGIN}/{_nonce()}/ui/%2e%2e%2f%2e%2e%2fephe_cli.py"
    )
    assert response.status_code == 400, response.text
    assert _reason(response) == "plugin_ui_asset_refused"
    assert "def main" not in response.text


def test_a_suffix_the_surface_does_not_serve_is_refused(client) -> None:
    # No file is planted: the suffix rule answers before the walk looks for anything.
    response = client.get(f"/api/plugin-artifacts/{PLUGIN}/{_nonce()}/ui/diagram.exe")
    assert response.status_code == 400, response.text
    assert _reason(response) == "plugin_ui_asset_refused"


def test_an_unknown_plugin_id_is_refused(client) -> None:
    response = client.get(f"/api/plugin-artifacts/no-such-plugin/{_nonce()}/ui/app.css")
    assert response.status_code == 404, response.text
    assert _reason(response) == "plugin_ui_unavailable"


def test_each_refusal_code_carries_its_sentence_in_both_bundles(client) -> None:
    bundles = {
        name: json.loads((ROOT / "app" / "src" / "locales" / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("en", "de")
    }
    for code in ("plugin_ui_unauthorized", "plugin_ui_asset_refused", "plugin_ui_unavailable"):
        for name, bundle in bundles.items():
            sentence = bundle.get(f"serverError.{code}") or bundle.get("serverError", {}).get(code)
            assert sentence and sentence.strip(), f"{name} has no sentence for {code}"

