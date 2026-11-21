"""Who owns the product port, and how it is given back.

The owner's sentence — "the PWA may not be running or reachable when I started
nothing" — needs three facts the product did not keep in one place before this
module: the pid a backend reports in ``/api/health``, the owner token it was
started with, and the process start time that makes a recycled pid harmless.
They live in ``~/.ephe/run/backend-<port>.json``, written by the server that
binds the port and read by ``ephe stop`` / ``ephe start``.

Two rules are the point of the file:

* **Nothing is killed that this installation cannot prove it started.** The
  pidfile is written with the server's own pid, owner token and process start
  time; a health answer whose ``pid``/``owner`` do not match that record is
  named and left alone. A recycled pid fails the start-time comparison.
* **A port that answers is never silently shared.** ``inspect_port`` separates
  our backend from a stale version, another checkout, an unowned Ephe backend,
  and a listener that is not Ephe at all. Only the first two ever reach
  ``--takeover``; a stranger is reported, never signalled.

The module is deliberately standard-library only and imports the device folder
lazily, so ``run_server.py`` can use it before FastAPI is loaded.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The variable the desktop shell and the server already share: it travels in
#: ``/api/health`` and proves which process started which backend.
OWNER_ENV = "EPHE_BACKEND_OWNER"

#: Where the pidfiles live inside the device folder (``~/.ephe`` by default).
PIDFILE_DIRNAME = "run"

#: Kinds of port state. ``OURS``/``STALE_VERSION`` can be proven with a pidfile;
#: ``UNOWNED_EPHE``/``FOREIGN_INSTALL`` speak Ephe but were not started by this
#: installation's current record; ``NOT_EPHE`` is a stranger.
NOT_RUNNING = "not_running"
DEAD_PIDFILE = "dead_pidfile"
LEFT_OVER = "left_over"
OURS = "ours"
STALE_VERSION = "stale_version"
UNOWNED_EPHE = "unowned_ephe"
FOREIGN_INSTALL = "foreign_install"
NOT_EPHE = "not_ephe"

_POLL_S = 0.05


def repo_root() -> Path:
    """The checkout this module belongs to (``core/`` is one level down)."""
    return Path(__file__).resolve().parents[1]


def _version() -> str:
    from core._version import __version__

    return __version__


def _api_contract() -> int:
    from core._version import API_CONTRACT

    return int(API_CONTRACT)


def config_root(config_dir: Path | str | None = None) -> Path:
    """The device folder: the explicit argument, else ``EPHE_CONFIG_DIR`` / ``~/.ephe``."""
    if config_dir is not None:
        return Path(config_dir)
    from core.engine_config import config_root as _root

    return Path(_root())


def pidfile_path(port: int, config_dir: Path | str | None = None) -> Path:
    """``<device>/run/backend-<port>.json`` — one record per port, never per checkout."""
    return config_root(config_dir) / PIDFILE_DIRNAME / f"backend-{int(port)}.json"


def new_owner_token(pid: int | None = None) -> str:
    """The shape the desktop shell already uses: ``<epoch-ns hex>-<pid hex>``."""
    return f"{time.time_ns():x}-{(int(pid) if pid else os.getpid()):x}"


def owner_pid(token: str) -> int | None:
    """The shell pid a token names, or None for an unlabelled token."""
    tail = token.rsplit("-", 1)[-1] if "-" in token else ""
    try:
        pid = int(tail, 16)
    except ValueError:
        return None
    return pid if pid > 1 else None


def process_start_time(pid: int) -> str:
    """The kernel's start stamp for ``pid`` — the fact a pid alone cannot carry.

    Returns "" where ``ps`` cannot answer. Both the writer and the reader of the
    pidfile run on the same host, so an empty value degrades to "no start-time
    check" rather than to a wrong one.
    """
    if pid <= 1:
        return ""
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, pid is an int
            ["ps", "-p", str(int(pid)), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def process_command(pid: int) -> str:
    if pid <= 1:
        return ""
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv
            ["ps", "-p", str(int(pid)), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def process_is_running(pid: int) -> bool:
    """Alive and not a zombie. A zombie holds no socket, so it is already gone here."""
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv
            ["ps", "-o", "stat=", "-p", str(int(pid))],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    stat = done.stdout.strip()
    if done.returncode != 0:
        return False
    return not stat.startswith("Z")


def listening(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    """A completed TCP handshake on the port. Any listener counts, Ephe or not."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(timeout)
            return probe.connect_ex((host, int(port))) == 0
    except OSError:
        return False


def listener_pids(port: int) -> list[int] | None:
    """PIDs holding ``port`` in LISTEN via ``lsof``, or None where lsof is absent."""
    import shutil

    if shutil.which("lsof") is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, port is an int
            ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    pids: list[int] = []
    for token in done.stdout.split():
        if token.isdigit() and int(token) not in pids:
            pids.append(int(token))
    return pids


def probe_health(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> dict[str, Any] | None:
    """``GET /api/health`` on loopback, through an opener that ignores proxy env."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{host}:{int(port)}/api/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — any answer that is not the document is "no statement"
        return None
    return payload if isinstance(payload, dict) else None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def looks_like_ephe(health: dict[str, Any] | None) -> bool:
    """A health document this installation can reason about, old or new."""
    if not isinstance(health, dict):
        return False
    return _int(health.get("pid")) > 1 and bool(str(health.get("version") or "").strip())


def same_path(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except (OSError, RuntimeError, ValueError):
        return str(left) == str(right)


@dataclass(frozen=True)
class Pidfile:
    """The record a running server writes about itself."""

    pid: int
    port: int
    owner: str
    root: str
    version: str
    api_contract: int
    started_at: float
    start_time: str

    def to_json(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "port": self.port,
            "owner": self.owner,
            "root": self.root,
            "version": self.version,
            "api_contract": self.api_contract,
            "started_at": self.started_at,
            "start_time": self.start_time,
        }


def _parse_pidfile(payload: object) -> Pidfile | None:
    if not isinstance(payload, dict):
        return None
    pid = _int(payload.get("pid"))
    port = _int(payload.get("port"))
    if pid <= 1 or port <= 0:
        return None
    return Pidfile(
        pid=pid,
        port=port,
        owner=str(payload.get("owner") or ""),
        root=str(payload.get("root") or ""),
        version=str(payload.get("version") or ""),
        api_contract=_int(payload.get("api_contract")),
        started_at=float(payload.get("started_at") or 0.0),
        start_time=str(payload.get("start_time") or ""),
    )


def read_pidfile(port: int, config_dir: Path | str | None = None) -> Pidfile | None:
    try:
        payload = json.loads(pidfile_path(port, config_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_pidfile(payload)


def write_pidfile(
    port: int,
    *,
    pid: int,
    owner: str,
    root: str,
    version: str,
    api_contract: int,
    host: str = "127.0.0.1",
    config_dir: Path | str | None = None,
    started_at: float | None = None,
    start_time: str | None = None,
) -> Path:
    """Write the one record that makes this process stoppable, owner-only and atomically.

    A half-written file would read as "no record" at exactly the moment a stop
    needs one, so the bytes go through a temp name and a rename.
    """
    target = pidfile_path(port, config_dir)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = Pidfile(
        pid=int(pid),
        port=int(port),
        owner=owner,
        root=root,
        version=version,
        api_contract=int(api_contract),
        started_at=float(started_at if started_at is not None else time.time()),
        start_time=(
            start_time if start_time is not None else process_start_time(int(pid))
        ),
    )
    temp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record.to_json(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, target)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def remove_pidfile(port: int, *, pid: int | None = None, config_dir: Path | str | None = None) -> bool:
    """Remove the record, and only when it still names ``pid`` if one is given.

    A server that shut down must not delete the pidfile of the successor that
    already took the port over.
    """
    target = pidfile_path(port, config_dir)
    if pid is not None:
        record = read_pidfile(port, config_dir)
        if record is not None and record.pid != int(pid):
            return False
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


@dataclass(frozen=True)
class PortState:
    """Everything the lifecycle needs to know about one port, in one inspection."""

    port: int
    kind: str
    listening: bool
    health: dict[str, Any] | None
    pidfile: Pidfile | None
    pid: int
    owner: str
    root: str
    version: str
    api_contract: int
    start_time: str
    detail: str = ""

    @property
    def owned(self) -> bool:
        """True only when the pidfile and the health answer name the same live process."""
        pidfile = self.pidfile
        if pidfile is None or self.pid <= 1:
            return False
        if pidfile.pid != self.pid or pidfile.owner != self.owner:
            return False
        if pidfile.root and self.root and not same_path(pidfile.root, self.root):
            return False
        live_start = self.start_time or process_start_time(self.pid)
        if pidfile.start_time and live_start and pidfile.start_time != live_start:
            return False
        return True


def inspect_port(
    port: int,
    *,
    config_dir: Path | str | None = None,
    health_timeout: float = 5.0,
) -> PortState:
    """Classify the port without touching anything.

    The order matters: a listener is asked who it is before the pidfile is
    trusted, because a stale pidfile must never turn a stranger into "ours".
    """
    port = int(port)
    open_now = listening(port)
    pidfile = read_pidfile(port, config_dir)
    health = probe_health(port, timeout=health_timeout) if open_now else None
    our_root = str(repo_root())

    if open_now and not looks_like_ephe(health):
        pids = listener_pids(port)
        pid = pids[0] if pids else 0
        who = f"pid {pid}" if pid else "an unnamed process"
        return PortState(
            port=port, kind=NOT_EPHE, listening=True, health=health if isinstance(health, dict) else None,
            pidfile=pidfile, pid=pid, owner="", root="", version="", api_contract=0,
            start_time=process_start_time(pid) if pid else "",
            detail=f"port {port} is held by {who} that does not answer /api/health as Ephe",
        )

    if health is not None:
        pid = _int(health.get("pid"))
        owner = str(health.get("owner") or "")
        root = str(health.get("root") or "")
        version = str(health.get("version") or "")
        contract = _int(health.get("api_contract"))
        state = PortState(
            port=port, kind=OURS, listening=True, health=health, pidfile=pidfile, pid=pid,
            owner=owner, root=root, version=version, api_contract=contract,
            start_time=process_start_time(pid),
        )
        if state.owned:
            if contract == _api_contract() and same_path(root, our_root):
                return state
            if same_path(root, our_root):
                return PortState(**{**state.__dict__, "kind": STALE_VERSION})
            return PortState(**{**state.__dict__, "kind": FOREIGN_INSTALL})
        if root and same_path(root, our_root):
            return PortState(**{**state.__dict__, "kind": UNOWNED_EPHE})
        return PortState(**{**state.__dict__, "kind": FOREIGN_INSTALL})

    if pidfile is not None:
        if (
            process_is_running(pidfile.pid)
            and "run_server.py" in process_command(pidfile.pid)
            and (
                not pidfile.start_time
                or pidfile.start_time == process_start_time(pidfile.pid)
            )
        ):
            return PortState(
                port=port, kind=LEFT_OVER, listening=False, health=None, pidfile=pidfile,
                pid=pidfile.pid, owner=pidfile.owner, root=pidfile.root,
                version=pidfile.version, api_contract=pidfile.api_contract,
                start_time=pidfile.start_time,
                detail=f"pid {pidfile.pid} from the pidfile is alive but not listening",
            )
        return PortState(
            port=port, kind=DEAD_PIDFILE, listening=False, health=None, pidfile=pidfile,
            pid=pidfile.pid, owner=pidfile.owner, root=pidfile.root,
            version=pidfile.version, api_contract=pidfile.api_contract,
            start_time=pidfile.start_time,
            detail=f"pid {pidfile.pid} from the pidfile is gone",
        )

    return PortState(
        port=port, kind=NOT_RUNNING, listening=False, health=None, pidfile=None, pid=0,
        owner="", root="", version="", api_contract=0, start_time="",
    )


@dataclass(frozen=True)
class StopResult:
    exit_code: int
    status: str
    message: str
    pid: int = 0


@dataclass(frozen=True)
class StartDecision:
    allowed: bool
    reused: bool
    stopped: bool
    status: str
    message: str
    pid: int = 0


def _still_same_process(pid: int, expected_start: str) -> bool:
    if not process_is_running(pid):
        return False
    if expected_start:
        live = process_start_time(pid)
        if live and live != expected_start:
            return False
    return True


def _terminate(
    pid: int,
    port: int,
    *,
    expected_start: str = "",
    term_timeout: float = 5.0,
    kill_timeout: float = 3.0,
) -> tuple[bool, str]:
    """SIGTERM, wait, SIGKILL, wait, then verify the port. The FIFO the brief asks for."""
    if pid <= 1:
        return False, "no pid to stop"
    if not _still_same_process(pid, expected_start):
        return (not listening(port)), f"pid {pid} was already gone"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + term_timeout
    while time.monotonic() < deadline:
        if not process_is_running(pid):
            break
        time.sleep(_POLL_S)
    if process_is_running(pid):
        if not _still_same_process(pid, expected_start):
            return (not listening(port)), f"pid {pid} changed identity before SIGKILL"
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + kill_timeout
        while time.monotonic() < deadline:
            if not process_is_running(pid):
                break
            time.sleep(_POLL_S)
    if process_is_running(pid):
        return False, f"pid {pid} survived SIGTERM and SIGKILL"
    deadline = time.monotonic() + term_timeout
    while time.monotonic() < deadline:
        if not listening(port):
            return True, f"port {port} is free"
        time.sleep(_POLL_S)
    pids = listener_pids(port)
    holders = ", ".join(str(item) for item in pids) if pids else "an unnamed process"
    return False, (
        f"pid {pid} is gone but port {port} is still held by {holders}; "
        "that listener is not ours and was not signalled"
    )


def _refusal(state: PortState, *, takeover: bool = False) -> str:
    """The sentence for a port this installation may not take silently."""
    if state.kind == NOT_EPHE:
        pid = f"pid {state.pid}" if state.pid else "an unnamed process"
        return (
            f"port {state.port} is held by {pid} that is not an Ephe backend — "
            f"not killed. Find it with: lsof -nP -iTCP:{state.port} -sTCP:LISTEN"
        )
    root = state.root or "an unknown root"
    version = state.version or "unknown"
    pid = state.pid or "unknown"
    if state.kind == UNOWNED_EPHE:
        reason = (
            f"port {state.port} holds backend {version} (pid {pid}) without a pidfile "
            f"from this installation — not reused and not killed"
        )
    elif state.kind == FOREIGN_INSTALL:
        reason = (
            f"port {state.port} holds backend {version} (pid {pid}) from {root}, "
            f"another installation — not reused"
        )
    else:
        reason = (
            f"port {state.port} holds backend {version} (pid {pid}); this installation "
            f"is {_version()} — not reused"
        )
    if state.owned and state.kind == STALE_VERSION:
        return f"{reason}. Stop it with: ephe stop --port {state.port}"
    if takeover:
        return f"{reason}, and --takeover could not end it"
    return f"{reason}. Replace it with: ephe start --takeover"


def stop_backend(
    port: int,
    *,
    config_dir: Path | str | None = None,
    term_timeout: float = 5.0,
    kill_timeout: float = 3.0,
) -> StopResult:
    """`ephe stop`: end only the backend this installation recorded, then verify the port."""
    state = inspect_port(port, config_dir=config_dir)
    if state.kind == NOT_RUNNING:
        return StopResult(0, NOT_RUNNING, f"not running — nothing listening on port {port}")
    if state.kind == DEAD_PIDFILE:
        removed = remove_pidfile(port, config_dir=config_dir)
        suffix = " and removed its stale pidfile" if removed else ""
        return StopResult(0, NOT_RUNNING, f"not running — cleaned pid {state.pid}{suffix}", state.pid)
    if state.kind == LEFT_OVER:
        ok, detail = _terminate(
            state.pid, port, expected_start=state.start_time,
            term_timeout=term_timeout, kill_timeout=kill_timeout,
        )
        if ok:
            remove_pidfile(port, pid=state.pid, config_dir=config_dir)
            return StopResult(0, "stopped", f"stopped leftover backend pid {state.pid}; {detail}", state.pid)
        return StopResult(1, "failed", f"leftover backend pid {state.pid} did not stop: {detail}", state.pid)
    if state.owned:
        ok, detail = _terminate(
            state.pid, port, expected_start=state.start_time,
            term_timeout=term_timeout, kill_timeout=kill_timeout,
        )
        if ok:
            remove_pidfile(port, pid=state.pid, config_dir=config_dir)
            return StopResult(0, "stopped", f"stopped backend pid {state.pid}; {detail}", state.pid)
        return StopResult(1, "failed", f"backend pid {state.pid} did not stop: {detail}", state.pid)
    return StopResult(1, "refused", _refusal(state), state.pid)


def _take_over(
    state: PortState, *, term_timeout: float, kill_timeout: float
) -> tuple[bool, str]:
    """Replace an Ephe backend that is not ours — only after a second identity check."""
    fresh = probe_health(state.port)
    if not looks_like_ephe(fresh) or _int(fresh.get("pid")) != state.pid:
        return False, "the backend on the port changed before --takeover could act"
    ok, detail = _terminate(
        state.pid, state.port, expected_start=state.start_time,
        term_timeout=term_timeout, kill_timeout=kill_timeout,
    )
    if not ok:
        return False, detail
    remove_pidfile(state.port, pid=state.pid)
    return True, detail


def preflight_start(
    port: int,
    *,
    takeover: bool = False,
    config_dir: Path | str | None = None,
    term_timeout: float = 5.0,
    kill_timeout: float = 3.0,
) -> StartDecision:
    """What `ephe start` has to decide before it spawns anything."""
    state = inspect_port(port, config_dir=config_dir)
    if state.kind == NOT_RUNNING:
        return StartDecision(True, False, False, "free", f"port {port} is free")
    if state.kind == DEAD_PIDFILE:
        removed = remove_pidfile(port, config_dir=config_dir)
        detail = f"removed stale pidfile for pid {state.pid}" if removed else "stale pidfile found"
        return StartDecision(True, False, False, "cleaned", f"port {port} is free; {detail}")
    if state.kind == LEFT_OVER:
        ok, detail = _terminate(
            state.pid, port, expected_start=state.start_time,
            term_timeout=term_timeout, kill_timeout=kill_timeout,
        )
        if ok:
            remove_pidfile(port, pid=state.pid, config_dir=config_dir)
            return StartDecision(
                True, False, True, "left_over_stopped",
                f"stopped leftover backend pid {state.pid} that was not listening; {detail}",
            )
        return StartDecision(False, False, False, "left_over_failed",
                             f"leftover backend pid {state.pid} could not be stopped: {detail}")
    if state.kind == OURS:
        return StartDecision(
            True, True, False, "reused",
            f"already running — pid {state.pid}, version {state.version}; "
            f"port {port} is served by this installation",
        )
    if state.kind == NOT_EPHE:
        return StartDecision(False, False, False, NOT_EPHE, _refusal(state))
    if not takeover:
        return StartDecision(False, False, False, state.kind, _refusal(state))
    ok, detail = _take_over(state, term_timeout=term_timeout, kill_timeout=kill_timeout)
    if ok:
        return StartDecision(
            True, False, True, "taken_over",
            f"stopped {state.version or 'unknown'} backend pid {state.pid} on port {port}; {detail}",
        )
    return StartDecision(False, False, False, "takeover_failed",
                         f"{_refusal(state, takeover=True)}: {detail}")
