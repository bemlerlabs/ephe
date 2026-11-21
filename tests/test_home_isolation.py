"""Guard: no test may write into the real home configuration directory.

Why this exists (measured 2026-10-08): the owner's real ``~/.ephe/subagent_history.json``
holds two records that no user ever ran — ``a3`` (role ``r``, task ``t``) and ``a1``
(task ``find it``), both started 2026-10-02T14:54:25. They come from a helper-subagent
test that ran without isolating the configuration directory, so
``core.subagent_history._persist()`` resolved ``~/.ephe`` and wrote the whole registry
there. Since wave R10 a helper run is a visible chat, so that junk now shows up in his
Helpers tab.

Isolation today rests on autouse fixtures in ``tests/conftest.py`` (``EPHE_CONFIG_DIR``,
hermetic sessions/audit/artifacts). That is fine until one test undoes it — a
``monkeypatch.delenv``, a direct ``os.environ[...]`` write, a ``reset_for_test(path)``
that leaks, or a writer that runs outside the fixture window (a post-turn thread, a
teardown, module import). None of those fail anything; they just quietly land in the
developer's home.

The guard therefore does not watch file timestamps (the owner's own backend on :8765
writes into ``~/.ephe`` while the suite runs, so a timestamp check would be flaky by
construction). It installs an **in-process tripwire on the write primitives** at import
time — collection happens before the first test runs — and watches every write whose
resolved destination is inside the real home directory.

This is a ratchet, not a hard wall, so the tripwire can live in the tree while old debt
is driven out. Its policy is recorded in ``tests/home-isolation-baseline.json`` and the
decision logic lives in ``scripts/home_isolation_gate.py`` (the same shape as
``.architecture-baseline.json`` and ``scripts/language-baseline.json``):

* a write by a test that is already recorded in the baseline is **tolerated and counted**
  (the test stays green, the write still reaches disk for that known debt);
* a write by any other test **fails immediately**, with that test's own name, wherever it
  lives in the suite, and the write never reaches disk;
* a test in the baseline may not write *more* times than recorded — exceeding the recorded
  count is a regression and fails.

The baseline may only ever shrink: ``scripts/home_isolation_gate.py --update`` refuses to
raise it, and refuses any shape (an absolute home path, an exemption key) that could hide
growth. Run the suite once with ``EPHE_HOME_ISOLATION_REPORT=<path>`` to record the current
offenders, then lower the baseline from that report.

Writes into a temporary configuration directory (what an isolated test does) are never
touched, so a clean suite passes.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import sys
from pathlib import Path

import pytest

import core.subagent_history as subagent_history

# the ratchet policy is owned by scripts/home_isolation_gate.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import home_isolation_gate as _gate  # noqa: E402  (path bootstrap above)

BASELINE_PATH = _REPO_ROOT / "tests" / "home-isolation-baseline.json"

#: The home configuration directory as it was when the suite started, i.e. before any
#: test could patch HOME or EPHE_CONFIG_DIR. ``None`` when EPHE_CONFIG_DIR is already
#: set for the whole run — then no test can resolve the real home through that env.
_REAL_HOME_CFG: Path | None = None
if not (os.environ.get("EPHE_CONFIG_DIR") or "").strip():
    _REAL_HOME_CFG = Path.home() / ".ephe"
else:
    # The process-wide env is already redirected, but ``~/.ephe`` is still reachable by
    # code that ignores EPHE_CONFIG_DIR. Guard that folder too, resolved from HOME.
    _REAL_HOME_CFG = Path(os.environ.get("HOME") or str(Path.home())) / ".ephe"

#: Recording mode: set ``EPHE_HOME_ISOLATION_REPORT`` and the guard never fails a test —
#: it only counts offenders so a full run can regenerate the baseline.
_RECORD_MODE = bool((os.environ.get("EPHE_HOME_ISOLATION_REPORT") or "").strip())

#: The committed baseline (test id -> tolerated write count), loaded once. A missing or
#: malformed file is not a pass: it becomes an empty tolerance, so every leak fails loudly
#: and the dedicated ratchet test below reports the real reason.
try:
    _BASELINE: dict[str, int] = _gate.load_baseline(BASELINE_PATH)
    _BASELINE_ERROR: str | None = None
except _gate.GateError as exc:
    _BASELINE = {}
    _BASELINE_ERROR = str(exc)

#: The test currently running, written by the autouse attribution fixture in conftest.py.
#: ``None`` outside a test body (module import, a detached thread) — those writes cannot
#: fail their own test and are collected under the un-attributed key.
_current: str | None = None

#: Writes counted per test id this run (both tolerated and, for the report, all of them).
_seen: dict[str, int] = {}
#: Un-attributed offenders (a write with no running test). These can never be baselined
#: by test id, so the ratchet test surfaces them as debt that must be isolated.
_unattributed: list[str] = []
#: Violation labels raised at write time; the guard's self-probes prune themselves out.
_violations: list[str] = []

#: The guard's own test id prefix — those tests write into the real home on purpose to
#: prove the tripwire works, so they always raise and never count as offenders.
_SELF_PREFIX = "tests/test_home_isolation.py::"


def _set_current(nodeid: str | None) -> None:
    """Called by the conftest attribution fixture before and after each test."""
    global _current
    _current = nodeid


def _under_real_home(target: object) -> bool:
    """True when ``target`` resolves inside the owner's home configuration directory."""
    if _REAL_HOME_CFG is None or target is None:
        return False
    if isinstance(target, int):  # an int target is a file descriptor
        return False
    try:
        resolved = Path(os.path.expanduser(str(target))).resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    home = _REAL_HOME_CFG.resolve()
    return resolved == home or home in resolved.parents


def _reject(target: object, writer: str) -> None:
    label = f"{target} (written by {writer})"
    node = _current

    # The guard proving itself: those writes must always raise, in either mode.
    if node is not None and node.startswith(_SELF_PREFIX):
        _violations.append(label)
        raise _fail(label)

    if node is None:
        # Not inside a test body: a collection-time import or a detached thread. We cannot
        # fail a test that is not running, so the write proceeds (guarded only by the
        # ratchet test) and is surfaced there — never silently dropped.
        _unattributed.append(label)
        return

    if _RECORD_MODE:
        _seen[node] = _seen.get(node, 0) + 1
        return

    budget = _BASELINE.get(node, 0)
    if _seen.get(node, 0) < budget:
        # Known, recorded debt: tolerate and count it, so the suite stays green while the
        # offender is driven out.
        _seen[node] = _seen.get(node, 0) + 1
        return

    _seen[node] = _seen.get(node, 0) + 1
    _violations.append(label)
    raise _fail(label)


def _fail(label: str) -> AssertionError:
    return AssertionError(
        "tests/test_home_isolation.py guard: a test wrote into the real home "
        f"configuration directory — {label}. Isolate the write instead: "
        "monkeypatch.setenv('EPHE_CONFIG_DIR', str(tmp_path)) for env-resolving "
        "writers, a work root in tmp_path for the cell suites (see "
        "tests/conftest.py::_hermetic_cell_work_dir), or monkeypatch the module "
        "attribute (e.g. core.subagent_history._path) for import-time-bound paths. "
        "If this offender is pre-existing debt, record it with "
        "scripts/home_isolation_gate.py --update — never by editing the guard."
    )


# tripwire on the write primitives (installed once, at import)
#
# Only writes are wrapped; reads pass through untouched. Every wrapper is a plain
# pass-through for any path outside the owner's home, so production code and pytest
# itself keep working unchanged.

_WRAPPED_FLAG = "_ephe_home_isolation_guard"

_real_write_text = Path.write_text
_real_write_bytes = Path.write_bytes
_real_touch = Path.touch
_real_unlink = Path.unlink
_real_replace = Path.replace
_real_open = builtins.open
_real_os_replace = os.replace
_real_os_rename = os.rename


def _guarded_write_text(self, data, *args, **kwargs):
    if _under_real_home(self):
        _reject(self, "Path.write_text")
    return _real_write_text(self, data, *args, **kwargs)


def _guarded_write_bytes(self, data, *args, **kwargs):
    if _under_real_home(self):
        _reject(self, "Path.write_bytes")
    return _real_write_bytes(self, data, *args, **kwargs)


def _guarded_touch(self, *args, **kwargs):
    if _under_real_home(self):
        _reject(self, "Path.touch")
    return _real_touch(self, *args, **kwargs)


def _guarded_unlink(self, *args, **kwargs):
    # Deleting a file in the owner's home is worse than writing one.
    if _under_real_home(self):
        _reject(self, "Path.unlink")
    return _real_unlink(self, *args, **kwargs)


def _guarded_replace(self, target, *args, **kwargs):
    if _under_real_home(target) or _under_real_home(self):
        _reject(target, "Path.replace")
    return _real_replace(self, target, *args, **kwargs)


def _guarded_os_replace(src, dst, *args, **kwargs):
    if _under_real_home(dst):
        _reject(dst, "os.replace")
    return _real_os_replace(src, dst, *args, **kwargs)


def _guarded_os_rename(src, dst, *args, **kwargs):
    if _under_real_home(dst):
        _reject(dst, "os.rename")
    return _real_os_rename(src, dst, *args, **kwargs)


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in str(mode) for flag in ("w", "a", "x", "+")) and _under_real_home(file):
        _reject(file, "open")
    return _real_open(file, mode, *args, **kwargs)


def _install_tripwire() -> None:
    """Patch the write primitives once per process (import can happen twice)."""
    if getattr(builtins, _WRAPPED_FLAG, False):
        return
    Path.write_text = _guarded_write_text  # type: ignore[method-assign]
    Path.write_bytes = _guarded_write_bytes  # type: ignore[method-assign]
    Path.touch = _guarded_touch  # type: ignore[method-assign]
    Path.unlink = _guarded_unlink  # type: ignore[method-assign]
    Path.replace = _guarded_replace  # type: ignore[method-assign]
    os.replace = _guarded_os_replace
    os.rename = _guarded_os_rename
    builtins.open = _guarded_open  # type: ignore[assignment]
    io.open = _guarded_open  # type: ignore[assignment]
    setattr(builtins, _WRAPPED_FLAG, True)


_install_tripwire()


def measured_offenders() -> dict[str, int]:
    """The offenders recorded this run, as the gate expects them: test id -> count.

    Only writes attributed to a real test are counted; the guard's own self-probes are
    not debt. Un-attributed writes are carried under the sentinel key so a recorded run
    never silently loses them (the gate refuses that key unless it is truly debt).
    """
    offenders = {node: hits for node, hits in _seen.items() if not node.startswith(_SELF_PREFIX)}
    if _unattributed:
        offenders["tests/UNATTRIBUTED::home-write"] = len(_unattributed)
    return offenders


def dump_report(path: Path) -> None:
    """Write the recorded offenders to ``path`` (called from conftest at session end)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(measured_offenders(), sort_keys=True, indent=1) + "\n", encoding="utf-8")


# the guard proves itself, both directions


def _expect_rejection(write) -> None:
    """Run ``write`` expecting the guard to refuse it, and keep the probe out of the
    violation log — the log is the evidence the last test reads, and these probes show
    the guard working rather than a test misbehaving."""
    start = len(_violations)
    with pytest.raises(AssertionError, match="home configuration directory"):
        write()
    assert len(_violations) > start, "the write raised, but not from this guard"
    del _violations[start:]


def test_guard_rejects_a_direct_write_into_the_real_home() -> None:
    """Failing direction: a plain write at the owner's home must raise, and the file
    must not exist afterwards — the guard protects the data, it does not only report."""
    victim = _REAL_HOME_CFG / "home_isolation_guard_probe.json"
    assert not victim.exists(), "probe target already exists — refusing to test over it"

    _expect_rejection(lambda: victim.write_text('{"probe": true}', encoding="utf-8"))

    assert not victim.exists(), "the guard reported the write but let it reach the disk"


def test_guard_blocks_open_in_a_write_mode_and_deletes_too() -> None:
    """Two other ways into the same folder: ``open(..., 'w')`` and ``unlink()``."""
    victim = _REAL_HOME_CFG / "home_isolation_guard_open.json"

    def _open_write() -> None:
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("{}")

    _expect_rejection(_open_write)
    assert not victim.exists()
    _expect_rejection(lambda: (_REAL_HOME_CFG / "subagent_history.json").unlink())


def test_guard_blocks_the_production_writer_once_isolation_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured defect, in its own shape: a test that drops the isolation the
    conftest fixtures provide (here: ``EPHE_CONFIG_DIR``) makes
    ``core.subagent_history._path()`` resolve the owner's ledger again. That write must
    raise and the file must stay byte-identical.

    Deliberately no call to ``_persist()`` itself — if the guard ever stopped working,
    that call would overwrite the owner's ledger with the test registry.
    """
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)
    ledger = _REAL_HOME_CFG / "subagent_history.json"
    assert subagent_history._path() == ledger, (
        "this guard only proves anything while the production writer really resolves "
        f"the home ledger, but it resolved {subagent_history._path()}"
    )
    before = ledger.read_bytes() if ledger.exists() else None

    _expect_rejection(lambda: Path(subagent_history._path()).write_text("[]", encoding="utf-8"))

    after = ledger.read_bytes() if ledger.exists() else None
    assert after == before, "the owner's subagent ledger changed during the guard test"


def test_guard_passes_a_write_into_an_isolated_config_dir(tmp_path: Path) -> None:
    """Passing direction: the same write primitives aimed at a per-test configuration
    directory are untouched, so an isolated suite stays green."""
    isolated = tmp_path / "ephe-home"
    isolated.mkdir()
    ledger = isolated / "subagent_history.json"
    ledger.write_text("[]", encoding="utf-8")
    ledger.touch()
    staging = isolated / "staging.json"
    staging.write_text('{"moved": true}', encoding="utf-8")
    staging.replace(ledger)
    payload = isolated / "payload.bin"
    payload.write_bytes(b"ok")
    os.replace(payload, isolated / "payload-moved.bin")
    assert ledger.read_text(encoding="utf-8") == '{"moved": true}'
    assert (isolated / "payload-moved.bin").read_bytes() == b"ok"


def test_guard_lets_reads_and_unrelated_paths_through(tmp_path: Path) -> None:
    """A write guard, and only that: reading the owner's ledger and
    writing anywhere else in the test's own tmp tree keeps working."""
    ledger = _REAL_HOME_CFG / "subagent_history.json"
    if ledger.exists():
        with open(ledger, "r", encoding="utf-8") as handle:
            assert handle.read().startswith("[")
    elsewhere = tmp_path / "nested" / "deep.txt"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text("fine", encoding="utf-8")
    assert elsewhere.read_text(encoding="utf-8") == "fine"


# the ratchet holds: recorded debt is bounded, nothing new slips silently


def test_the_committed_baseline_is_well_shaped() -> None:
    """The baseline file must exist and refuse any shape that could hide growth.

    A missing or malformed baseline raises a gate error, because a pass on nothing would
    let the guard silently tolerate everything. In recording mode this run is what *builds* the
    baseline, so the check is deferred to the enforcing run.
    """
    if _RECORD_MODE:
        pytest.skip("recording run: this run produces the baseline it would check")
    assert _BASELINE_ERROR is None, (
        f"tests/home-isolation-baseline.json cannot be loaded, so nothing is tolerated "
        f"and every leak fails: {_BASELINE_ERROR}"
    )


def test_no_unattributed_write_reached_the_real_home() -> None:
    """A write the guard could not attribute to a running test (a module import, a
    detached thread) can never be baselined by test id, so it is reported here instead
    of silently landing in the developer's home."""
    if _RECORD_MODE:
        pytest.skip("recording run: un-attributed writes are captured in the report")
    assert not _unattributed, (
        "writes reached the real home configuration directory outside any test body "
        "(import time or a detached thread); isolate their source: "
        + "; ".join(_unattributed)
    )
