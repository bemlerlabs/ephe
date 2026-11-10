"""The page-storage shim the mount places in a sandboxed surface document.

The mount restores the Storage API without giving the document an origin: the
shim (`sdk/ephe-storage.js`) answers synchronous reads from a snapshot of this
bundle's own page store, embedded in the document ahead of the bundle's first
script, and sends writes over the existing `ephe.sdk` bridge. These tests are the
HTTP and unit half of that claim — the browser half, where a write survives a
read and a reload inside the real sandbox, is
`tests/test_plugin_surface_storage_shim_browser.py`.

What is pinned here: the order the shim and the snapshot arrive in, the fact
that a document carries only its own bundle's store, that a stored value can
never close the data block, that a bundle file named `ephe-storage.js` cannot
replace the build's copy, and that the policy is still the one without
`allow-same-origin`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_runtime
from server import plugin_surface_storage

SHIM_FILE = ROOT / "sdk" / "ephe-storage.js"
SNAPSHOT = re.compile(
    r'<script type="application/json" id="ephe-storage-snapshot">(.*?)</script>', re.DOTALL
)
PLUGIN_A = "acme-storage-a"
PLUGIN_B = "acme-storage-b"
ENTRY = '<!doctype html><title>Storage</title><script src="app.js"></script>'
APP = "console.log('surface');"


def _manifest(name: str, entry: str = "ui/index.html") -> dict:
    return {
        "manifest_version": 1,
        "name": name,
        "version": "1.0.0",
        "description": "A surface whose entries are kept in page storage",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "ui": {
                "type": "floating-window",
                "entry": entry,
                "title": "Storage",
                "capabilities": ["notifications"],
            },
        },
    }


def _install(config: Path, name: str, files: dict[str, str], entry: str = "ui/index.html") -> None:
    plugin = config / "plugins" / name
    for relative, text in files.items():
        target = plugin / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (plugin / "ephe-plugin.json").write_text(json.dumps(_manifest(name, entry)), encoding="utf-8")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Two installed surfaces: a value stored for one must never reach the other."""
    config = tmp_path / "ephe-home"
    _install(
        config,
        PLUGIN_A,
        {
            "ui/index.html": ENTRY,
            "ui/app.js": APP,
            "ui/panel.html": "<!doctype html><title>Panel</title>",
            "ui/sub/deep.html": "<!doctype html><title>Deep</title>",
            "ui/ephe-storage.js": "/* the bundle's own, which must not be served */",
            "ui/sub/ephe-storage.js": "/* a nested shadow, also not served */",
        },
    )
    _install(config, PLUGIN_B, {"ui/index.html": ENTRY, "ui/app.js": APP})
    (config / "plugin-state.json").write_text(
        json.dumps({"schema": 1, "pause_all": False, "plugins": {}}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


@pytest.fixture()
def client(home):
    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as test_client:
        test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield test_client


def _nonce(client, plugin_id: str) -> str:
    minted = client.post(f"/api/plugins/{plugin_id}/surface-token", json={})
    assert minted.status_code == 200, minted.text
    return minted.json()["surface"]


def _document(client, plugin_id: str):
    response = client.get(f"/api/plugins/ui/{plugin_id}/{_nonce(client, plugin_id)}/")
    assert response.status_code == 200, response.text
    return response


def _store(client, plugin_id: str, key: str, value: object) -> None:
    saved = client.put(
        f"/api/plugins/{plugin_id}/client/storage", json={"key": key, "value": value}
    )
    assert saved.status_code == 200, saved.text


def _snapshot_of(response) -> dict:
    found = SNAPSHOT.search(response.text)
    assert found is not None, response.text
    return json.loads(found.group(1))


def test_the_shim_and_its_snapshot_arrive_ahead_of_the_bundles_first_script(client):
    text = _document(client, PLUGIN_A).text
    assert text.startswith("<!doctype html>"), text
    doctype = text.index("<!doctype html>") + len("<!doctype html>")
    data = text.index(plugin_surface_storage.SNAPSHOT_ELEMENT_ID)
    shim = text.index(f'src="{plugin_surface_storage.SHIM_NAME}"')
    bundle = text.index('src="app.js"')
    # The data block precedes the script that reads it, and both precede every
    # byte the bundle authored: no bundle script can reach `localStorage` first.
    assert doctype < data < shim < bundle, text
    assert _snapshot_of(_document(client, PLUGIN_A)) == {}


def test_a_document_carries_only_its_own_bundles_store(client):
    _store(client, PLUGIN_A, "theme", "dark")
    _store(client, PLUGIN_B, "theme", "light")

    first = _snapshot_of(_document(client, PLUGIN_A))
    second = _snapshot_of(_document(client, PLUGIN_B))

    assert first == {"theme": "dark"}, first
    assert second == {"theme": "light"}, second
    assert "light" not in _document(client, PLUGIN_A).text


def test_a_stored_value_cannot_close_the_snapshot_block(client):
    hostile = "</script><script>window.pwned = 1</script>"
    _store(client, PLUGIN_A, "payload", hostile)

    text = _document(client, PLUGIN_A).text
    found = SNAPSHOT.search(text)
    assert found is not None, text
    # The block parses back to the exact value the bundle wrote, and the raw
    # closing token never appears inside it.
    assert json.loads(found.group(1)) == {"payload": hostile}
    assert "</script><script>window.pwned" not in text
    assert "\\u003c/script\\u003e" in found.group(1)
    # Three script starts: the data block, the shim, and the bundle's own
    # `app.js`. The hostile value added none.
    assert text.count("<script") == 3, text
    assert text.count('<script src="app.js"') == 1, text


def test_a_value_written_by_the_page_sdk_reads_as_its_json_text(client):
    _store(client, PLUGIN_A, "note", {"n": 1})
    assert _snapshot_of(_document(client, PLUGIN_A)) == {"note": {"n": 1}}


def test_a_bundle_file_named_like_the_shim_cannot_replace_the_build_copy(client):
    served = client.get(
        f"/api/plugins/ui/{PLUGIN_A}/{_nonce(client, PLUGIN_A)}/{plugin_surface_storage.SHIM_NAME}"
    )
    assert served.status_code == 200, served.text
    assert served.headers["content-type"].startswith("application/javascript")
    assert served.content == SHIM_FILE.read_bytes()
    assert b"must not be served" not in served.content


def test_the_shim_is_a_script_the_mount_may_load_and_never_a_document(client):
    response = client.get(
        f"/api/plugins/ui/{PLUGIN_A}/{_nonce(client, PLUGIN_A)}/{plugin_surface_storage.SHIM_NAME}",
        headers={"Origin": "null"},
    )
    assert response.status_code == 200, response.text
    csp = response.headers["content-security-policy"]
    assert "sandbox" not in csp, csp
    assert "allow-same-origin" not in csp, csp
    # A classic script asks for nothing, but the same request from a module would
    # need the opaque origin named, exactly like `ephe.js`.
    assert response.headers.get("access-control-allow-origin") == "null"


def test_a_nested_document_gets_the_shim_and_its_bundles_snapshot_too(client):
    _store(client, PLUGIN_A, "theme", "dark")
    nested = client.get(
        f"/api/plugins/ui/{PLUGIN_A}/{_nonce(client, PLUGIN_A)}/panel.html"
    )
    assert nested.status_code == 200, nested.text
    assert nested.headers["content-type"].startswith("text/html")
    assert "sandbox" in nested.headers["content-security-policy"]
    assert "allow-same-origin" not in nested.headers["content-security-policy"]
    assert _snapshot_of(nested) == {"theme": "dark"}


def test_a_nested_document_in_a_subdirectory_finds_the_reserved_shim(client):
    """The injected `src` is relative, so a nested document asks for its own
    subdirectory's `ephe-storage.js`. The reserved name answers at every depth."""
    _store(client, PLUGIN_A, "theme", "dark")
    nested = client.get(f"/api/plugins/ui/{PLUGIN_A}/{_nonce(client, PLUGIN_A)}/sub/deep.html")
    assert nested.status_code == 200, nested.text
    assert _snapshot_of(nested) == {"theme": "dark"}
    served = client.get(
        f"/api/plugins/ui/{PLUGIN_A}/{_nonce(client, PLUGIN_A)}/sub/ephe-storage.js"
    )
    assert served.status_code == 200, served.text
    assert served.content == SHIM_FILE.read_bytes()
    assert b"nested shadow" not in served.content


def test_reading_a_document_creates_no_state_folder(client):
    from core.plugin_state import state_home

    _document(client, PLUGIN_B)
    assert not state_home(PLUGIN_B).exists()


def test_the_injection_keeps_a_doctype_and_a_bom_where_they_were():
    tag = plugin_surface_storage.snapshot_markup({"a": "b"})
    bom_document = b"\xef\xbb\xbf<!doctype html><title>x</title>"
    injected = plugin_surface_storage.install_shim(bom_document, {"a": "b"})
    assert injected.startswith(b"\xef\xbb\xbf<!doctype html>")
    assert injected[len(b"\xef\xbb\xbf<!doctype html>"):].startswith(tag)

    # A document with no doctype already parses without one; the shim goes first.
    plain = plugin_surface_storage.install_shim(b"<p>no doctype</p>", {})
    assert plain.startswith(tag[:32])
    assert plain.endswith(b"<p>no doctype</p>")


def test_the_mount_policy_still_withholds_the_origin(client):
    response = _document(client, PLUGIN_A)
    csp = response.headers["content-security-policy"]
    assert "sandbox allow-scripts allow-popups" in csp, csp
    assert "allow-same-origin" not in csp, csp
    assert "script-src 'self'" in csp, csp
