"""Guard: a Playwright leg may not test a server it did not start, and may not leave one.

Measured on this machine 2026-10-11 against the three configs in `app/tests/playwright`
(that directory is another lane's write path tonight, so this file reads it and never runs
or edits it):

* `playwright.config.ts` used to start `python3 -m http.server 9199 --directory dist` with
  `reuseExistingServer: true`. Reproduced on an ephemeral port with a listener already on
  it that the leg did not start: Playwright never ran the command, the run was still green
  (`1 passed`), and the page the spec read back was the stranger's
  (`FOREIGN-SQUATTER-DIST`). The leg tested whoever owned the port. Fixed: the leg now
  picks a free port at run time and is exclusive, so it only ever tests a server it
  started. What is pinned here is the absence of a number — it declares no fixed port and
  reuses none — because a fixed number is one a stray server can hold.
* The holder on :9199 while this was measured is exactly that shape — PID 82841,
  `python3 -m http.server 9199 --directory dist`, PPID 1, started Sun Oct 11 01:13:57
  2026 out of `/work/ephe/app`, answering 200 text/html. An orphan of an earlier
  spec run that no teardown reaped, and the next `pnpm run test:e2e` was driven by it. This
  is the :8765 case of 2026-10-08 (`tests/test_port_squatter_guard.py`) one port down: a
  fixed port plus a reuse flag plus a detached child is how a test ends up answering for
  the product.
* `playwright.real.config.ts:41` claims the product port and `:52` is exclusive. Measured
  on an ephemeral port, the exclusive form refuses before the first test —
  `http://127.0.0.1:<port>/ is already used, make sure that nothing is running on the
  port/url or set reuseExistingServer:true in config.webServer`. With the live backend on
  :8765 that refusal is the only thing keeping a spec run off it, so exclusivity is pinned
  here rather than assumed.

Three registers hold what is true today and must only shrink: a port a leg reuses instead
of owning, a writing spec running on a leg that does not start its server, and a spec
bound to an origin its own leg does not declare. Each names the fix that removes it. The
first is now empty — `playwright.config.ts` picks its own port and is exclusive — so no leg
may reuse any port. Every other rule in this file fails on a new violation.

Platform behaviour is read rather than assumed. Run 38098961455, `pytest-linux (py3.12)`:
the residue test asserted the macOS parent value and went red on Linux, where an orphan's
parent is whichever ancestor declared itself a child subreaper — a runner service does. The
parent is carried as a field now, and a test that needs an instrument the box does not have
(`git`, `lsof`, as in `python:3.12-slim`) skips by name instead of reddening the leg.

Two things this guard does not cover, stated rather than implied away:

* A leftover child that has released its port cannot be attributed to a run. The residue
  rule keys on the port, so a server process still running after letting go of the port is
  invisible to it. Under `-n auto` that is not a theoretical gap: an early version scanned
  `ps` for the leg command names instead, and one worker's in-flight plant was reported as
  another worker's residue — a detached plant has no live parent pointing back at its own
  run. Closing it needs the leg to record the pid it started, a change in
  `app/tests/playwright` or in the CI leg.
* The product-port half is proven on an ephemeral port only. Nothing here binds :8765: the
  live backend on it belongs to another lane tonight. `tests/conftest.py` already watches
  the product port for every pytest session, so the rule that would have been falsified
  there is the same `residue_after_run` code path, called with a different port number.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.subprocess_env import hermetic_env
from tests.test_port_squatter_guard import (
    PRODUCT_PORT,
    describe,
    is_another_runs_child,
    is_the_developers_own_server,
    listening_pids,
    marks_a_test_home,
    port_is_open,
    process_command,
    process_env,
)

PW_DIR = REPO_ROOT / "app" / "tests" / "playwright"
CONFIGS = ("playwright.config.ts", "playwright.real.config.ts", "dogfood.config.ts")
E2E_SERVER = REPO_ROOT / "app" / "tests" / "e2e_server.py"
VITE_CONFIG = REPO_ROOT / "app" / "vite.config.ts"


def tracked_specs() -> list[Path]:
    """Tracked spec files only.

    `r4-motion-paint.spec.ts` was untracked and belonged to another lane when these
    registers were written; keying on the index keeps a file that is still being authored
    out of the counts, so it cannot flip this suite over someone else's work in progress.
    Without git there is no index to read, which is a named skip rather than a green.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "app/tests/playwright"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        pytest.skip("no git on this platform: the registers read the index for spec files")
    specs = sorted(REPO_ROOT / line for line in out.stdout.split() if line.endswith(".spec.ts"))
    assert specs, "git ls-files found no spec: the registers below would pass by emptiness"
    return specs


def can_name_listeners() -> bool:
    """Whether a listener can be attributed to a pid here at all.

    Measured in `python:3.12-slim`: the image has no `lsof`, so a listener can be probed
    but not owned, and 4 residue tests failed on an empty answer rather than reporting the
    missing instrument. A guard that quietly finds nothing is the worse failure.
    """
    return shutil.which("lsof") is not None


def config_text(name: str) -> str:
    return (PW_DIR / name).read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Config source with comment lines dropped, one line at a time.

    A regex block-comment strip cannot work here: `'**/setup-e2e/**'` contains both `/*`
    and `*/`, and dropping that range would delete a glob. Whole-line comments are what
    these files actually use — `dogfood.config.ts:3` names :8765 in prose, and only the
    declared values may count as a claim on a port.
    """
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )


#: (config, spec) where a non-GET request reaches a server the leg did not start.
#: `dogfood.config.ts` declares no webServer (`:4` says the dev server runs externally) and
#: its testIgnore (`:10`) drops only the setup spec, so `artifact-export.spec.ts` runs
#: there: POST `/api/chat/stream` at `:12` and DELETE `/api/artifacts/<id>` at `:43`, on a
#: baseURL of `localhost:5173` that `vite.config.ts:43` proxies to :8765 — the live product
#: server, with the developer's own `~/.ephe` behind it.
#: Removal: ignore the spec there, or give the dogfood leg a backend on an isolated config
#: dir.
WRITE_THROUGH_WITHOUT_OWN_SERVER = {
    ("dogfood.config.ts", "artifact-export.spec.ts"),
}

#: Ports a leg reuses instead of owning. Empty, and it must stay empty: the last entry —
#: `playwright.config.ts` on the static dist server at :9199 — was measured against an
#: orphaned holder of that exact command (PID 82841): the leg's own command never ran and
#: the spec still passed. That leg now picks a free port at run time and is exclusive, so
#: there is no fixed port to reuse and no number for the register to name; it states its
#: exclusivity in `test_the_leg_ports_are_measured_not_assumed` instead.
REUSED_SERVER_PORTS: set[tuple[str, int]] = set()

#: (config, spec) where a spec names an origin that is not the config's own port.
#: `r14.spec.ts` was the first entry until 2026-10-14: its `:12,14` went to
#: `localhost:5173` while the leg served a static dist, so the file needed a dev server up
#: before the leg could pass. Register #68 moved both navigations through the lane's
#: `baseURL` — the pair's own removal note — and the entry left the register, which is the
#: only direction this one may take. On the same day the leg also stopped declaring a port
#: of its own: it binds a free one at run time, so `REUSED_SERVER_PORTS` is empty and the
#: exclusivity assertion below is what holds the line instead.
#: `r4-motion-paint.spec.ts:83` builds `http://127.0.0.1:8765` into a constant and
#: navigates `${LIVE_ORIGIN}/#/chat` at `:444`, so in both the static leg and the dogfood
#: leg it either skips on the probe at `:439` or, when a live backend is up, leaves its own
#: leg and reads the product server. It never writes: the reach is GET.
#: Removal: navigate through the baseURL, the way r14 now does.
LEG_ORIGIN_MISMATCH = {
    ("playwright.config.ts", "r4-motion-paint.spec.ts"),
    ("dogfood.config.ts", "r4-motion-paint.spec.ts"),
}



def declared_ports(text: str) -> set[int]:
    """The ports a leg declares: baseURL, webServer port and probe url, plus a port inside
    the webServer command — the command is what actually binds."""
    text = code_only(text)
    ports: set[int] = set()
    for match in re.finditer(r"(?:baseURL|url):\s*['\"`]https?://[^/'\"`:]+:(\d{2,5})", text):
        ports.add(int(match.group(1)))
    for match in re.finditer(r"\bport:\s*(\d{2,5})\b", text):
        ports.add(int(match.group(1)))
    for match in re.finditer(r"\b(?:http\.server|--port)[ =]+(\d{2,5})\b", text):
        ports.add(int(match.group(1)))
    return ports


def reuse_flag(text: str) -> bool | None:
    match = re.search(r"reuseExistingServer:\s*(true|false)", code_only(text))
    return None if match is None else match.group(1) == "true"


def web_server_command(text: str) -> str:
    match = re.search(r"command:\s*(['\"`])(.*?)\1", code_only(text))
    return match.group(2) if match else ""


def declared_test_dir(text: str) -> str:
    match = re.search(r"testDir:\s*['\"`](.*?)['\"`]", code_only(text))
    return (match.group(1) if match else ".").lstrip("./")


def declared_test_ignore(text: str) -> list[str]:
    match = re.search(r"testIgnore:\s*(\[[^\]]*\]|'[^']*')", code_only(text))
    if match is None:
        return []
    return re.findall(r"'([^']+)'", match.group(1))


def spec_is_included(spec: Path, name: str) -> bool:
    """Whether this config runs the spec: it sits under testDir and stays out of
    testIgnore."""
    text = config_text(name)
    relative = spec.relative_to(PW_DIR).as_posix()
    directory = declared_test_dir(text)
    if directory and not (relative == directory or relative.startswith(directory + "/")):
        return False
    for glob in declared_test_ignore(text):
        stem = glob.removeprefix("**/").split("/**")[0].rstrip("/")
        if relative == stem or relative.startswith(stem + "/"):
            return False
    return True


NON_GET = re.compile(r"\.(post|put|patch|delete)\s*\(|method:\s*['\"](POST|PUT|PATCH|DELETE)")
#: Any host:port literal in spec code. Matching only inside `goto('http://host:port')`
#: would miss `r4-motion-paint.spec.ts:83`, which builds the origin into a constant and
#: navigates `${LIVE_ORIGIN}/#/chat` at `:444`.
ABSOLUTE_ORIGIN = re.compile(r"https?://(?:localhost|127\.0\.0\.1):(\d{2,5})")


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(("//", "*", "/*"))


def non_get_lines(spec: Path) -> list[int]:
    """File line numbers, so the report points at the source a reader opens."""
    lines = spec.read_text(encoding="utf-8").splitlines()
    return [
        number
        for number, line in enumerate(lines, start=1)
        if not _is_comment(line) and NON_GET.search(line)
    ]


def absolute_origins(spec: Path) -> set[int]:
    lines = spec.read_text(encoding="utf-8").splitlines()
    return {
        int(match.group(1))
        for line in lines
        if not _is_comment(line)
        for match in ABSOLUTE_ORIGIN.finditer(line)
    }


def leg_ports() -> dict[str, set[int]]:
    return {name: declared_ports(config_text(name)) for name in CONFIGS}


def writing_specs() -> list[Path]:
    return [spec for spec in tracked_specs() if non_get_lines(spec)]



def server_command_patterns() -> set[str]:
    """Substrings identifying the servers these legs start."""
    patterns: set[str] = set()
    for name in CONFIGS:
        command = web_server_command(config_text(name))
        if "http.server" in command:
            patterns.add("http.server")
        if "e2e_server.py" in command:
            patterns.add("e2e_server.py")
    return patterns


class Plant(NamedTuple):
    """A server this file started: its pid, the pid that launched it, the handle if alive."""

    pid: int
    launcher_pid: int
    proc: subprocess.Popen | None


class Residue(NamedTuple):
    """One listener a leg's port lost track of, as fields the tests can read.

    Run 38098961455, `pytest-linux (py3.12)`: the same plant reported
    `PID 775 … — listens on the leg port 37019 with a command a leg declares` on Linux and
    `… orphaned to PPID 1 …` on macOS. An orphan's parent is 1 where launchd is PID 1, and
    on Linux it is whichever ancestor declared itself a child subreaper — a runner service
    does, and reproduced here in `python:3.12-slim` under `PR_SET_CHILD_SUBREAPER`. The
    parent is therefore carried as data; no rule compares it to one platform's value.
    """

    pid: int
    port: int
    parent_pid: int | None
    command: str
    marker: str | None
    declares_leg_server: bool


def _command(pid: int) -> str:
    """Command line from `/proc` where it exists, through `ps` elsewhere.

    A slim container has neither: the answer is an explicit `<unreadable>`, which the rule
    below treats as residue worth naming rather than as a reason to stay quiet.
    """
    cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        if cmdline.is_file():
            parts = cmdline.read_bytes().split(b"\0")
            return " ".join(part.decode("utf-8", "replace") for part in parts if part)
    except OSError:
        return "<unreadable>"
    try:
        return process_command(pid)
    except (OSError, subprocess.SubprocessError):
        return "<unreadable>"


def parent_of(pid: int) -> int | None:
    """A pid's parent, or None when the platform offers no way to read it.

    `/proc/<pid>/stat` is read past the comm field because a command name may hold spaces
    and parentheses; `ps` is the fallback and is absent on a slim image, which is a None
    rather than a crash.
    """
    stat = Path(f"/proc/{pid}/stat")
    try:
        if stat.is_file():
            fields = stat.read_text().rpartition(") ")[2].split()
            return int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else None
    except OSError:
        return None
    try:
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(out) if out.isdigit() else None


def snapshot(ports: set[int]) -> dict[int, list[int]]:
    """Who already holds the leg ports, before a run starts.

    Every judgement below is a diff against this, and it is scoped by port rather than by
    command text: measured with `-n 4`, an unscoped command scan reported a sibling
    worker's in-flight plant as this run's residue, because a detached plant has no live
    parent to point back at its own run.
    """
    return {port: list(listening_pids(port) or []) for port in ports}


def residue_after_run(
    ports: set[int], baseline_listeners: dict[int, list[int]]
) -> list[Residue]:
    """Listeners that appeared on a leg's declared ports during the run and are still there.

    Baseline-relative the way `tests/conftest.py` reads the product port before the first
    test, so a server that predates the run — the developer's own, or the :9199 holder
    measured tonight — is not this run's residue.
    """
    records: list[Residue] = []
    patterns = server_command_patterns()
    for port in sorted(ports):
        for pid in listening_pids(port) or []:
            if pid in baseline_listeners.get(port, []):
                continue
            if is_another_runs_child(pid):
                continue
            env = process_env(pid)
            command = _command(pid)
            declares = bool(patterns) and any(pattern in command for pattern in patterns)
            marker = marks_a_test_home(env)
            unreadable = command == "<unreadable>"
            if (
                not unreadable
                and not declares
                and not marker
                and is_the_developers_own_server(env)
            ):
                continue
            records.append(
                Residue(
                    pid=pid,
                    port=port,
                    parent_pid=parent_of(pid),
                    command=command,
                    marker=marker,
                    declares_leg_server=declares,
                )
            )
    return records


def format_residue(records: list[Residue]) -> str:
    """The report a failing leg prints: PID, start time, command, parent, proof."""
    blocks = []
    for record in records:
        parent = (
            f"parent pid {record.parent_pid}"
            if record.parent_pid is not None
            else "parent pid unreadable on this platform"
        )
        reason = f"listens on port {record.port}, which a Playwright leg declares"
        if record.declares_leg_server:
            reason += ", with a command a leg starts, after its launcher exited"
        blocks.append(describe(record.pid, reason, record.marker) + f"\n      parent:  {parent}")
    return "\n".join(blocks)


_DIST_SERVER = (
    "import http.server, socketserver, sys\n"
    "socketserver.TCPServer.allow_reuse_address = True\n"
    "server = socketserver.TCPServer(('127.0.0.1', int(sys.argv[1])), "
    "http.server.SimpleHTTPRequestHandler)\n"
    "server.serve_forever()\n"
)


@pytest.fixture
def ephemeral_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    assert port != PRODUCT_PORT, "this lane never takes the product port"
    return port


@pytest.fixture
def planted_server(tmp_path):
    """Starts the command shape the legs declare, on a port this file picked."""
    children: list[subprocess.Popen] = []

    def _plant(port: int, *, detach: bool = False) -> Plant:
        assert port != PRODUCT_PORT, "this lane never takes the product port"
        if not can_name_listeners():
            pytest.skip("no lsof on this platform: a listener cannot be attributed to a pid")
        env = hermetic_env(PATH="/usr/bin:/bin", HOME=str(Path.home()))
        if detach:
            # A launcher that exits leaves the server parentless — the shape of PID 82841,
            # and the reason a parent's teardown is not enough. Where the parent lands
            # differs by platform: launchd at 1 here, a child subreaper on a Linux runner.
            launcher_script = (
                "import subprocess, sys\n"
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]],\n"
                "                 start_new_session=True, cwd=sys.argv[3])\n"
            )
            launcher = subprocess.Popen(
                [sys.executable, "-c", launcher_script, _DIST_SERVER, str(port), str(tmp_path)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            launcher.wait(timeout=30)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not port_is_open(port):
                time.sleep(0.2)
            pids = listening_pids(port) or []
            assert pids, f"the detached plant never bound port {port}"
            return Plant(pid=int(pids[0]), launcher_pid=launcher.pid, proc=None)
        proc = subprocess.Popen(
            [sys.executable, "-c", _DIST_SERVER, str(port)],
            env=env,
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        children.append(proc)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not port_is_open(port):
            time.sleep(0.2)
        assert port_is_open(port), "the plant never bound its port"
        return Plant(pid=proc.pid, launcher_pid=os.getpid(), proc=proc)

    yield _plant
    for proc in children:
        try:
            proc.kill()
        finally:
            proc.wait(timeout=10)


def test_only_one_leg_claims_the_product_port() -> None:
    claiming = sorted(name for name, ports in leg_ports().items() if PRODUCT_PORT in ports)
    assert claiming == ["playwright.real.config.ts"], (
        f"legs naming :{PRODUCT_PORT} are now {claiming} — that is where the developer's "
        "own engine.json lives, so a second leg on it has to be justified here first"
    )


def test_a_leg_that_claims_the_product_port_is_exclusive() -> None:
    """Measured: the exclusive form refuses the port, the reuse form runs green anyway.

    With the live backend on :8765, exclusivity is what turns a collision into a failed
    run instead of a passing run against the wrong server.
    """
    for name in CONFIGS:
        text = config_text(name)
        if PRODUCT_PORT not in declared_ports(text):
            continue
        assert reuse_flag(text) is False, (
            f"app/tests/playwright/{name} claims the product port while reusing a server "
            f"it did not start: the leg would test whoever answers :{PRODUCT_PORT}, and a "
            "spec that writes would write into that server"
        )


def test_the_e2e_server_binds_the_port_the_leg_probes() -> None:
    """The probe url and the uvicorn bind have to be the same number.

    `select_free_port` (`run_server.py:29`) walks to the next free port. If the e2e entry
    ever used it, the command would come up on 8766 while `playwright.real.config.ts:50`
    reads :8765, and an outside server on :8765 would satisfy the probe while the leg
    believed it had started its own.
    """
    text = E2E_SERVER.read_text(encoding="utf-8")
    assert "select_free_port" not in text, (
        "app/tests/e2e_server.py walks to a free port, so the leg's health probe can be "
        "answered by a server this leg never started"
    )
    bound = re.search(r"port\s*=\s*(\d{2,5})", text)
    assert bound, "app/tests/e2e_server.py no longer names a fixed uvicorn port"
    probe = re.search(
        r"url:\s*['\"`]http://127\.0\.0\.1:(\d{2,5})",
        config_text("playwright.real.config.ts"),
    )
    assert probe, "the real leg has no probe url to compare the bind against"
    assert int(bound.group(1)) == int(probe.group(1)) == PRODUCT_PORT


def test_the_e2e_leg_isolates_its_config_dir_from_the_developers_home() -> None:
    text = E2E_SERVER.read_text(encoding="utf-8")
    assert re.search(r'config_dir\s*=\s*runtime_dir\s*/\s*"config"', text), (
        "app/tests/e2e_server.py no longer builds its config dir under .e2e-runtime"
    )
    assert 'os.environ["EPHE_CONFIG_DIR"]' in text, "the isolated config dir is never set"
    assert 'Path.home()' not in text, "the e2e server resolves the developer's home"


def test_the_static_dist_leg_excludes_every_writing_spec() -> None:
    included = [
        spec.name
        for spec in writing_specs()
        if spec_is_included(spec, "playwright.config.ts")
    ]
    assert not included, (
        f"specs issuing a non-GET request are inside the static leg: {included} — the "
        "static dist server has no backend, so those calls 404 against http.server and "
        "the write they pin is untested rather than proven absent"
    )


def test_a_writing_spec_runs_only_on_a_leg_that_starts_its_server() -> None:
    measured = {
        (name, spec.relative_to(PW_DIR).as_posix())
        for name in CONFIGS
        if not web_server_command(config_text(name))
        for spec in writing_specs()
        if spec_is_included(spec, name)
    }
    assert measured <= WRITE_THROUGH_WITHOUT_OWN_SERVER, (
        f"new write-through pairs {sorted(measured - WRITE_THROUGH_WITHOUT_OWN_SERVER)}: a "
        "leg with no webServer of its own now includes a spec that writes, so the write "
        "lands on whatever backend that baseURL points at — through the dev proxy that is "
        "the live product server"
    )


def test_the_reuse_register_only_shrinks() -> None:
    measured = {
        (name, port)
        for name in CONFIGS
        if reuse_flag(config_text(name)) is True
        for port in declared_ports(config_text(name))
    }
    assert measured <= REUSED_SERVER_PORTS, (
        f"legs now reuse {sorted(measured - REUSED_SERVER_PORTS)}: measured tonight, a "
        "reused port runs the leg green against a server it never started"
    )


def test_a_spec_is_not_bound_to_an_origin_its_leg_does_not_declare() -> None:
    """A spec that names its own host and port leaves the leg it belongs to, so the run
    only passes while somebody else's server happens to be up on that number."""
    measured = {
        (name, spec.relative_to(PW_DIR).as_posix())
        for name in CONFIGS
        for spec in tracked_specs()
        if spec_is_included(spec, name)
        and absolute_origins(spec) - declared_ports(config_text(name))
    }
    assert measured <= LEG_ORIGIN_MISMATCH, (
        f"specs now pinned to a foreign origin: {sorted(measured - LEG_ORIGIN_MISMATCH)} — "
        "each one makes its leg depend on a server the leg does not start, so the run "
        "passes only while somebody else's dev server happens to be up"
    )



def _reap(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_residue_names_a_leg_server_whose_launcher_is_gone(
    ephemeral_port, planted_server
) -> None:
    """The PID 82841 shape: the launcher exited, nothing reaped the server it started.

    Asserted on fields, because the parent number is a platform fact: 1 under launchd, the
    runner's pid under a Linux child subreaper (measured in `python:3.12-slim` with
    `PR_SET_CHILD_SUBREAPER`, which reproduced run 38098961455's failure here). What is
    invariant is that the parent is no longer the launcher.
    """
    listeners = snapshot({ephemeral_port})
    plant = planted_server(ephemeral_port, detach=True)
    try:
        records = residue_after_run({ephemeral_port}, listeners)
        assert [record.pid for record in records] == [plant.pid], records
        record = records[0]
        if record.command == "<unreadable>":
            pytest.skip(
                "no /proc and no ps on this platform: a leg server cannot be told from "
                "any other listener on the port, so the command fields are unprovable"
            )
        assert record.port == ephemeral_port
        assert record.declares_leg_server is True
        assert "http.server" in record.command
        assert sys.executable in record.command
        assert record.parent_pid != plant.launcher_pid, (
            "the launcher exited, so it must not still read as this server's owner"
        )
        report = format_residue(records)
        assert str(plant.pid) in report and str(ephemeral_port) in report
    finally:
        _reap(plant.pid)


def test_a_reaped_fixture_server_leaves_no_residue(ephemeral_port, planted_server) -> None:
    """Passing direction: the same command, reaped before the check, is not residue."""
    listeners = snapshot({ephemeral_port})
    plant = planted_server(ephemeral_port)
    assert plant.proc is not None
    plant.proc.kill()
    plant.proc.wait(timeout=10)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and listening_pids(ephemeral_port):
        time.sleep(0.2)
    assert residue_after_run({ephemeral_port}, listeners) == []


def test_a_server_this_run_started_is_this_runs_residue_to_name(
    ephemeral_port, planted_server
) -> None:
    """The pytest guard's sibling rule exempts a child another live run still owns, so a
    server this process started is claimed here. That is what lets two concurrent legs
    each account for the child they started."""
    listeners = snapshot({ephemeral_port})
    plant = planted_server(ephemeral_port)
    assert plant.proc is not None
    try:
        assert is_another_runs_child(plant.pid) is False
        records = residue_after_run({ephemeral_port}, listeners)
        assert [record.pid for record in records] == [plant.pid], records
        assert records[0].parent_pid == os.getpid()
    finally:
        plant.proc.kill()
        plant.proc.wait(timeout=10)


def test_the_baseline_spares_a_holder_that_predates_the_run(
    ephemeral_port, planted_server
) -> None:
    """A leg started while something else holds its port is judged against the baseline,
    so the developer's long-running server is never this run's residue."""
    listeners = snapshot({ephemeral_port})
    plant = planted_server(ephemeral_port, detach=True)
    try:
        assert residue_after_run({ephemeral_port}, listeners) != []
        assert residue_after_run({ephemeral_port}, {ephemeral_port: [plant.pid]}) == []
    finally:
        _reap(plant.pid)


def test_the_leg_ports_are_measured_not_assumed() -> None:
    """The numbers the CI lane sizes its job on, pinned so a silent port move is a red.

    The static dist leg is the exception: it declares no number at all. It picks a free
    port at run time and owns it, so what is pinned here is the absence — no fixed port a
    stray server could hold — and, separately, that it never reuses one. The reuse cannot
    be read off `REUSED_SERVER_PORTS` any more: that register keys on a declared port, and
    this leg declares none, so the flag is asserted here directly.
    """
    assert leg_ports() == {
        "playwright.config.ts": set(),
        "playwright.real.config.ts": {PRODUCT_PORT},
        "dogfood.config.ts": {5173},
    }
    static = config_text("playwright.config.ts")
    assert reuse_flag(static) is False, (
        "app/tests/playwright/playwright.config.ts no longer states "
        "`reuseExistingServer: false`: a leg that reuses a server it did not start "
        "reports green or red about a bundle it never served"
    )
    assert "tests/e2e_server.py" in web_server_command(config_text("playwright.real.config.ts"))
    assert not web_server_command(config_text("dogfood.config.ts"))
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert re.search(
        r"const API_TARGET = process\.env\.EPHE_API_TARGET \|\| 'http://127\.0\.0\.1:8765'",
        config,
    ), (
        "the dev proxy no longer forwards /api to the product port, so the dogfood leg's "
        "reach into :8765 has to be re-read before a CI job is sized on it"
    )
    assert re.search(r"target:\s*API_TARGET", config), (
        "the /api proxy no longer uses the measured product target"
    )


def test_the_writing_specs_are_enumerated() -> None:
    """Every non-GET call the tracked specs make, with its line.

    Kept as a count because this is the set a CI leg has to reason about: a fourth
    writing spec means a fourth server the leg could be corrupting.
    """
    measured = {spec.name: non_get_lines(spec) for spec in writing_specs()}
    assert measured == {
        "artifact-export.spec.ts": [12, 44],
        "setup-e2e.spec.ts": [183],
    }, f"the non-GET set moved: {measured}"
