"""Wave E1: model Python in the pinned CPython cell — the ceilings shown by proof.

Three layers (docs/SECURITY_THREAT_MODEL.md §7): content = the injection guard,
intent = the approval gate, execution = Ephemora Cell. This file hammers the
third layer down: what has to run inside the cell (print, arithmetic, stdlib,
variables across calls), what it has to stop (fuel, memory, network,
host files) and what the user has to be told about it (runtime in the result).

The live tests mirror `tests/test_sandboxed_code_tool.py:34`: with no installed
and verified guest they skip cleanly — the rest of the suite is untouched.
"""
from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import os
import re
from pathlib import Path

import pytest

from core import cell_output as cell_out
from core import cell_policy
from core import cpython_cell as cell
from core.tools import code_kernel
from core.tools.approval import classify_tool
from core.tools.session_ctx import set_current_session

MCP_STDIN_CAP_BYTES = 9_216  # core/tools/mcp_client.py: size of what Seam B sends per call


def _guest_live() -> bool:
    try:
        state = cell.guest_state()
    except Exception:  # noqa: BLE001 — an unreadable guest is not a live path
        return False
    return bool(state["entry_ok"] and state["tree_ok"])


live = pytest.mark.skipif(not _guest_live(), reason="CPython-Gast nicht installiert/verifiziert (opt-in)")


def _run(code: str, *, session: str = "e1-test", reset: bool = True) -> dict:
    return asyncio.run(cell.run_python(code, session, reset=reset))


def blob_size(path: Path) -> int:
    """Size of a file, or -1 when it is missing — a vanished blob is an error case."""
    return path.stat().st_size if path.is_file() else -1


def _agent_code(code: str, *, session: str = "e1-test", reset: bool = True) -> str:
    """The path the model takes: execute_code — including the routing decision."""
    token = set_current_session(session)
    try:
        return asyncio.run(code_kernel.execute_code(code, reset=reset))
    finally:
        from core.tools.session_ctx import _CURRENT_SESSION

        _CURRENT_SESSION.reset(token)


# Manifest and acquisition (always run)

def test_manifest_pins_guest_with_hashes_and_provenance():
    man = cell.manifest()
    guest = man["guest"]
    assert re.fullmatch(r"[0-9a-f]{64}", guest["entry_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", guest["root_tree_sha256"])
    assert guest["abi"] == "wasi_snapshot_preview1"
    assert guest["license"] == "PSF-2.0"
    prov = man["provenance"]
    assert prov["recipe"] == "build_cpython_guest.py"
    assert prov["source_url"].startswith("https://www.python.org/ftp/python/")
    assert re.fullmatch(r"[0-9a-f]{64}", prov["source_sha256"])
    assert "ac_cv_func_fdatasync=no" in prov["build_command"]


def test_guest_lives_outside_the_repository():
    """A ~150 MB guest does not belong in Git — the install path lives outside."""
    directory = cell.guest_dir()
    assert directory is not None
    repo = Path(__file__).resolve().parent.parent
    assert not str(directory.resolve()).startswith(str(repo) + os.sep)


def test_build_recipe_file_exists():
    repo = Path(__file__).resolve().parent.parent
    assert (repo / cell.manifest()["provenance"]["recipe"]).is_file()


# Routing: cell by default, the opt-out names its consequence

def test_kernel_optout_is_explicit_and_names_its_consequence(monkeypatch):
    monkeypatch.setenv(cell.ENV_EXEC, cell.RUNTIME_KERNEL)
    out = _agent_code("print(1+1)")
    assert f"runtime={cell.RUNTIME_KERNEL}" in out
    assert "UNSANDBOXED" in out and "host access" in out
    assert "2" in out


def test_unknown_optout_refuses_instead_of_guessing(monkeypatch):
    """No silent default in either direction: an unclear value leads to nothing."""
    monkeypatch.setenv(cell.ENV_EXEC, "vielleicht-sandbox")
    out = _agent_code("print(1+1)")
    assert cell.ENV_EXEC in out and "Nothing was executed" in out
    assert "2" not in out


def test_missing_guest_fails_closed_never_falls_through_to_kernel(monkeypatch):
    monkeypatch.setenv(cell.ENV_EXEC, cell.RUNTIME_CELL)
    monkeypatch.setattr(cell, "guest_state", lambda **kw: {
        "manifest": True, "version": "3.13.18", "installed": True, "library": True,
        "entry_ok": False, "tree_ok": False, "path": "/tmp/gast",
        "reason": "Entry-Hash weicht vom Manifest ab",
    })
    report = _run("print(1+1)")
    assert report["status"] == "GUEST_UNVERIFIED"
    text = cell.format_report(report)
    assert "GUEST_UNVERIFIED" in text and "EPHE_CODE_EXEC=kernel" in text
    assert f"runtime={cell.RUNTIME_KERNEL}" not in text


def test_installed_but_unverified_guest_is_never_the_kernel(tmp_path, monkeypatch):
    """Default path (no env): a tampered guest must not end up unsandboxed.

    The promise in exec_runtime()'s docstring — and needed precisely because the
    existing refusal test *forces* ENV_EXEC=cell and therefore skipped exactly the
    fork that had built the silent fallback.

    The library probe is pinned True rather than read from the runner: `guest_state()`
    short-circuits on the missing `ephemora_cell` import (core/cpython_guest.py:131-136)
    and answers the *other* remedy ("pip install 'ephe[sandbox]'"), which never names
    build_cpython_guest.py. CI installs neither the opt-in extra — a BUSL-1.1 package
    deliberately kept out of the pipeline — so this case failed on every leg while
    passing on a machine that has the sandbox installed. The assertions that matter
    here are the refusal ones below them, and they must run in CI, not skip.
    """
    from core import cpython_guest
    from core import engine_config

    monkeypatch.delenv(cell.ENV_EXEC, raising=False)
    monkeypatch.setattr(cpython_guest, "_library_present", lambda: True)
    monkeypatch.setattr(engine_config, "CONFIG_DIR", str(tmp_path))
    (tmp_path / str(cell.manifest()["guest"]["install_dir"])).mkdir(parents=True)

    assert cell.guest_installed() is True
    assert cell.exec_runtime() == cell.RUNTIME_CELL
    out = _agent_code("print(1 + 1)")
    assert "status=GUEST_UNVERIFIED" in out
    assert f"runtime={cell.RUNTIME_KERNEL}" not in out
    assert "build_cpython_guest.py" in out


def test_never_installed_guest_names_the_kernel_it_falls_back_to(tmp_path, monkeypatch):
    """The other half of the same distinction: never-installed is honest."""
    from core import engine_config

    monkeypatch.delenv(cell.ENV_EXEC, raising=False)
    monkeypatch.setattr(engine_config, "CONFIG_DIR", str(tmp_path))
    assert cell.guest_installed() is False
    assert cell.exec_runtime() == cell.RUNTIME_KERNEL


def test_approval_gate_follows_the_runtime(monkeypatch):
    """W3-15 refines E1: the gate is no longer untouched for execute_code.

    E1 moved the execution and left the gate static (execute_code SAFE/auto-run).
    The hole in that: without the cell the same tool executes on the host, and the
    static SAFE meant that host execution needed no approval. Now the cell is the
    licence — contained ⇒ auto-run, uncontained ⇒ gated like run_shell.
    """
    monkeypatch.delenv(cell.ENV_EXEC, raising=False)
    monkeypatch.setattr(cell, "guest_installed", lambda: True)
    contained = classify_tool("execute_code")
    assert contained.category == "SAFE" and contained.is_mutating is False
    assert contained.auto_approve_by_default is True

    monkeypatch.setenv(cell.ENV_EXEC, cell.RUNTIME_KERNEL)
    uncontained = classify_tool("execute_code")
    assert uncontained.category == "MUTATING" and uncontained.is_mutating is True
    assert uncontained.auto_approve_by_default is False

    # The guest stays the conservative path for a pre-built WASI module.
    assert classify_tool("run_sandboxed_code").is_mutating is True


def test_doctor_cell_check_is_failsoft(monkeypatch):
    monkeypatch.setattr(cell_policy, "guest_state", lambda **kw: {
        "manifest": True, "version": "", "installed": False, "library": False,
        "entry_ok": False, "tree_ok": False, "path": "", "reason": "Gast nicht installiert",
    })
    ok, detail = cell_policy.doctor_snapshot()
    assert ok is True  # informational: without a guest execute_code runs in the kernel
    assert "Kernel" in detail or "ephe[sandbox]" in detail


# Seam decision: A (native) instead of B (guest as an MCP tool)
# A guard instead of a second implementation: choose A, keep B as a cheap test,
# so the reasoning does not turn into folklore.

def test_seam_a_is_the_only_python_execution_path():
    """Guard instead of a second build: the code path calls the cell library, never an MCP server."""
    source = Path(code_kernel.__file__).read_text(encoding="utf-8")
    assert "cpython_cell" in source
    for seam_b in ("mcp_client", "call_registered_mcp_tool", "sync_mcp_tools"):
        assert seam_b not in source, f"execute_code haelt an {seam_b} — Seam B ist nicht der Code-Pfad"


def test_seam_b_would_cap_every_program():
    """The cell takes programs of any size — the MCP path would hit the wall at 9.216 bytes."""
    from core.tools import mcp_client

    assert cell_out.OUTPUT_CAP_BYTES > 0
    assert MCP_STDIN_CAP_BYTES < 20_000
    assert not hasattr(mcp_client, "run_python")


# The Apache tier owns the I/O hardening; the BUSL release does not carry it

#: The file ceilings Ephe ships. Only what the installed module actually has may
#: be claimed here — a changelog is not evidence.
IO_CEILINGS = ("disk_quota_bytes", "io_cpu_seconds", "io_budget_bytes")


def test_installed_cell_module_knows_the_io_ceilings():
    """Proven against the installed ephemora_cell; a release intention proves nothing."""
    ephemora_cell = pytest.importorskip("ephemora_cell")
    fields = {f.name for f in dataclasses.fields(ephemora_cell.WASIConfig)}
    fehlend = set(IO_CEILINGS) - fields
    assert not fehlend, (
        f"die installierte Cell kennt {sorted(fehlend)} nicht — core/cpython_cell.py "
        "schreibt dann Deckel, die in dieser Version keine Wirkung haben"
    )


@live
def test_cell_config_carries_every_ceiling_it_claims(monkeypatch):
    """report == enforced: the WASIConfig is built from Ephe's values where defaults differ."""
    import ephemora_cell

    captured: dict = {}

    def fake_run_isolated(entry, config, args=None, **kwargs):
        captured["entry"] = entry
        captured["args"] = list(args or [])
        captured.update({f.name: getattr(config, f.name) for f in dataclasses.fields(config)})
        return {"status": "OK", "stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(ephemora_cell, "run_isolated", fake_run_isolated)
    report = _run("print(1)")

    assert captured["disk_quota_bytes"] == cell.DEFAULT_DISK_QUOTA_BYTES
    assert captured["io_cpu_seconds"] == cell.DEFAULT_IO_CPU_SECONDS
    assert captured["io_budget_bytes"] == cell.DEFAULT_IO_BUDGET_BYTES
    assert captured["max_fuel"] == cell.fuel_budget()
    assert captured["max_memory_mb"] == cell.DEFAULT_MAX_MEMORY_MB
    assert any(str(d).endswith("::/work") for d in captured["allow_dirs"])
    # The guest was never really started: the launcher names the boot script where the
    # program would be, and without a real run there is no output at all.
    assert captured["args"] == ["/work/cell_boot.py"]
    assert "1" not in report["stdout"]


@pytest.mark.skipif(
    importlib.util.find_spec("ephemora_cell") is None,
    reason="ephemora-cell is the opt-in sandbox extra (BUSL-capped, deliberately not "
    "installed in CI); the card's absent-package half is covered unconditionally below",
)
def test_cell_runtime_license_is_read_from_the_installed_package():
    """The settings card invents no licence: it stands in the installed Dist-Info.

    A hardcoded string would be a licence claim into the void as soon as another
    version is installed. The PyPI ladder and the BUSL decision about it are
    `ephe doctor`'s watch (test_dependency_license_fence.py) — it is not
    rebuilt a second time here.
    """
    from importlib.metadata import metadata, version

    behauptet = cell_policy.cell_runtime_license()
    assert version("ephemora-cell") in behauptet, behauptet
    assert (metadata("ephemora-cell").get("License") or "") in behauptet
    assert "1.0.4.3" not in behauptet or version("ephemora-cell") == "1.0.4.3"
    assert "Pin" not in behauptet, "die Doctor-Watch hat schon einen Satz fuer die Leiter"


def test_cell_runtime_license_without_the_package_claims_nothing(monkeypatch):
    """Runs on every CI leg: with the distribution absent the card says "unknown".

    This is the half the skipped test above cannot show, and it is the one that keeps
    the promise honest — an uninstalled opt-in runtime must not print a version or a
    licence name it does not have (core/cell_policy.py:40-48).
    """
    import importlib.metadata as md

    def _missing(_name: str):
        raise md.PackageNotFoundError("ephemora-cell")

    monkeypatch.setattr(md, "metadata", _missing)
    monkeypatch.setattr(md, "version", _missing)

    assert cell_policy.cell_runtime_license() == "ephemora-cell: Version unbestimmt"


# Policy truth: report == enforced

def test_policy_snapshot_matches_runner_constants():
    pol = cell_policy.policy_snapshot()
    assert pol["max_fuel"] == cell.fuel_budget()
    assert pol["max_memory_mb"] == cell.DEFAULT_MAX_MEMORY_MB
    assert pol["timeout_seconds"] == cell.DEFAULT_TIMEOUT_SECONDS
    assert pol["network"] == "none"
    assert pol["guest"]["version"]
    assert pol["measured"]["boot_fuel"] > 0
    assert "runtime" in pol and pol["runtime"] in (cell.RUNTIME_CELL, cell.RUNTIME_KERNEL)


def test_reported_caps_equal_the_config_the_runner_writes_without_the_guest(monkeypatch):
    """report == enforced on every CI leg, including a machine with no guest.

    ``test_cell_config_carries_every_ceiling_it_claims`` is the live witness, but it
    needs the installed package and a verified guest, so the identity it proves is
    absent from CI. Here a fake ``ephemora_cell`` stands in front of the real
    enforcement path — ``run_python`` -> ``_run_sync`` -> ``WASIConfig`` — and the
    config it builds is pinned to ``policy_snapshot()``. Drift in either direction
    fails here: a reported cap the runner does not write, or a cap the runner writes
    the panel does not show.
    """
    import importlib.machinery
    import sys
    import types

    monkeypatch.setattr(cell, "guest_state", lambda **kw: {
        "manifest": True, "version": cell.manifest()["guest"]["version"],
        "installed": True, "library": True, "entry_ok": True, "tree_ok": True,
        "path": "/tmp/gast", "reason": "",
    })

    captured: dict = {}

    class FakeWASIConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    # A stand-in module for `from ephemora_cell import WASIConfig, run_isolated`.
    # It carries a __spec__ because `_library_present()` runs find_spec on the name.
    fake = types.SimpleNamespace(
        __spec__=importlib.machinery.ModuleSpec("ephemora_cell", None),
        WASIConfig=FakeWASIConfig,
        run_isolated=lambda entry, config, args=None, **kw: {
            "status": "SUCCESS", "stdout": "", "stderr": "", "exit_code": 0,
        },
    )
    monkeypatch.setitem(sys.modules, "ephemora_cell", fake)

    report = _run("print(1)")
    pol = cell_policy.policy_snapshot()

    # Every budget the card, `ephe doctor` and the status page report is exactly
    # the value the runner writes into the WASIConfig.
    assert captured["max_fuel"] == pol["max_fuel"]
    assert captured["max_memory_mb"] == pol["max_memory_mb"]
    assert captured["timeout_seconds"] == pol["timeout_seconds"]
    assert captured["io_budget_bytes"] == pol["io_budget_bytes"]
    assert captured["io_cpu_seconds"] == pol["io_cpu_seconds"]
    assert captured["disk_quota_bytes"] == pol["disk_quota_bytes"]
    # The receipt the model reads carries the same enforced memory and fuel.
    assert report["memory_mb"] == pol["max_memory_mb"]
    assert report["fuel_budget"] == pol["max_fuel"]

    # Network: the guest is socketless (WASI Preview1), so the enforced config
    # carries no egress surface at all — no allow-net / sidecar / egress key —
    # and opens only the read-only guest root plus the writable /work.
    for egress in ("allow_net", "allow_network", "net_allow", "network", "egress", "sidecar"):
        assert egress not in captured, f"{egress} turns the reported network=none into a lie"
    assert pol["network"] == "none"
    dirs = [str(d) for d in captured["allow_dirs"]]
    assert any(d.endswith("::/work") for d in dirs)
    assert any(d.endswith("::/") for d in dirs)


def test_settings_endpoint_exposes_the_effective_policy():
    """GET /api/settings/code-exec is the policy truth for the UI — read-only, secret-free."""
    import json

    from fastapi.testclient import TestClient

    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/api/settings/code-exec")
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_fuel"] == cell.DEFAULT_MAX_FUEL
    assert body["max_memory_mb"] == cell.DEFAULT_MAX_MEMORY_MB
    # The card only reads what the server knows — so the scope of the two
    # disk numbers has to arrive over the API as well as stand in the Python module.
    assert body["disk_quota_bytes"] == cell.DEFAULT_DISK_QUOTA_BYTES
    assert body["work_quota_bytes"] == cell.DEFAULT_WORK_QUOTA_BYTES
    assert "je Session" in body["quota_scopes"]["work_quota_bytes"]
    assert body["network"] == "none"
    assert body["guest"]["version"]
    assert "secret" not in json.dumps(body).lower()


def test_ephemeral_cell_policy_exposes_the_cell_budget():
    """The agent cell has a different budget than a pre-built module — both visible."""
    from core.ephemeral_cell import get_policy

    pol = get_policy()
    code_exec = pol["code_exec"]
    assert code_exec["max_fuel"] == cell.DEFAULT_MAX_FUEL
    assert code_exec["max_memory_mb"] == cell.DEFAULT_MAX_MEMORY_MB
    # The old keys stay those of the WASI-module path (parity with sandbox_tools).
    from core.tools import sandbox_tools as sb
    assert pol["max_fuel"] == sb.DEFAULT_MAX_FUEL


def test_report_text_carries_the_runtime_for_the_panel():
    text = cell.format_report({"runtime": cell.RUNTIME_CELL, "guest_version": "3.13.18",
                               "status": "OK", "exit_code": 0, "fuel_consumed": 1,
                               "fuel_budget": 2, "elapsed_ms": 3.0, "memory_mb": 256,
                               "stdout": "hi", "stderr": "", "names": [], "dropped": []})
    assert cell.runtime_of_report_text(text) == cell.RUNTIME_CELL
    assert "net=none" in text and "fuel=1/2" in text


# Live proofs: what has to run

@live
def test_model_python_prints_in_the_cell():
    out = _agent_code("print(1 + 1)")
    assert f"runtime={cell.RUNTIME_CELL}/" in out
    assert "2" in out.split("stdout:")[1]


@live
def test_pure_computation_and_stdlib_import():
    report = _run("import json\nprint(json.dumps({'zwei': 2 * 3}, sort_keys=True))")
    assert report["status"] == "OK"
    assert '{"zwei": 6}' in report["stdout"]


@live
def test_variables_survive_between_calls_and_reset_clears_them():
    session = "e1-persist"
    first = _run("fib = [0, 1]\nfor _ in range(12): fib.append(fib[-1] + fib[-2])", session=session)
    assert "fib" in first["names"]
    second = _run("print(len(fib), fib[-1])", session=session, reset=False)
    assert second["stdout"].split() == ["14", "233"]
    third = _run("print(fib)", session=session)  # reset=True in the helper
    assert "NameError" in third["stderr"]


@live
def test_big_program_runs_although_the_mcp_stdin_would_cap_it():
    program = "x = 0\n" + "".join(f"x += {i}\n" for i in range(1200)) + "print(x)\n"
    assert len(program.encode("utf-8")) > MCP_STDIN_CAP_BYTES
    report = _run(program)
    assert report["status"] == "OK"
    assert report["stdout"].strip() == str(sum(range(1200)))


# Live proofs: what the cell has to stop

@live
def test_fuel_bomb_is_stopped_by_the_sandbox_and_ephe_survives():
    report = _run("while True:\n    pass", session="e1-bomb")
    assert report["status"] == "FUEL_EXHAUSTED"
    assert report["fuel_consumed"] == report["fuel_budget"]
    # Ephe lives: same process, same runner, next run is fine.
    again = _run("print('noch da')", session="e1-bomb")
    assert again["status"] == "OK" and "noch da" in again["stdout"]


@live
def test_memory_hungry_guest_hits_the_cap():
    report = _run("b = bytearray(512 * 1024 * 1024)\nprint(len(b))", session="e1-mem")
    assert report["status"] != "OK"
    assert "MemoryError" in report["stderr"]
    assert "536870912" not in report["stdout"]
    again = _run("print('nach der memory-kappe')", session="e1-mem")
    assert again["status"] == "OK"


@live
def test_host_files_are_not_readable():
    report = _run("print(open('/etc/passwd').read()[:40])", session="e1-fs")
    assert report["status"] != "OK"
    assert "root:" not in report["stdout"]


@live
def test_network_egress_is_denied():
    report = _run("import socket\ns = socket.socket()\nprint('SOCKET', s)", session="e1-net")
    assert report["status"] != "OK"
    assert "SOCKET" not in report["stdout"]


@live
def test_guest_cannot_rewrite_its_own_interpreter():
    """The preopen '/' is read-only: a model cannot rebuild its own interpreter."""
    target = "/usr/local/lib/python3.13/json/__init__.py"
    report = _run(
        f"open({target!r}, 'w').write('x')\nprint('TAMPERED')",
        session="e1-tamper",
    )
    assert "TAMPERED" not in report["stdout"]
    # The verification of the next hour must not be waved through.
    state = cell.guest_state(deep=True)
    assert state["entry_ok"] and state["tree_ok"], state["reason"]


@live
def test_work_dir_is_writable_but_quotenced():
    """/work is the only writable folder — and it is capped per FILE."""
    session = "e1-quota"
    try:
        report = _run(
            "with open('/work/blob.bin', 'wb') as fh:\n"
            "    for _ in range(64):\n"
            "        fh.write(b'0' * (1024 * 1024))\n"
            "print('WROTE 64MB')\n",
            session=session,
        )
        assert "WROTE 64MB" not in report["stdout"]
        blobs = list(cell.work_dir(session).rglob("*.bin"))
        assert sum(p.stat().st_size for p in blobs) <= cell.DEFAULT_DISK_QUOTA_BYTES
        # The per-file boundary is not a cap that truncates the rest: the engine
        # sets RLIMIT_FSIZE, the write attempt faults with EFBIG — and the file
        # stands exactly at the ceiling. A run that silently ended at 33.554.431
        # would be a quieter, harder-to-find lie.
        assert blob_size(cell.work_dir(session) / "blob.bin") == cell.DEFAULT_DISK_QUOTA_BYTES
        assert "Errno 22" in report["stderr"], report["stderr"][-400:]
    finally:
        cell.reset_work_dir(session)


# The session quota: the total ceiling the engine does not set
#
# Measured 2026-10-02: `disk_quota_bytes` bounds EACH FILE (RLIMIT_FSIZE, EFBIG at
# exactly that value). The engine does not see the sum over many files — eight
# files a 4 MiB got through (34.238.818 bytes on disk, status SUCCESS), and
# `io_budget_bytes` counts its own sandbox folder and misses Ephe's /work preopen
# (reported: `io_bytes_written: 0`). The settings card showed the same number as
# "Disk-Kontingent (/work)" — a ceiling nobody sets. So ephe sets the total
# ceiling itself (`core.cpython_guest.sweep_work_dir`) and names what it removed
# for that. Two numbers, two scopes, two enforcers.


def test_der_Gesamtdeckel_ist_groesser_als_der_Dateideckel():
    """What is allowed per file has to fit per session — otherwise the numbers contradict each other."""
    assert cell.DEFAULT_WORK_QUOTA_BYTES > cell.DEFAULT_DISK_QUOTA_BYTES
    assert cell.DEFAULT_WORK_QUOTA_BYTES % 1048576 == 0


def test_policy_nennt_zu_jedem_Deckel_seinen_Scope_und_Seinen_Durchsetzer():
    """'32 MiB' without a scope was the defect: the card must say who caps what."""
    pol = cell_policy.policy_snapshot()
    assert pol["disk_quota_bytes"] == cell.DEFAULT_DISK_QUOTA_BYTES
    assert pol["work_quota_bytes"] == cell.DEFAULT_WORK_QUOTA_BYTES
    scopes = pol["quota_scopes"]
    assert "je Datei" in scopes["disk_quota_bytes"]
    assert "RLIMIT_FSIZE" in scopes["disk_quota_bytes"]
    assert "je Session" in scopes["work_quota_bytes"]
    assert "sweep_work_dir" in scopes["work_quota_bytes"]
    # A counter that does not see /work must not appear as a ceiling of /work.
    assert "0" in scopes["io_budget_bytes"], scopes["io_budget_bytes"]


def test_sweep_evictiert_das_Aelteste_und_laesst_die_Zusagen_stehen(tmp_path):
    """The total ceiling is not paid for by the journal promise — nor by the newest result."""
    work = tmp_path / "work"
    work.mkdir()

    def make(name: str, size: int, when: float) -> Path:
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"0" * size)
        os.utime(path, (when, when))
        return path

    make(cell_out.STDOUT_LOG_NAME, 3 * 1024 * 1024, 100)
    make(cell_out.STDERR_LOG_NAME, 1024, 100)
    make("result.json", 1024, 100)
    make("state.pkl", 2 * 1024 * 1024, 100)
    make("pyc/mod.pyc", 1024, 150)
    make("alt.bin", 4 * 1024 * 1024, 200)
    make("neu.bin", 4 * 1024 * 1024, 300)
    total = 13 * 1024 * 1024 + 3 * 1024
    assert cell_out.dir_bytes(work) == total

    out = cell.sweep_work_dir(work, 12 * 1024 * 1024)

    assert out["evicted"] == ["pyc/mod.pyc", "alt.bin"], out
    assert out["evicted_data"] == ["alt.bin"], (
        "der Puffer zaehlt nicht als verlorene Arbeit — nur sie wird im Report beim Namen genannt"
    )
    assert out["work_bytes"] == total - 1024 - 4 * 1024 * 1024, out
    assert out["freed_bytes"] == 4 * 1024 * 1024 + 1024
    assert out["over_quota"] is False
    assert (work / "neu.bin").is_file(), "das neueste Ergebnis bleibt — der Modell-Code will es wiederlesen"
    for name in (cell_out.STDOUT_LOG_NAME, cell_out.STDERR_LOG_NAME, "result.json", "state.pkl"):
        assert (work / name).is_file(), f"{name} traegt eine Zusage und wird nie veraeussert"


def test_sweep_verkauft_die_Zusagen_nicht_um_die_Quota_voll_zu_machen(tmp_path):
    """If the evictable remainder is not enough, ephe says so — instead of deleting the session state."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "state.pkl").write_bytes(b"0" * (6 * 1024 * 1024))
    (work / cell_out.STDOUT_LOG_NAME).write_bytes(b"0" * 1024)

    out = cell.sweep_work_dir(work, 4 * 1024 * 1024)

    assert out["evicted"] == []
    assert out["over_quota"] is True
    assert out["work_bytes"] == 6 * 1024 * 1024 + 1024
    assert (work / "state.pkl").is_file()


def test_die_Eviction_Zeile_nennt_das_Raeumen_ohne_dreissig_Pfade():
    """The bytecode buffer is the large, worthless part of the list: it counts, it is not listed."""
    report = {
        "runtime": cell.RUNTIME_CELL, "status": "OK", "exit_code": 0,
        "work_bytes": 1024, "work_quota_bytes": 64 * 1024 * 1024,
        "work_freed_bytes": 21_643_606,
        "work_evicted": [f"pyc/mod{i}.pyc" for i in range(30)] + ["a.bin", "b.bin"],
        "work_evicted_data": ["a.bin", "b.bin"],
    }
    zeile = next(line for line in cell.format_report(report).splitlines() if line.startswith("[work:"))
    assert "session quota 64 MiB" in zeile
    assert "21643606 bytes removed, oldest first" in zeile
    assert "30 bytecode cache file(s)" in zeile
    assert "2 oldest results: a.bin, b.bin" in zeile
    assert "pyc/" not in zeile, zeile
    assert len(zeile) < 300, zeile


def test_ueber_Quota_ohne_Evictierbares_ist_eine_Aussage_und_kein_Schweigen():
    """When only protected files remain, ephe says so — it does not pretend the number still holds."""
    report = {
        "runtime": cell.RUNTIME_CELL, "status": "OK", "exit_code": 0,
        "work_bytes": 8 * 1024 * 1024, "work_quota_bytes": 4 * 1024 * 1024,
        "work_over_quota": True, "work_evicted": [],
    }
    out = cell.format_report(report)
    assert "still over the session quota" in out
    assert "nothing was deleted" in out


@live
def test_die_Session_Quota_grenzt_die_Summe_ueber_Dateien():
    """The measured case: many files under the per-file ceiling, together over it."""
    session = "i2-work-quota"
    try:
        report = _run(
            "for i in range(20):\n"
            "    with open(f'/work/teil{i}.bin', 'wb') as fh:\n"
            "        fh.write(b'0' * (4 * 1024 * 1024))\n"
            "print('TEILE 20')\n",
            session=session,
        )
        assert report["status"] == "OK", report["stderr"][-400:]
        assert report["work_bytes"] <= cell.DEFAULT_WORK_QUOTA_BYTES, report["work_bytes"]
        assert report["work_evicted"], "80 MiB enden nicht ohne Durchsetzung bei 64 MiB"
        assert report["work_quota_bytes"] == cell.DEFAULT_WORK_QUOTA_BYTES
        assert cell_out.STDOUT_LOG_NAME in [p.name for p in cell.work_dir(session).iterdir()], \
            "die Quota loescht nicht den abholbaren Rest"
        out = cell.format_report(report)
        assert "session quota" in out and "removed" in out, out
        assert f"work={report['work_bytes']}B/{report['work_quota_bytes']}B" in out
    finally:
        cell.reset_work_dir(session)


@live
def test_die_Session_Quota_gilt_auch_vor_dem_Lauf():
    """A run does not start on a full workspace: clear first, report afterwards."""
    session = "i2-work-quota-pre"
    try:
        _run(
            "for i in range(18):\n"
            "    with open(f'/work/alt{i}.bin', 'wb') as fh:\n"
            "        fh.write(b'0' * (4 * 1024 * 1024))\nprint('ALT')\n",
            session=session,
        )
        report = _run("open('/work/neu.bin', 'wb').write(b'1' * (4 * 1024 * 1024))\nprint('NEU')\n",
                      session=session, reset=False)
        assert report["status"] == "OK", report["stderr"][-400:]
        assert report["work_bytes"] <= cell.DEFAULT_WORK_QUOTA_BYTES
        assert (cell.work_dir(session) / "neu.bin").is_file()
        assert any(name.startswith("alt") for name in report["work_evicted"]), report["work_evicted"]
    finally:
        cell.reset_work_dir(session)


@live
def test_no_host_tool_is_reachable_from_the_cell():
    """The guest reaches no host tools, including those the kernel hands through."""
    out = _agent_code(
        "from ephe_tools import run_shell\nprint(run_shell(command='echo pwned'))",
        session="e1-gate",
    )
    assert "pwned" not in out
    assert "is not reachable" in out
    assert "run_shell" in out


# The output sink: a print must not kill the model's code (I1-5)
#
# Measured 2026-10-02: up to 10.000 bytes per stream the guest survives; from
# about 11.000 its own sys.stdout.write throws 'OSError: [Errno 29] I/O error'.
# The model therefore crashed on its own output and additionally saw 8192 bytes
# from somewhere. An agent that prints a large JSON is the ordinary thing an
# agent does here; the error case is the write that throws.

BIG = "import sys\nsys.stdout.write('A' * 30000)\nprint('ZEILE_AM_ENDE')\n"


@live
def test_large_output_does_not_crash_the_model_code():
    report = _run(BIG, session="out-cap")
    assert report["status"] == "OK"
    assert "Errno 29" not in report["stderr"]
    assert report["stdout_bytes"] == 30014
    assert len(report["stdout"].encode("utf-8")) <= cell_out.OUTPUT_CAP_BYTES
    assert report["output_capped"] is True


@live
def test_the_last_line_survives_the_cut():
    """A head alone would cut exactly the line the output is usually about."""
    report = _run(BIG, session="out-tail")
    assert "ZEILE_AM_ENDE" in report["stdout"]


@live
def test_small_output_claims_no_cap():
    """The earlier length guessing reported a cap at exactly 10.000 bytes — without loss."""
    report = _run("print('hallo')\n", session="out-small")
    assert report["output_capped"] is False
    assert report["stdout"].strip() == "hallo"
    assert report["stdout_bytes"] == len("hallo\n")


@live
def test_the_rest_is_reachable_in_the_same_session():
    """The fetchable remainder is only a promise when it really lies there."""
    first = _run(BIG, session="out-journal")
    assert first["stdout_log_bytes"] == 30014
    again = _run(
        "f = open('/work/stdout.log', 'rb')\n"
        f"f.seek({first['stdout_log_start'] + 29990})\n"
        "print(f.read(24))\n",
        session="out-journal",
        reset=False,
    )
    assert again["status"] == "OK"
    assert "ZEILE_AM_ENDE" in again["stdout"]
    assert again["stdout_log_start"] >= first["stdout_log_bytes"]


@live
def test_tee_ceiling_names_the_loss_instead_of_promising_the_file():
    """/work does not write without limit: above the tee ceiling the report must
    not say 'vollstaendig' — that would be the same false claim in new clothes."""
    report = _run("import sys\nsys.stdout.write('B' * 2_000_000)\n", session="out-tee")
    assert report["status"] == "OK"
    assert report["stdout_bytes"] == 2_000_000
    assert report["stdout_log_bytes"] == cell_out.GUEST_TEE_CAP_BYTES
    out = cell.format_report(report)
    assert "sind weg" in out
    assert "vollstaendig" not in out


@live
def test_work_bytes_measures_what_the_engine_counter_misses():
    """Measured: io_bytes_written stays at 0 while the guest writes into /work.

    Not forgetfulness but design: the io_budget watcher scans the engine's sandbox
    folder, Ephe's /work is a preopen next to it. So ephe measures the floor itself
    and never grounds its total ceiling in that counter.
    """
    session = "out-work"
    try:
        report = _run(
            "with open('/work/spurbin.bin', 'wb') as fh:\n"
            "    fh.write(b'0' * (4 * 1024 * 1024))\nprint('ok')\n",
            session=session,
        )
        assert report["status"] == "OK"
        assert report["io_bytes_written"] == 0, report["io_bytes_written"]
        assert report["work_bytes"] >= 4 * 1024 * 1024
        out = cell.format_report(report)
        assert f"work={report['work_bytes']}B/{report['work_quota_bytes']}B" in out
    finally:
        cell.reset_work_dir(session)


@live
def test_direct_fd_write_is_a_documented_edge_not_a_fake_success():
    """os.write(1, …) bypasses the tee and keeps faulting. Known edge: it may
    read as a success while the model's error never surfaces and the output stays mute."""
    report = _run("import os\nos.write(1, b'C' * 30000)\n", session="out-edge")
    assert report["status"] != "OK"


def test_forward_budget_can_never_reach_the_sink_wall():
    """Proved rather than hoped: what the boot passes through stays, with both
    payloads and their markers, under the wall that used to kill the guest."""
    from core import cell_boot

    assert cell_boot.FORWARD_BYTES == cell_out.GUEST_FORWARD_BYTES
    assert cell_boot.TEE_CAP_BYTES == cell_out.GUEST_TEE_CAP_BYTES
    reserved_worst_case = cell_out.GUEST_FORWARD_BYTES * 2 + 4096
    assert reserved_worst_case < cell_out.SINK_CEILING_BYTES, (
        f"Forward {cell_out.GUEST_FORWARD_BYTES} x2 + Marker 4096 = {reserved_worst_case} "
        f"traegt bis an die Senkenwand ({cell_out.SINK_CEILING_BYTES})"
    )


def test_policy_publishes_the_ceiling_it_protects_against():
    """A cap without the number it protects against is half the truth."""
    pol = cell_policy.policy_snapshot()
    assert pol["output_cap_bytes"] == cell_out.OUTPUT_CAP_BYTES
    assert pol["guest_forward_bytes"] < pol["sink_ceiling_bytes"]
    assert pol["guest_tee_cap_bytes"] > pol["output_cap_bytes"]


def test_journal_rotiert_bevor_es_die_quota_der_nachbarn_frisst(tmp_path):
    """The journal writes into the same ceiling the program uses to lay down files."""
    big = tmp_path / "stdout.log"
    big.write_bytes(b"x" * (cell_out.JOURNAL_MAX_BYTES + 1))
    assert cell_out.rotate_journal(big) is True
    assert not big.exists()
    small = tmp_path / "stderr.log"
    small.write_bytes(b"x" * 1024)
    assert cell_out.rotate_journal(small) is False
    assert small.exists()


def test_journal_groessen_stehen_zur_Session_Quota():
    """Two journals plus state and buffer must stay clearly under the total ceiling.

    The per-file ceiling was never the calculation here: the journals together already
    are half of it, and they are protected from eviction.
    """
    headroom = cell.DEFAULT_WORK_QUOTA_BYTES - 2 * cell_out.JOURNAL_MAX_BYTES
    assert headroom >= 8 * 1024 * 1024, "zu wenig Platz fuer state.pkl und pyc"
    assert 2 * cell_out.JOURNAL_MAX_BYTES < cell.DEFAULT_WORK_QUOTA_BYTES


def test_kernel_path_keeps_its_tail_too(monkeypatch):
    """Both deliveries cut at the cap — neither may cut off the end."""
    monkeypatch.setenv(cell.ENV_EXEC, cell.RUNTIME_KERNEL)
    out = _agent_code("print('K' * 30000)\nprint('Kernel-Ende')\n", session="kernel-tail")
    assert "Kernel-Ende" in out
    assert "characters not passed" in out
    assert len(out) < 30_000
