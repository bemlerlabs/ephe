"""The shell's answer about its own backend, read where that answer is decided.

Two issues meet here, and both are about a window that claimed more than it had:

* #193 — started from the bundle with a fresh HOME (no `~/.ephe/desktop.json`), the
  shell started no backend on purpose, and the surface still showed "Ready" with a live
  composer and a model. The promise ("without that line nothing is guessed") was kept;
  the surface was never told. So the shell now builds one value — `Bereitschaft` in
  `app/src-tauri/src/backend.rs` — from the start attempt it made, hands it out as the
  `backend_readiness` command, and emits it as `ephe:backend-state` when the attempt
  finishes. Only a backend that answered for itself is `bereit`.
* #194 — `desktop.json` accepted a `port`, and only the backend start honoured it: the
  window's Content-Security-Policy and the surface's default base URL both name 8765.
  A configured port therefore started a backend the window could not talk to. The shell
  now refuses a configured port it does not serve, with both numbers in the sentence,
  instead of starting it into a dead end.

The behaviour is pinned by the Rust tests in `backend.rs` (`cargo test` in the shell
gate, `.github/workflows/rust-shell.yml`); this file holds the wiring — a state that is
computed but never handed to the surface, or a refusal that is defined but never reached,
would compile and test green while the defect stayed exactly where it was.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "app" / "src-tauri"
BACKEND = TAURI_DIR / "src" / "backend.rs"
SHELL = TAURI_DIR / "src" / "lib.rs"


def source(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def test_the_shell_hands_the_state_to_the_surface():
    """
    GIVEN the shell's command list and its start thread
    WHEN both are read
    THEN `backend_readiness` is a registered command and the state the start reached is
         emitted as `ephe:backend-state` — a surface cannot render a value nobody sends
    """
    backend = source(BACKEND)
    shell = source(SHELL)

    assert "pub struct Readiness" in backend, "the readiness value is gone"
    assert "serde::Serialize" in backend.split("pub struct Readiness")[0].rsplit("#[derive", 1)[-1], (
        "Readiness has to serialize: it crosses the IPC boundary"
    )
    assert "fn backend_readiness" in shell, "the command the surface would call does not exist"
    assert "backend_readiness," in shell.split("tauri::generate_handler![", 1)[1], (
        "backend_readiness is defined but not registered, so the surface cannot invoke it"
    )
    assert 'emit("ephe:backend-state"' in shell, "the state is computed and never announced"
    assert "backend::remember(" in shell, (
        "the emitted value has to be the recorded one, or command and event can disagree"
    )


def test_only_a_backend_that_answered_is_ready():
    """
    GIVEN the value the shell builds from a start attempt
    WHEN its arms are read
    THEN exactly the two states that mean "a backend is there or on its way" say
         `bereit: true`, and the unconfigured state names the command that fixes it.

    This is the state table of issue #193 in the file itself: `KeinBefehl` (no
    `desktop.json`, the state measured with a fresh HOME) must never read as ready.
    """
    backend = source(BACKEND)
    table = backend.split("impl Readiness", 1)[1].split("/// The last state", 1)[0]

    ready_arms = re.findall(r'"(ready|starting)"', table)
    assert ready_arms == ["ready", "starting"], f"the ready states changed: {ready_arms}"
    assert 'Ergebnis::KeinBefehl => verdict(\n                false,' in table, (
        "the unconfigured state must be `ready: false`"
    )
    assert "ephe desktop" in table, (
        "the unconfigured sentence has to name the command that writes desktop.json"
    )
    for state in (
        "unconfigured",
        "refused",
        "unreachable",
        "configured",
    ):
        assert f'"{state}"' in table, f"the state {state!r} is gone"


def test_a_configured_port_the_window_does_not_serve_is_refused_before_any_start():
    """
    GIVEN `sicherstellen`, the one place a backend is started
    WHEN the configured port is compared with the served one
    THEN the mismatch returns `PortAnders` before `starten` is reached, and the refusal
         names both numbers — a backend on a port the window cannot reach is worse than
         no backend, because it looks like one (issue #194)
    """
    backend = source(BACKEND)
    body = backend.split("pub fn sicherstellen", 1)[1]
    check = body.split("let key = key_for_start", 1)[0]
    start = body.split("match starten(", 1)[1]

    assert "if befehl.port != port {" in check, (
        "sicherstellen no longer compares the configured port with the served one"
    )
    assert "Ergebnis::PortAnders" in check, "the mismatch has to return its own verdict"
    assert "starten(" not in check, "the refusal must sit before the spawn"
    assert "Ergebnis::Gestartet" in start, "sicherstellen no longer starts anything at all"

    refusal = backend.split("Ergebnis::PortAnders { named, served } => verdict(", 1)
    assert len(refusal) == 2, "the readiness arm for a refused port is gone"
    arm = refusal[1].split("),", 1)[0]
    assert "named" in arm and "served" in arm, (
        "the sentence has to carry the requested and the served port"
    )
    assert '"refused"' in arm, "a refused port is not a ready state"
