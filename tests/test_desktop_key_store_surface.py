"""The desktop key store: what the surface promises has to be what the shell does.

Two languages and one secret. The frontend calls three shell commands, the shell writes one
file, and the settings hint is the only sentence the user reads about where his token goes.
Each pair here is pinned across the boundary, the way
`tests/test_desktop_engine_key.py` pins the resolver's sources: a renamed command, a moved
file or a hint that claims more than the code does has to fail in this file first.

W1-3 added a second bridge over the same boundary — three window commands behind a door the
shell wraps its whole registration in — so the read of that registration is a helper here and
the door is one of the things asserted.

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
SURFACE_BRIDGE_TS = ROOT / "app" / "src" / "lib" / "pluginSurface.ts"
SETUP_TSX = ROOT / "app" / "src" / "pages" / "SetupPage.tsx"

COMMANDS = ("save_engine_key", "engine_key_state", "clear_engine_key")
SURFACE_COMMANDS = ("plugin_window_open", "plugin_window_close", "plugin_window_bounds")

# The two ends of the registered list as lib.rs writes it. Held here rather than counted:
# a walk that stops early or starts late is a broken parse, and a broken parse that stays
# quiet is a pin that passes on nothing.
REGISTERED_FIRST = "quit_app"
REGISTERED_LAST = "set_global_shortcut"


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


def _registered_commands() -> list[str]:
    """The names in the list the shell registers, read through the surface door.

    W1-3 wrapped that list in `plugin_window::guard_before_dispatch`, so the registration no
    longer sits directly inside `invoke_handler(...)`. Reading it goes where it is written,
    and the door over it is asserted instead of assumed: taking the wrap off is the same
    class of accident as renaming a command, and this file is the only place the two are
    compared. The walk then says so when it finds only part of the list.
    """
    source = LIB_RS.read_text(encoding="utf-8")
    assert re.search(r"guard_before_dispatch\(\s*tauri::generate_handler!\[", source), (
        "lib.rs registers its command list without the surface door over it"
    )
    handler = re.search(r"generate_handler!\[(.*?)\]\s*\)", source, re.S)
    assert handler, "lib.rs registers no command list, wrapped or not"
    names = []
    for entry in handler.group(1).split(","):
        entry = re.sub(r"//[^\n]*", "", entry).strip()
        if entry:
            names.append(entry.rsplit("::", 1)[-1])
    assert REGISTERED_FIRST in names and REGISTERED_LAST in names, (
        f"the register walk read {len(names)} entries and missed an end of the list, so "
        "its verdict on a missing command means nothing"
    )
    return names


def test_the_bridge_invokes_only_commands_the_shell_registers():
    """One rename on either side and the desktop would report a store it never made."""
    registered = _registered_commands()
    for command in COMMANDS:
        assert command in registered, f"{command} is not registered in the shell"

    invoked = set(re.findall(r"bridgeInvoke\('([a-z_]+)'", BRIDGE_TS.read_text(encoding="utf-8")))
    assert invoked == set(COMMANDS), f"the frontend bridge calls {sorted(invoked)}"


def test_the_surface_bridge_invokes_only_commands_the_shell_registers():
    """A second bridge arrived in W1-3 with three window commands and no pin.

    `pluginSurface.ts` asks the shell through `core(...)` the way `engineKey.ts` asks
    through `bridgeInvoke(...)`. A surface command the shell does not register is a window
    that never opens while the page still reports the plugin as mounted, and a name spelled
    differently on the two sides fails exactly that quietly.
    """
    registered = _registered_commands()
    for command in SURFACE_COMMANDS:
        assert command in registered, f"{command} is not registered in the shell"

    called = set(re.findall(r"core\('([a-z_]+)'", SURFACE_BRIDGE_TS.read_text(encoding="utf-8")))
    assert called == set(SURFACE_COMMANDS), f"the surface bridge calls {sorted(called)}"


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
