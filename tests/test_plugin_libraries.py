"""LIB-01.. — the offline library runtime: declared bytes, served bytes, one hash.

`core/plugin_libraries.py` is the contract this file exercises, and the reading is the
attacker's as usual: a vendor file swapped on disk after install, a declared library
that never shipped, bytes under `vendor/` nobody declared, a wasm module offered to a
mount that may not compile it, a cap somebody could have invented. One fixture bundle
(`tests/fixtures/library-runtime/hello-scene`) carries the valid case end to end, and
its declared hash is recomputed from its own bytes in
`test_the_fixture_declaration_matches_the_bytes_it_ships`, which is what keeps a
committed fixture from going stale and staying green.

The serving half rides the same ASGI stack `tests/test_plugin_ui_serving.py` drives:
the manifest is re-read on every request, which is what turns a validation error into
a refusal on the very next fetch.

"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_libraries, plugin_runtime  # noqa: E402
from core.plugin_libraries import (  # noqa: E402
    LIBRARIES_FILENAME,
    MAX_LIBRARY_FILE_BYTES,
    MAX_LIBRARY_TOTAL_BYTES,
)
from core.plugin_manifest import dir_sha256, load_manifest  # noqa: E402
from core.plugin_ui_capabilities import UI_CAPABILITIES  # noqa: E402
from server import plugin_surface, plugin_surface_policy  # noqa: E402
from server.middleware import init_auth  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "library-runtime" / "hello-scene"
PLUGIN_ID = "hello-scene"
LIBRARY_REL = "ui/vendor/tiny-renderer.mjs"
LIBRARY_URL = "vendor/tiny-renderer.mjs"
LIBRARY_MARK = "export const RENDERER_VERSION"
PEER_DESKTOP = "127.0.0.1"
MOUNT = f"/api/plugins/ui/{PLUGIN_ID}/"


@pytest.fixture(autouse=True)
def _auth_stays_off():
    yield
    init_auth(lan_mode=False)


def _declaration(plugin_dir: Path) -> dict:
    return json.loads((plugin_dir / LIBRARIES_FILENAME).read_text(encoding="utf-8"))


def _write_declaration(plugin_dir: Path, declaration: dict) -> None:
    (plugin_dir / LIBRARIES_FILENAME).write_text(
        json.dumps(declaration, indent=2), encoding="utf-8"
    )


def _bundle(root: Path, mutate=None, name: str = PLUGIN_ID) -> Path:
    """A copy of the fixture bundle, `mutate`d the way a broken plugin would be."""
    plugin = root / name
    plugin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, plugin)
    if mutate is not None:
        mutate(plugin)
    return plugin


def _library_entry(path: str, kind: str = "module", name: str = "tiny-lib") -> dict:
    return {"name": name, "version": "1.0.0", "path": path, "sha256": "0" * 64, "kind": kind}


def _add_library(
    plugin_dir: Path, relative: str, kind: str = "module", name: str = "tiny-lib"
) -> dict:
    """Ship one extra file and declare it with the hash of its own bytes."""
    target = plugin_dir / relative
    entry = _library_entry(relative, kind, name)
    entry["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    declaration = _declaration(plugin_dir)
    declaration["libraries"].append(entry)
    _write_declaration(plugin_dir, declaration)
    return entry


def _point_at(plugin_dir: Path, relative: str, kind: str = "module") -> None:
    """Replace the whole declaration with one entry for `relative`, hashed as shipped."""
    entry = _library_entry(relative, kind)
    entry["sha256"] = hashlib.sha256((plugin_dir / relative).read_bytes()).hexdigest()
    _write_declaration(plugin_dir, {"schema": 1, "libraries": [entry]})


def _set_capabilities(plugin_dir: Path, capabilities: list[str]) -> None:
    manifest = json.loads((plugin_dir / "ephe-plugin.json").read_text(encoding="utf-8"))
    manifest["components"]["ui"]["capabilities"] = capabilities
    (plugin_dir / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


def _csp_rows(header: str) -> dict[str, str]:
    rows = [chunk.strip().partition(" ") for chunk in header.split(";")]
    return {name: sources for name, _, sources in rows if name}


def _loaded(entry: str) -> dict:
    """The `ephe-plugin.json` of one shipped bundle, as the manifest writer wrote it."""
    return json.loads((Path(entry) / "ephe-plugin.json").read_text(encoding="utf-8"))


# -- the fixture, and the outcomes the contract promises --


def test_the_fixture_declaration_matches_the_bytes_it_ships() -> None:
    declared = _declaration(FIXTURE)["libraries"][0]
    assert declared["path"] == LIBRARY_REL
    shipped = hashlib.sha256((FIXTURE / LIBRARY_REL).read_bytes()).hexdigest()
    assert declared["sha256"] == shipped, (
        "the committed fixture declares the hash of its own bytes, so this suite "
        "tests the promise a plugin really makes"
    )


def test_a_declared_library_loads_the_plugin(tmp_path) -> None:
    manifest, error = load_manifest(_bundle(tmp_path))
    assert error is None and manifest is not None


def test_a_swapped_vendor_file_quarantines_the_whole_plugin(tmp_path) -> None:
    plugin = _bundle(tmp_path, lambda p: (p / LIBRARY_REL).write_text("evil\n"))
    manifest, error = load_manifest(plugin)
    assert manifest is None, "a hash mismatch is a manifest violation like any other"
    assert "hashes to" in error and LIBRARY_REL in error


def test_a_declared_library_that_never_ships_quarantines_the_plugin(tmp_path) -> None:
    plugin = _bundle(tmp_path, lambda p: (p / LIBRARY_REL).unlink())
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert "does not ship" in error


def test_a_library_past_the_per_file_cap_is_refused_with_the_stated_limit(tmp_path) -> None:
    oversized = MAX_LIBRARY_FILE_BYTES + 1
    plugin = _bundle(tmp_path, lambda p: (p / LIBRARY_REL).write_bytes(b"x" * oversized))
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert f"{oversized} bytes" in error
    assert "8 MiB per-file limit" in error, "the refusal states the number it applied"


def test_a_bundle_past_the_per_plugin_total_cap_is_refused(tmp_path) -> None:
    def fatten(plugin_dir: Path) -> None:
        for index in range(3):
            (plugin_dir / "ui/vendor" / f"big{index}.js").write_bytes(
                b"y" * MAX_LIBRARY_FILE_BYTES
            )
            _add_library(plugin_dir, f"ui/vendor/big{index}.js")

    total_expected = MAX_LIBRARY_FILE_BYTES * 3 + (FIXTURE / LIBRARY_REL).stat().st_size
    assert total_expected > MAX_LIBRARY_TOTAL_BYTES, "the test data is over the cap"
    plugin = _bundle(tmp_path, fatten)
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert f"{total_expected} bytes" in error
    assert "24 MiB per-plugin limit" in error


def test_undeclared_bytes_under_the_vendor_root_are_refused(tmp_path) -> None:
    plugin = _bundle(tmp_path)
    (plugin / "ui/vendor/zzz-extra.js").write_text("undeclared\n")
    (plugin / "ui/vendor/aaa-extra.js").write_text("undeclared\n")
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert "aaa-extra.js" in error, "the walk is sorted, so the reason never depends on order"
    assert "nothing declares it" in error


def test_a_vendor_directory_with_no_declaration_at_all_is_refused(tmp_path) -> None:
    plugin = _bundle(tmp_path, lambda p: (p / LIBRARIES_FILENAME).unlink())
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert "every vendored file has to be declared" in error


def test_a_plugin_that_ships_no_library_reads_no_library_bytes(tmp_path, monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("a bundle with nothing declared hashes nothing")

    monkeypatch.setattr(plugin_libraries, "_file_sha256", explode)
    plain = _bundle(tmp_path / "src", name="hello-scene")
    (plain / LIBRARIES_FILENAME).unlink()
    shutil.rmtree(plain / "ui/vendor")
    manifest, error = load_manifest(plain)
    assert manifest is not None and error is None


# -- the shape of a declaration --


def _broken(field: str, value: object):
    def mutate(plugin_dir: Path) -> None:
        declaration = _declaration(plugin_dir)
        if field == "@root":
            declaration["schema"] = value
        elif field == "@list":
            declaration["libraries"] = value
        else:
            declaration["libraries"][0][field] = value
        _write_declaration(plugin_dir, declaration)

    return mutate


@pytest.mark.parametrize(
    "field, value, expected, extra",
    [
        ("path", "../outside.js", "must stay inside the plugin directory", None),
        ("path", "/etc/passwd", "must be a relative path", None),
        ("path", "ui\\vendor\\x.mjs", "must be a relative path", None),
        ("path", "ui/nothing-here.mjs", "does not ship", None),
        ("path", "ui/vendor/deep/x.mjs", "does not ship", None),
        ("path", "top-side.mjs", "sits above the entry document", "console.log(1);"),
        ("path", "ui/notes.txt", "a vendored library is one of", "state\n"),
        ("path", "ui/readme.md", "a vendored library is one of", "docs\n"),
        ("sha256", "0" * 63, "64 lowercase hex", None),
        ("sha256", "A" * 64, "64 lowercase hex", None),
        ("sha256", 12345, "64 lowercase hex", None),
        ("name", "Tiny Renderer", "lowercase slug", None),
        ("kind", "worker", "is not one of", None),
        ("kind", "script", "cannot load a .mjs", None),
        ("version", "x" * 65, "at most 64 characters", None),
        ("version", "   ", "non-empty string", None),
        ("sri", "sha256-abc", "unknown field", None),
        ("@root", 2, "schema must be 1", None),
        ("@list", [], "names nothing", None),
        ("@list", {"a": 1}, "list of library entries", None),
    ],
)
def test_a_declaration_outside_the_contract_quarantines_the_plugin(
    tmp_path, field, value, expected, extra
) -> None:
    plugin = _bundle(tmp_path, _broken(field, value))
    if extra is not None:
        (plugin / str(value)).parent.mkdir(parents=True, exist_ok=True)
        (plugin / str(value)).write_text(extra, encoding="utf-8")
    manifest, error = load_manifest(plugin)
    assert manifest is None, (field, value)
    assert expected in error, (field, value, error)


def test_a_missing_field_is_named_and_never_left_unread(tmp_path) -> None:
    def mutate(plugin_dir: Path) -> None:
        declaration = _declaration(plugin_dir)
        declaration["libraries"][0].pop("sha256")
        _write_declaration(plugin_dir, declaration)

    manifest, error = load_manifest(_bundle(tmp_path, mutate))
    assert manifest is None
    assert "missing field(s): sha256" in error


def test_two_declarations_of_one_file_are_refused(tmp_path) -> None:
    def mutate(plugin_dir: Path) -> None:
        declaration = _declaration(plugin_dir)
        clone = dict(declaration["libraries"][0])
        clone["name"] = "second-name"
        declaration["libraries"].append(clone)
        _write_declaration(plugin_dir, declaration)

    manifest, error = load_manifest(_bundle(tmp_path, mutate))
    assert manifest is None
    assert "duplicate declaration" in error


def test_unreadable_json_in_the_declaration_is_a_refusal(tmp_path) -> None:
    plugin = _bundle(tmp_path, lambda p: (p / LIBRARIES_FILENAME).write_text("{oops"))
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert "unreadable JSON" in error


def test_a_declared_library_needs_a_surface_that_can_load_it(tmp_path) -> None:
    def mutate(plugin_dir: Path) -> None:
        manifest = _loaded(plugin_dir)
        manifest["components"].pop("ui")
        (plugin_dir / "ephe-plugin.json").write_text(json.dumps(manifest))

    manifest, error = load_manifest(_bundle(tmp_path, mutate))
    assert manifest is None
    assert "needs a components.ui surface" in error


# -- WebAssembly: the one type a capability has to pay for --


def _ship_wasm(plugin_dir: Path) -> None:
    (plugin_dir / "ui/vendor/engine.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00" + b"\x00" * 32)
    _add_library(plugin_dir, "ui/vendor/engine.wasm", kind="wasm", name="mesh-decoder")


def test_a_wasm_library_without_the_wasm_capability_is_refused(tmp_path) -> None:
    manifest, error = load_manifest(_bundle(tmp_path, _ship_wasm))
    assert manifest is None
    assert "needs components.ui.capabilities to declare 'wasm'" in error


def test_a_wasm_library_with_the_capability_loads(tmp_path) -> None:
    def mutate(plugin_dir: Path) -> None:
        _ship_wasm(plugin_dir)
        _set_capabilities(plugin_dir, ["webgl", "wasm"])

    manifest, error = load_manifest(_bundle(tmp_path, mutate))
    assert error is None and manifest is not None


# -- the numbers, pinned to the layers that already state them --


def test_the_per_file_cap_is_the_surface_asset_cap() -> None:
    """One ceiling per byte count: a library validation accepted has to be a library
    the asset route can deliver, so the two constants stay one number."""
    assert MAX_LIBRARY_FILE_BYTES == plugin_surface.MAX_SURFACE_ASSET_BYTES


def test_every_declared_suffix_is_a_type_the_surface_route_serves() -> None:
    for suffix in plugin_libraries.LIBRARY_KIND_SUFFIXES:
        assert plugin_surface.ASSET_MEDIA_TYPES[suffix]


def test_the_wasm_capability_rule_is_the_same_at_both_layers() -> None:
    assert (
        plugin_libraries.LIBRARY_REQUIRED_CAPABILITIES["wasm"]
        == plugin_surface.ASSET_REQUIRED_CAPABILITIES["application/wasm"]
        == "wasm"
    )


def test_the_lockfile_hash_covers_the_declaration_and_the_vendor_bytes(tmp_path) -> None:
    clean = _bundle(tmp_path / "before")
    moved = _bundle(tmp_path / "after", lambda p: (p / LIBRARY_REL).write_text("evil\n"))
    assert dir_sha256(clean) != dir_sha256(moved)
    rewritten = _bundle(tmp_path / "declared")
    before = dir_sha256(rewritten)
    _write_declaration(rewritten, {"schema": 1, "libraries": []})
    assert dir_sha256(rewritten) != before, "the bytes and their promise both ride"


# -- the served mount --


def _home(tmp_path: Path, monkeypatch, plugin: Path) -> None:
    config = tmp_path / "ephe-home"
    shutil.copytree(plugin, config / "plugins" / plugin.name)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    plugin_runtime.invalidate_ownership_cache()


def _app(tmp_path, monkeypatch, mutate=None):
    from server.main import create_app

    _home(tmp_path, monkeypatch, _bundle(tmp_path / "src", mutate))
    return create_app(lan_mode=False)


def _nonce(app) -> str:
    """One live mount credential, reused so a later refusal still hits the same URL."""
    held = getattr(app.state, "surface_nonce", "")
    if held:
        return held
    transport = httpx.ASGITransport(app=app, client=(PEER_DESKTOP, 54321))

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as c:
            return await c.post(
                f"/api/plugins/{PLUGIN_ID}/surface-token",
                json={},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "http://127.0.0.1:8765",
                },
            )

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    nonce = response.json()["surface"]
    app.state.surface_nonce = nonce
    return nonce


def _get(app, url: str, peer: str = PEER_DESKTOP):
    if url.startswith(MOUNT):
        url = f"/api/plugins/ui/{PLUGIN_ID}/{_nonce(app)}/{url[len(MOUNT):]}"
    transport = httpx.ASGITransport(app=app, client=(peer, 54321))

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as c:
            return await c.get(url)

    return asyncio.run(run())


def _reason(response) -> str:
    return response.json()["error"]["reason_params"]["reason"]


def test_the_document_and_its_declared_library_arrive_from_the_mount(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    document = _get(app, MOUNT)
    assert document.status_code == 200, document.text
    assert f'src="{LIBRARY_URL}"' in document.text, "the entry loads it by relative path"
    library = _get(app, MOUNT + LIBRARY_URL)
    assert library.status_code == 200, library.text
    assert library.headers["content-type"].startswith("application/javascript")
    assert LIBRARY_MARK in library.text
    assert _csp_rows(library.headers["content-security-policy"])["script-src"] == "'self'"
    assert "sandbox" not in library.headers["content-security-policy"]
    assert library.headers["x-content-type-options"] == "nosniff"
    assert library.headers["cache-control"] == "no-store"


def test_a_tampered_vendor_file_stops_answering_on_the_next_request(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    url = MOUNT + LIBRARY_URL
    assert _get(app, url).status_code == 200
    shipped = Path(os.environ["EPHE_CONFIG_DIR"]) / "plugins" / PLUGIN_ID / LIBRARY_REL
    shipped.write_text("import('https://cdn.example/lib.js');\n", encoding="utf-8")
    refused = _get(app, url)
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["reason_code"] == "plugin_ui_unavailable"
    assert "hashes to" in _reason(refused), "the quarantined plugin keeps its own words"
    assert _get(app, MOUNT).status_code == 404, "the whole plugin is refused, the entry too"


def test_a_library_above_the_entry_is_something_the_mount_cannot_reach(tmp_path) -> None:
    """The reach rule in validation has a serving reason beside it: the asset walk
    refuses a `..` segment by text, so a document at `ui/index.html` has no URL that
    loads a file living above `ui/`."""
    plugin = _bundle(tmp_path)
    (plugin / "top-side.mjs").write_text("export const X = 1;\n", encoding="utf-8")
    held, reason = plugin_surface.resolve_surface_file(plugin, "../top-side.mjs")
    assert held is None
    assert reason == plugin_surface.REFUSED_SHAPES["walkout"]


def test_a_wasm_asset_never_arrives_for_a_surface_that_may_not_compile_it(
    tmp_path, monkeypatch
) -> None:
    def mutate(plugin_dir: Path) -> None:
        (plugin_dir / "ui/engine.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")

    app = _app(tmp_path, monkeypatch, mutate=mutate)
    refused = _get(app, MOUNT + "engine.wasm")
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
    assert "capability" in _reason(refused)


def test_a_wasm_asset_arrives_with_the_capability_that_lets_it_run(
    tmp_path, monkeypatch
) -> None:
    def mutate(plugin_dir: Path) -> None:
        (plugin_dir / "ui/engine.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
        _set_capabilities(plugin_dir, ["wasm"])

    app = _app(tmp_path, monkeypatch, mutate=mutate)
    served = _get(app, MOUNT + "engine.wasm")
    assert served.status_code == 200, served.text
    assert served.headers["content-type"].startswith("application/wasm")
    assert "'wasm-unsafe-eval'" in _csp_rows(served.headers["content-security-policy"])["script-src"]


@pytest.mark.parametrize("capability", sorted(UI_CAPABILITIES))
def test_no_capability_declaration_names_a_remote_source(capability) -> None:
    """Every widening the policy can build keeps `script-src` on this origin, so a
    document that invents a CDN `<script>` gets nothing back. The offline path of
    `core/plugin_libraries.py` is the answer this suite pins."""
    policy = plugin_surface_policy.surface_content_security_policy(
        [capability], ["http://127.0.0.1:8765", "tauri://localhost"]
    )
    rows = _csp_rows(policy)
    loaded = {name: sources for name, sources in rows.items() if name != "frame-ancestors"}
    assert rows["default-src"] == "'self'"
    assert rows["script-src"] in ("'self'", "'self' 'wasm-unsafe-eval'")
    assert rows["style-src"] == "'self' 'unsafe-inline'"
    assert "connect-src" not in rows
    assert "*" not in " ".join(loaded.values())
    assert "://" not in " ".join(loaded.values())
