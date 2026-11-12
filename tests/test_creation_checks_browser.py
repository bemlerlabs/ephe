"""The browser half of the creation eval set's end state (Creator task #51c).

`evals/creation_checks.py` grades a staged bundle from its bytes. Three rows cannot be
answered that way: whether the mount really serves a document that holds something,
whether loading it leaves an error behind, and whether the same answer survives a
reload. Those are promises about a running server and a real engine, so this file reads
them from one — the same route, the same per-mount nonce and the same sandboxed frame
the product uses (`tests/test_plugin_surface_isolation_browser.py` measured that frame's
authority; this one asks what the document shows). The mount is framed the way the shell
frames it: a same-origin host page holds the iframe and answers the `ephe.sdk` protocol,
so a surface that asks its host is answered rather than told it has none.

Two layers, so the rules can be read without an engine:

  * the verdict builders take evidence an engine already produced, and the first half of
    the module supplies it directly. Every rule is therefore proved able to fail, which is
    the part a browser test cannot show on its own;
  * the live tests boot the real app on a loopback port, stage and install a bundle
    through the Creator tools, and drive a real engine. An engine that cannot boot is
    skipped with its name in the reason.

The content rule is deliberately blunt: a non-zero box on a `canvas`, `svg`, `img` or
`video`, or non-whitespace text in the body. It answers "a document arrived", which is
what `mounts` claims. That a widget does what its case asked is a different question and
task #31 grades that one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.creation_checks import Verdict  # noqa: E402  (the same verdict shape as offline)

ENGINES = ("chromium", "webkit")


def _load(
    status: int = 200,
    ready: str = "complete",
    text: int = 40,
    graphics: int = 0,
    errors: tuple[str, ...] = (),
    measured: bool = True,
):
    from evals.creation_checks_browser import Load

    return Load(
        status=status, ready=ready, text=text, graphics=graphics,
        errors=errors, measured=measured,
    )


def _case(checks: list[str]) -> dict:
    return {"id": "creation-browser", "category": "widget", "checks": checks}


def _verdicts(case: dict, load, reload=None, plugin: str = "measure-bundle") -> dict:
    from evals.creation_checks_browser import browser_verdicts

    rows = browser_verdicts(case, plugin, load, reload)
    assert all(isinstance(row, Verdict) for row in rows), rows
    return {row.check: row for row in rows}


def test_a_document_with_text_mounts() -> None:
    """GIVEN a load that answered 200 with text WHEN `mounts` reads it THEN it passes."""
    verdict = _verdicts(_case(["mounts"]), _load(text=18))["mounts"]
    assert verdict.ok is True, verdict.detail
    assert "18" in verdict.detail, verdict.detail


def test_a_canvas_only_surface_mounts() -> None:
    """A game or a 3D scene draws; text is the wrong ruler, so a box has to be enough."""
    verdict = _verdicts(_case(["mounts"]), _load(text=0, graphics=1))["mounts"]
    assert verdict.ok is True, verdict.detail
    assert "1" in verdict.detail, verdict.detail


def test_an_empty_document_fails_the_mount() -> None:
    """The rule has to be able to say no: 200 bytes of an empty body is not a surface."""
    verdict = _verdicts(_case(["mounts"]), _load(text=0, graphics=0))["mounts"]
    assert verdict.ok is False, verdict.detail
    assert "empty" in verdict.detail.lower(), verdict.detail


def test_a_refused_url_fails_the_mount_and_names_the_status() -> None:
    """A mount URL whose nonce died answers with no bytes; the number belongs in the row."""
    verdict = _verdicts(_case(["mounts"]), _load(status=403, text=0, graphics=0))["mounts"]
    assert verdict.ok is False, verdict.detail
    assert "403" in verdict.detail, verdict.detail


def test_the_mount_row_names_the_bundle_it_read() -> None:
    verdict = _verdicts(_case(["mounts"]), _load(), plugin="web-clock")["mounts"]
    assert "web-clock" in verdict.detail, verdict.detail




def test_a_clean_load_passes_the_console_check() -> None:
    verdict = _verdicts(_case(["no_console_errors"]), _load())["no_console_errors"]
    assert verdict.ok is True, verdict.detail


def test_an_error_from_the_surface_is_named_in_the_failure() -> None:
    """The whole point of the row: the message the page produced has to reach the receipt."""
    verdict = _verdicts(
        _case(["no_console_errors"]), _load(errors=("console.error: boom",))
    )["no_console_errors"]
    assert verdict.ok is False, verdict.detail
    assert "boom" in verdict.detail, verdict.detail


def test_the_console_count_is_stated_when_the_list_is_long() -> None:
    errors = tuple(f"console.error: failure {index}" for index in range(9))
    verdict = _verdicts(_case(["no_console_errors"]), _load(errors=errors))[
        "no_console_errors"
    ]
    assert verdict.ok is False, verdict.detail
    assert "9" in verdict.detail, verdict.detail


def test_the_console_row_fails_when_no_error_channel_was_live() -> None:
    """A load nobody watched is not a clean load: an empty list from a dead channel is no evidence."""
    from evals.creation_checks_browser import Load

    verdict = _verdicts(_case(["no_console_errors"]), Load(measured=False))[
        "no_console_errors"
    ]
    assert verdict.ok is False, verdict.detail
    assert "channel" in verdict.detail.lower(), verdict.detail



def test_survives_reload_needs_a_second_navigation() -> None:
    """Without the second read there is no comparison, so the row says so."""
    verdict = _verdicts(_case(["survives_reload"]), _load(), reload=None)["survives_reload"]
    assert verdict.ok is False, verdict.detail
    assert "reload" in verdict.detail.lower(), verdict.detail


def test_survives_reload_passes_when_the_second_read_answers_clean() -> None:
    verdict = _verdicts(_case(["survives_reload"]), _load(), reload=_load(text=12))[
        "survives_reload"
    ]
    assert verdict.ok is True, verdict.detail


def test_survives_reload_fails_when_the_surface_loses_its_content() -> None:
    """The comparison has to be able to fail: the same mount, second read, nothing left."""
    verdict = _verdicts(
        _case(["survives_reload"]), _load(), reload=_load(text=0, graphics=0)
    )["survives_reload"]
    assert verdict.ok is False, verdict.detail


def test_survives_reload_fails_when_the_second_read_reports_an_error() -> None:
    verdict = _verdicts(
        _case(["survives_reload"]),
        _load(),
        reload=_load(errors=("uncaught: TypeError: x is undefined",)),
    )["survives_reload"]
    assert verdict.ok is False, verdict.detail
    assert "TypeError" in verdict.detail, verdict.detail




def test_only_the_names_the_case_asks_get_a_verdict() -> None:
    rows = _verdicts(_case(["mounts", "no_console_errors"]), _load())
    assert sorted(rows) == ["mounts", "no_console_errors"], sorted(rows)


def test_a_check_outside_the_browser_group_gets_no_verdict() -> None:
    """`manifest_valid` belongs to the offline module; a second opinion would be noise."""
    rows = _verdicts(_case(["manifest_valid", "mounts"]), _load())
    assert list(rows) == ["mounts"], list(rows)


def test_the_browser_group_holds_exactly_three_names() -> None:
    from evals.creation_checks import BROWSER_CHECKS
    from evals.creation_checks_browser import BROWSER_CHECK_NAMES

    assert BROWSER_CHECK_NAMES == BROWSER_CHECKS
    assert set(BROWSER_CHECKS) == {"mounts", "no_console_errors", "survives_reload"}


def test_the_page_snippets_are_valid_javascript(tmp_path: Path) -> None:
    """A syntax error in the page code costs every live test its run; node settles it first."""
    from evals.creation_checks_browser import JS_SNIPPETS

    assert set(JS_SNIPPETS) == {"PROBE_HOOK", "CONTENT_PROBE", "HOST_SCRIPT"}
    for name, script in JS_SNIPPETS.items():
        path = tmp_path / f"{name}.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_the_host_page_frames_the_mount_in_the_product_sandbox() -> None:
    """The host's iframe is the shell's: this mount document, this sandbox, same origin."""
    from evals.creation_checks_browser import SURFACE_SANDBOX, host_document

    mount = "http://127.0.0.1:1/api/plugins/ui/demo/abc123/"
    document = host_document(mount, "demo")
    assert f'src="{mount}"' in document, document
    assert f'sandbox="{SURFACE_SANDBOX}"' in document, document



def _stage(home: Path, name: str, files: dict[str, str]) -> str:
    """Scaffold a bundle with the product's own tool, overwrite what the case needs, install.

    A local install lands switched off — `install_plugin_bundle` answers `"enabled": false`
    and points at the Extensions switch — and a disabled bundle is a coded 404 at the mount
    route (`server/routes/plugin_ui.py:112`). The switch is the person's, so the test that
    measures a mount has to hold it: `plugin_runtime.lifecycle().set_enabled` is the one
    gate every caller passes, the HTTP route and the CLI alike.
    """
    from core import plugin_runtime
    from core.tools import creator_tools

    answer = json.loads(
        creator_tools.create_plugin_scaffold(name, "A bundle the eval mounts")
    )
    assert "bundle" in answer, answer
    directory = home / "creator" / "plugins" / name
    for relative, text in files.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    installed = json.loads(creator_tools.install_plugin_bundle(name))
    assert installed.get("status") == "installed", installed
    assert installed.get("enabled") is False, installed
    plugin_runtime.lifecycle().set_enabled(name, True, actor="eval")
    plugin_runtime.invalidate_ownership_cache()
    assert plugin_runtime.is_plugin_active(name), name
    return name


@pytest.fixture()
def surface(request, tmp_path, monkeypatch):
    """One live session per test, in a config home of its own, closed whatever the engine did.

    The autouse home fixtures point `EPHE_CONFIG_DIR` at a per-test folder before this one
    runs, so the last write wins here; the server thread reads it per request.
    """
    engine = request.param
    from evals.creation_checks_browser import SurfaceSession

    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    os.environ["EPHE_CONFIG_DIR"] = str(tmp_path)
    session = SurfaceSession(engine=engine, config=tmp_path)
    try:
        session.start()
    except Exception as refused:  # an engine that cannot boot is named, per the brief
        session.stop()
        pytest.skip(f"{engine} is not drivable in this lane: {refused}")
    yield session, tmp_path
    session.stop()


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_scaffolded_bundle_mounts_and_survives_a_reload(surface) -> None:
    """The product's own scaffold, installed and mounted: a document with text, clean."""
    session, home = surface
    name = _stage(home, "eval-scaffold", {})
    load, reload = session.evidence(name)
    rows = _verdicts(
        _case(["mounts", "no_console_errors", "survives_reload"]), load, reload, plugin=name
    )
    for check, verdict in rows.items():
        assert verdict.ok is True, f"{check}: {verdict.detail}"


#: The paid run's class-2 shape: a page written against the Storage API, with no
#: `ephe.storage` call. Without the mount's shim its first `localStorage` read throws
#: the `SecurityError` that failed `creation-05`.
LOCAL_STORAGE_ENTRY = """<!doctype html><html><body><p id="score">0</p>
<script src="app.js"></script></body></html>
"""

LOCAL_STORAGE_APP = """
var saved = localStorage.getItem("highScore");
var score = saved === null ? 7 : Number(saved);
localStorage.setItem("highScore", String(score));
document.getElementById("score").textContent =
  "high-score-" + localStorage.getItem("highScore");
"""

#: What "high-score-7" leaves once the probe strips whitespace.
STORAGE_MARKER_CHARS = 12


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_bundle_that_writes_local_storage_mounts_clean(surface) -> None:
    """`creation-05`'s browser rows, read through the eval's own instrument.

    The mount serves the page-storage shim ahead of the bundle's first script, so the
    property answers, the write does not raise, and both loads report no error. The
    rendered marker proves the area answered rather than the script dying on the way.
    The eval frames the mount in its same-origin host, so the shim's write is answered
    by that host instead of failing with `storage_no_host`; where the value lands in the
    product is measured by `tests/test_plugin_surface_storage_shim_browser.py`.
    """
    session, home = surface
    name = _stage(
        home,
        "eval-page-storage",
        {"ui/index.html": LOCAL_STORAGE_ENTRY, "ui/app.js": LOCAL_STORAGE_APP},
    )
    load, reload = session.evidence(name)
    rows = _verdicts(
        _case(["mounts", "no_console_errors", "survives_reload"]), load, reload, plugin=name
    )
    for check, verdict in rows.items():
        assert verdict.ok is True, f"{check}: {verdict.detail}"
    assert load.errors == () and reload.errors == (), (load.errors, reload.errors)
    assert load.text == STORAGE_MARKER_CHARS, load
    assert reload.text == STORAGE_MARKER_CHARS, reload


#: A surface that keeps its state through `ephe.storage` and asks for a tool, which is the
#: shape the paid run's `note-studio` had. The element starts empty so the collector waits
#: for the answer instead of settling on a placeholder.
SDK_STATE_ENTRY = """<!doctype html><html><body><p id="state"></p>
<script src="ephe.js"></script><script src="state.js"></script></body></html>
"""

SDK_STATE_APP = """
var out = document.getElementById("state");
ephe.storage.set("theme", "dark")
  .then(function () { return ephe.storage.get("theme"); })
  .then(function (value) {
    return ephe.callTool("eval-no-tool", {}).then(
      function () { out.textContent = "tool-allowed-" + value; },
      function (error) { out.textContent = "stored-" + value + "-refused-" + error.code; }
    );
  })
  .catch(function (error) {
    console.error("ephe sdk failed: " + String(error && error.code));
    out.textContent = "failed-" + String(error && error.code);
  });
"""

#: What a surface that got its two answers renders, whitespace stripped.
SDK_STATE_MARKER = "stored-dark-refused-sdk_refused"


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_surface_that_asks_its_host_mounts_and_reloads_clean(surface) -> None:
    """F3 of the 2026-11-12 analysis: the mount is framed, so its host answers it.

    `ephe.storage.set` and `ephe.storage.get` travel the `ephe.sdk` bridge to the eval's
    same-origin host, which keeps them in its own `localStorage`; `tool.call` comes back
    as the coded `sdk_refused` refusal, because a browser row runs no tool. The marker
    names all three answers, and both loads are clean. Read top-level, the same page
    renders `failed-sdk_no_host` and the console row goes red — the false error the
    analysis recorded for creation-18's storage-using surface.
    """
    session, home = surface
    name = _stage(
        home,
        "eval-sdk-state",
        {"ui/index.html": SDK_STATE_ENTRY, "ui/state.js": SDK_STATE_APP},
    )
    load, reload = session.evidence(name)
    rows = _verdicts(
        _case(["mounts", "no_console_errors", "survives_reload"]), load, reload, plugin=name
    )
    for check, verdict in rows.items():
        assert verdict.ok is True, f"{check}: {verdict.detail}"
    assert load.errors == () and reload.errors == (), (load.errors, reload.errors)
    assert load.text == len(SDK_STATE_MARKER), load
    assert reload.text == len(SDK_STATE_MARKER), reload


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_blank_document_fails_the_mount_in_a_real_engine(surface) -> None:
    """The mutation, measured in the engine: an empty body is not a surface."""
    session, home = surface
    name = _stage(
        home,
        "eval-blank",
        {"ui/index.html": "<!doctype html><html><body></body></html>", "ui/app.js": ""},
    )
    load, _reload = session.evidence(name)
    rows = _verdicts(_case(["mounts"]), load, plugin=name)
    assert rows["mounts"].ok is False, rows["mounts"].detail
    assert load.text == 0 and load.graphics == 0, load


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_page_error_fails_the_console_row_in_a_real_engine(surface) -> None:
    """The other half of the mutation: an exception the engine really saw."""
    session, home = surface
    name = _stage(
        home, "eval-throwing", {"ui/app.js": "throw new Error('eval-page-error');\n"}
    )
    load, _reload = session.evidence(name)
    rows = _verdicts(_case(["no_console_errors"]), load, plugin=name)
    assert rows["no_console_errors"].ok is False, rows["no_console_errors"].detail
    assert "eval-page-error" in rows["no_console_errors"].detail


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_console_error_in_the_framed_surface_fails_the_console_row(surface) -> None:
    """The hook has to run inside the iframe: a `console.error` there is still the surface's."""
    session, home = surface
    name = _stage(
        home, "eval-console", {"ui/app.js": "console.error('eval-console-error');\n"}
    )
    load, _reload = session.evidence(name)
    rows = _verdicts(_case(["no_console_errors"]), load, plugin=name)
    assert rows["no_console_errors"].ok is False, rows["no_console_errors"].detail
    assert "eval-console-error" in rows["no_console_errors"].detail


@pytest.mark.parametrize("surface", ENGINES, indirect=True)
def test_a_canvas_surface_mounts_without_any_text(surface) -> None:
    """The graphics half, live: a document whose only content is a drawn box."""
    session, home = surface
    name = _stage(
        home,
        "eval-canvas",
        {
            "ui/index.html": '<!doctype html><html><body><canvas id="c" width="120"'
            ' height="60"></canvas></body><script src="app.js"></script></html>',
            "ui/app.js": "document.getElementById('c').getContext('2d')"
            ".fillRect(0, 0, 40, 20);\n",
        },
    )
    load, _reload = session.evidence(name)
    rows = _verdicts(_case(["mounts"]), load, plugin=name)
    assert rows["mounts"].ok is True, rows["mounts"].detail
    assert load.graphics >= 1, load
