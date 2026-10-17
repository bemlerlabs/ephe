"""The desktop shell's security posture, pinned by reading `tauri.conf.json`.

Measured 2026-10-13: `app/src-tauri/tauri.conf.json` carried
`app.security.csp = null` while the signed updater (pubkey plus a GitHub
endpoint) was fully configured. A WebView that runs the shell with no policy at
all is the weakest link in the product: the surface renders agent-generated
artifacts in sandboxed iframes and pulls media from the local backend, so an
injected script has the whole `__TAURI__` bridge within reach
(`withGlobalTauri: true`).

The checks below read the configuration the shell actually ships and fail when
any of three settings regress:

* `app.security.csp` back to `null` — the defect itself;
* the release over-building its artifacts — the updater endpoint and pubkey are
  set, so the release turns `createUpdaterArtifacts` on per build; committing it
  instead breaks every local build, which is why the config stays silent and the
  workflow carries the switch;
* the single-instance plugin dropped — the shell writes to one shared store
  (`~/.ephe`: one artifact index, one session storage), and the hand-rolled
  guard that protects it is compiled for Unix only.

The policy is read as text, so a directive that is silently widened (a dropped
`object-src`, an `'unsafe-inline'` in `script-src`) fails here rather than in a
review nobody runs.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "app" / "src-tauri"
TAURI_CONF = TAURI_DIR / "tauri.conf.json"

#: The origin the desktop WebView fetches from — `lib/desktopBaseUrl.ts`
#: (`TAURI_BACKEND_DEFAULT`), which the shell reaches over plain HTTP.
BACKEND_ORIGIN = "http://127.0.0.1:8765"


def conf() -> dict:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))


def directives(policy: str) -> dict[str, list[str]]:
    """One CSP string as `{directive: [sources]}` — split on `;`, then space."""
    out: dict[str, list[str]] = {}
    for part in policy.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, rest = part.partition(" ")
        out[name.strip().lower()] = rest.split()
    return out


def shipped_csp() -> str:
    csp = conf()["app"]["security"]["csp"]
    assert isinstance(csp, str) and csp.strip(), (
        "app.security.csp is null again: the desktop shell ships with no "
        "Content-Security-Policy while the signed updater stays configured"
    )
    return csp


def test_the_csp_is_a_real_policy():
    assert directives(shipped_csp()), "the CSP does not parse into any directive"


def test_scripts_are_same_origin_only():
    """No inline script, no eval: the shipped window is `'self'`-only.

    The one deliberate relaxation lives in `style-src` (React writes inline
    `style` attributes in 28 components); `script-src` carries none.
    """
    d = directives(shipped_csp())
    assert d.get("default-src") == ["'self'"], d.get("default-src")
    assert d.get("script-src") == ["'self'"], d.get("script-src")


def test_the_policy_has_no_wildcard_and_no_eval():
    d = directives(shipped_csp())
    flat = [source for sources in d.values() for source in sources]
    assert "*" not in flat, "a wildcard source leaves the policy open"
    assert "'unsafe-eval'" not in flat, "eval is not part of a strict policy"
    assert d.get("object-src") == ["'none'"], d.get("object-src")
    assert d.get("base-uri") == ["'self'"], d.get("base-uri")


def test_the_window_can_still_reach_the_local_backend():
    """The surface is only usable if `connect-src` keeps the backend alive.

    `http.ts`/`desktopBaseUrl.ts` fetch `http://127.0.0.1:8765` and open a
    WebSocket at the same origin; Tauri's own IPC rides on `ipc:`.
    """
    d = directives(shipped_csp())
    connect = d.get("connect-src", [])
    for source in ("'self'", "ipc:", "http://ipc.localhost", BACKEND_ORIGIN):
        assert source in connect, f"connect-src lost {source}: {connect}"
    assert "ws://127.0.0.1:8765" in connect, connect


def test_inline_styles_and_local_fonts_are_allowed():
    """The two sources the built UI genuinely needs: inline styles and fonts."""
    d = directives(shipped_csp())
    assert "'unsafe-inline'" in d.get("style-src", []), d.get("style-src")
    assert "'self'" in d.get("font-src", []) or "'self'" in d.get("default-src", []), d


def test_dev_keeps_a_policy_too():
    """`devCsp` exists, so `vite`/HMR runs under a policy instead of none.

    It is the looser of the two on purpose: Vite injects an inline module
    preamble for React refresh, so `script-src` there carries `'unsafe-inline'`.
    """
    dev = conf()["app"]["security"]["devCsp"]
    assert isinstance(dev, str) and dev.strip(), "devCsp is missing or empty"
    assert "'unsafe-inline'" in directives(dev).get("script-src", []), dev


def test_updater_artifacts_are_produced():
    """The artifacts must be produced WITHOUT this switch living in the config file.

    A committed `createUpdaterArtifacts: true` makes the bundler refuse every build
    that has no private key, which is every local `npm run tauri build` — the dev and
    verification path this repo mandates. The switch therefore belongs to the release
    build, passed per run, and what has to hold is the pair: the config stays silent
    and the workflow turns it on. Measured 2026-10-15: with the switch committed, a
    local build died on 'A public key has been found, but no private key'; with it
    passed as `--config` on a keyed build, the signed artifacts appear.
    """
    bundle = conf()["bundle"]
    assert bundle.get("createUpdaterArtifacts") is None, (
        "bundle.createUpdaterArtifacts must not be committed: every local build reads "
        "this file, and without a private key the bundler refuses to run at all"
    )
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "createUpdaterArtifacts" in workflow, (
        "the release workflow is now the only place that turns the switch on"
    )
    assert "--config" in workflow, (
        "the release must pass the switch per build rather than inherit it"
    )
    updater = conf()["plugins"]["updater"]
    assert updater.get("endpoints"), "the endpoint is what an installed app fetches"
    assert updater.get("pubkey"), "a signature cannot be verified without the pubkey"


def test_the_single_instance_plugin_is_wired():
    """One shared store, one process — and the plugin covers every platform.

    The hand-rolled guard in `src/instance.rs` is `#[cfg(unix)]`, so a non-Unix
    build had no guard at all; the plugin is registered unconditionally.
    """
    manifest = (TAURI_DIR / "Cargo.toml").read_text(encoding="utf-8")
    shell = (TAURI_DIR / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "tauri-plugin-single-instance" in manifest, "the crate is not a dependency"
    assert "tauri_plugin_single_instance::init" in shell, "the plugin is not registered"
