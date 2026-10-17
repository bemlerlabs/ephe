"""Guard: no test may leave a server it started holding the product port.

Measured 2026-10-08/09: a listener held ``127.0.0.1:8765`` for about 27 hours on the
developer's machine while nobody owned it. ``lsof`` named PID 79044, started
``Thu Oct 8 19:02:43 2026``, PPID 1 (orphaned), command line
``/path/to/python/bin/python /work/ephe/run_server.py --port 8765``,
and its environment carried ``EPHE_CONFIG_DIR``/``EPHE_WORKSPACE`` pointing into
``.../T/pytest-of-user/pytest-42/test_desktop_missing_toolchain0/`` — a test temporary
directory that had already been cleaned up. ``~/.ephe/logs/desktop-backend.log`` (the
file only ``ephe_cli._spawn_backend`` and the Tauri shell open) records
``Started server process [79044]`` under the banner ``No engine configured yet —
starting SETUP MODE``: the throwaway home has no ``engine.json``, so the server answered
every ``/api/health`` with a placeholder engine instead of the owner's
``~/.ephe/engine.json``. The Vite proxy on :5173 and ``app/src-tauri/src/backend.rs``
(PORT 8765, starts ``run_server.py`` when nothing listens) both talk to whatever owns
that port, so the desktop app, the PWA and two bench runs silently ran against a dead
test fixture.

The spawn path is the class, not the one test: ``_spawn_backend`` starts
``start_new_session=True`` — deliberately detached, because the product wants the
backend to outlive the CLI window — so the child survives its parent, reparents to
launchd, and inherits the pytest environment. Nothing in a test can undo that by
accident; the port has to be requested somewhere else.

Three rules decide an offender, and each one prints the PID, the start time, the
command line and the environment entry that proves it:

* **pytest home** — a listener on the guarded port whose ``EPHE_CONFIG_DIR``,
  ``EPHE_WORKSPACE``, ``EPHE_PERSONA_DIR`` or ``HOME`` names a test temporary directory.
  This rule needs no baseline, so it also catches a squatter a *previous* run left
  behind, which would otherwise block every later run silently.
* **appeared** — a listener that was not holding the port when the session started and
  whose environment does not resolve the developer's own configuration home. A server
  the developer starts by hand during a run is excluded here on purpose: on this machine
  the product server on :8765 is the normal state, and a guard that blamed it would be
  switched off within a week.
* **unreaped server child** — any process still running ``run_server.py`` whose
  environment names a test temporary directory, on *any* port. A test that moves to an
  ephemeral port and forgets to reap its child does not squat :8765, but it does leave a
  product server holding a deleted home; ``tests/test_engine_e2e_qwen.py`` shows the
  child exists for a second after a clean kill, which is why this rule re-checks before
  it reports.

Naming that last class was never enough to end it. Under ``-n 8`` on a loaded runner a
worker can be killed — xdist losing it, an OOM killer, a cancelled job — between its
``Popen`` and its ``finally``, so its detached child outlives the session and nothing on
the box owns it afterwards; the guard's advice to kill the PID only ever reached the human
reading the message, and the next run inherited the squatter. A fourth step therefore ends
the signature the suite's own children carry, and only that signature:
``reap_leaked_test_servers`` signals a process whose command line runs ``run_server.py``,
whose environment names a pytest temporary directory, and which still holds a listening
socket. A server out of the developer's login home carries no test home, a foreign listener
carries no product command line, and the guard's own falsification plants carry no bound
port, so all three are left standing.

``tests/conftest.py::_no_port_squatter_left_behind`` takes the baseline before the first
test and runs ``session_offenders`` when the session ends. The sweep runs on both sides of
that: once before the baseline, so residue a cancelled predecessor left is cleared before
this session is judged, and once before the report, so what the report names is what the
sweep could not end. The functions are importable, so the rules can be aimed at a listener
the file plants itself (``test_guard_flags_a_live_listener_that_was_not_there_before``).

The guarded port is the product port. ``EPHE_GUARDED_PORT`` moves it for the guard's own
falsification test, which cannot bind 8765 on a machine where the product server holds
it; no CI leg sets it, and ``test_the_guarded_port_is_the_product_default`` keeps the
default tied to ``run_server.py``.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.subprocess_env import hermetic_env

PRODUCT_PORT = 8765

#: Environment entries a test-started server inherits from tests/conftest.py.
_MARKER_VARS = ("EPHE_CONFIG_DIR", "EPHE_WORKSPACE", "EPHE_PERSONA_DIR", "HOME")

#: A pytest temporary root: ``<tmpdir>/pytest-of-<user>/pytest-<n>/<test><i>``.
_PYTEST_TMP = re.compile(r"pytest-of-|/pytest-\d")


def guarded_port() -> int:
    """The port this session is watched on — 8765 unless the guard's own test moved it."""
    override = (os.environ.get("EPHE_GUARDED_PORT") or "").strip()
    return int(override) if override else PRODUCT_PORT


def listening_pids(port: int) -> list[int] | None:
    """PIDs holding ``port`` in LISTEN, or None when this box has no ``lsof``.

    None is a degraded mechanism, never a pass: the caller says the port was open
    without naming a PID instead of pretending it was checked.
    """
    if shutil.which("lsof") is None:
        return None
    done = subprocess.run(  # noqa: S603 — fixed argv, port is an int
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    pids: list[int] = []
    for line in done.stdout.split():
        if line.isdigit() and int(line) not in pids:
            pids.append(int(line))
    return pids


def port_is_open(port: int) -> bool:
    """Connect probe — works where ``lsof`` does not exist, and names no PID."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _ps(args: list[str]) -> str:
    done = subprocess.run(  # noqa: S603 — fixed argv
        ["ps", *args], capture_output=True, text=True, timeout=20
    )
    return done.stdout.strip()


def process_command(pid: int) -> str:
    """``-ww`` because procps cuts a column at ``COLUMNS``, and a child started inside a
    pytest test sees ``COLUMNS=80`` although ``os.environ`` carries none. The runner's
    interpreter path is 84 characters, so an unwide ``args=`` answers ``…/arm64/bin/python``
    — no version, and no ``pytest`` word for the sibling-worker rule. Measured on
    ``lab-box`` 2026-10-10. BSD ps ignores ``COLUMNS`` at any width.
    """
    return _ps(["-ww", "-p", str(pid), "-o", "args="]) or "<unreadable>"


def process_start_time(pid: int) -> str:
    return _ps(["-p", str(pid), "-o", "lstart="]) or "<unknown>"


def process_env(pid: int) -> dict[str, str]:
    """Environment of a process: Linux reads ``/proc``, macOS prints it after ``eww``.

    macOS puts the environment behind the command line as space-separated ``K=V``
    tokens, so a value containing a space is not recoverable. Every path this guard keys
    on is a token of its own, so the coarse split is enough.
    """
    environ = Path(f"/proc/{pid}/environ")
    if environ.is_file():
        try:
            raw = environ.read_bytes().split(b"\0")
        except OSError:
            return {}
        entries = [entry.decode("utf-8", "replace") for entry in raw]
    else:
        entries = _ps(["eww", "-p", str(pid)]).split()
    out: dict[str, str] = {}
    for token in entries:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            key, _, value = token.partition("=")
            out[key] = value
    return out


def marks_a_test_home(env: dict[str, str]) -> str | None:
    """The environment entry that proves this process came out of a test, else None."""
    for var in _MARKER_VARS:
        value = env.get(var, "")
        if _PYTEST_TMP.search(value):
            return f"{var}={value}"
    return None


def is_the_developers_own_server(env: dict[str, str]) -> bool:
    """True when the process resolves the developer's real configuration home.

    The product server on :8765 is started deliberately and stays; its signature is the
    opposite of a test's — the login ``HOME`` and no ``EPHE_CONFIG_DIR`` (or exactly the
    real ``~/.ephe``). Anything else, an env without HOME included, is not a server
    somebody logged in and started by hand.
    """
    home = (env.get("HOME") or "").strip()
    if home != str(Path.home()):
        return False
    cfg = (env.get("EPHE_CONFIG_DIR") or "").strip()
    return not cfg or Path(cfg).expanduser() == Path(home) / ".ephe"


def describe(pid: int, reason: str, marker: str | None) -> str:
    return (
        f"    PID {pid}, started {process_start_time(pid)} — {reason}\n"
        f"      command: {process_command(pid)}\n"
        f"      proof:   {marker or '<no test-home marker in the environment>'}"
    )


def server_processes() -> list[int]:
    """PIDs whose command line runs ``run_server.py``, on any port.

    ``pgrep -f`` instead of a socket scan: a child that was started on an ephemeral port
    and never reaped is the same residue, and it is the failure mode a free-port test
    still has. Returns [] when this box has no pgrep.
    """
    if shutil.which("pgrep") is None:
        return []
    done = subprocess.run(  # noqa: S603 — fixed argv
        ["pgrep", "-f", "run_server.py"], capture_output=True, text=True, timeout=20
    )
    return [int(token) for token in done.stdout.split() if token.isdigit()]


#: One residue the session left behind: (pid, why it is a residue, env proof).
_Candidate = tuple[int, str, str | None]

#: A SIGTERM'd server child does not vanish with its test: measured 2026-10-09 it was
#: still alive 1 s after the session ended serially (gone at 2 s) and still alive 1 s
#: after an xdist worker's session ended under ``-n auto``, without having leaked. A
#: candidate therefore has to survive the whole settle window to count, and that window
#: is only paid for when something lingered.
_GRACE_SECONDS = 5.0
_GRACE_STEP = 0.5

#: The window the two window-subject tests wait through, measured on the same shape the
#: guard judges: a SIGTERM'd ``ephe start`` server child was alive 0.01-0.25 s after its
#: group signal and gone by 0.25 s (py3.12 and py3.13 tool-cache builds, 2026-10-10), and
#: the note above puts the session-end case at "gone at 2 s". Used only where the window
#: itself is the thing under test — widening the ordinary rule calls to this did NOT fix
#: the cross-worker red: with the settle window on and the claim scoped back out, 4 of 8
#: runs on py3.12 went red again (2026-10-10, lab-box, measured against a red neighbour
#: in the same table). The rules answer for the instant they are asked about; the test
#: claims are what was wrong.
_ORPHAN_WINDOW_S = 2.0


def still_alive(pid: int) -> bool:
    """Whether ``pid`` is a process that can still act, or a corpse left in the table.

    ``ps`` answers for a zombie as readily as for a live process, and with ``args`` it
    answers ``<defunct>`` — measured on macOS 2026-10-15, where the state column reads ``Z``
    for the same PID. A child killed while its parent is inside the test that started it
    stays in the table until that parent reaps it, and a zombie holds no port: its
    descriptors are closed with it. Reading one as residue would name a squatter that cannot
    squat. The state column is the cheap half; the command line still decides for the rest.
    """
    if _ps(["-o", "stat=", "-p", str(pid)]).startswith("Z"):
        return False
    return process_command(pid) != "<unreadable>"


def _parent_of(pid: int) -> int | None:
    out = _ps(["-o", "ppid=", "-p", str(pid)])
    return int(out) if out.isdigit() else None


def is_another_runs_child(pid: int) -> bool:
    """True when a live pytest process other than this one still owns ``pid``.

    Only the ancestry is asked, never the process's own command line: a planted test
    child lives under a ``pytest-of-`` temporary directory, so its argv matches the word
    and the candidate would spare itself.

    Under ``-n auto`` a sibling worker can be inside the test that planted the server
    while this worker's session ends — measured 2026-10-09, before this filter existed
    one worker's own guard plant was reported as residue by three other workers. A
    process whose parent is gone is nobody's child any more; that is the state the
    27-hour squatter was in.
    """
    current = _parent_of(pid)
    seen = {pid}
    while current is not None and current > 1 and current not in seen:
        if current == os.getpid():
            return False
        seen.add(current)
        if "pytest" in process_command(current):
            return True
        current = _parent_of(current)
    return False


def _settle(candidates: list[_Candidate], grace: float) -> list[_Candidate]:
    """Drop every candidate that reaps itself inside the window; keep the residue."""
    alive = candidates
    deadline = time.monotonic() + grace
    while alive and time.monotonic() < deadline:
        time.sleep(_GRACE_STEP)
        alive = [item for item in alive if still_alive(item[0])]
    return alive


def session_offenders(
    port: int,
    baseline_pids: list[int],
    baseline_open: bool,
    grace: float = _GRACE_SECONDS,
) -> list[str]:
    """One block per residue that must not survive the session.

    A candidate is confirmed only if it is still there after ``grace``; sampling once
    would turn a child that is mid-shutdown into a flaky red.
    """
    candidates: list[_Candidate] = []

    def _claim(pid: int, reason: str, marker: str | None) -> None:
        if pid in {item[0] for item in candidates} or is_another_runs_child(pid):
            return
        candidates.append((pid, reason, marker))

    now = listening_pids(port)
    if now is None:
        if port_is_open(port) and not baseline_open:
            time.sleep(grace)
            if port_is_open(port):
                return [
                    f"    port {port} accepted connections at session end and did not at "
                    "session start, but lsof is not installed here, so no PID could be named"
                ]
        return []
    for pid in now:
        env = process_env(pid)
        marker = marks_a_test_home(env)
        if marker:
            _claim(
                pid,
                "left by a test — its environment names a pytest temporary "
                "directory on the product port",
                marker,
            )
        elif pid not in baseline_pids and not is_the_developers_own_server(env):
            _claim(
                pid,
                "was not listening on the product port when the session started and "
                "does not resolve the developer's configuration home",
                None,
            )

    for pid in server_processes():
        marker = marks_a_test_home(process_env(pid))
        if marker:
            _claim(
                pid,
                "runs the product server on a port the session never released; a "
                "detached child is only ever reaped by the test that started it",
                marker,
            )

    if not candidates:
        return []
    return [
        describe(pid, reason, marker) for pid, reason, marker in _settle(candidates, grace)
    ]


# The guard is tested against live processes: every rule gets a real listener.


#: The signature a leaked product server carries: the interpreter plus the file this suite
#: starts its servers from. ``server_processes`` scans with the loose ``pgrep -f`` a report
#: can afford; the sweep is allowed to signal only what this pattern names.
_RUN_SERVER_ARGV = re.compile(r"(?:^|\s)(?:\S*/)?run_server\.py(?:\s|$)")


def holds_a_listening_socket(pid: int) -> bool:
    """Whether ``pid`` itself holds a TCP socket in LISTEN, read from ``lsof``.

    Asked before anything is signalled, and the reason is this suite's own shape rather than
    politeness: under ``-n 8`` another worker can be inside a test that started a process
    named ``run_server.py`` under a pytest home, and this file's falsification plants are
    exactly that shape. A process that serves nothing holds no port either, so the report
    keeps it and the sweep leaves it alone.

    False when the box has no ``lsof``: the mechanism then degrades to naming residue, never
    to guessing at it.
    """
    if shutil.which("lsof") is None:
        return False
    done = subprocess.run(  # noqa: S603 — fixed argv, pid is an int
        ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return bool(done.stdout.split())


def is_a_leaked_test_server(pid: int) -> bool:
    """Whether ``pid`` is a product server a test started: both marks, and a port held.

    The two marks are the ones the suite cannot avoid leaving: the command line runs
    ``run_server.py`` and the environment carries a pytest temporary directory. Either one on
    its own is a weaker claim — the product server out of the login home runs the same file,
    and a plain listener in a test home is not a server at all — while the pair is what
    ``backend_factory`` in tests/test_engine_reuse_statement.py produces on every start.
    """
    if _RUN_SERVER_ARGV.search(process_command(pid)) is None:
        return False
    if marks_a_test_home(process_env(pid)) is None:
        return False
    return holds_a_listening_socket(pid)


def _end_process(pid: int, grace: float) -> bool:
    """SIGTERM, then SIGKILL once ``grace`` has passed; True when it is gone.

    Only ``pid`` is signalled, never its process group: a child started without
    ``start_new_session`` shares this worker's group, so a group signal would take the
    worker down together with the residue.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return not still_alive(pid)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not still_alive(pid):
            return True
        time.sleep(_GRACE_STEP)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not still_alive(pid):
            return True
        time.sleep(_GRACE_STEP)
    return not still_alive(pid)


def reap_leaked_test_servers(grace: float = _GRACE_SECONDS) -> list[int]:
    """End every process matching the leaked-server signature; return the PIDs signalled.

    Called by ``tests/conftest.py::_no_port_squatter_left_behind`` before the baseline and
    again before the session's report. The class it closes is the one no teardown reaches:
    a worker killed between its ``Popen`` and its ``finally`` leaves a detached child that
    reparents to launchd, and nothing on the box owns it afterwards. Measured across one
    day of local runs, killing such a child by hand only produced another leak in the next
    round, which is why this ends the class instead of naming it.

    Three filters keep the act as narrow as the report: the signature above, one bound
    listening socket, and ``is_another_runs_child`` — a live pytest ancestor means a sibling
    worker is inside the test that its child belongs to, and that child is not residue.

    A process that could not be ended is left out of the answer, so a caller can compare the
    return value against the report instead of taking the attempt for the outcome.
    """
    reaped: list[int] = []
    for pid in server_processes():
        if pid == os.getpid() or not is_a_leaked_test_server(pid):
            continue
        if is_another_runs_child(pid):
            continue
        if _end_process(pid, grace):
            reaped.append(pid)
    return reaped


def _developer_own_env() -> dict[str, str]:
    """The environment a hand-started product server carries: the login home, no test
    directory."""
    return hermetic_env(HOME=str(Path.home()), PATH=os.environ.get("PATH", ""))


def _foreign_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The shape a hermetic test helper builds: a fabricated HOME, nothing to do with a
    login session. Only the appeared rule can tell this from the developer's server.

    Built from scratch rather than from ``os.environ``, which carries this run's own
    ``EPHE_CONFIG_DIR`` and would mark every plant as residue before the rules run. The
    loader keys are the one part of the parent that crosses over: on the arm64 runner the
    plant is a shared-linked interpreter and dies at exec without them, exit 127,
    measured there on 2026-10-10.
    """
    env = hermetic_env(HOME="/tmp/ephe-hermetic-sandbox", PATH=os.environ.get("PATH", ""))
    env.update(extra or {})
    return env


_LISTENER_SCRIPT = (
    "import socket, time\n"
    "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
    "sock.bind(('127.0.0.1', 0))\n"
    "sock.listen(1)\n"
    "print(sock.getsockname()[1], flush=True)\n"
    "time.sleep(300)\n"
)


_SIBLING_SCRIPT = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'],\n"
    "                         start_new_session=True)\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(300)\n"
)

#: ``/proc/<pid>/environ`` of a child that has not finished ``execve`` reads empty:
#: measured on ``lab-box`` 2026-10-10, 64 of 150 immediate reads after ``Popen`` missed
#: the marker the test had just put in the child's environment. A guard that reads a
#: process this early decides on ``{}``, so the plant says ``ready`` before it is read.
_READY_SCRIPT = "import time\nprint('ready', flush=True)\ntime.sleep(30)\n"

#: A wrapper that starts a detached ``run_server.py`` child and exits at once, so the child
#: is orphaned (ppid 1) before it is judged — the state run 38046942987's macOS leg produced
#: for gw8's server, and the state the 27-hour squatter was in.
_ORPHANER_SCRIPT = (
    "import subprocess, sys\n"
    "child = subprocess.Popen([sys.executable, sys.argv[1]], start_new_session=True)\n"
    "print(child.pid, flush=True)\n"
)

#: Refuses the very signal the window waits for. A SIGTERM'd server child measured here died
#: 0.01-0.25 s after the group signal, so one that is still serving after 2 s is not shutting
#: down — it stayed. The sleep is bounded so a cleanup that misses the kill cannot leave an
#: orphan that outlives the session: at 300 s it reached the end-of-session port guard and
#: reddened the macOS leg once (run 38216295056), which is longer than any assertion here needs.
_STUBBORN_SCRIPT = (
    "import signal, time\n"
    "signal.signal(signal.SIGTERM, lambda *_: None)\n"
    "time.sleep(20)\n"
)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
    if proc.stdout is not None:
        proc.stdout.close()
    proc.wait(timeout=10)


@pytest.fixture
def planted_listener():
    """Starts a child that binds an ephemeral port, prints it, and never exits by itself.

    The plant is killed in the fixture's teardown — pytest runs it on the
    assertion-failure path too — and on an ephemeral port, because :8765 belongs to the
    developer's running product.
    """
    procs: list[subprocess.Popen] = []

    def _plant(env: dict[str, str]) -> tuple[int, subprocess.Popen]:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
            [sys.executable, "-c", _LISTENER_SCRIPT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        procs.append(proc)
        ready, _, _ = select.select([proc.stdout], [], [], 20)
        assert ready, "the planted listener never reported a port"
        line = proc.stdout.readline().strip()
        assert line.isdigit(), f"the plant reported {line!r}"
        return int(line), proc

    yield _plant
    for proc in procs:
        _kill_group(proc)


@pytest.fixture
def planted_script_listener():
    """The same residue in the shape the product server has: a file named
    ``run_server.py``, started detached, so only a process scan finds it."""
    procs: list[subprocess.Popen] = []

    def _plant(tmp_path: Path) -> tuple[int, subprocess.Popen]:
        script = tmp_path / "run_server.py"
        script.write_text(_LISTENER_SCRIPT, encoding="utf-8")
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
            [sys.executable, str(script)],
            env=_foreign_env(
                {"EPHE_CONFIG_DIR": "/tmp/pytest-of-dev/pytest-5/test_unreaped_child0/"
                                    "ephe-home"}
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        procs.append(proc)
        ready, _, _ = select.select([proc.stdout], [], [], 20)
        assert ready, "the planted server never reported a port"
        line = proc.stdout.readline().strip()
        assert line.isdigit(), f"the plant reported {line!r}"
        return int(line), proc

    yield _plant
    for proc in procs:
        _kill_group(proc)


def test_the_guarded_port_is_the_product_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The override must not drift the guard off the port that matters: the default is
    read from the same parser the product server starts with."""
    import run_server

    monkeypatch.delenv("EPHE_GUARDED_PORT", raising=False)
    default = run_server.build_parser().parse_args([]).port
    assert PRODUCT_PORT == 8765
    assert guarded_port() == default == PRODUCT_PORT
    monkeypatch.setenv("EPHE_GUARDED_PORT", "60001")
    assert guarded_port() == 60001


def _named_for(pid: int, offenders: list[str]) -> list[str]:
    """The report lines naming ``pid``.

    A per-test assertion may only be about its own plant: under ``-n auto`` the process table
    is shared with every other worker, and an orphan whose parent is already gone cannot be
    spared by the ancestry rule even when it is another test's live plant. Measured on
    ``lab-box`` 2026-10-10 — with the deliberate orphan of
    ``test_an_orphan_that_ignores_sigterm_is_named_despite_the_window`` alive in another
    worker, ``len(offenders) == 1`` went red for a plant that was itself reported correctly.
    The claim over the whole table is the session hook's job, and this form still catches a
    plant reported by two rules at once: that gives two lines here.
    """
    return [line for line in offenders if f"PID {pid}" in line]


def test_listening_pids_and_the_probe_find_a_real_listener(planted_listener) -> None:
    """The guard's eyes, before its judgements: lsof names the PID and the connect probe
    agrees. Both would return nothing if the argv were wrong."""
    port, proc = planted_listener(_foreign_env())
    assert proc.pid in listening_pids(port)
    assert port_is_open(port)


def test_unreaped_server_child_is_named_on_a_port_the_guard_does_not_watch(
    tmp_path, planted_script_listener
) -> None:
    """The free-port mistake: a test that moves off :8765 and still forgets to reap its
    child leaves a product server running against a deleted home. Only a process rule
    sees that, and it must not report the developer's own server while doing so."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        quiet_port = probe.getsockname()[1]

    port, proc = planted_script_listener(tmp_path)

    offenders = session_offenders(quiet_port, baseline_pids=[], baseline_open=False,
                                  grace=0.0)

    named = _named_for(proc.pid, offenders)
    assert len(named) == 1, offenders
    assert "port the session never released" in named[0]


def test_a_child_that_reaps_itself_is_not_residue(planted_listener) -> None:
    """The flake the settle window exists to prevent: a SIGTERM'd server child stays
    visible for roughly a second after its test ends, on a serial run and on an xdist
    worker alike (measured 2026-10-09, which is what turned a clean `-n auto` run red
    here). A child that disappears within the settle window was still shutting down."""
    import threading

    port, proc = planted_listener(_foreign_env())
    threading.Timer(1.0, lambda: _kill_group(proc)).start()

    assert _named_for(proc.pid, session_offenders(port, baseline_pids=[],
                                                  baseline_open=False, grace=3.0)) == []


def test_an_orphan_that_ignores_sigterm_is_named_despite_the_window(tmp_path) -> None:
    """The other half of the window, and the shape run 38046942987 actually produced: a
    detached ``run_server.py`` child whose parent is already gone. Nothing about the window
    may hide that — it is the residue the guard exists for — so the child here refuses
    SIGTERM and has to be named even though the ancestry filter is blind by construction.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        quiet_port = probe.getsockname()[1]

    server = tmp_path / "run_server.py"
    server.write_text(_STUBBORN_SCRIPT, encoding="utf-8")
    marker = "/tmp/pytest-of-dev/pytest-11/test_orphaned_server0/ephe"
    parent = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [sys.executable, "-c", _ORPHANER_SCRIPT, str(server)],
        env=_foreign_env({"EPHE_CONFIG_DIR": marker}),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    orphan: int | None = None
    try:
        ready, _, _ = select.select([parent.stdout], [], [], 20)
        assert ready, "the planted parent never reported its child"
        orphan = int(parent.stdout.readline().strip())
        assert parent.wait(timeout=20) == 0, "the parent must exit so the child is an orphan"

        offenders = session_offenders(quiet_port, baseline_pids=[], baseline_open=False,
                                      grace=_ORPHAN_WINDOW_S)
        named = _named_for(orphan, offenders)
        assert len(named) == 1, offenders
        assert "port the session never released" in named[0]
        assert f"EPHE_CONFIG_DIR={marker}" in named[0]
    finally:
        if orphan is not None:
            try:
                os.kill(orphan, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        _kill_group(parent)


def test_appeared_rule_names_a_listener_and_the_baseline_spares_it(
    planted_listener,
) -> None:
    """The baseline comparison in both directions: the same listener is an offender
    because it was not there at session start, and is not one when it was.

    The rule is asked at the instant it describes (``grace=0.0``), and each half judges only
    the plant this test started. What used to break this under ``-n auto`` was the exclusive
    claim over the table: run 38046942987's macOS leg reddened it on another worker's live
    ``run_server.py`` (gw8, PID 83182, orphaned to launchd so no ancestry filter can spare
    it), and the same shape reappears on py3.12 as two listeners answering for one port
    number — measured 2026-10-10, gw5's plant port also naming gw15's live server. Widening
    the grace instead of scoping the claim leaves that red: see ``_ORPHAN_WINDOW_S``."""
    port, proc = planted_listener(_foreign_env())

    offenders = session_offenders(port, baseline_pids=[], baseline_open=False, grace=0.0)
    named = _named_for(proc.pid, offenders)
    assert len(named) == 1, offenders
    assert "was not listening" in named[0]
    assert sys.executable in named[0], "the command line is not in the report"

    spared = session_offenders(port, [proc.pid], baseline_open=True, grace=0.0)
    assert _named_for(proc.pid, spared) == [], spared


def test_the_appeared_rule_does_not_blame_a_product_shaped_listener(
    planted_listener,
) -> None:
    """The exemption that keeps the guard usable on this machine: a listener carrying the
    login home is not test residue, even when the session did not see it at startup. A
    developer who starts ``run_server.py`` while the suite runs must not turn the suite
    red — measured, that is the normal state here, since the product server has held
    :8765 through every run of this guard."""
    port, proc = planted_listener(_developer_own_env())
    spared = session_offenders(port, baseline_pids=[], baseline_open=False, grace=0.0)
    assert _named_for(proc.pid, spared) == [], spared


def test_pytest_home_rule_names_a_squatter_that_predates_the_baseline(
    planted_listener,
) -> None:
    """The 27-hour case: a listener that was already holding the port when the session
    started is still an offender, because its environment names a pytest temporary
    directory. Only the baseline-independent rule catches that one."""
    marker_home = "/tmp/pytest-of-dev/pytest-7/test_desktop_missing_toolchain0/ephe-home"
    port, proc = planted_listener(_foreign_env({"EPHE_CONFIG_DIR": marker_home}))

    offenders = session_offenders(port, [proc.pid], baseline_open=True, grace=0.0)

    named = _named_for(proc.pid, offenders)
    assert len(named) == 1, offenders
    assert f"EPHE_CONFIG_DIR={marker_home}" in named[0]


def test_the_rules_separate_the_product_server_from_a_test_residue() -> None:
    """The two env shapes on the developer's machine, decided without a listener: the
    measured zombie signature against the hand-started server that must stay green."""
    tmp_root = os.environ.get("TMPDIR", "/tmp")
    zombie = {
        "HOME": str(Path.home()),
        "EPHE_CONFIG_DIR": f"{tmp_root}pytest-of-user/pytest-42/"
                           "test_desktop_missing_toolchain0/ephe-home",
        "EPHE_WORKSPACE": f"{tmp_root}pytest-of-user/pytest-42/"
                          "test_desktop_missing_toolchain0/ws-none",
    }
    assert marks_a_test_home(zombie).startswith("EPHE_CONFIG_DIR=")
    assert not is_the_developers_own_server(zombie)

    product = {"HOME": str(Path.home()), "PWD": str(Path.home())}
    assert is_the_developers_own_server(product)
    assert not marks_a_test_home(product)

    assert not is_the_developers_own_server({}), "an unreadable environment proves nothing"
    assert is_the_developers_own_server(
        {"HOME": str(Path.home()), "EPHE_CONFIG_DIR": str(Path.home() / ".ephe")}
    )


def test_a_sibling_workers_server_is_not_this_runs_residue(
    planted_listener,
) -> None:
    """The ``-n auto`` case. A worker that is inside its own server test while a
    different session ends must not be named by that session: measured 2026-10-09, before
    this filter existed, one worker's guard plant turned three other workers red. What
    outlives its parent — ancestry ending at launchd, the state PID 79044 was in for 27
    hours — is residue and has to be named."""
    sibling = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [sys.executable, "-c", _SIBLING_SCRIPT, "pytest-worker-stub"],
        env=_foreign_env(),
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    grandchild: int | None = None
    try:
        ready, _, _ = select.select([sibling.stdout], [], [], 20)
        assert ready, "the planted sibling worker never reported"
        grandchild = int(sibling.stdout.readline().strip())

        assert is_another_runs_child(grandchild) is True

        _port, ours = planted_listener(_foreign_env())
        assert is_another_runs_child(ours.pid) is False, (
            "a child of this run is this run's residue to report"
        )
    finally:
        if grandchild is not None:
            try:
                os.kill(grandchild, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        _kill_group(sibling)


def test_guard_reads_the_environment_and_command_line_of_a_live_process() -> None:
    """Both platform routes (Linux ``/proc``, macOS ``ps eww``) have to answer for a real
    PID, or every rule above is decided on an empty dictionary. The plant reports on
    stdout before it is read, for the reason written above ``_READY_SCRIPT``."""
    marker = "/tmp/pytest-of-dev/pytest-3/test_desktop_missing_toolchain0/ws-none"
    proc = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [sys.executable, "-c", _READY_SCRIPT],
        env=_foreign_env({"EPHE_WORKSPACE": marker}),
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        ready, _, _ = select.select([proc.stdout], [], [], 20)
        assert ready, "the planted process never reported"
        assert proc.stdout.readline().strip() == "ready"
        assert marks_a_test_home(process_env(proc.pid)) == f"EPHE_WORKSPACE={marker}"
        assert sys.executable in process_command(proc.pid)
        assert process_start_time(proc.pid) != "<unknown>"
    finally:
        _kill_group(proc)


def _wait_for(predicate, seconds: float) -> bool:
    """Poll ``predicate`` until it holds or ``seconds`` have passed."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


def _reported_port(path: Path) -> int:
    """The port a plant wrote to ``path``, or 0 while it has not bound one yet.

    A bound socket never reports port 0, so the sentinel cannot be mistaken for an answer.
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return 0
    return int(text) if text.isdigit() else 0


#: The server tests/test_engine_reuse_statement.py starts, as a stub with the same argv: a
#: relative ``run_server.py --port N --port-file P --host 127.0.0.1`` under the working
#: directory, whose body binds the port and writes the number it got to ``P``. Port 0 is the
#: honest request here: the number belongs to the kernel either way, and naming one in
#: advance only opens a window for a stranger to take it between the free-port probe and the
#: bind. Measured against run 38046942987's macOS leg, whose gw8 left
#: ``.venv/bin/python run_server.py --port 65066 --host 127.0.0.1`` serving with a
#: ``pytest-829/popen-gw8`` home in its environment.
_PORT_SERVER_SCRIPT = (
    "import socket, sys, time\n"
    "args = sys.argv[1:]\n"
    "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
    "sock.bind(('127.0.0.1', int(args[args.index('--port') + 1])))\n"
    "sock.listen(64)\n"
    "open(args[args.index('--port-file') + 1], 'w').write(str(sock.getsockname()[1]))\n"
    "time.sleep(300)\n"
)

#: The worker that gets SIGKILLed while its server serves. It starts the child detached and
#: then waits to be killed, so the kill lands between the spawn and any teardown of its own:
#: an exit no ``finally`` can answer. The child reparents to launchd, the state gw8's server
#: was found in and the state nothing on the box reaches afterwards.
_TORN_WORKER_SCRIPT = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, 'run_server.py', '--port', '0',\n"
    "                          '--port-file', sys.argv[2], '--host', '127.0.0.1'],\n"
    "                         start_new_session=True)\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(300)\n"
)


def test_a_torn_down_worker_leaves_a_server_the_sweep_ends(tmp_path) -> None:
    """Adverse: the worker is SIGKILLed, so the teardown its fixture wrote never runs.

    The plant is run 38046942987's leak on gw8 — ``run_server.py`` as a relative path under
    the working directory, an environment naming a ``pytest-829/popen-gw8`` home, the child
    detached and serving — and the parent dies by SIGKILL, the one signal a ``finally``
    cannot answer. What follows is not a report: the session sweeps the signature the
    suite's own children carry, and the port is quiet afterwards.

    The half that keeps the sweep from being a port-wide reaper: once the port is free, the
    same script under another name, carrying the same pytest home, is put on it, and the
    sweep is asked again. A listener whose command line is not the product's has to survive
    it and keep answering. A sibling worker's session can also end while this plant is up,
    and its sweep is box-wide by design, so the two claims about the plant's own state are
    made only while it is still there; the end state below holds either way.
    """
    (tmp_path / "run_server.py").write_text(_PORT_SERVER_SCRIPT, encoding="utf-8")
    (tmp_path / "foreign_listener.py").write_text(_PORT_SERVER_SCRIPT, encoding="utf-8")
    marker = "/tmp/pytest-of-dev/pytest-829/popen-gw8/test_the_two_starts_leave_the_0/ephe"
    port_file = tmp_path / "leak.port"
    worker = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [sys.executable, "-c", _TORN_WORKER_SCRIPT, "0", str(port_file)],
        cwd=tmp_path,
        env=_foreign_env({"EPHE_CONFIG_DIR": marker}),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    children: list[int] = []
    plants: list[subprocess.Popen] = [worker]
    try:
        ready, _, _ = select.select([worker.stdout], [], [], 20)
        assert ready, "the planted worker never reported its child"
        line = worker.stdout.readline().strip()
        assert line.isdigit(), f"the plant reported {line!r}"
        children.append(int(line))
        assert _wait_for(lambda: _reported_port(port_file) > 0, 30), (
            f"the planted server never bound: {port_file} stayed empty"
        )
        port = _reported_port(port_file)

        os.kill(worker.pid, signal.SIGKILL)
        assert worker.wait(timeout=20) == -signal.SIGKILL, "SIGKILL leaves no exit status"
        if still_alive(children[0]):
            assert _parent_of(children[0]) == 1, "an orphan is nobody's child any more"
            named = _named_for(children[0], session_offenders(port, [], False, grace=0.0))
            assert len(named) == 1, named
            assert f"EPHE_CONFIG_DIR={marker}" in named[0]

        reap_leaked_test_servers()
        assert not still_alive(children[0]), "a leaked product server survived the sweep"
        assert _wait_for(lambda: not port_is_open(port), 20), (
            "the port is still answering after the sweep"
        )

        foreign_file = tmp_path / "foreign.port"
        foreign = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
            [sys.executable, "foreign_listener.py", "--port", "0", "--port-file",
             str(foreign_file), "--host", "127.0.0.1"],
            cwd=tmp_path,
            env=_foreign_env({"EPHE_CONFIG_DIR": marker}),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        plants.append(foreign)
        assert _wait_for(lambda: _reported_port(foreign_file) > 0, 30), (
            f"the planted foreign listener never bound: {foreign_file} stayed empty"
        )
        foreign_port = _reported_port(foreign_file)

        assert foreign.pid not in reap_leaked_test_servers()
        assert still_alive(foreign.pid), "a listener that is not the product server was ended"
        assert port_is_open(foreign_port), "the foreign listener stopped answering"
    finally:
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        for proc in plants:
            _kill_group(proc)


def test_the_sweep_leaves_the_owners_server_alone(tmp_path) -> None:
    """One command line, two homes, and only the test's home may be signalled.

    The developer's own product server has held :8765 through every run of this guard, and a
    sweep that went by ``run_server.py`` alone would end the server they are working against
    — which is how a guard gets switched off. Both plants run the same script with the same
    argv here; ``_foreign_env`` against ``_developer_own_env`` is the whole difference, and
    the leak is in the call so an empty result cannot pass for the mechanism working.
    """
    leak_dir = tmp_path / "leak"
    own_dir = tmp_path / "owner"
    for directory in (leak_dir, own_dir):
        directory.mkdir()
        (directory / "run_server.py").write_text(_PORT_SERVER_SCRIPT, encoding="utf-8")

    argv = [sys.executable, "run_server.py", "--port", "0", "--host", "127.0.0.1"]
    leaked = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [*argv, "--port-file", str(tmp_path / "leak.port")],
        cwd=leak_dir,
        env=_foreign_env({"EPHE_CONFIG_DIR": "/tmp/pytest-of-dev/pytest-829/popen-gw8/leak0/e"}),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    owner = subprocess.Popen(  # noqa: S603 — fixed argv, this file's own plant
        [*argv, "--port-file", str(tmp_path / "owner.port")],
        cwd=own_dir,
        env=_developer_own_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert _wait_for(
            lambda: _reported_port(tmp_path / "leak.port") > 0
            and _reported_port(tmp_path / "owner.port") > 0,
            30,
        ), "the planted servers never bound"
        own_port = _reported_port(tmp_path / "owner.port")

        reaped = reap_leaked_test_servers()

        assert leaked.pid in reaped, "the test home is what the sweep owns"
        assert owner.pid not in reaped, "a server out of the login home is not test residue"
        assert not still_alive(leaked.pid)
        assert still_alive(owner.pid), "the developer's own server was ended"
        assert port_is_open(own_port), "the developer's own server stopped answering"
    finally:
        _kill_group(leaked)
        _kill_group(owner)
