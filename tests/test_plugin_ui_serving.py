"""The plugin surface route: one document, its assets, and a CSP per declaration.

This route is the first place in the product that serves plugin-written HTML into a
privileged webview, so every test here reads it from the attacker's side: a manifest
naming a path outside its own directory, a URL walking out with `..`, a credential
minted for one plugin and offered to another, a policy claiming a capability the
manifest never granted, a document trying to spend the user's own authority.

Two boundaries hold together. The document and its assets carry a
`Content-Security-Policy` assembled from `components.ui.capabilities`, and the
document carries a `sandbox` without `allow-same-origin` so an attacker-authored
page arrives on an opaque origin — the browser half of that claim is measured in
`tests/test_plugin_surface_isolation_browser.py`, and the transport half is
probed here at the HTTP level. A plugin surface authenticates with a short-lived
nonce riding a path segment inside a directory-shaped mount URL, on loopback and
off it, because an iframe can send no header and a query string is not inherited
by the sub-resources the document derives. The app's own fetches of other `/api`
routes stay token-free on loopback.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_runtime  # noqa: E402
from server.middleware import init_auth  # noqa: E402

ENTRY_MARK = "<!doctype html><title>Countdown</title>"
OUTSIDE_MARK = "OUTSIDE-OF-THE-PLUGIN-DIRECTORY"
DEFAULT_CAPABILITIES = ["notifications", "dock-badge"]
PLUGIN_ID = "acme-countdown"
PEER_LAN = "192.168.50.99"
PEER_DESKTOP = "127.0.0.1"

#: every file one surface plugin ships; asset URLs below are relative to the
#: entry's own directory, exactly as a browser derives them from the document URL
SHIPPED = {
    "ui/index.html": f"{ENTRY_MARK}<script src='app.js'></script>",
    "ui/app.js": "console.log('surface');",
    "ui/theme.css": "body{margin:0}",
    "ui/mark.svg": "<svg xmlns='x'></svg>",
    "ui/keep.txt": "not-a-surface-type",
    # a POSIX filename may legally hold a backslash: only the text-level shape
    # check refuses it, and the two tests below say so on their own
    "ui/a\\b.js": "BACKSLASH-FILE-CONTENT",
    "ui/deep/extra.js": "console.log('nested');",
    "ui/panel/frame.css": "body{color:rebeccapurple}",
    "tools/helper.py": "VALUE = 1",
    "state.json": '{"secret": 1}',
}


def _manifest(name: str, capabilities: list[str], entry: str) -> dict:
    return {
        "manifest_version": 1,
        "name": name,
        "version": "1.0.0",
        "description": "A countdown that survives a restart",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {
            "skills": [], "commands": [],
            "ui": {
                "type": "floating-window", "entry": entry, "title": "Countdown",
                "capabilities": capabilities,
            },
        },
    }


def _home(tmp_path: Path, monkeypatch, specs: dict[str, dict], disabled=()) -> Path:
    """A config home holding these plugins, plus the switch states named."""
    config = tmp_path / "ephe-home"
    for name, spec in specs.items():
        plugin = config / "plugins" / name
        manifest = spec.get("raw_manifest") or _manifest(
            name, list(spec.get("capabilities", DEFAULT_CAPABILITIES)),
            str(spec.get("entry", "ui/index.html")),
        )
        for rel, text in SHIPPED.items():
            target = plugin / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (plugin / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (config / "outside.html").write_text(OUTSIDE_MARK, encoding="utf-8")
    states = {name: {"user": {"committed": "disabled"}} for name in disabled}
    (config / "plugin-state.json").write_text(
        json.dumps({"schema": 1, "pause_all": False, "plugins": states}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    plugin_runtime.invalidate_ownership_cache()
    return config


def _app(tmp_path, monkeypatch, *, lan: bool = False, specs=None, disabled=()):
    from server.main import create_app

    _home(tmp_path, monkeypatch, specs or {PLUGIN_ID: {}}, disabled)
    return create_app(lan_mode=lan)


def _call(
    app, path: str, *, method: str = "GET", peer: str = PEER_DESKTOP,
    host: str = "127.0.0.1:8765", headers: dict | None = None, body: dict | None = None,
    params: dict | None = None,
):
    """One request through the real middleware stack, with the peer and Host named.

    A desktop mutation that names no Origin is sent as the app, at
    ``http://127.0.0.1:8765``. The shell's own fetch carries that header.
    """
    sent = dict(headers or {})
    if (
        method not in {"GET", "HEAD", "OPTIONS"}
        and "origin" not in {key.lower() for key in sent}
        and peer in {"127.0.0.1", "::1", "localhost"}
    ):
        sent["Origin"] = "http://127.0.0.1:8765"
    transport = httpx.ASGITransport(app=app, client=(peer, 54321))

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url=f"http://{host}") as c:
            return await c.request(method, path, headers=sent, json=body, params=params)

    return asyncio.run(run())


@pytest.fixture(autouse=True)
def _auth_stays_off():
    yield
    init_auth(lan_mode=False)


def _origins(entries) -> list[str]:
    """A `frame-ancestors` list as scheme+authority, parsed instead of substring-matched.

    `"https://a.example" in kept` answers yes for `https://a.example.evil.example` and
    for `https://user:pass@a.example` — the incomplete-URL-substring shape, and a weaker
    assertion than a header deserves. `urlsplit` compares the two parts a CSP entry is;
    a keyword (`'self'`) or a non-URL scheme (`javascript:`) passes through as written.
    """
    out: list[str] = []
    for entry in entries:
        parsed = urlsplit(entry)
        if parsed.scheme and parsed.netloc:
            out.append(f"{parsed.scheme}://{parsed.netloc}")
        else:
            out.append(entry)
    return out


def _lan_headers(app):
    from server import middleware

    return {"X-Auth-Token": middleware.LAN_AUTH_TOKEN, "X-Requested-With": "XMLHttpRequest"}


def _remote(path: str, app=None, **kwargs):
    return _call(app, path, peer=PEER_LAN, host=f"{PEER_LAN}:8765", **kwargs)


def _csp_of(response) -> dict[str, str]:
    """The policy as directive -> its sources, so a test names the directive it checks."""
    header = response.headers["content-security-policy"]
    rows = [chunk.strip().partition(" ") for chunk in header.split(";")]
    return {name: sources for name, _, sources in rows if name}


def _mint_response(app, plugin_id: str):
    """The mint call itself. LAN mode presents the token. Desktop does not."""
    from server import middleware

    path = f"/api/plugins/{plugin_id}/surface-token"
    headers = {"X-Requested-With": "XMLHttpRequest"}
    if middleware.LAN_AUTH_TOKEN is not None:
        headers["X-Auth-Token"] = middleware.LAN_AUTH_TOKEN
        return _remote(path, app, method="POST", body={}, headers=headers)
    return _call(app, path, method="POST", body={}, headers=headers)


def _mint(app, plugin_id: str) -> str:
    response = _mint_response(app, plugin_id)
    assert response.status_code == 200, response.text
    return response.json()["surface"]


def _mount(plugin_id: str = PLUGIN_ID, nonce: str | None = None) -> str:
    """The directory-shaped document URL; the nonce segment rides inside it."""
    return f"/api/plugins/ui/{plugin_id}/" if nonce is None else f"/api/plugins/ui/{plugin_id}/{nonce}/"


def _asset(plugin_id: str, relative: str, nonce: str | None = None) -> str:
    return _mount(plugin_id, nonce) + relative


def _document(
    app, plugin_id: str = PLUGIN_ID, nonce: str | None = None, *, credential: bool = True, **kwargs
):
    """The document. A missing nonce is minted, unless the case asks for the bare URL."""
    if nonce is None and credential:
        minted = _mint_response(app, plugin_id)
        if minted.status_code != 200:
            return minted
        nonce = minted.json()["surface"]
    return _call(app, _mount(plugin_id, nonce), **kwargs)


def _load(app, relative: str, plugin_id: str = PLUGIN_ID, **kwargs):
    """One asset beside the entry, through a live nonce for that plugin."""
    minted = _mint_response(app, plugin_id)
    if minted.status_code != 200:
        return minted
    return _call(app, _asset(plugin_id, relative, minted.json()["surface"]), **kwargs)


def _reason(response) -> str:
    return response.json()["error"]["reason_params"]["reason"]


# -- the document --


def test_an_active_surface_serves_its_document_with_the_header_set(tmp_path, monkeypatch):
    response = _document(_app(tmp_path, monkeypatch))
    assert response.status_code == 200, response.text
    # The mount places the storage shim directly after the doctype, so the entry's
    # own bytes follow it rather than starting the body.
    assert response.text.startswith("<!doctype html>")
    assert "<title>Countdown</title>" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    csp = _csp_of(response)
    for directive, value in (
        ("default-src", "'self'"), ("script-src", "'self'"), ("object-src", "'none'"),
        ("base-uri", "'none'"), ("form-action", "'none'"),
    ):
        assert csp[directive] == value, csp
    # the attacker-authored document holds no same-origin authority: the token
    # that removes it (`allow-same-origin`) must never appear in the header.
    assert csp["sandbox"] == "allow-scripts allow-popups", csp
    assert "allow-same-origin" not in response.headers["content-security-policy"]


def test_the_bare_mount_url_redirects_to_the_directory_shape(tmp_path, monkeypatch):
    """A document without the trailing slash resolves its assets beside the plugin
    id; the old shape must send every caller to the URL a browser can use."""
    response = _call(_app(tmp_path, monkeypatch), f"/api/plugins/ui/{PLUGIN_ID}")
    assert response.status_code == 307, response.text
    assert response.headers["location"] == _mount()


def test_a_disabled_plugin_is_refused_while_its_active_sibling_serves(tmp_path, monkeypatch):
    """A mount credential is bought while the bundle is on; switching it off closes the
    document that credential points at. The credential belongs to the surface's life, not
    to the switch, so the reader meets the 404 and not a stale frame."""
    app = _app(tmp_path, monkeypatch,
               specs={PLUGIN_ID: {}, "acme-other": {"capabilities": ["notifications"]}})
    surface = _mint(app, "acme-other")
    switched_off = _call(
        app, "/api/plugins/acme-other/enabled", method="PUT",
        body={"enabled": False}, headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert switched_off.status_code == 200, switched_off.text
    refused = _document(app, "acme-other", surface)
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["reason_code"] == "plugin_ui_unavailable"
    assert _document(app).status_code == 200


def test_a_plugin_declaring_no_surface_is_refused(tmp_path, monkeypatch):
    bare = _manifest("acme-headless", [], "ui/index.html")
    bare["components"] = {"skills": [], "commands": []}
    refused = _document(_app(tmp_path, monkeypatch, specs={"acme-headless": {"raw_manifest": bare}}),
                        "acme-headless")
    assert refused.status_code == 404
    assert refused.json()["error"]["reason_code"] == "plugin_ui_unavailable"


@pytest.mark.parametrize(
    "entry, marker", [("../outside.html", OUTSIDE_MARK), ("/etc/passwd", "root:")]
)
def test_a_manifest_naming_an_entry_outside_the_directory_returns_no_content(
    tmp_path, monkeypatch, entry, marker
):
    escaping = _manifest(PLUGIN_ID, DEFAULT_CAPABILITIES, entry)
    response = _document(_app(tmp_path, monkeypatch, specs={PLUGIN_ID: {"raw_manifest": escaping}}))
    assert response.status_code == 404, response.text
    assert marker not in response.text


def test_the_surface_document_reaches_no_api_authority_as_a_null_origin(
    tmp_path, monkeypatch
):
    """The HTTP half of the opaque-origin claim, probed without a browser.

    A sandboxed document's requests carry `Origin: null` and can never be read
    cross-origin, and off loopback it holds no credential: what a mount would
    use the user's token for arrives here as a refusal. `/api/file` and
    `/api/settings` — the two reads the review named — answer the null-origin
    client with a 401 and never with an allow header that would let the browser
    hand the body back. The browser half, that the engine really sends those
    requests from an opaque origin, is measured by the Playwright suite.
    """
    app = _app(tmp_path, monkeypatch, lan=True)
    for path in (
        "/api/settings",
        "/api/file?path=" + quote(str(Path(os.environ["EPHE_CONFIG_DIR"]) / "outside.html")),
    ):
        attempted = _remote(path, app, headers={"Origin": "null"})
        assert attempted.status_code == 401, (path, attempted.text)
        assert attempted.headers.get("access-control-allow-origin") not in ("null", "*")
    mutation = _remote(
        "/api/plugins/master", app, method="POST", body={},
        headers={"Origin": "null", "X-Requested-With": "XMLHttpRequest"},
    )
    assert mutation.status_code == 401, mutation.text


# -- the policy --


def test_wasm_unsafe_eval_arrives_only_with_the_wasm_capability(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, specs={
        "acme-wasm": {"capabilities": ["wasm"]}, "acme-gl": {"capabilities": ["webgl"]},
    })
    assert "'wasm-unsafe-eval'" in _csp_of(_document(app, "acme-wasm"))["script-src"]
    plain = _csp_of(_document(app, "acme-gl"))
    assert plain["script-src"] == "'self'"
    assert "wasm-unsafe-eval" not in _document(app, "acme-gl").headers["content-security-policy"]


def test_worker_src_arrives_only_with_the_workers_capability(tmp_path, monkeypatch):
    """Honest shape: the widening exists and its `'self'` is the app origin — no
    per-plugin origin exists to widen against, and the capability record in
    core/plugin_ui_capabilities.py says the layer is not per-plugin yet."""
    app = _app(tmp_path, monkeypatch, specs={
        "acme-w": {"capabilities": ["workers"]}, "acme-q": {"capabilities": ["wasm"]},
    })
    assert _csp_of(_document(app, "acme-w"))["worker-src"] == "'self' blob:"
    assert "worker-src" not in _document(app, "acme-q").headers["content-security-policy"]


def test_no_capability_broadens_connect_src(tmp_path, monkeypatch):
    """`network` names hosts a manifest cannot carry today, so nothing is widened."""
    app = _app(tmp_path, monkeypatch, specs={"acme-net": {"capabilities": ["network"]}})
    assert "connect-src" not in _document(app, "acme-net").headers["content-security-policy"]


def test_frame_ancestors_names_our_origins_and_never_a_wildcard(tmp_path, monkeypatch):
    csp = _csp_of(_document(_app(tmp_path, monkeypatch)))
    assert "*" not in csp["frame-ancestors"]
    assert "'self'" in csp["frame-ancestors"]
    assert "tauri://localhost" in _origins(csp["frame-ancestors"].split())


def test_the_ancestor_filter_keeps_authorities_and_drops_everything_else():
    """The unit layer over `frame_ancestors`, whose input includes the operator's
    `EPHE_DEV_ORIGINS`: a scheme plus an authority survives, a wildcard, a
    fragment, a bare word or an empty entry never reaches the header."""
    from server import plugin_surface_policy

    kept = plugin_surface_policy.frame_ancestors([
        "https://a.example", "  https://pad.example  ", "http://b.example:8123",
        "tauri://localhost", "*", "'none'", "https://x.example/../", "", None,
        "javascript:alert(1)", "https://user:pass@creep.example",
    ])
    assert kept[0] == "'self'"
    # The whole list, by origin: a path-walk entry (`https://x.example/../`) and one
    # carrying userinfo (`https://user:pass@creep.example`) are dropped, and a sibling
    # host that merely starts with an allowed one cannot match a substring here.
    assert _origins(kept) == [
        "'self'", "http://b.example:8123", "https://a.example",
        "https://pad.example", "tauri://localhost",
    ]
    for refused in ("*", "'none'", "javascript:alert(1)", ""):
        assert refused not in kept, kept


def test_a_wildcard_dev_origin_never_reaches_the_served_header(tmp_path, monkeypatch):
    """The operator widens the allow-set through `EPHE_DEV_ORIGINS`; a stray `*`
    in that list is dropped by the filter before the header is assembled."""
    monkeypatch.setenv("EPHE_DEV_ORIGINS", "* ,https://dev.example")
    csp = _csp_of(_document(_app(tmp_path, monkeypatch)))
    origins = _origins(csp["frame-ancestors"].split())
    assert any(entry == "https://dev.example" for entry in origins), csp
    assert all(entry != "*" for entry in origins), csp


def test_the_sandbox_lands_on_documents_and_on_nothing_a_mount_has_to_load(
    tmp_path, monkeypatch
):
    """`.js` and `.css` arrive un-sandboxed or the mount cannot boot; a nested
    `.html` is a document of its own and arrives sandboxed like the entry."""
    app = _app(tmp_path, monkeypatch)
    for name in ("app.js", "theme.css"):
        response = _load(app, name)
        assert response.status_code == 200, name
        assert "sandbox" not in response.headers["content-security-policy"], name
    nested = _load(app, "index.html")
    assert nested.status_code == 200
    assert nested.headers["content-type"].startswith("text/html")
    assert "allow-same-origin" not in nested.headers["content-security-policy"]
    assert "sandbox" in _csp_of(nested)


# -- the assets --


def test_a_module_fetch_of_its_own_file_names_the_opaque_origin(tmp_path, monkeypatch):
    """`<script type="module">` is fetched in CORS mode, so a sandboxed document
    whose origin is `null` reads its own script only if the response says so. A
    classic `<script>` asks for nothing and a module asks for exactly this, which
    is why a surface written with ESM in it loads no code at all while the header
    is missing. Naming an origin is not the same as lending a credential: this
    server sets no cookie and gives the mount no token, so the bytes arrive with a
    name on them."""
    app = _app(tmp_path, monkeypatch)
    for name in ("app.js", "theme.css", "deep/extra.js"):
        granted = _load(app, name, headers={"Origin": "null"})
        assert granted.status_code == 200, name
        assert granted.headers.get("access-control-allow-origin") == "null", name
        assert "set-cookie" not in granted.headers, name
        assert "Origin" in granted.headers.get("vary", ""), name


def test_the_opaque_origin_grant_reaches_no_other_caller(tmp_path, monkeypatch):
    """The word `null` is the whole widening: a request from an ordinary origin,
    and one that sends no Origin at all, get the same bytes with no grant naming
    them, so nothing here hands a file to a caller that a classic `<script>` could
    not already load."""
    app = _app(tmp_path, monkeypatch)
    for origin in ("https://evil.example", "http://127.0.0.1:8765"):
        refused = _load(app, "app.js", headers={"Origin": origin})
        assert refused.status_code == 200, origin
        assert refused.headers.get("access-control-allow-origin") != "null", origin
    silent = _load(app, "app.js")
    assert silent.status_code == 200
    assert silent.headers.get("access-control-allow-origin") != "null"


def test_declared_asset_types_arrive_with_their_media_type(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    for name, expected in (
        ("app.js", "application/javascript"), ("theme.css", "text/css"),
        ("index.html", "text/html"), ("deep/extra.js", "application/javascript"),
    ):
        response = _load(app, name)
        assert response.status_code == 200, (name, response.text)
        assert response.headers["content-type"].startswith(expected), name
        assert "'self'" in _csp_of(response)["script-src"], name


def test_an_undeclared_media_type_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    for name in ("keep.txt", "state.json", "tools/helper.py"):
        response = _load(app, name)
        assert response.status_code == 400, name
        assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
        assert "not-a-surface-type" not in response.text


def test_a_plugin_svg_is_never_served_as_a_scriptable_document(tmp_path, monkeypatch):
    response = _load(_app(tmp_path, monkeypatch), "mark.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "sandbox" in response.headers["content-security-policy"]


def test_a_directory_never_answers_with_a_listing(tmp_path, monkeypatch):
    response = _load(_app(tmp_path, monkeypatch), "panel")
    assert response.status_code == 400
    assert "frame.css" not in response.text


@pytest.mark.parametrize(
    "walkout",
    [
        "%2e%2e/outside.html",
        "..%2f..%2f..%2foutside.html",
        "deep/%2e%2e/%2e%2e/%2e%2e/outside.html",
        "ui/%2e%2e/outside.html",
    ],
)
def test_a_walking_path_is_refused_by_the_text_layer_and_by_under_too(tmp_path, monkeypatch, walkout):
    """Coded refusal on the way out, and no content on the way back.

    These shapes are caught twice on purpose: the text-level `..` refusal fires
    first, and `_under` resolves every one of them outside the directory even if
    that text check were deleted — the layers standing on their own each have a
    test of their own below, and this one keeps the pair honest together.
    """
    app = _app(tmp_path, monkeypatch)
    response = _load(app, walkout)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
    assert OUTSIDE_MARK not in response.text


def test_the_text_layer_refuses_a_backslash_a_posix_filename_could_legally_hold(
    tmp_path, monkeypatch
):
    """The shape check stands alone: a file named `a\\b.js` really exists inside
    the entry directory, `_under` would resolve it to that file, and serving
    scanner-shaped text is what the contract refuses before any syscall."""
    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    real = config / "plugins" / PLUGIN_ID / "ui" / "a\\b.js"
    assert real.is_file()
    response = _load(_app(tmp_path, monkeypatch), quote("a\\b.js"))
    assert response.status_code == 400, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
    assert _reason(response) == "the path holds a segment a URL may not carry"
    assert "BACKSLASH-FILE-CONTENT" not in response.text


def test_the_text_layer_refuses_a_nul_before_a_syscall_could_raise_over_it(
    tmp_path, monkeypatch
):
    """And the NUL stands alone the other way: `os.path.realpath` answers an
    embedded NUL with a `ValueError`, so deleting the text check turns this
    request into a 500 where the route owes the reader a coded refusal."""
    app = _app(tmp_path, monkeypatch)
    response = _load(app, quote("a\x00b.js"))
    assert response.status_code == 400, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
    assert _reason(response) == "the path holds a segment a URL may not carry"


def test_an_asset_past_the_size_bound_is_refused(tmp_path, monkeypatch):
    from server import plugin_surface

    app = _app(tmp_path, monkeypatch)
    monkeypatch.setattr(plugin_surface, "MAX_SURFACE_ASSET_BYTES", 4)
    response = _load(app, "app.js")
    assert response.status_code == 400
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"


def test_a_symlink_inside_the_plugin_directory_is_refused_before_it_is_read(
    tmp_path, monkeypatch
):
    """The named containment case: the author ships `ui/escape.html` pointing at
    the config home's own file. `_under` resolves the link, sees it land outside
    the directory, and the request never reaches an open(); the bytes of
    `outside.html` never travel back."""
    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    link = config / "plugins" / PLUGIN_ID / "ui" / "escape.html"
    link.symlink_to(config / "outside.html")
    response = _load(_app(tmp_path, monkeypatch), "escape.html")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"
    assert OUTSIDE_MARK not in response.text


def test_a_symlink_swapped_in_after_containment_is_refused_by_the_open(tmp_path, monkeypatch):
    """TOCTOU: the author edits the directory while a request is in flight. The
    path passes containment as a real file, the author then replaces it with a
    link out, and the read — done through the component walk, whose every step
    carries `O_NOFOLLOW` — refuses the swap. A `read_bytes()` by path would have
    returned the secret.
    """
    from server import plugin_surface

    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    plugin = config / "plugins" / PLUGIN_ID
    victim = plugin / "ui" / "app.js"
    held, reason = plugin_surface.resolve_surface_file(plugin, "ui/app.js")
    assert (held, reason) == (victim.resolve(), "")
    victim.unlink()
    victim.symlink_to(config / "outside.html")
    data, refused = plugin_surface.read_surface_bytes(plugin, "ui/app.js")
    assert data is None
    assert refused == plugin_surface.REFUSED_SHAPES["walkout"]
    # the same path still hands its bytes to a plain `read_bytes()` — that is
    # exactly the read the old code did, and exactly why the descriptor matters
    assert OUTSIDE_MARK.encode() in held.read_bytes()


def test_an_intermediate_directory_swapped_for_a_link_is_refused_by_the_walk(
    tmp_path, monkeypatch
):
    """The same race one level up, which the leaf flag never covered.

    `O_NOFOLLOW` applies to the last component of the name handed to `os.open`, so a
    check that refuses a link at `ui/app.js` still follows a link at `ui/`: the
    author ships a real `ui/`, the request passes containment against it, the author
    then removes the directory and puts a symlink to an outside one in its place, and
    an open by path walks straight out. The read resolves no component by path — each
    one is opened on its parent's descriptor, so the swapped step is the step that
    dies. A plain `read_bytes()` on the proven path still returns the secret, which is
    the leak this layer exists for.
    """
    from server import plugin_surface

    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    plugin = config / "plugins" / PLUGIN_ID
    held, reason = plugin_surface.resolve_surface_file(plugin, "ui/app.js")
    assert (held, reason) == ((plugin / "ui" / "app.js").resolve(), "")
    elsewhere = config / "elsewhere"
    (elsewhere / "nested").mkdir(parents=True)
    for target in (elsewhere / "app.js", elsewhere / "nested" / "app.js"):
        target.write_text(OUTSIDE_MARK, encoding="utf-8")
    shutil.rmtree(plugin / "ui")
    (plugin / "ui").symlink_to(elsewhere)
    data, refused = plugin_surface.read_surface_bytes(plugin, "ui/app.js")
    assert data is None, data
    assert refused == plugin_surface.REFUSED_SHAPES["walkout"]
    # the very path containment proved is still readable by path
    assert OUTSIDE_MARK.encode() in held.read_bytes()


def test_read_surface_bytes_serves_a_contained_file_and_bounds_the_rest(tmp_path):
    """The descriptor walk in its honest states: the file it was proven for, a
    directory, a leaf that is a link, and a step of the walk that is one."""
    from server import plugin_surface

    plugin = tmp_path / "plugins" / PLUGIN_ID
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "app.js").write_text("console.log('x');", encoding="utf-8")
    held, _ = plugin_surface.resolve_surface_file(plugin, "ui/app.js")
    data, reason = plugin_surface.read_surface_bytes(plugin, "ui/app.js")
    assert (reason, data == b"console.log('x');") == ("", True)
    data, reason = plugin_surface.read_surface_bytes(plugin, "ui")
    assert data is None and reason == plugin_surface.REFUSED_SHAPES["listing"]
    sneaky = plugin / "ui" / "gone.js"
    sneaky.symlink_to("/etc/hostname")
    assert plugin_surface.read_surface_bytes(plugin, "ui/gone.js") == (
        None, plugin_surface.REFUSED_SHAPES["walkout"])
    # a step that is a link *inside* the root is refused too: `realpath` blessed it at
    # the check, the walk refuses it, and the walk is the layer holding the bytes
    (plugin / "mirror").symlink_to(plugin / "ui")
    assert plugin_surface.read_surface_bytes(plugin, "mirror/app.js") == (
        None, plugin_surface.REFUSED_SHAPES["walkout"])
    # a step that is a regular file is the same `missing` the check layer gives a path
    # running through one
    assert plugin_surface.read_surface_bytes(plugin, "ui/app.js/deep.js") == (
        None, plugin_surface.REFUSED_SHAPES["missing"])
    shutil.rmtree(plugin / "ui")
    (plugin / "ui").symlink_to(tmp_path)
    assert plugin_surface.read_surface_bytes(plugin, "ui/app.js") == (
        None, plugin_surface.REFUSED_SHAPES["walkout"])
    # the text layer is shared with the containment check, so the walk never sees
    # a segment that would open legally on a directory descriptor
    assert plugin_surface.read_surface_bytes(plugin, "../ephe-plugin.json")[1] == (
        plugin_surface.REFUSED_SHAPES["walkout"])


# -- the nonce --


def test_a_surface_token_is_short_lived_and_is_never_the_lan_token(tmp_path, monkeypatch):
    from server import middleware, plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    assert surface != middleware.LAN_AUTH_TOKEN
    assert len(surface) >= 16
    record = plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface)
    assert record is not None and record.plugin_id == PLUGIN_ID
    # The record carries the module's configured lifetime and no clock is read to answer
    # for it. Spelled as a ceiling against a literal, that same fact lands in the shape
    # tests/test_timing_assertion_guard.py refuses inside the parallel leg, so the row
    # says equality and stays load-insensitive. The lifetime running out is the subject of
    # `test_an_expired_surface_token_is_refused`, which moves the clock and waits on
    # nothing.
    assert record.ttl_seconds == plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS


def test_a_token_minted_for_one_plugin_is_refused_for_another(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, lan=True,
               specs={PLUGIN_ID: {}, "acme-other": {"capabilities": ["notifications"]}})
    surface = _mint(app, PLUGIN_ID)
    stolen = _remote(_mount("acme-other", surface), app)
    assert stolen.status_code == 401, stolen.text
    assert stolen.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
    held = _remote(_mount(PLUGIN_ID, surface), app)
    assert held.status_code == 200, held.text


def test_an_expired_surface_token_is_refused(tmp_path, monkeypatch):
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    started = plugin_surface_nonce.surface_clock()
    monkeypatch.setattr(plugin_surface_nonce, "surface_clock",
                        lambda: started + plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS + 1)
    stale = _remote(_mount(PLUGIN_ID, surface), app)
    assert stale.status_code == 401
    assert stale.json()["error"]["reason_code"] == "plugin_ui_unauthorized"


def _renew(app, plugin_id: str, surface: str, headers: dict | None = None):
    """POST the standing credential back to the mint route."""
    return _remote(
        f"/api/plugins/{plugin_id}/surface-token",
        app,
        method="POST",
        body={"surface": surface},
        headers=_lan_headers(app) if headers is None else headers,
    )


def test_a_document_fetch_leaves_the_nonce_clock_where_the_mint_set_it(tmp_path, monkeypatch):
    """A sub-resource loaded while the mount is open leaves the credential's
    start where the mint put it. The clock moves when the authenticated route
    is asked to renew, and only then."""
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    issued = plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface).issued_at
    loaded = _remote(_asset(PLUGIN_ID, "app.js", surface), app)
    assert loaded.status_code == 200, loaded.text
    assert plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface).issued_at == issued


def test_an_authenticated_renewal_keeps_the_same_nonce_past_its_first_window(
    tmp_path, monkeypatch
):
    """The parent asks the mint route to keep the standing credential. The value
    in the URL stays the one the frame already holds, so a fetch after the
    original window still serves on the LAN path and on the desktop path. The
    lifetime of that value stays the module constant, and once the renewed
    window ends the same URL is refused again."""
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    started = plugin_surface_nonce.surface_clock()
    monkeypatch.setattr(plugin_surface_nonce, "surface_clock", lambda: started + 200)
    renewed = _renew(app, PLUGIN_ID, surface)
    assert renewed.status_code == 200, renewed.text
    body = renewed.json()
    assert body["surface"] == surface
    assert body["expires_in"] == int(plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS)
    assert plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface).issued_at == started + 200
    later = started + 200 + plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS - 1
    monkeypatch.setattr(plugin_surface_nonce, "surface_clock", lambda: later)
    lan_doc = _remote(_mount(PLUGIN_ID, surface), app)
    assert lan_doc.status_code == 200, lan_doc.text
    desktop_doc = _document(app, nonce=surface)
    assert desktop_doc.status_code == 200, desktop_doc.text
    assert "<title>Countdown</title>" in desktop_doc.text
    lan_asset = _remote(_asset(PLUGIN_ID, "app.js", surface), app)
    assert lan_asset.status_code == 200, lan_asset.text
    ended = started + 200 + plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS + 1
    monkeypatch.setattr(plugin_surface_nonce, "surface_clock", lambda: ended)
    stale = _remote(_mount(PLUGIN_ID, surface), app)
    assert stale.status_code == 401
    assert stale.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
    desktop_stale = _document(app, nonce=surface)
    assert desktop_stale.status_code != 200
    assert ENTRY_MARK not in desktop_stale.text


def test_a_dead_nonce_stays_dead_when_it_is_offered_again(tmp_path, monkeypatch):
    """Once the window has passed, presenting the old value to the mint route
    answers 401. A later fetch of that URL stays refused. A fresh mint is a
    different value, and the old URL stays refused beside it."""
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    started = plugin_surface_nonce.surface_clock()
    monkeypatch.setattr(
        plugin_surface_nonce,
        "surface_clock",
        lambda: started + plugin_surface_nonce.SURFACE_NONCE_TTL_SECONDS + 1,
    )
    again = _renew(app, PLUGIN_ID, surface)
    assert again.status_code == 401, again.text
    assert again.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
    assert _remote(_mount(PLUGIN_ID, surface), app).status_code == 401
    fresh = _mint(app, PLUGIN_ID)
    assert fresh != surface
    assert _remote(_mount(PLUGIN_ID, surface), app).status_code == 401
    assert _remote(_mount(PLUGIN_ID, fresh), app).status_code == 200


def test_a_renewal_for_another_plugin_leaves_the_live_mount_serving(tmp_path, monkeypatch):
    """A credential offered under a different plugin id is refused, and the
    mount it was minted for keeps serving."""
    app = _app(
        tmp_path,
        monkeypatch,
        lan=True,
        specs={PLUGIN_ID: {}, "acme-other": {"capabilities": ["notifications"]}},
    )
    surface = _mint(app, PLUGIN_ID)
    stolen = _renew(app, "acme-other", surface)
    assert stolen.status_code == 401, stolen.text
    held = _remote(_mount(PLUGIN_ID, surface), app)
    assert held.status_code == 200, held.text


def test_a_renewal_without_the_lan_credential_leaves_the_clock_alone(tmp_path, monkeypatch):
    """A URL copied into a message can be replayed only inside its window, and
    presenting it to the mint route without the caller's credential does not
    move the clock."""
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    issued = plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface).issued_at
    bare = _renew(app, PLUGIN_ID, surface, headers={})
    assert bare.status_code == 401, bare.text
    assert plugin_surface_nonce.surface_nonce_record(PLUGIN_ID, surface).issued_at == issued


def test_a_forged_surface_token_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, lan=True)
    forged = _remote(_mount(PLUGIN_ID, "a" * 32), app)
    assert forged.status_code == 401
    assert forged.json()["error"]["reason_code"] == "plugin_ui_unauthorized"


def test_a_missing_nonce_is_refused_on_the_desktop_path_and_off_loopback(
    tmp_path, monkeypatch
):
    """The surface family requires its path nonce on every peer.

    Off loopback the missing LAN token is still a 401 from the token check.
    On the desktop path the same bare mount is refused before a byte of the
    plugin directory is read, and a mount that carries a live nonce still serves.
    """
    app = _app(tmp_path, monkeypatch, lan=True)
    remote = _document(app, credential=False, peer=PEER_LAN, host=f"{PEER_LAN}:8765")
    assert remote.status_code == 401, remote.text
    assert remote.json()["error"]["code"] == "auth_error"
    bare = _document(app, credential=False)
    assert bare.status_code == 401, bare.text
    assert bare.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
    assert _document(app).status_code == 200


def test_an_asset_needs_the_same_credential_as_its_document(tmp_path, monkeypatch):
    """Rewritten to the shape a browser actually issues: the document mounts at
    the directory URL with its nonce segment, the sub-resource the page derives
    (`<script src='app.js'>` beside the entry) carries the same segment for free,
    and the same URL with the segment removed arrives credential-less and dies.
    The old query-string form is dead too: nothing in the path means no mount.
    """
    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    granted = _remote(_asset(PLUGIN_ID, "app.js", surface), app)
    assert granted.status_code == 200, granted.text
    stripped = _remote(_asset(PLUGIN_ID, "app.js"), app)
    assert stripped.status_code == 401, stripped.text
    query_only = _remote(_asset(PLUGIN_ID, "app.js"), app, params={"surface": surface})
    assert query_only.status_code == 401, query_only.text
    bare_stripped = _remote(f"/api/plugins/ui/{PLUGIN_ID}", app, params={"surface": surface})
    assert bare_stripped.status_code == 401, bare_stripped.text
    after = _remote(_mount(PLUGIN_ID), app, params={"surface": surface})
    assert after.status_code == 401, after.text


def test_a_mount_nonce_with_no_trailing_slash_answers_the_directory_shape(
    tmp_path, monkeypatch
):
    """`/{id}/{nonce}` is where relative resolution would drop the credential;
    the route redirects it to the directory shape instead of serving a document
    the browser cannot load its own files from."""
    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    slashless = _remote(f"/api/plugins/ui/{PLUGIN_ID}/{surface}", app)
    assert slashless.status_code == 307, slashless.text
    assert slashless.headers["location"] == _mount(PLUGIN_ID, surface)


def test_a_rejected_nonce_leaves_an_audit_line_and_the_bypass_stays_a_get(
    tmp_path, monkeypatch
):
    """Two gaps the review named, closed together: guessing a nonce is visible in
    the audit log, and the middleware's nonce bypass answers GET and HEAD only —
    a mutation riding a nonce-shaped path still needs the LAN token."""
    from server import middleware
    from core import audit_log

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    lines: list[dict] = []
    monkeypatch.setattr(audit_log, "audit_event",
                        lambda kind, **fields: lines.append(fields))
    monkeypatch.setattr(middleware, "_refusal_allowed", lambda key: True)
    forged = _remote(_mount(PLUGIN_ID, "forged-" + surface[7:]), app)
    assert forged.status_code == 401, forged.text
    assert any(
        row.get("decision") == "surface_nonce_refused" and row.get("status") == "denied"
        for row in lines
    ), lines
    lines.clear()
    mutation = _remote(
        _mount(PLUGIN_ID, surface), app, method="POST", body={},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert mutation.status_code == 401, mutation.text
    assert any(row.get("decision") == "token_missing" for row in lines), lines


def test_a_nonce_minting_loop_never_evicts_another_plugins_live_mount(
    tmp_path, monkeypatch
):
    """`MAX_SURFACE_NONCES` is a memory guard, and a guard that silently kills
    another plugin's mount is a denial of service wearing one: the loop evicts
    its own oldest credential and the peer's live mount keeps serving."""
    from server import plugin_surface_nonce

    app = _app(tmp_path, monkeypatch, lan=True,
               specs={PLUGIN_ID: {}, "acme-looper": {"capabilities": ["notifications"]}})
    peer = _mint(app, PLUGIN_ID)
    first = _mint(app, "acme-looper")
    for _ in range(plugin_surface_nonce.MAX_SURFACE_NONCES + 20):
        _mint(app, "acme-looper")
    assert len(plugin_surface_nonce._nonces) <= plugin_surface_nonce.MAX_SURFACE_NONCES
    live = _remote(_mount(PLUGIN_ID, peer), app)
    assert live.status_code == 200, live.text
    oldest = _remote(_mount("acme-looper", first), app)
    assert oldest.status_code == 401, oldest.text


def test_the_surface_credential_unlocks_the_surface_family_only(
    tmp_path, monkeypatch
):
    """R21 both ways: the nonce opens `/api/plugins/ui/...`, and nothing else
    reads a credential from a query — the long-lived LAN token in a URL, or the
    nonce value offered to another route, unlocks zero."""
    from server import middleware

    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    for path in ("/api/plugins", "/api/settings", "/api/plugins/commands"):
        borrowed = _remote(path, app, params={"surface": surface})
        assert borrowed.status_code == 401, path
    leaky = _remote(_mount(PLUGIN_ID), app, params={"token": middleware.LAN_AUTH_TOKEN})
    assert leaky.status_code == 401, leaky.text


def test_a_bad_nonce_run_off_loopback_costs_the_attacker_its_own_budget(
    tmp_path, monkeypatch
):
    """The nonce-shape bypass was free, and free is the shape of a guessing run.

    `AuthMiddleware` hands a GET whose path *shape* carries a nonce segment straight
    to the route, which owns the value: nothing is compared before the answer, and the
    `surface_nonce_refused` audit line is throttled to one per client per minute, so a
    stranger on the LAN could sweep guesses and leave no trace worth the shared
    400-a-minute budget. The family therefore rides its own per-client budget, and a
    refused guess is coded before it is counted out. The desktop path keeps serving —
    the bound covers the clients the bypass was opened for, and a loopback mount is
    allowed a burst of its own page plus the assets it derives.
    """
    from server import middleware

    app = _app(tmp_path, monkeypatch, lan=True)
    budget = middleware.SURFACE_FAMILY_MAX_REQUESTS
    for attempt in range(budget):
        guessed = _remote(_mount(PLUGIN_ID, f"forged-{attempt:03d}"), app)
        assert guessed.status_code == 401, (attempt, guessed.text)
        assert guessed.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
    limited = _remote(_mount(PLUGIN_ID, "forged-final"), app)
    assert limited.status_code == 429, limited.text
    assert limited.headers.get("retry-after") == "60", dict(limited.headers)
    assert _document(app).status_code == 200


def test_the_surface_budget_is_per_client_and_binds_the_family_off_loopback_only(
    tmp_path, monkeypatch
):
    """The bucket is keyed by client, so one phone's sweep cannot deny the paired
    phone its mount, and a client inside the budget is served, not swallowed."""
    app = _app(tmp_path, monkeypatch, lan=True)
    served = _mint(app, PLUGIN_ID)
    other = "192.168.50.77"
    for attempt in range(40):
        assert _call(
            app, _mount(PLUGIN_ID, f"forged-{attempt:03d}"), peer=other, host=f"{other}:8765"
        ).status_code == 401
    neighbour = _remote(_mount(PLUGIN_ID, served), app)
    assert neighbour.status_code == 200, neighbour.text


def test_a_strange_id_or_path_never_answers_500(tmp_path, monkeypatch):
    """A non-ASCII name still reaches the constant-time comparison, and is refused."""
    app = _app(tmp_path, monkeypatch, lan=True)
    surface = _mint(app, PLUGIN_ID)
    for path in ("/api/plugins/ui/%C3%A4/%C3%A4/", _asset(PLUGIN_ID, quote("ä.js"), surface)):
        odd = _remote(path, app)
        assert odd.status_code in (400, 401, 404), (path, odd.text)


def test_a_file_the_server_cannot_read_is_a_coded_refusal(tmp_path, monkeypatch):
    """The gap between checking a path and reading it is a refusal, and no crash."""
    from server.main import create_app

    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    locked = config / "plugins" / PLUGIN_ID / "ui" / "theme.css"
    locked.chmod(0o000)
    try:
        response = _load(create_app(), "theme.css")
    finally:
        locked.chmod(0o644)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_asset_refused"


def test_a_closed_folder_over_the_entry_is_a_coded_refusal_with_no_path_in_the_body(
    tmp_path, monkeypatch
):
    """A directory without search permission fails every `stat` the mount asks about.

    The runtime scan, the manifest validator and the containment probe each answer it
    with an `OSError` that `pathlib` lets travel, and an unhandled one is a 500 whose
    body quotes the absolute path of the plugin. The reader gets the coded 404, and
    the filesystem keeps its own address.
    """
    from server.main import create_app

    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    app = create_app()
    target = config / "plugins" / PLUGIN_ID / "ui"
    target.chmod(0o000)
    try:
        response = _document(app)
    finally:
        target.chmod(0o755)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_unavailable"
    assert "Permission denied" not in response.text
    assert str(target) not in response.text


def test_a_closed_folder_over_an_asset_is_a_coded_refusal(tmp_path, monkeypatch):
    """The asset branch prepares the mount first, so a closed folder answers 404 here.

    Both branches read the same directory before they read a file in it, and the
    refusal is coded either way: the point is that no shape of an unreadable plugin
    reaches the reader as a 500.
    """
    from server.main import create_app

    config = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}})
    app = create_app()
    target = config / "plugins" / PLUGIN_ID / "ui"
    target.chmod(0o000)
    try:
        response = _load(app, "theme.css")
    finally:
        target.chmod(0o755)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["reason_code"] == "plugin_ui_unavailable"
    assert "Permission denied" not in response.text


def test_the_containment_probe_refuses_a_closed_folder_and_a_special_file(tmp_path):
    """`resolve_surface_file` answers a reason for every shape it cannot read.

    A path the process may not `stat` is a refusal, a named pipe is a refusal, and a
    path that is simply absent keeps its own words — none of them is an exception.
    """
    from server import plugin_surface

    plugin = tmp_path / "plugins" / PLUGIN_ID
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "index.html").write_text(ENTRY_MARK, encoding="utf-8")
    specials = tmp_path / "specials"
    specials.mkdir()
    os.mkfifo(specials / "pipe.html")

    held, reason = plugin_surface.resolve_surface_file(plugin, "ui/index.html")
    assert (held, reason) == (plugin.resolve() / "ui" / "index.html", "")
    (plugin / "ui").chmod(0o000)
    try:
        assert plugin_surface.resolve_surface_file(plugin, "ui/index.html") == (
            None, plugin_surface.REFUSED_SHAPES["unreadable"])
    finally:
        (plugin / "ui").chmod(0o755)
    assert plugin_surface.resolve_surface_file(plugin, "ui/gone.html") == (
        None, plugin_surface.REFUSED_SHAPES["missing"])
    assert plugin_surface.resolve_surface_file(plugin, "/etc/passwd") == (
        None, plugin_surface.REFUSED_SHAPES["shape"])
    assert plugin_surface.resolve_surface_file(tmp_path, "specials/pipe.html") == (
        None, plugin_surface.REFUSED_SHAPES["irregular"])


def test_a_non_ascii_id_off_the_credential_path_is_a_coded_refusal(tmp_path, monkeypatch):
    """A foreign id never becomes a mount, and a bad remainder never becomes a file.

    The bare URL has no nonce, so the answer is 401 before the directory is
    opened. The mint is where the slug rule runs, and that rule is a pattern
    match with no syscall. A live mount still refuses a remainder the text
    layer will not carry.
    """
    app = _app(tmp_path, monkeypatch)
    for name in ("%C3%A4", "%E6%97%A5%E6%9C%AC", "%F0%9F%98%80"):
        response = _call(app, f"/api/plugins/ui/{name}/")
        assert response.status_code == 401, (name, response.text)
        assert response.json()["error"]["reason_code"] == "plugin_ui_unauthorized"
        minted = _call(
            app,
            f"/api/plugins/{name}/surface-token",
            method="POST",
            body={},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert minted.status_code == 404, (name, minted.text)
        assert minted.json()["error"]["reason_code"] == "plugin_ui_unavailable"
        asset = _load(app, f"{name}.html")
        assert asset.status_code == 400, asset.text
        assert asset.json()["error"]["reason_code"] == "plugin_ui_asset_refused"


def test_the_mint_needs_an_authenticated_fetch(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, lan=True)
    anonymous = _remote(
        f"/api/plugins/{PLUGIN_ID}/surface-token", app, method="POST", body={},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert anonymous.status_code == 401


def test_the_whole_flow_serves_a_surface_with_lan_auth_off(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, lan=False, specs={PLUGIN_ID: {"capabilities": ["workers"]}})
    document = _document(app)
    assert document.status_code == 200, document.text
    assert _csp_of(document)["worker-src"] == "'self' blob:"
    assert _load(app, "app.js").status_code == 200
    minted = _call(app, f"/api/plugins/{PLUGIN_ID}/surface-token", method="POST", body={},
                   headers={"X-Requested-With": "XMLHttpRequest"})
    assert minted.status_code == 200, minted.text
    surface = minted.json()["surface"]
    assert _document(app, nonce=surface).status_code == 200
    bare = _document(app, credential=False, params={"surface": "forged-while-lan-is-off"})
    assert bare.status_code == 401, bare.text
    assert bare.json()["error"]["reason_code"] == "plugin_ui_unauthorized"


def test_the_component_walk_proves_the_join_before_it_opens_anything(tmp_path, monkeypatch):
    """The walk opens segments one at a time relative to a descriptor, which a scanner
    cannot read as "inside the plugin directory". The join is therefore also proven as
    text, on the separator boundary, before the first `os.open` — and `..` answers the
    same `walkout` the text layer does instead of walking the descriptor's parent."""
    from server import plugin_surface

    plugin = _home(tmp_path, monkeypatch, {PLUGIN_ID: {}}) / "plugins" / PLUGIN_ID
    assert plugin_surface._open_below(plugin, ["..", "app.js"]) == (
        None,
        plugin_surface.REFUSED_SHAPES["walkout"],
    )
    assert plugin_surface._open_below(plugin, ["ui", "..", "..", "ephe-plugin.json"]) == (
        None,
        plugin_surface.REFUSED_SHAPES["walkout"],
    )
