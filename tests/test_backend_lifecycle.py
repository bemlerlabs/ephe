"""The port promise: nothing is reachable unless this installation started it.

Measured on 2026-11-10: three ``run_server.py`` processes held :8765 at once and a
test fixture's detached child outlived every run that could have reaped it. The
owner's sentence — "the PWA may not be running or reachable when I started
nothing" — is therefore not a convention but a lifecycle:

* ``ephe stop`` ends the backend this installation wrote into
  ``~/.ephe/run/backend-<port>.json`` and verifies the port afterwards. It is
  idempotent and never signals a process the pidfile/health pair does not name.
* ``ephe start`` inspects the port first. A backend from another checkout or
  version is named and refused, not silently replaced by a second server on the
  next port; ``--takeover`` is the explicit permission to end it.
* the server writes its pid, owner token and process start time into the pidfile
  at start, removes it on a graceful exit, and leaves it behind on SIGKILL so the
  next start can recognise the orphan.

Every test uses an ephemeral port. :8765 belongs to whatever the developer is
running by hand, and the suite's own port-squatter guard watches it.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait(predicate, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


def _health(port: int) -> dict | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _cli_env(home: Path, config: Path) -> dict[str, str]:
    return hermetic_env(
        HOME=str(home),
        EPHE_CONFIG_DIR=str(config),
        PATH=os.environ.get("PATH", ""),
        PYTHONPATH=str(ROOT),
    )


def _run_cli(*args: str, env: dict[str, str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(ROOT / "ephe_cli.py"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _pidfile(config: Path, port: int) -> Path:
    return config / "run" / f"backend-{port}.json"


#: A backend-shaped child: answers /api/health with its own pid and the version
#: the test says, and dies on SIGTERM. It is not the product server; it exists to
#: put a *named* backend on a port without paying the full import price.
_STUB_BACKEND = """
import json, os, signal, socket, sys, threading

port, version, root, contract = (
    int(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
)
owner = os.environ.get("EPHE_BACKEND_OWNER", "")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen(16)


def answer(conn):
    try:
        conn.recv(4096)
        body = json.dumps({
            "status": "ok",
            "version": version,
            "api_contract": contract,
            "pid": os.getpid(),
            "root": root,
            "owner": owner,
            "instance_id": "stub",
            "engine_key_challenge": False,
        }).encode()
        conn.sendall(
            b"HTTP/1.1 200 OK\\r\\ncontent-type: application/json\\r\\n"
            b"content-length: " + str(len(body)).encode()
            + b"\\r\\nconnection: close\\r\\n\\r\\n" + body
        )
    except OSError:
        pass
    finally:
        conn.close()


if os.environ.get("STUB_IGNORE_TERM") == "1":
    signal.signal(signal.SIGTERM, lambda *_: None)
else:
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
print("ready", flush=True)
while True:
    conn, _ = sock.accept()
    threading.Thread(target=answer, args=(conn,), daemon=True).start()
"""

#: A listener that is not Ephe at all: it accepts and never answers.
_FOREIGN_LISTENER = """
import os, signal, socket, sys, time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", int(sys.argv[1])))
sock.listen(16)
signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
print("ready", flush=True)
while True:
    conn, _ = sock.accept()
    time.sleep(1)
"""


def _spawn_stub(tmp_path: Path, port: int, *, version: str, root: str,
                contract: int = 1, owner: str = "",
                ignore_term: bool = False) -> subprocess.Popen:
    script = tmp_path / "stub_backend.py"
    script.write_text(_STUB_BACKEND, encoding="utf-8")
    env = _cli_env(tmp_path, tmp_path / "cfg")
    env["EPHE_BACKEND_OWNER"] = owner
    if ignore_term:
        env["STUB_IGNORE_TERM"] = "1"
    proc = subprocess.Popen(
        [PYTHON, str(script), str(port), version, root, str(contract)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    assert _wait(lambda: _health(port) is not None, 10), "the stub never answered health"
    return proc


def _spawn_foreign(tmp_path: Path, port: int) -> subprocess.Popen:
    script = tmp_path / "foreign_listener.py"
    script.write_text(_FOREIGN_LISTENER, encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, str(script), str(port)],
        cwd=tmp_path,
        env=_cli_env(tmp_path, tmp_path / "cfg"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    return proc


def _start_real_backend(tmp_path: Path, port: int) -> subprocess.Popen:
    """The product server itself, on an ephemeral port, for the end-to-end case."""
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    err = (tmp_path / "server.err").open("wb")
    proc = subprocess.Popen(
        [PYTHON, "run_server.py", "--port", str(port), "--host", "127.0.0.1"],
        cwd=ROOT,
        env=_cli_env(tmp_path, config),
        stdout=subprocess.DEVNULL,
        stderr=err,
        start_new_session=True,
    )
    assert _wait(lambda: _health(port) is not None, 60), (
        "the product server never answered /api/health"
    )
    return proc


def test_start_stop_frees_the_port_and_removes_the_pidfile(tmp_path: Path):
    """The end-to-end promise: start, stop, no health answer, no listener."""
    port = _free_port()
    proc = _start_real_backend(tmp_path, port)
    config = tmp_path / "cfg"
    health = _health(port)
    assert health is not None and health["pid"] == proc.pid

    pidfile = _pidfile(config, port)
    assert _wait(lambda: pidfile.is_file(), 10), "the server did not write its pidfile"
    payload = json.loads(pidfile.read_text(encoding="utf-8"))
    assert payload["pid"] == proc.pid
    assert payload["port"] == port
    assert payload["owner"] == health["owner"] != ""
    assert payload["start_time"], "a pid alone is not identity: the start time is missing"
    assert payload["api_contract"] == health["api_contract"]

    try:
        stopped = _run_cli("stop", "--port", str(port), env=_cli_env(tmp_path, config))
        assert stopped.returncode == 0, stopped.stderr + stopped.stdout
        assert _wait(lambda: proc.poll() is not None, 30), "the backend survived ephe stop"
        assert _wait(lambda: not _port_open(port), 20), "the port is still answering"
        assert _health(port) is None
        assert not pidfile.exists(), "a stopped backend left its pidfile behind"
    finally:
        _kill(proc)
        if proc.returncode is None:
            proc.wait(timeout=10)


def test_stop_is_idempotent_when_nothing_is_running(tmp_path: Path):
    port = _free_port()
    config = tmp_path / "cfg"
    env = _cli_env(tmp_path, config)
    for _ in range(2):
        result = _run_cli("stop", "--port", str(port), env=env)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "not running" in result.stdout.lower()


def test_stop_leaves_a_foreign_process_on_the_port_alone(tmp_path: Path):
    """No health statement, no ownership: the process is named and left standing."""
    port = _free_port()
    foreign = _spawn_foreign(tmp_path, port)
    try:
        result = _run_cli("stop", "--port", str(port), env=_cli_env(tmp_path, tmp_path / "cfg"))
        assert result.returncode == 1, result.stdout + result.stderr
        assert "not" in result.stdout.lower() and "kill" in result.stdout.lower()
        assert foreign.poll() is None, "ephe stop killed a process it could not identify"
        assert _port_open(port), "the foreign listener stopped answering"
    finally:
        _kill(foreign)


def test_stop_does_not_kill_an_ephe_backend_without_our_pidfile(tmp_path: Path):
    """An old backend is named, never adopted. It has no pidfile this installation wrote."""
    port = _free_port()
    stub = _spawn_stub(tmp_path, port, version="0.5.7", root="/somewhere/else")
    try:
        result = _run_cli("stop", "--port", str(port), env=_cli_env(tmp_path, tmp_path / "cfg"))
        assert result.returncode == 1, result.stdout + result.stderr
        assert "0.5.7" in result.stdout or "0.5.7" in result.stderr
        assert stub.poll() is None, "a backend without our pidfile was killed by stop"
        assert _health(port) is not None
    finally:
        _kill(stub)


def test_stop_escalates_to_sigkill_when_sigterm_is_ignored(tmp_path: Path):
    """The FIFO half that keeps a wedged backend from holding the port forever."""
    from core.backend_lifecycle import stop_backend, write_pidfile

    port = _free_port()
    config = tmp_path / "cfg"
    stub = _spawn_stub(
        tmp_path, port, version="0.6.2", root=str(ROOT),
        owner="test-owner", ignore_term=True,
    )
    write_pidfile(
        port, pid=stub.pid, owner="test-owner", root=str(ROOT), version="0.6.2",
        api_contract=1, config_dir=config,
    )
    try:
        result = stop_backend(port, config_dir=config, term_timeout=0.5, kill_timeout=3.0)
        assert result.exit_code == 0, result.message
        assert result.status == "stopped", result.message
        assert _wait(lambda: stub.poll() is not None, 10), "SIGKILL did not end the backend"
        assert _wait(lambda: not _port_open(port), 10), "the port stayed held"
        assert not _pidfile(config, port).exists()
    finally:
        _kill(stub)


def test_a_dead_pidfile_is_recognised_as_stale_and_cleared(tmp_path: Path):
    """The file outlives a SIGKILLed backend; it may not block or impersonate the next start."""
    from core.backend_lifecycle import preflight_start

    port = _free_port()
    config = tmp_path / "cfg"
    (config / "run").mkdir(parents=True)
    dead = subprocess.Popen([PYTHON, "-c", "pass"])
    dead.wait(timeout=10)
    pidfile = _pidfile(config, port)
    pidfile.write_text(
        json.dumps({
            "pid": dead.pid,
            "port": port,
            "owner": "gone-1",
            "root": str(ROOT),
            "version": "0.0.0",
            "api_contract": 1,
            "started_at": time.time() - 60,
            "start_time": "gone",
        }),
        encoding="utf-8",
    )
    decision = preflight_start(port, config_dir=config)
    assert decision.allowed, decision.message
    assert decision.reused is False
    assert "stale" in decision.message.lower()
    assert not pidfile.exists(), "the stale pidfile survived the start inspection"


def test_start_names_a_backend_from_another_installation_and_takeover_ends_it(tmp_path: Path):
    """The measured 0.5.7-on-8765 state: named with both facts, refused, replaceable only on request."""
    from core.backend_lifecycle import preflight_start

    port = _free_port()
    config = tmp_path / "cfg"
    stub = _spawn_stub(tmp_path, port, version="0.5.7", root="/somewhere/else")
    env = _cli_env(tmp_path, config)
    try:
        refused = preflight_start(port, config_dir=config)
        assert not refused.allowed
        assert "0.5.7" in refused.message and str(stub.pid) in refused.message
        assert "--takeover" in refused.message
        assert stub.poll() is None

        taken = preflight_start(port, config_dir=config, takeover=True)
        assert taken.allowed, taken.message
        assert _wait(lambda: stub.poll() is not None, 20), "--takeover did not end the stale backend"
        assert _wait(lambda: not _port_open(port), 10), "the port stayed held after takeover"
    finally:
        _kill(stub)


def test_start_refuses_a_non_ephe_listener_even_with_takeover(tmp_path: Path):
    """--takeover may replace an Ephe backend; a stranger is reported instead."""
    from core.backend_lifecycle import preflight_start

    port = _free_port()
    config = tmp_path / "cfg"
    foreign = _spawn_foreign(tmp_path, port)
    try:
        refused = preflight_start(port, config_dir=config, takeover=True)
        assert not refused.allowed
        assert "not" in refused.message.lower()
        assert foreign.poll() is None, "a listener that is not Ephe was taken over"
        assert _port_open(port)
    finally:
        _kill(foreign)


def test_ephe_start_refuses_before_spawning_a_second_backend(tmp_path: Path, monkeypatch, capsys):
    """`ephe start` must not drift onto 8766 while an old backend keeps 8765."""
    import argparse

    import ephe_cli

    port = _free_port()
    config = tmp_path / "cfg"
    stub = _spawn_stub(tmp_path, port, version="0.5.7", root="/somewhere/else")
    spawned: list[list[str]] = []
    try:
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
        monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_: None)
        monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
        monkeypatch.setattr(ephe_cli, "_run", lambda *a, **k: spawned.append(a) or type(
            "Done", (), {"returncode": 0}
        )())
        args = argparse.Namespace(
            port=port, host="127.0.0.1", lan=False, model=None, skip_model_check=True,
            reload=False, open=False, takeover=False, command="start",
        )
        code = ephe_cli.cmd_start(args)
        out = capsys.readouterr().out
        assert code == 1
        assert "0.5.7" in out
        assert not spawned, "a second backend was started next to the stale one"
        assert stub.poll() is None
    finally:
        _kill(stub)


def test_ephe_start_takeover_replaces_the_stale_backend_and_spawns(tmp_path: Path, monkeypatch, capsys):
    import argparse

    import ephe_cli

    port = _free_port()
    config = tmp_path / "cfg"
    stub = _spawn_stub(tmp_path, port, version="0.5.7", root="/somewhere/else")
    spawned: list[list[str]] = []
    try:
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
        monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_: None)
        monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
        monkeypatch.setattr(
            ephe_cli, "_run",
            lambda *a, **k: spawned.append(a) or type("Done", (), {"returncode": 0})(),
        )
        args = argparse.Namespace(
            port=port, host="127.0.0.1", lan=False, model=None, skip_model_check=True,
            reload=False, open=False, takeover=True, command="start",
        )
        code = ephe_cli.cmd_start(args)
        capsys.readouterr()
        assert code == 0
        assert spawned, "--takeover did not reach the spawn"
        assert _wait(lambda: stub.poll() is not None, 20), "the stale backend survived --takeover"
    finally:
        _kill(stub)


def test_status_reports_not_running_then_running(tmp_path: Path):
    port = _free_port()
    config = tmp_path / "cfg"
    env = _cli_env(tmp_path, config)

    stopped = _run_cli("status", "--port", str(port), env=env)
    assert stopped.returncode == 1
    assert "not running" in stopped.stdout.lower()

    proc = _start_real_backend(tmp_path, port)
    try:
        assert _wait(lambda: _pidfile(config, port).is_file(), 10)
        running = _run_cli("status", "--port", str(port), env=env)
        assert running.returncode == 0, running.stdout + running.stderr
        assert "running" in running.stdout.lower()
        assert str(proc.pid) in running.stdout
    finally:
        _kill(proc)


def test_pidfile_is_owner_only_and_records_a_process_start_time(tmp_path: Path):
    from core.backend_lifecycle import process_start_time, read_pidfile, write_pidfile

    config = tmp_path / "cfg"
    path = write_pidfile(
        4242, pid=os.getpid(), owner="owner-1", root=str(ROOT), version="9.9.9",
        api_contract=7, host="127.0.0.1", config_dir=config,
    )
    assert path == _pidfile(config, 4242)
    assert (path.stat().st_mode & 0o777) == 0o600
    record = read_pidfile(4242, config_dir=config)
    assert record is not None
    assert record.pid == os.getpid() and record.owner == "owner-1"
    assert record.start_time == process_start_time(os.getpid())
    assert record.start_time, "the start time must be readable on this host"


def test_the_desktop_shell_stops_its_backend_and_its_pidfile_on_exit():
    """The shell's exit path is the same promise, in Rust: no child and no pidfile left."""
    backend = (ROOT / "app" / "src-tauri" / "src" / "backend.rs").read_text(encoding="utf-8")
    shell = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert 'join("run")' in backend and "backend-{port}.json" in backend, (
        "the desktop spawn does not know the backend pidfile"
    )
    assert "fn stop_backend" in backend
    stop_slice = backend[backend.index("fn stop_backend"):][:2000]
    assert "clear_pidfile" in stop_slice, (
        "stop_backend leaves the pidfile of the child it killed"
    )
    assert "fn clear_pidfile" in backend and "remove_file" in backend
    exit_branch = shell[shell.index("tauri::RunEvent::Exit"):][:800]
    assert "backend::stop_backend()" in exit_branch
