"""Tests for core/ephemeral_cell.py — bot = 1-cell lifecycle + envelope."""
from __future__ import annotations

import pytest

from core.ephemeral_cell import (
    CELL_IDLE_TTL_SECONDS,
    effective_ttl,
    forget,
    EphemeralCell,
    AgentEnvelope,
    create_cell,
    get_cell,
    reap_idle,
    reset_cells,
    cell_count,
    cells_created,
    cell_life,
    record_call,
    envelope_from_cell,
    run_in_cell,
    get_policy,
    snapshot_cell,
    rollback_cell,
    prewarm_cell,
    prewarm_count,
    KIND_KERNEL,
    SUMMARY_CAP,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_cells()
    yield
    reset_cells()


def test_create_cell_isolates_sessions():
    a = create_cell("sess-a")
    b = create_cell("sess-b")
    assert a.id != b.id
    assert a.session_id == "sess-a" and b.session_id == "sess-b"
    assert cell_count() == 2


def test_create_cell_idempotent_per_session():
    a1 = create_cell("s")
    a2 = create_cell("s")
    assert a1.id == a2.id
    assert cell_count() == 1


def test_get_cell_touches_last_active():
    c = create_cell("s")
    first = c.last_active_at
    got = get_cell("s")
    assert got is not None and got.id == c.id
    assert got.last_active_at >= first


def test_get_cell_missing_returns_none():
    assert get_cell("nope") is None


def test_reap_discards_expired():
    c = create_cell("s", ttl_seconds=0.0)  # already expired
    assert c.is_expired(1e9) is True
    removed = reap_idle(now=1e9)
    assert removed == 1
    assert cell_count() == 0


def test_reap_keeps_fresh():
    create_cell("s", ttl_seconds=1e6)
    assert reap_idle() == 0
    assert cell_count() == 1


def test_envelope_caps_summary():
    big = "x" * (SUMMARY_CAP + 500)
    env = envelope_from_cell(big, status="ok", artifacts=["/tmp/a.pdf"], tokens=42)
    assert isinstance(env, AgentEnvelope)
    assert len(env.summary) == SUMMARY_CAP
    assert env.artifacts == ["/tmp/a.pdf"]
    assert env.tokens == 42
    assert env.status == "ok"


def test_envelope_facts_are_nonempty_lines():
    env = envelope_from_cell("line1\n\nline2\n")
    assert env.facts == ["line1", "line2"]


@pytest.mark.asyncio
async def test_run_in_cell_executes_and_binds_cell():
    from core.tools.session_ctx import set_current_session
    set_current_session("sess-k")
    out = await run_in_cell("print(1+1)")
    assert "2" in out
    # the cell was bound
    assert get_cell("sess-k") is not None


# C5: get-policy parity (report == enforced)
def test_get_policy_parity_with_sandbox_defaults():
    from core.ephemeral_cell import get_policy
    from core.tools import sandbox_tools as sb
    pol = get_policy()
    assert pol["max_memory_mb"] == sb.DEFAULT_MAX_MEMORY_MB
    assert pol["max_fuel"] == sb.DEFAULT_MAX_FUEL
    assert pol["timeout_seconds"] == sb.DEFAULT_TIMEOUT_SECONDS
    assert pol["io_cpu_seconds"] == sb.DEFAULT_IO_CPU_SECONDS
    assert pol["io_budget_bytes"] == sb.DEFAULT_IO_BUDGET_BYTES
    assert pol["preopens"] == []          # preopen is denied by default
    assert pol["network"] == "none"        # Egress ADR-002


# C6: transactional snapshot / rollback
def test_snapshot_rollback_restores_state():
    c = create_cell("s")
    c.state = {"k": 1}
    snap = snapshot_cell("s")
    assert snap is not None and snap["state"] == {"k": 1}
    c.state = {"k": 2}                      # the unsafe call changes state
    assert rollback_cell("s", snap) is True
    assert get_cell("s").state == {"k": 1}  # back to the restore point


def test_snapshot_missing_cell_none():
    assert snapshot_cell("nope") is None
    assert rollback_cell("nope", None) is False


def test_rollback_ignores_foreign_id():
    create_cell("s")
    snap = snapshot_cell("s")
    snap["id"] = "fremd"
    assert rollback_cell("s", snap) is False


# C7: Prewarming (speculative preallocation)
def test_prewarm_idempotent_and_counted():
    cid = prewarm_cell("s")
    assert cid == create_cell("s").id        # the same cell, no duplicate
    assert prewarm_count() == 1
    assert cell_count() == 1


# WP5: the life line — every number has a writer
def test_record_call_geburt_undlauf():
    """A run without a prior birth IS the birth — and it counts as the first run."""
    assert cell_life("s")["alive"] is False
    record_call("s", 12.5)
    record_call("s", 7.5)
    life = cell_life("s")
    assert life["alive"] is True and life["calls"] == 2
    assert life["avg_ms"] == 10.0
    assert life["seconds_left"] <= life["ttl_seconds"]


def test_cell_life_liest_ohne_zu_verlaengern():
    """A glance from the surface is not a use: it must not move the reap boundary,
    otherwise the idle-TTL starves because somebody looked at it."""
    cell = create_cell("s", ttl_seconds=60.0)
    before = cell.last_active_at
    assert cell_life("s")["alive"] is True
    assert cell.last_active_at == before
    # get_cell, by contrast, IS a use — that difference is the whole point
    assert get_cell("s").last_active_at >= before


def test_cell_life_nennt_abgelaufenes_als_tot():
    create_cell("s", ttl_seconds=0.0)
    life = cell_life("s")
    assert life["alive"] is False and life["calls"] == 0 and life["avg_ms"] is None
    assert isinstance(life["contained"], bool)
    assert cell_count() == 0          # the read pass really does remove them


def test_cell_life_says_whether_a_turn_would_be_contained(monkeypatch):
    """The line may not report calls and idle time beside a guest that is absent:
    the flag is what lets the surface say "sandbox off" instead."""
    from core import ephemeral_cell

    monkeypatch.setattr(ephemeral_cell, "_containment_available", lambda: False)
    create_cell("s")
    assert cell_life("s")["contained"] is False
    monkeypatch.setattr(ephemeral_cell, "_containment_available", lambda: True)
    assert cell_life("s")["contained"] is True


def test_containment_flag_mirrors_the_approval_gate(monkeypatch):
    from core import cpython_cell, ephemeral_cell

    monkeypatch.setattr(cpython_cell, "code_runs_uncontained", lambda: True)
    assert ephemeral_cell._containment_available() is False
    monkeypatch.setattr(cpython_cell, "code_runs_uncontained", lambda: False)
    assert ephemeral_cell._containment_available() is True


def test_ordinal_zaehlt_prozessweit_und_resetzt():
    assert create_cell("a").ordinal == 1
    assert create_cell("b").ordinal == 2
    assert create_cell("a").ordinal == 1    # idempotent: no new number
    assert cells_created() == 2
    reset_cells()
    assert cells_created() == 0
    assert create_cell("c").ordinal == 1


@pytest.mark.asyncio
async def test_execute_code_haelt_die_registry_live():
    """The product path has to fill the registry — otherwise the UI shows a cell
    that never ran (the state before WP5: only tests called create_cell)."""
    from core.tools.code_kernel import execute_code
    from core.tools.session_ctx import set_current_session

    set_current_session("sess-wp5")
    assert cell_life("sess-wp5")["alive"] is False
    await execute_code("print(6*7)")
    life = cell_life("sess-wp5")
    assert life["alive"] is True
    assert life["calls"] == 1
    assert life["kind"] in ("wasi", "kernel")


# WP7: the ephemerality has controls with an effect
@pytest.fixture()
def _config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Ban settings.json and the cell folders into a test room."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    yield tmp_path


def test_idle_ttl_folgt_dem_regler(_config):
    from core.settings_schema import save_deep_settings

    assert effective_ttl() == CELL_IDLE_TTL_SECONDS      # without an entry: the constant
    save_deep_settings({"ephemera": {"ephemera.idle_ttl_minutes": 90}})
    assert effective_ttl() == 5400.0
    assert create_cell("s").ttl_seconds == 5400.0


def test_regler_ohne_wert_laesst_die_Konstante_stehen(_config):
    """A 0 in the register is not "die immediately": the register's guard rail
    applies first, and the cell lives out the floor (5 minutes). A cell that
    dies immediately would be worse than one that lives too long."""
    from core.settings_schema import settings_path

    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '{"version": 1, "sections": {"ephemera": {"ephemera.idle_ttl_minutes": 0}}}',
        encoding="utf-8",
    )
    assert effective_ttl() == 300.0


def test_fehlender_Eintrag_ohne_Register_laesst_die_Konstante_gelten(_config, monkeypatch):
    """If the line itself is broken (foreign file, unknown key), the module
    constant applies — not null, and no abort of the execution."""
    import core.settings_schema as schema

    def boom(_key):
        raise KeyError("ephemera.idle_ttl_minutes")

    monkeypatch.setattr(schema, "deep_number", boom)
    assert effective_ttl() == CELL_IDLE_TTL_SECONDS


def test_verdunsten_zerstoert_registry_und_arbeitsmappe(_config):
    from core.cpython_guest import work_dir

    create_cell("s")
    (work_dir("s") / "spur.txt").write_text("x", encoding="utf-8")
    assert forget("s") is True
    assert cell_life("s")["alive"] is False
    assert list(work_dir("s").iterdir()) == []


def test_verdunsten_einer_unbekannten_Sitzung_sagt_nein(_config):
    assert forget("niemals-da") is False


def test_sofort_verdunsten_ist_per_Default_aus(_config):
    """AGENTS.md: conservative defaults. Deleting destroys nothing the user did
    not explicitly approve; the idle boundary takes care of it anyway."""
    from core.settings_schema import SCHEMA, deep_bool

    assert SCHEMA["ephemera.evaporate_on_delete"]["default"] is False
    assert deep_bool("ephemera.evaporate_on_delete") is False
