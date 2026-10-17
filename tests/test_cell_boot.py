"""Guest-side coverage for the CPython cell boot loader and its output tee.

`core/cell_boot.py` runs inside the WASI cell; only its refusal helper and the top-level
import ever executed, so the sandbox boot, both stream tees and every failure path were
unmeasured. These tests drive `main()` in-process with the module path constants pointed
at a private /work, and drive `_BoundedTee` directly for the branches a whole boot cannot
reach.
"""
from __future__ import annotations

import io
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import cell_boot


class _FailingSink:
    """A sink whose every write raises, so the tee's OSError branches are reachable."""

    def __init__(self):
        self.writes = 0

    def write(self, data):
        self.writes += 1
        raise OSError("sink gone")

    def flush(self):
        raise OSError("sink gone")


class _FailingJournal:
    """A log handle whose write and close raise, to drive the journal error branches."""

    def write(self, data):
        raise OSError("journal gone")

    def close(self):
        raise OSError("journal gone")


class _Stream:
    """A text stream good enough for the tee: one binary buffer and a flush.

    A real `io.TextIOWrapper` closes its buffer when the tee replaces it on `sys`, so a
    shim keeps the buffer alive across the boot and still hands `_wrap_stream` its `.buffer`.
    """

    def __init__(self, buf, fail_flush=False):
        self.buffer = buf
        self._fail_flush = fail_flush

    def write(self, text):
        return self.buffer.write(text.encode("utf-8"))

    def flush(self):
        if self._fail_flush:
            raise OSError("stream gone")


class _ScriptGlobals(dict):
    """Running the file as ``__main__`` re-executes the source, so its own ``/work``
    assignments would win over a monkeypatch on the module. This mapping drops those
    six writes and keeps the tmp paths, which is what lets the guard run off the host.
    """

    _PINNED = ("WORK", "PROGRAM", "STATE", "RESULT", "STDOUT_LOG", "STDERR_LOG")

    def __init__(self, work: Path):
        super().__init__(
            __name__="__main__",
            __builtins__=__builtins__,
            WORK=str(work),
            PROGRAM=str(work / "program.py"),
            STATE=str(work / "state.pkl"),
            RESULT=str(work / "result.json"),
            STDOUT_LOG=str(work / "stdout.log"),
            STDERR_LOG=str(work / "stderr.log"),
        )

    def __setitem__(self, key, value):
        if key in self._PINNED and dict.__contains__(self, key):
            return
        super().__setitem__(key, value)


@pytest.fixture
def cell(tmp_path, monkeypatch):
    """A private /work plus two in-memory streams the tests attach on demand.

    The module reads its path globals at call time, so pointing them at tmp_path keeps a
    run off the host. pytest's capture replaces `sys.stdout` at the start of the call
    phase, after fixtures run, so `_attach` binds the streams from inside the test body
    where nothing overwrites them again.
    """
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(cell_boot, "PROGRAM", str(work / "program.py"))
    monkeypatch.setattr(cell_boot, "STATE", str(work / "state.pkl"))
    monkeypatch.setattr(cell_boot, "RESULT", str(work / "result.json"))
    monkeypatch.setattr(cell_boot, "STDOUT_LOG", str(work / "stdout.log"))
    monkeypatch.setattr(cell_boot, "STDERR_LOG", str(work / "stderr.log"))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.delitem(sys.modules, "ephe_tools", raising=False)
    return SimpleNamespace(
        work=work, out_buf=io.BytesIO(), err_buf=io.BytesIO(), monkeypatch=monkeypatch,
    )


def _attach(cell) -> None:
    cell.monkeypatch.setattr(sys, "stdout", _Stream(cell.out_buf))
    cell.monkeypatch.setattr(sys, "stderr", _Stream(cell.err_buf))


def _run_boot(cell) -> dict:
    _attach(cell)
    cell_boot.main()
    sys.stdout.flush()
    sys.stderr.flush()
    cell.forwarded_stdout = cell.out_buf.getvalue()
    cell.forwarded_stderr = cell.err_buf.getvalue()
    target = cell.work / "result.json"
    cell.result = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    return cell.result


def _program(cell, source: str) -> None:
    (cell.work / "program.py").write_text(source, encoding="utf-8")


def test_the_boot_runs_the_program_and_names_its_variables(cell):
    """Only the names the program leaves behind reach result.json, measured from the run."""
    _program(cell, "x = 1\nprint('hello from the cell')\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == ["x"]
    assert result["dropped"] == []
    assert "hello from the cell" in cell.forwarded_stdout.decode()
    assert result["stdout_bytes"] > 0
    assert result["stdout_log"] == str(cell.work / "stdout.log")


def test_the_boot_restores_the_namespace_from_the_previous_run(cell):
    """A carried variable has to be visible to the next program, or state.pkl is decoration."""
    # state.pkl is the boot's own format, so the test seeds the file the same run reads back.
    (cell.work / "state.pkl").write_bytes(pickle.dumps({"carried": 41}))
    _program(cell, "print(carried + 1)\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == ["carried"]
    assert "42" in cell.forwarded_stdout.decode()


def test_the_boot_writes_the_namespace_back_for_the_next_run(cell):
    _program(cell, "carried = 7\n")
    _run_boot(cell)
    assert pickle.loads((cell.work / "state.pkl").read_bytes()) == {"carried": 7}


def test_a_variable_that_does_not_pickle_is_dropped(cell):
    """A lock or a lambda must cost its own name, never the whole namespace."""
    _program(cell, "keep = 1\ndrop = lambda value: value\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == ["keep"]
    assert result["dropped"] == ["drop"]


def test_the_boot_installs_a_refusing_ephe_tools_module(cell):
    """The model's cell program that reaches a gated tool is answered with the refusal."""
    _program(cell, "import ephe_tools\nprint(ephe_tools.run_shell('ls'))\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert "not reachable from the cell" in cell.forwarded_stdout.decode()
    assert "ephe_tools" not in result["names"]


def test_the_ephe_tools_import_path_also_reaches_the_refusal(cell):
    _program(cell, "from ephe_tools import run_shell\nprint(run_shell())\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert "not reachable from the cell" in cell.forwarded_stdout.decode()


def test_the_refusal_module_hides_dunders_and_answers_every_name():
    module = cell_boot._make_ephe_tools()
    assert module.TOOL_NAMES == ()
    assert "not reachable from the cell" in module.run_shell("ls")
    assert "not reachable from the cell" in module.tool_call("browser")
    with pytest.raises(AttributeError):
        module.__wrapped__


def test_a_syntax_error_is_reported_without_running_the_program(cell):
    """A program that will not compile must answer with a status, measured on the tee'd stderr."""
    _program(cell, "def broken(:\n")
    result = _run_boot(cell)
    assert result["status"] == "syntax-error"
    assert result["names"] == []
    assert "SyntaxError" in cell.forwarded_stderr.decode()


def test_a_missing_program_is_an_io_error(cell):
    result = _run_boot(cell)
    assert result["status"] == "io-error"
    assert "cannot be read" in cell.forwarded_stderr.decode()


def test_sys_exit_without_a_code_is_ok(cell):
    _program(cell, "import sys\nsys.exit(0)\n")
    assert _run_boot(cell)["status"] == "ok"


def test_a_nonzero_sys_exit_keeps_the_code(cell):
    _program(cell, "import sys\nsys.exit(3)\n")
    assert _run_boot(cell)["status"] == "exit:3"


def test_an_exception_becomes_an_error_with_a_traceback(cell):
    _program(cell, "raise ValueError('boom')\n")
    result = _run_boot(cell)
    assert result["status"] == "error"
    assert "ValueError" in cell.forwarded_stderr.decode()


def test_a_damaged_state_reads_as_empty_and_reaches_the_journal(cell):
    """The damaged-state report must land in the append-only journal the host reads.

    A later run in the same session reads only the byte range this run appended, so a
    report printed before the streams are redirected stays invisible to the host.
    """
    (cell.work / "stderr.log").write_bytes(b"previous run\n")
    (cell.work / "state.pkl").write_bytes(b"\x80\x04 not a pickle")
    _program(cell, "print('fresh')\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == []
    journal = (cell.work / "stderr.log").read_text(encoding="utf-8")
    assert "unlesbar" in journal
    assert "previous run" in journal


def test_a_state_that_is_not_a_mapping_is_ignored(cell):
    (cell.work / "state.pkl").write_bytes(pickle.dumps([1, 2, 3]))
    _program(cell, "print('ok')\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == []


def test_an_unwritable_state_still_reports_the_output(cell, monkeypatch):
    monkeypatch.setattr(cell_boot, "STATE", str(cell.work / "missing" / "state.pkl"))
    _program(cell, "a = 1\nprint('done')\n")
    result = _run_boot(cell)
    assert result["status"] == "ok"
    assert result["names"] == []
    assert result["dropped"] == ["a"]
    assert "could not be written" in cell.forwarded_stderr.decode()
    assert "done" in cell.forwarded_stdout.decode()


def test_the_tee_lets_only_the_room_under_the_cap_through(tmp_path):
    inner = io.BytesIO()
    tee = cell_boot._BoundedTee(inner, str(tmp_path / "o.log"), 4, 0)
    assert tee.write(b"abcdefg") == 7
    assert tee.total_bytes == 7
    assert tee.forwarded_bytes == 4
    assert inner.getvalue() == b"abcd"
    tee.write(b"hi")
    assert inner.getvalue() == b"abcd"
    assert tee.total_bytes == 9


def test_the_tee_stops_the_journal_at_the_ceiling(tmp_path, monkeypatch):
    monkeypatch.setattr(cell_boot, "TEE_CAP_BYTES", 3)
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "o.log"), 10, 0)
    tee.write(b"abcdef")
    assert tee.log_bytes == 3
    assert (tmp_path / "o.log").read_bytes() == b"abc"
    tee.write(b"z")
    assert tee.log_bytes == 3


def test_a_broken_sink_latches_the_forward_cap(tmp_path):
    sink = _FailingSink()
    tee = cell_boot._BoundedTee(sink, str(tmp_path / "o.log"), 10, 0)
    assert tee.write(b"x") == 1
    assert tee.forwarded_bytes == 0
    assert tee.write(b"y") == 1
    assert sink.writes == 1


def test_an_unopenable_journal_leaves_the_run_alive(tmp_path):
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "gone" / "o.log"), 10, 0)
    assert tee.write(b"q") == 1
    assert tee.log_bytes == 0
    assert tee._log_fh is None


def test_a_journal_write_error_drops_the_handle(tmp_path):
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "o.log"), 10, 0)
    tee._log_fh = _FailingJournal()
    tee.write(b"q")
    assert tee._log_fh is None
    assert tee.log_bytes == 0


def test_the_tee_closes_its_journal(tmp_path):
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "o.log"), 10, 0)
    tee.write(b"a")
    assert tee._log_fh is not None
    tee.close()
    assert tee._log_fh is None


def test_closing_a_broken_journal_does_not_raise(tmp_path):
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "o.log"), 10, 0)
    tee._log_fh = _FailingJournal()
    tee.close()
    assert tee._log_fh is None


def test_a_broken_sink_flush_is_swallowed(tmp_path):
    tee = cell_boot._BoundedTee(_FailingSink(), str(tmp_path / "o.log"), 10, 0)
    tee.flush()


def test_write_through_bypasses_the_byte_count(tmp_path):
    inner = io.BytesIO()
    tee = cell_boot._BoundedTee(inner, str(tmp_path / "o.log"), 1, 0)
    tee.write_through("mark")
    assert inner.getvalue() == b"mark"
    assert tee.total_bytes == 0
    assert tee.forwarded_bytes == 0


def test_write_through_ignores_a_broken_channel(tmp_path):
    tee = cell_boot._BoundedTee(_FailingSink(), str(tmp_path / "o.log"), 1, 0)
    tee.write_through("mark")


def test_the_journal_start_is_the_existing_size(tmp_path):
    path = tmp_path / "o.log"
    assert cell_boot._journal_start(str(path)) == 0
    path.write_bytes(b"12345")
    assert cell_boot._journal_start(str(path)) == 5


def test_a_stream_without_a_buffer_is_left_alone(monkeypatch):
    stream = object()
    monkeypatch.setattr(sys, "stdout", stream)
    assert cell_boot._wrap_stream("stdout", "/tmp/whatever.log") is None
    assert sys.stdout is stream


def test_install_tees_wraps_both_streams(cell):
    _attach(cell)
    counters = cell_boot._install_tees()
    assert set(counters["tees"]) == {"stdout", "stderr"}
    assert isinstance(sys.stdout, io.TextIOWrapper)
    counters["tees"]["stdout"].write(b"tick")
    assert b"tick" in cell.out_buf.getvalue()


def test_stream_counts_names_every_field(tmp_path):
    tee = cell_boot._BoundedTee(io.BytesIO(), str(tmp_path / "o.log"), 4, 2)
    tee.write(b"abcdef")
    counts = cell_boot._stream_counts({"tees": {"stdout": tee}})
    assert counts["stdout_bytes"] == 6
    assert counts["stdout_forwarded_bytes"] == 4
    assert counts["stdout_log"] == str(tmp_path / "o.log")
    assert counts["stdout_log_start"] == 2
    assert counts["stdout_log_bytes"] == 6


def test_flush_tees_marks_a_complete_journal(cell):
    tee = cell_boot._BoundedTee(cell.out_buf, str(cell.work / "stdout.log"), 1, 0)
    tee.write(b"abc")
    cell_boot._flush_tees({"tees": {"stdout": tee}})
    assert b"vollstaendig" in cell.out_buf.getvalue()


def test_flush_tees_names_the_partial_range(cell, monkeypatch):
    monkeypatch.setattr(cell_boot, "TEE_CAP_BYTES", 2)
    tee = cell_boot._BoundedTee(cell.out_buf, str(cell.work / "stdout.log"), 1, 0)
    tee.write(b"abcde")
    cell_boot._flush_tees({"tees": {"stdout": tee}})
    marker = cell.out_buf.getvalue().decode()
    assert "5 Byte" in marker
    assert "gesichert" in marker


def test_flush_tees_stays_quiet_below_the_cap(cell):
    tee = cell_boot._BoundedTee(cell.out_buf, str(cell.work / "stdout.log"), 10, 0)
    tee.write(b"abc")
    cell_boot._flush_tees({"tees": {"stdout": tee}})
    assert b"uebergeben" not in cell.out_buf.getvalue()


def test_flush_tees_without_tees_does_nothing(cell):
    cell_boot._flush_tees({})


def test_flush_tees_survives_a_stream_that_will_not_flush(cell, monkeypatch):
    """A channel that refuses to flush must not tip the report the run already wrote."""
    monkeypatch.setattr(sys, "stdout", _Stream(cell.out_buf, fail_flush=True))
    cell_boot._flush_tees({})


def test_write_result_survives_an_unwritable_target(cell, monkeypatch):
    monkeypatch.setattr(cell_boot, "RESULT", str(cell.work / "missing" / "result.json"))
    cell_boot._write_result("ok", [], [])
    assert not (cell.work / "missing").exists()


def test_starting_the_file_as_a_script_runs_the_boot(tmp_path, monkeypatch):
    """The host launches the file itself, so the `__main__` guard is the only entry that
    matters and an import never reaches it; the source is executed as a script here."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "program.py").write_text("booted = True\nprint('script boot ok')\n", encoding="utf-8")
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", _Stream(out))
    monkeypatch.setattr(sys, "stderr", _Stream(io.BytesIO()))
    monkeypatch.setattr(sys, "argv", ["cell_boot.py"])
    monkeypatch.delitem(sys.modules, "ephe_tools", raising=False)
    source = Path(cell_boot.__file__).read_text(encoding="utf-8")
    exec(compile(source, cell_boot.__file__, "exec"), _ScriptGlobals(work))  # noqa: S102 — the run under test
    result = json.loads((work / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert result["names"] == ["booted"]
    assert "script boot ok" in out.getvalue().decode()


def test_a_whole_boot_over_a_broken_sink_keeps_the_report_and_journal(cell):
    """The sink dies mid-print the way the guest's fd wall does; the tee has to absorb
    it, so the run finishes ok and the journal holds every byte the sink never took."""
    sink = _FailingSink()
    cell.monkeypatch.setattr(sys, "stdout", _Stream(sink))
    cell.monkeypatch.setattr(sys, "stderr", _Stream(sink))
    _program(cell, "kept = 3\nprint('x' * 100)\n")
    cell_boot.main()
    result = json.loads((cell.work / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert result["names"] == ["kept"]
    assert result["stdout_bytes"] == 101
    assert result["stdout_forwarded_bytes"] == 0
    assert sink.writes >= 1
    assert "x" * 100 in (cell.work / "stdout.log").read_text(encoding="utf-8")
