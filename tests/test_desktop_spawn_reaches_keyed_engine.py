"""Does the token a user enters in the app reach the backend the icon starts next time?

The desktop spawn is read out of its own source here, so a fixture cannot flatter it:
`starten()` in `app/src-tauri/src/backend.rs` composes the child's argv and touches the
child's environment at exactly one line, which makes the set of variables a desktop-spawned
backend can be handed a fact about that file. The token's other halves are pinned elsewhere —
the key file's refusal rules in
`tests/test_desktop_engine_key.py::test_the_key_file_rules_match_the_desktop_spawn`, the
two-process health statement in `tests/test_engine_reuse_statement.py` — and neither of them
asks what becomes of a token that never came from a terminal.

That is the open step. The product's own key entry is the engine form, and
`server/routes/settings.py` answers it with one statement that writes the value into
`os.environ` of the process serving the request. A process cannot pass its runtime environment
to a process that starts later, and the spawn consults two sources: the variable it inherits
and `~/.ephe/engine.key`. A keyed engine chosen inside the app is therefore reachable while
that one server lives, and unreachable for every desktop start after it, unless the user opens
a terminal and writes the file by hand.

The countable claim: a desktop-shaped child has to resolve a token wherever the surface put
one. Two answers are measured here, one per surface. A browser writes nowhere on the machine and
its child receives no `EPHE_` variable at all; the desktop surface stores the value through
`save_engine_key` (`app/src-tauri/src/backend.rs::store_key`, commit 478b8aa2), and a child
started after that store resolves it. The token value never reaches an assertion message or the
child's output.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.subprocess_env import hermetic_env  # noqa: E402

BACKEND_RS = ROOT / "app" / "src-tauri" / "src" / "backend.rs"
SETTINGS_PY = ROOT / "server" / "routes" / "settings.py"

#: the variable a keyed endpoint is authenticated by, as the engine reads it
KEY_ENV = "EPHE_OPENAI_COMPAT_API_KEY"

#: a public host is the endpoint class that needs a token (core/model_provider.py)
KEYED_URL = "https://api.example-gateway.test/v1"

STARTEN = r"fn starten\(befehl: &Startbefehl[^{]*\{.*?\n}\n"


def _backend_source() -> str:
    return BACKEND_RS.read_text(encoding="utf-8")


def _slice(name: str, pattern: str) -> str:
    """One function's source text out of backend.rs, the way the sibling files slice it."""
    match = re.search(pattern, _backend_source(), re.S)
    assert match, f"backend.rs declares no {name} — re-read the desktop spawn"
    return match.group(0)


def _const(name: str) -> str:
    match = re.search(rf'pub const {name}: &str = "([^"]+)"', _backend_source())
    assert match, f"backend.rs declares no {name}"
    return match.group(1)


def spawn_env_names() -> set[str]:
    """Every variable name `starten()` sets on the child, resolved through its consts."""
    body = _slice("starten", STARTEN)
    by_const = {_const(name) for name in re.findall(r'\.env\(\s*([A-Z][A-Z0-9_]*)\s*,', body)}
    by_literal = set(re.findall(r'\.env\(\s*"([^"]+)"\s*,', body))
    return by_const | by_literal


def spawn_argv() -> list[str]:
    """The script and the literal flags the desktop spawn composes, in argument order."""
    body = _slice("starten", STARTEN)
    script = re.search(r'projekt\.join\("([^"]+)"\)', body)
    assert script, "starten() no longer joins a script onto the recorded project root"
    return [script.group(1), *re.findall(r'\.arg\(\s*"([^"]+)"\s*\)', body)]


def spawn_key_file(home: Path) -> Path:
    """The file `key_for_start()` may read, named the way the Rust code names it."""
    body = _slice("key_for_start", r"pub fn key_for_start\([^)]*\)[^{]*\{.*?\n}\n")
    assert "key_from_file" in body, "key_for_start() no longer consults a file"
    return home / ".ephe" / _const("KEY_FILE")


def surface_write_target() -> str:
    """Where the engine form puts a token the user typed: one statement in the route."""
    source = SETTINGS_PY.read_text(encoding="utf-8")
    assigns = re.search(rf'os\.environ\["{KEY_ENV}"\]\s*=\s*(\w+)', source)
    assert assigns, "settings.py no longer writes the typed token into the running process env"
    value = assigns.group(1)
    if value != "req.provider.api_key":
        assert re.search(rf"{value}\s*=\s*req\.provider\.api_key", source), (
            "settings.py writes the env var from something other than the submitted key"
        )
    return KEY_ENV


def desktop_child_env(home: Path, **extra: str) -> dict[str, str]:
    """The environment the icon-launched spawn hands a child: a launchd-shaped base, plus the
    names `starten()` sets when the caller says a token was found, and no host `EPHE_*`."""
    base = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
        "SHELL": os.environ.get("SHELL", "/bin/zsh"),
        "TMPDIR": str(home),
    }
    return hermetic_env(**{k: v for k, v in base.items() if v}, **extra)


PROBE = """
import json, os, sys
sys.path.insert(0, {root!r})
from core.engine_config import engine_api_key_for
print(json.dumps({{
    "ephe_names": sorted(n for n in os.environ if n.startswith("EPHE_")),
    "token_resolved": bool(engine_api_key_for({url!r})),
}}))
"""


def ask_desktop_child(home: Path, *, with_token: bool = False) -> dict:
    """Run the resolver the way a desktop-spawned backend does. The environment is composed
    from `starten()`'s own line, so no in-process monkeypatch can stand in for exec."""
    extra = {surface_write_target(): "fixture-token-never-printed"} if with_token else {}
    proc = subprocess.run(
        [sys.executable, "-c", PROBE.format(root=str(ROOT), url=KEYED_URL)],
        env=desktop_child_env(home, **extra),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture()
def app_only_home(tmp_path: Path) -> Path:
    """A machine whose engine was chosen and keyed, with nothing stored yet: `engine.json`
    written by the settings route, no `engine.key`. That is the browser surface, and the state a
    desktop machine is in before its user saves a key through `save_engine_key`.
    """
    home = tmp_path / "home"
    (home / ".ephe").mkdir(parents=True)
    (home / ".ephe" / "engine.json").write_text(
        json.dumps(
            {"provider": "openai_compatible", "model": "chosen-keyed-model", "api_url": KEYED_URL}
        ),
        encoding="utf-8",
    )
    return home


def test_the_spawn_hands_one_variable_and_no_credential_on_the_command_line():
    """The measured shape, kept in the tree so the next assertion has a denominator.

    `starten()` sets the token name and nothing else; the child then derives provider, model
    and endpoint for itself from `~/.ephe/engine.json` (`run_server.py` bootstraps the engine
    choice and `apply_env()` never sets a token). One name is the whole budget, and argv
    carries no secret.
    """
    assert spawn_env_names() == {KEY_ENV}
    assert spawn_argv() == ["run_server.py", "--port"]


def test_a_browser_entry_stays_in_the_process_that_received_it(app_only_home: Path):
    """The surface with no shell behind it: the token lives in one process and nowhere else.

    `POST /api/settings` writes the typed value into `os.environ` of the answering server
    (`server/routes/settings.py:175`), and the route's other assembly of a request token,
    `server/routes/model_provider.py:120`, is scoped by the decision above it (`:77-80`) to a
    `/models` probe: "a chat turn is keyed by the env variable or `~/.ephe/engine.key` or not at
    all". A page cannot ask a machine to keep a file, so a child started afterwards inherits no
    `EPHE_` name and resolves none — while the same child handed the variable resolves it, the
    control that keeps this a statement about the path and not about the resolver.
    """
    assert spawn_key_file(app_only_home).is_file() is False
    child = ask_desktop_child(app_only_home)
    assert child["ephe_names"] == [], f"a launchd-shaped child must inherit no EPHE_ name: {child}"
    assert child["token_resolved"] is False, "a browser-side entry reached a later start"
    control = ask_desktop_child(app_only_home, with_token=True)
    assert control["token_resolved"] is True, "the resolver stopped reading the env it is given"


def test_a_key_stored_on_the_desktop_reaches_the_next_start(app_only_home: Path):
    """The half work item #53 closes: a token the surface stores outlives the server.

    `save_engine_key` (`app/src-tauri/src/backend.rs::store_key`, commit 478b8aa2) writes the file
    under the rules `tests/test_desktop_engine_key.py` pins — owner-only, one line, regular file —
    and the spawn reads it back for the next start. The write is reproduced here from those rules
    because a Python test cannot call into the shell; the shell side is held by its own Rust tests
    (`a_stored_key_is_the_key_the_next_start_reads`).
    """
    stored = spawn_key_file(app_only_home)
    stored.write_text("typed-token\n", encoding="utf-8")
    stored.chmod(0o600)

    child = ask_desktop_child(app_only_home)
    assert child["ephe_names"] == [], (
        f"the desktop child must reach the stored key through the file, not an inherited name: {child}"
    )
    assert child["token_resolved"] is True, (
        f"a key stored on the desktop is not read back: sources = [inherited "
        f"{surface_write_target()}, {stored.name}], file present = {stored.is_file()}"
    )
