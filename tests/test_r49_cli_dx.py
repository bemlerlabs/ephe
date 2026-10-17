"""
◑ Ephe – W4 S1: free-port selection + the --web alias.
tests/test_r49_cli_dx.py

RULE: the tests were written BEFORE the implementation.

Pins:
1. select_free_port: the default port 8765 taken → a port that is FREE and is NOT
   the requested one, inside the sequential retry window (never a hard-coded number).
2. select_free_port(0) → a positive ephemeral port.
3. Banner == EPHE_PORT env == the socket port actually bound, and that port is free
   and is not the requested one (subprocess proof: URL line, uvicorn kwarg and env
   all show the same, real port).
4. `ephe web` is an alias onto the start path (same flags, same func).
5. The probe binds loopback whatever host it is asked for: the wildcard belongs to
   the server's own bind, behind the opt-in that forces auth.
"""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(REPO / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: select_free_port retries base + offset for this many candidates (run_server.py).
#: A machine with every port in this window taken makes the server exit(1); nothing
#: about this test should depend on which offset inside it happens to be free.
RETRY_WINDOW = 20


def _port_is_free(host: str, port: int) -> bool:
    """True when a fresh socket can bind ``port`` right now.

    No SO_REUSEADDR: the point is to prove the returned port is idle *for this
    process*, and reuse semantics would accept a port still in TIME_WAIT.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _occupy(port: int) -> socket.socket | None:
    """Occupy a port; EADDRINUSE (e.g. from the already running server) satisfies the
    'port taken' precondition by itself — in that case None is returned.

    8765 is the subject here, not a careless choice: the pin is that the product default
    being busy moves the server on, and no other port proves that. The socket belongs to
    the pytest process and every caller closes it in a ``finally``.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError as exc:
        s.close()
        if exc.errno == 48:  # EADDRINUSE: precondition already met
            return None
        raise
    return s


def test_select_free_port_falls_back_to_a_free_port_when_default_busy():
    """8765 taken → the answer is the next free port, whatever number that is here.

    The runner may already hold 8766 as well (a second Ephe, another dev server),
    so the only portable assertions are the properties: not the requested port,
    actually free, and inside the retry window the implementation promises.
    """
    run_server = _load("run_server_r49", "run_server.py")
    busy = _occupy(8765)
    try:
        chosen = run_server.select_free_port("127.0.0.1", 8765)
        assert chosen != 8765, "8765 is occupied: returning it hands back a taken port"
        assert _port_is_free("127.0.0.1", chosen), f"{chosen} was returned as free but is not"
        assert 8765 < chosen < 8765 + RETRY_WINDOW, f"{chosen} is outside the retry window"
    finally:
        if busy is not None:
            busy.close()


def test_select_free_port_zero_returns_ephemeral():
    run_server = _load("run_server_r49b", "run_server.py")
    port = run_server.select_free_port("127.0.0.1", 0)
    assert isinstance(port, int) and port > 0


def test_the_probe_binds_loopback_whatever_host_is_asked_for(monkeypatch):
    """0.0.0.0 named → the probe still binds 127.0.0.1.

    A probe is not a service. The wildcard is reached by the server's own bind
    (`main` → uvicorn), where the --lan / --host 0.0.0.0 opt-in has already forced
    EPHE_LAN and the pairing token; the probe never opens one.
    """
    run_server = _load("run_server_r49c", "run_server.py")
    seen: list[tuple] = []

    class Recording(socket.socket):
        def bind(self, address):
            seen.append(address)
            return super().bind(address)

    monkeypatch.setattr(socket, "socket", Recording)
    port = run_server.select_free_port("0.0.0.0", 0)
    assert port > 0
    assert seen == [("127.0.0.1", 0)]


def test_banner_env_and_socket_agree_on_real_port():
    """With 8765 taken, the subprocess has to draw banner, uvicorn kwarg and EPHE_PORT
    all onto the same, actually-free port — and never onto the requested 8765.

    The port itself is read from the run: on a runner that also holds 8766 the correct
    answer is 8767, and a test that demanded 8766 would be asserting the machine is
    idle where the question is whether the code is right.
    """
    busy = _occupy(8765)
    probe = (
        "import json, os, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "sys.argv = ['run_server.py', '--port', '8765']\n"
        "import run_server, uvicorn\n"
        "captured = {}\n"
        "uvicorn.run = lambda app, **kw: captured.update(kw)\n"
        "run_server.main()\n"
        "print('CAP ' + json.dumps({'port': captured.get('port'), "
        "'env': os.environ.get('EPHE_PORT')}))\n"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", probe, str(REPO)],
            capture_output=True, text=True, timeout=60,
        )
        assert r.returncode == 0, r.stderr
        cap_line = [ln for ln in r.stdout.splitlines() if ln.startswith("CAP ")][-1]
        cap = json.loads(cap_line[len("CAP "):])
        url_line = [ln for ln in r.stdout.splitlines() if "URL:" in ln][0]
        banner_port = int(url_line.rsplit(":", 1)[-1])
        assert banner_port != 8765, "the banner names the requested port, not the one bound"
        assert cap["port"] == banner_port, "uvicorn binds a different port than the banner prints"
        assert cap["env"] == str(banner_port), "EPHE_PORT disagrees with the banner"
        assert _port_is_free("127.0.0.1", banner_port), f"banner port {banner_port} is not free"
        assert 8765 < banner_port < 8765 + RETRY_WINDOW
    finally:
        if busy is not None:
            busy.close()


def test_web_alias_parses_like_start():
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(
        ["web", "--port", "9101", "--host", "127.0.0.1", "--lan", "--open"]
    )
    assert args.func is ephe_cli.cmd_start
    assert args.port == 9101
    assert args.lan is True and args.open is True


def test_web_alias_in_help_and_completion():
    import ephe_cli

    help_text = ephe_cli.build_parser().format_help()
    assert "web" in help_text
    assert "web" in ephe_cli._completion_subcommands()
