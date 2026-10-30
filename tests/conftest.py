"""
pytest fixtures shared across all Ephe tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.types import Message
from tests import timing_segment


@pytest.fixture(autouse=True)
def _home_isolation_attribution(request: pytest.FixtureRequest):
    """Tell the home-isolation guard which test is running, so a write into the real
    ``~/.ephe`` fails that test by name (or is tolerated when it is recorded debt).

    The guard is an in-process tripwire, not a per-test fixture: it needs to know the
    current test id at write time to decide tolerate-vs-fail. It is looked up lazily in
    ``sys.modules`` so this fixture is a no-op whenever the guard is not part of the run
    (a single file selected without it), and never couples the whole suite to the guard.
    """
    guard = sys.modules.get("tests.test_home_isolation")
    if guard is not None:
        guard._set_current(request.node.nodeid)
    yield
    if guard is not None:
        guard._set_current(None)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001 (pytest hook signature)
    """In recording mode (EPHE_HOME_ISOLATION_REPORT set) the guard never fails a test —
    it only counts offenders. Dump them here so ``scripts/home_isolation_gate.py --update``
    can lower the committed baseline from a full run."""
    report_path = (os.environ.get("EPHE_HOME_ISOLATION_REPORT") or "").strip()
    if not report_path:
        return
    guard = sys.modules.get("tests.test_home_isolation")
    if guard is not None:
        guard.dump_report(Path(report_path))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Stand the serial timing segment down when the clock cannot be trusted.

    A local `pytest tests -n 8` excludes nothing, so the 15 units of the serial segment
    reach every worker session; without this hook each of them still reads its wall clock
    there, and the number then describes the machine (run 37974211156: 324.7 ms against a
    200 ms budget). Nothing changes for the serial CI step — no workers, load far below
    the bar — so what it measures is what it always measured. An item that already carries
    an active skip is left alone, which keeps a gate's own stand-down reason (for example
    `EPHE_BENCH_GATE=0`) in the report instead of overwriting it.
    """
    reason = timing_segment.stand_down_reason()
    if reason is None:
        return
    try:
        marked = timing_segment.segment_items(items)
    except (OSError, AssertionError):
        return  # no readable workflow to key the segment on; the guard test reports that shape
    marker = pytest.mark.skip(reason=f"{timing_segment.SKIP_TAG}: {reason}")
    for item in marked:
        if not timing_segment.skips_in_this_session(item):
            item.add_marker(marker)


@pytest.fixture(autouse=True)
def _isolate_gate_context():
    """ApprovalPolicy and the sandbox confirm callback are empty for every test.

    Both live in ContextVars (core.tools.session_ctx, core.vision), and a
    ContextVar value outlives the function and the file. Without a reset here a
    later test sees a dialog nobody ever set — or a policy a CLI test left
    behind. That skews precisely the gate tests.
    """
    from core.tools import session_ctx
    from core.tools import ask_gate
    from core.vision import set_sandbox_confirm_cb

    session_ctx._CURRENT_POLICY.set(None)
    set_sandbox_confirm_cb(None)
    ask_gate.set_ask_cb(None)
    yield
    session_ctx._CURRENT_POLICY.set(None)
    set_sandbox_confirm_cb(None)
    ask_gate.set_ask_cb(None)


# ---------------------------------------------------------------------------
# MCP tool namespace isolation (autouse) — root-cause fix for test pollution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_mcp_registry():
    """The remote-tool namespace is empty for every test and restored after it.

    `sync_mcp_tools()` writes the module-level `_MCP_TOOLS` dict, and a test that
    drives it with a fake server (`tests/test_mcp_lifecycle.py:283`) leaves those
    tools registered for the rest of the session. In a full run the leak reached
    `tests/test_tools.py::TestToolSchemas`, which asserts that every advertised
    schema carries `parameters` and that every name maps to a function in
    `core.tools` — the leaked `mcp_read` had neither. It passed in isolation and
    failed only as part of `pytest tests/`, which is precisely what CI runs.

    Clearing on entry (not just restoring on exit) is the point: a test must
    register the server it wants, the same way `_isolate_provider_state` makes a
    test declare its own provider.
    """
    from core.tools import mcp_client

    saved = dict(mcp_client._MCP_TOOLS)
    mcp_client._MCP_TOOLS.clear()
    mcp_client._invalidate_schema_cache()
    yield
    mcp_client._MCP_TOOLS.clear()
    mcp_client._MCP_TOOLS.update(saved)
    mcp_client._invalidate_schema_cache()


@pytest.fixture(autouse=True)
def _no_update_feed(monkeypatch: pytest.MonkeyPatch):
    """No unit test reaches the update feed.

    The TUI asks at boot, the doctor row asks, and the PWA route asks on a
    thread — all fail-soft, so a live request would only be slow and
    non-deterministic here. Tests that want an answer patch these themselves
    (tests/test_r67_update_check.py)."""
    from core import update_check

    def offline(*_a, **_k):
        raise OSError("update feed is off in tests")

    monkeypatch.setattr(update_check, "_fetch_latest", offline)
    monkeypatch.setattr(update_check, "_fetch_main_compare", offline)
    update_check._reset_cache()


# ---------------------------------------------------------------------------
# Provider state isolation (autouse) — root-cause fix for test pollution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_provider_state(monkeypatch: pytest.MonkeyPatch):
    """
    Isolates the provider global state and the provider env variables per test.

    Root cause (sprint audit): cmd_tui/cmd_start and set_active_provider()
    write EPHE_MODEL_PROVIDER / EPHE_OPENAI_COMPAT_* into os.environ and set the
    module global core.model_provider._ACTIVE_OVERRIDE. Tests that really run
    those paths (engine_config, settings_ssot) do not clean up → later tests that
    mock ollama.AsyncClient and expect the local_ollama path hit the OpenAI path
    instead (real HTTP against the DGX URL → 400/404). That broke 11
    tool_calling-/performance tests.

    This autouse fixture establishes provider isolation for every test:
    _ACTIVE_OVERRIDE=None and all provider env variables removed (default
    = local_ollama). Tests that need a specific provider set it
    explicitly (monkeypatch.setenv / apply_env / set_active_provider).
    """
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)
    for var in (
        "EPHE_MODEL_PROVIDER",
        "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_MODEL",
        "EPHE_OPENAI_COMPAT_API_KEY",
        "EPHE_ENGINE_KEY_SOURCE",
        "EPHE_CUSTOM_OLLAMA_BASE_URL",
        "EPHE_LOCAL_OLLAMA_BASE_URL",
        "EPHE_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    # EPHE_SETUP_MODE/EPHE_LAN/EPHE_HOST/EPHE_PORT: run_server (lines 100/115/117/118)
    # writes them DIRECTLY into os.environ (no monkeypatch entry) → monkeypatch.undo()
    # does not catch them. Direct pop before + after the test, otherwise e.g. an
    # EPHE_HOST='0.0.0.0' from test_lan_failclosed leaks into the loopback tests of
    # test_engine_fail_closed (LAN branch -> SystemExit(1) instead of setup mode).
    # EPHE_MEMORY_DIR: ~10 route tests write it just as directly. Under wave D that
    # is not just another path but another BRAIN — the legacy rule
    # "whoever names persist_dir gets Chroma" also applies to this env path, and a
    # leaked value would have run the memory tests against Chroma while they
    # assert Kepta behaviour.
    for _k in (
        "EPHE_SETUP_MODE",
        "EPHE_ENGINE_KEY_REPAIR",
        "EPHE_LAN",
        "EPHE_HOST",
        "EPHE_PORT",
        "EPHE_MEMORY_DIR",
    ):
        os.environ.pop(_k, None)
    yield
    for _k in (
        "EPHE_SETUP_MODE",
        "EPHE_ENGINE_KEY_REPAIR",
        "EPHE_LAN",
        "EPHE_HOST",
        "EPHE_PORT",
        "EPHE_MEMORY_DIR",
    ):
        os.environ.pop(_k, None)


@pytest.fixture(autouse=True)
def _no_network_update_check(monkeypatch: pytest.MonkeyPatch):
    """A test run is no device, so it makes no update call.

    The terminal app asks the release feed once a day when it starts. Without
    this, every pilot test that mounts EpheApp waits on GitHub and gets a real
    update prompt over the surface it is asserting on.
    """
    monkeypatch.setenv("EPHE_NO_UPDATE_CHECK", "1")


@pytest.fixture(autouse=True)
def _hermetic_engine_key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No test may resolve the developer's own stored engine token.

    Since 2026-10-10 every start reads the key file (the desktop spawn always did), so an
    empty ``EPHE_OPENAI_COMPAT_API_KEY`` no longer means "no key" on a machine that has one —
    a test would authenticate a stub endpoint with a live secret and assert on the wrong
    engine. An explicitly passed ``home`` still wins, which is how the file's own tests
    address it.
    """
    import core.engine_config as ec

    declared = ec.key_file_path

    def hermetic(home=None):
        return declared(home) if home is not None else tmp_path / "engine.key"

    monkeypatch.setattr(ec, "key_file_path", hermetic)


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_session_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Redirect Ephe session path to a temporary directory.
    Each test gets a clean, isolated session directory.
    """
    session_dir = tmp_path / ".ephe" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)

    import core.session as session_module

    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(
        session_module, "SESSION_FILE", session_dir / "default.json"
    )
    return session_dir


@pytest.fixture
def sample_messages() -> list[Message]:
    return [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there!"),
        Message(role="user", content="How are you?"),
        Message(role="assistant", content="I am fine, danke!"),
    ]


# ---------------------------------------------------------------------------
# Ollama mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ollama_chunks() -> list[str]:
    """A realistic list of streaming chunks."""
    return ["Hello", " from", " the", " Black", " Forest", "!"]


@pytest.fixture
def mock_ollama_stream(mock_ollama_chunks: list[str]):
    """AsyncMock that simulates ollama AsyncClient streaming."""

    async def fake_stream(*args, **kwargs):
        for chunk in mock_ollama_chunks:
            yield {"message": {"content": chunk}}

    mock_client = MagicMock()
    mock_client.chat = MagicMock(return_value=fake_stream())
    return mock_client


@pytest.fixture
def mock_ollama_connection_error():
    """Simulates Ollama being unreachable."""
    with patch("ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.chat.side_effect = ConnectionRefusedError(
            "Connection refused – Ollama not running"
        )
        mock_class.return_value = instance
        yield mock_class


@pytest.fixture
def werkbank():
    """The birthplace under the artifact guard — read from the same source the tools
    read it from (core.artifact_store.artifact_session_dir). No test guesses at a
    folder; the `ohne-session` fallback (language-gate: ignore — names a stored identifier)."""
    from core.artifact_workbench import artifact_session_dir

    return artifact_session_dir()


@pytest.fixture(autouse=True)
def _hermetic_artifact_store(tmp_path, monkeypatch):
    """R17 artifact hub: every test gets its own library DB.

    Without this guard, stream tests (chat ingest) wrote test artifacts into the
    REAL ~/.ephe/artifacts.db (28 junk rows in the full suite).

    R4-A1 also covers the **workbench** itself: since the birthplace moved, every
    output tool writes under ~/.ephe/artifacts/<session>. A test run without this
    line would leave real files in the real folder.
    Tests that explicitly check the workbench set EPHE_CONFIG_DIR themselves,
    later — a monkeypatch in the test body runs after this fixture.
    """
    from core import artifact_store as _store

    monkeypatch.setattr(_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))


@pytest.fixture(autouse=True)
def _hermetic_skills_state(tmp_path, monkeypatch):
    """R16 skill manager: skill files and the disabled state never reach the real ~/.ephe.

    WHY redirect the directory too, not just the state file: ``DEFAULT_USER_SKILLS_DIR``
    is bound at import (``config_subdir`` freezes ``~/.ephe/skills`` before the per-test
    ``EPHE_CONFIG_DIR`` patch runs) and the ``skill_manage`` tool reads that constant when
    it builds a ``SkillLoader`` — so create/delete wrote the ``.md`` straight into the
    developer's home. Patching the constant (the same seam tests/test_r66_importer.py uses)
    keeps the write in tmp; a test that wants its own dir still overrides it later.
    """
    import core.skills as _skills

    monkeypatch.setattr(_skills, "DEFAULT_USER_SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(_skills, "DISABLED_SKILLS_FILE", tmp_path / "skills_state.json")


@pytest.fixture(autouse=True)
def _hermetic_security_store(tmp_path, monkeypatch):
    """The developer's own approval preferences never decide a test.

    `security_config_path()` is built from `engine_config.CONFIG_DIR`, which is bound at
    import; `EPHE_CONFIG_DIR` alone therefore leaves the real `~/.ephe/security.json`
    in play. Measured 2026-10-23: a store with `ask_categories: ["NETWORK"]` made
    `chat_tool_requires_confirm("web_search")` return True, so eight approval tests went
    red or green depending on xdist distribution. A test that wants its own store
    patches later, which runs after this fixture.
    """
    import core.engine_config as _engine_config
    import core.security_config as _security

    developer_default = _engine_config.CONFIG_DIR

    def isolated_path():
        root = _engine_config.CONFIG_DIR
        return (tmp_path / "ephe-home" if root == developer_default else root) / "security.json"

    monkeypatch.setattr(_security, "security_config_path", isolated_path)


@pytest.fixture(autouse=True)
def _hermetic_audit_log(tmp_path, monkeypatch):
    """R23 audit: channel/tool events never go into the real ~/.ephe/audit.log.

    AUDIT_LOG_FILE is bound at import time → move the attribute. Tests that
    deliberately check the audit file set their own target via
    monkeypatch.setattr (runs after this autouse fixture).
    """
    import core.audit_log as _audit

    monkeypatch.setattr(_audit, "AUDIT_LOG_FILE", tmp_path / "audit.log")


@pytest.fixture(autouse=True)
def _hermetic_refusal_throttle(monkeypatch):
    """The LAN refusal audit is throttled per client+host+reason per minute; a
    shared dict would let one test's refusal mute the next test's expectation."""
    from server import middleware

    monkeypatch.setattr(middleware, "_REFUSAL_AUDIT", {})


@pytest.fixture(autouse=True)
def _hermetic_workspace(tmp_path, monkeypatch):
    """R29: tests never pick up the repo's own project rules file via cwd."""
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "ws-none"))


@pytest.fixture
def empty_ephe_home(tmp_path, monkeypatch):
    """I6-0: the state 'the user has configured nothing' is never the default on a
    developer machine — ~/.ephe holds engine.json (with the generation block) and
    settings.json, and both are read by presence (read_generation_explicit,
    load_deep_settings). A test that checks the empty-register behaviour gets an
    empty device folder here.

    deliberately NOT autouse: the same folder carries the installed CPython cell
    guest (core/cpython_cell.py), and a test that really runs code needs exactly
    the developer's machine. Isolation that forced it empty would turn real cell
    runs back onto the unsafe kernel path.
    """
    import core.engine_config as ec

    cfg = tmp_path / "ephe-empty"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg, raising=False)
    return cfg


@pytest.fixture
def no_cell_guest(empty_ephe_home: Path) -> Path:
    """For tests that drive the in-process code runtime and must not inherit the machine.

    ``execute_code`` chooses its runtime from the device folder
    (``core/cpython_cell.py:94-109`` reading ``core/cpython_guest.py:177-188``): a host
    that once installed the CPython guest answers with
    ``status=GUEST_UNVERIFIED`` when the sandbox library is absent, because an installed
    but unverifiable guest deliberately does not fall back to the kernel. Measured
    2026-10-09 on the developer's machine: five tests failed on the self-hosted
    macOS CI leg and passed with an empty config dir. The cause is the device folder,
    which a hosted runner does not have.

    This is ``empty_ephe_home`` under the name of what the test needs, so the dependency is
    stated instead of assumed. An empty home is *not* the general case, which is why
    ``empty_ephe_home`` stays opt-in: a test that really runs code in the cell needs exactly
    the developer's machine.
    """
    return empty_ephe_home


@pytest.fixture
def chosen_engine(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """I2-2: a headless agent run (`ephe code`/`ephe goal`) requires a chosen
    engine. Tests that let such a run through provide it here
    — isolated, so the real ~/.ephe/engine.json of the developer machine is never
    read (a run that is green on one machine only is not one)."""
    import core.engine_config as ec
    from core.engine_config import EngineChoice, save_engine_config

    cfg = tmp_path / "engine-cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    choice = EngineChoice(provider="local_ollama", model="gemma4:12b")
    save_engine_config(choice, cfg / "engine.json")
    return choice


@pytest.fixture(autouse=True)
def _hermetic_mcp_clients():
    """I1-8: an MCP client is a child process — none of them outlives the test.

    The sync keeps live clients in a module registry. Without the clearing, a spy
    client from test A would be handed to test B, and a real stdio server would
    remain as a process.
    """
    import core.tools.mcp_client as _mcp

    _mcp._LIVE_CLIENTS.clear()
    yield
    for client in list(_mcp._LIVE_CLIENTS.values()):
        link = getattr(client, "_link", None)
        proc = None if link is None else link.proc
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001 — cleaning up must not fail a test
                pass
    _mcp._LIVE_CLIENTS.clear()


@pytest.fixture(autouse=True)
def _hermetic_cell_work_dir(tmp_path, monkeypatch):
    """R-cells: the ephemeral CPython cell writes a per-session /work folder, and
    the suite is only green when that folder is not the developer's ``~/.ephe``.

    ``core.cpython_guest.work_dir`` resolves its root from ``EPHE_CELL_WORK_ROOT``
    first and falls back to ``<config dir>/cells/work``. The config directory is
    bound at import time, so a test module that imports ``engine_config`` during
    collection (before the per-test env fixtures run) freezes it to ``~/.ephe`` —
    that is exactly how the cell and session suites came to write their boot
    script and journals into the real home. Pointing the work root here redirects
    the writable folders for every test without moving the guest interpreter, so
    the live cell tests keep running against the installed guest.
    """
    monkeypatch.setenv("EPHE_CELL_WORK_ROOT", str(tmp_path / "cell-work"))


@pytest.fixture(autouse=True)
def _hermetic_persona_dir(tmp_path, monkeypatch):
    """R28: keep the agent persona out of the real home directory during tests."""
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(tmp_path / "persona"))


@pytest.fixture(autouse=True)
def _hermetic_sessions_dir(tmp_path, monkeypatch):
    """R33: the REST turn mirror (rest-<id>) and CLI sessions never touch the
    real ~/.ephe/sessions during tests.

    SESSIONS_DIR/REGISTRY_FILE/LEGACY_FILE are module attributes bound at
    import time, so the attributes (not the env) are the patch target. Every
    multi_session helper reads them at call time, so patching here covers all
    callers. Tests that intentionally assert on the store patch it again.
    """
    from core import multi_session as _ms

    root = tmp_path / "sessions"
    monkeypatch.setattr(_ms, "SESSIONS_DIR", root)
    monkeypatch.setattr(_ms, "REGISTRY_FILE", root / "registry.json")
    monkeypatch.setattr(_ms, "LEGACY_FILE", root / "default.json")


@pytest.fixture(autouse=True)
def _hermetic_scheduler_files(tmp_path, monkeypatch):
    """Scheduler: job persistence + run history never touch the real ~/.ephe.

    R26 deploy-check found real test entries ("persist test") inside the
    user's schedule_results.json. The paths are resolved lazily from env at
    call time, so patching the env here is sufficient for every test.
    """
    monkeypatch.setenv("EPHE_SCHEDULE_JOBS", str(tmp_path / "scheduled_jobs.json"))
    monkeypatch.setenv("EPHE_SCHEDULE_RESULTS", str(tmp_path / "schedule_results.json"))


@pytest.fixture(autouse=True)
def _hermetic_memory_provider(tmp_path, monkeypatch):
    """Wave D: the suite default is Kepta — no test writes provider.json.

    The provider detection rule (core/memory_provider.resolve_provider) decides
    "a retired store on disk → recognised and named, otherwise → kepta" and persists
    that as a record. Without this guard every suite run would overwrite the
    developer's record in ~/.ephe/memory/provider.json and switch their real brain —
    the same error circle as R17/R23/R26/R29, only with the memory as the stake.

    The value is `kepta`: `chroma` stopped being a provider when the package left the
    product, and a name outside VALID_PROVIDERS is ignored with a warning, so setting
    it would guard nothing. Tests that want the other path delete the variable
    explicitly (monkeypatch.delenv) or set it.
    """
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    yield


@pytest.fixture(autouse=True)
def _drain_chat_workers():
    """The chat route's post-turn workers finish BEFORE this test's patches undo.

    Both chat paths hand work to two single-worker executors. When a test's
    `client.stream(...)` block ends, the TestClient portal can close while that work is
    still queued, and two things follow from the same cause: the mirrored turn never
    gets written at all (the symptom in
    tests/test_r33_rest_history.py::test_stream_turn_is_mirrored — racy locally, red on
    three CI legs), and when the job does run late, monkeypatch has already restored
    `core.multi_session.SESSIONS_DIR` to the real home, so the write lands in the
    developer's ~/.ephe — the `sessions/.tmp_<pid>_<hex>` entry that
    tests/test_home_isolation.py reported as unattributed on the 3.10 and 3.11 legs.

    A sentinel job on each executor drains its queue. This fixture is defined last, so
    autouse teardown order (reverse of setup) runs it while the hermetic path fixtures
    above are still in force. It reads sys.modules instead of importing: a suite that
    never touched the server pays nothing.
    """
    yield

    import sys

    chat_route = sys.modules.get("server.routes.chat")
    if chat_route is None:
        return
    for executor in (chat_route._MIRROR_EXECUTOR, chat_route._POST_TURN_EXECUTOR):
        try:
            executor.submit(lambda: None).result(timeout=30)
        except Exception:  # noqa: BLE001 — a stuck worker must not fail the suite twice
            pass


@pytest.fixture(scope="session", autouse=True)
def _no_port_squatter_left_behind():
    """Ends the guard's own residue, then fails the session over what is left.

    Why a port guard and not only home isolation: ``ephe_cli._spawn_backend`` starts the
    server with ``start_new_session=True`` on purpose — the product wants the backend to
    outlive the CLI window — so a test that reaches it detaches a child no teardown can
    reap by accident. Measured 2026-10-08: PID 79044 held :8765 for ~27 h, orphaned to
    PPID 1, with an already-deleted ``pytest-42/test_desktop_missing_toolchain0`` home in
    its environment, and answered /api/health in setup mode while the owner's
    ``~/.ephe/engine.json`` said something else. The Vite proxy and the Tauri shell both
    talk to whoever owns that port.

    Naming that residue was not enough to end it. A worker killed before its teardown
    (xdist, an OOM, a cancelled job) leaves the detached child behind for good, and the
    advice to kill the PID by hand only ever reached the human reading the message. So the
    session sweeps the signature the suite's own children carry — ``run_server.py`` under a
    pytest home, still holding a port — once before the baseline, which clears what a
    cancelled predecessor left, and once before the report below, which turns that report
    into a statement about what the sweep could not end. The sweep, the signature and the
    list of what it leaves standing live in tests/test_port_squatter_guard.py.

    The baseline is read before the first test runs, so the developer's own product
    server on :8765 is never the offender. Rules, evidence and the
    ``lsof``-unavailable fallback live in tests/test_port_squatter_guard.py.
    """
    from tests import test_port_squatter_guard as port_guard

    port = port_guard.guarded_port()
    # Residue from a run that was cancelled before its workers tore down would otherwise be
    # read as this session's. The sweep takes the signature the fixture's own children
    # carry; the developer's server and a foreign listener cannot match it.
    port_guard.reap_leaked_test_servers()
    baseline_pids = port_guard.listening_pids(port) or []
    baseline_open = bool(baseline_pids) or port_guard.port_is_open(port)
    yield
    reaped = port_guard.reap_leaked_test_servers()
    offenders = port_guard.session_offenders(port, baseline_pids, baseline_open)
    assert not offenders, (
        "tests/test_port_squatter_guard.py: this session left a server it started "
        f"running — nothing on 127.0.0.1:{port} belongs to a test when the run is over:\n"
        + "\n".join(offenders)
        + f"\n  The session sweep ended {len(reaped)} leaked product server(s): a process "
        "running run_server.py under a pytest home and still holding a port. What is listed "
        "above outlived it, so it is not that shape — a listener a test started another "
        "way, or the developer's own server — or the sweep could not signal it. A test "
        "still has to bind an ephemeral port (run_server.select_free_port('127.0.0.1', 0)) "
        "and terminate its child in teardown on every path; what is left above needs a "
        "hand: kill <PID>."
    )
