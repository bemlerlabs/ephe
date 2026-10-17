"""The desktop key store: what the surface promises has to be what the shell does.

Two languages and one secret. The frontend calls three shell commands, the shell writes one
file, and the settings hint is the only sentence the user reads about where his token goes.
Each pair here is pinned across the boundary, the way
`tests/test_desktop_engine_key.py` pins the resolver's sources: a renamed command, a moved
file or a hint that claims more than the code does has to fail in this file first.

No token value is read, printed or compared anywhere in this file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_RS = ROOT / "app" / "src-tauri" / "src" / "backend.rs"
LIB_RS = ROOT / "app" / "src-tauri" / "src" / "lib.rs"
BRIDGE_TS = ROOT / "app" / "src" / "lib" / "engineKey.ts"
SETUP_TSX = ROOT / "app" / "src" / "pages" / "SetupPage.tsx"

COMMANDS = ("save_engine_key", "engine_key_state", "clear_engine_key")


def _hint(lang: str) -> str:
    locale = json.loads((ROOT / "app" / "src" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
    return locale["setup"]["apiKeyHint"]


def _key_file_name() -> str:
    match = re.search(r'pub const KEY_FILE: &str = "([^"]+)"', BACKEND_RS.read_text(encoding="utf-8"))
    assert match, "backend.rs declares no KEY_FILE"
    return match.group(1)


def test_both_locales_name_the_file_the_shell_actively_writes():
    """The hint is the user's only statement about storage, so it quotes the real path.

    The removed text claimed the key was "stored on this device" while the route wrote it into
    the env of the running server — an unbacked promise in two languages. The path is taken
    from backend.rs rather than repeated here, so a renamed file fails this test instead of
    quietly ageing the hint.
    """
    claimed = f"~/.ephe/{_key_file_name()}"
    for lang in ("en", "de"):
        hint = _hint(lang)
        assert claimed in hint, f"{lang}: setup.apiKeyHint does not name {claimed}"
        for token in ("desktop", "browser"):
            assert token in hint.lower(), f"{lang}: the hint no longer separates the two surfaces"


def test_the_bridge_invokes_only_commands_the_shell_registers():
    """One rename on either side and the desktop would report a store it never made."""
    registered = LIB_RS.read_text(encoding="utf-8")
    handler = re.search(r"invoke_handler\(tauri::generate_handler!\[(.*?)\]\)", registered, re.S)
    assert handler, "lib.rs registers no command list"
    for command in COMMANDS:
        assert command in handler.group(1), f"{command} is not registered in the shell"

    invoked = set(re.findall(r"bridgeInvoke\('([a-z_]+)'", BRIDGE_TS.read_text(encoding="utf-8")))
    assert invoked == set(COMMANDS), f"the frontend bridge calls {sorted(invoked)}"


def test_the_setup_page_stores_the_key_before_it_saves_the_engine():
    """Order is the contract: a shell refusal must stop the choice, not outlive it.

    Saving first and storing second would leave the surface reporting a keyed engine while the
    next start has no token — the exact state the strict xfail in
    `tests/test_desktop_spawn_reaches_keyed_engine.py` measures.
    """
    source = SETUP_TSX.read_text(encoding="utf-8")
    start = source.index("async function handleFinish")
    body = source[start : start + 1800]
    store, save = body.find("storeEngineKey("), body.find("await updateSettings(")
    assert store != -1 and save != -1, "handleFinish neither stores the key nor saves the engine"
    assert store < save, "the engine was saved before the shell was asked to keep the token"


def test_the_bridge_says_session_only_when_no_shell_answers():
    """A browser cannot write a device file, and the code states that instead of guessing."""
    bridge = BRIDGE_TS.read_text(encoding="utf-8")
    assert "session-only" in bridge, "the browser path lost its honest answer"
    assert "if (!call) return 'session-only'" in bridge, "storeEngineKey no longer answers without a shell"
