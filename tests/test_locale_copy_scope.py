"""W4-25's residual: the shell-sandbox row is drawn on every platform, so its copy says where it bites.

`sandbox-exec` is macOS Seatbelt. On a host without the wrapper,
`core/shell_sandbox.py::resolve_sandbox` answers `sandbox-unavailable` and a confirmed
command runs with the user's own rights, while the settings switch stays on. The row
renders an unconditional `Switch`
(`app/src/components/dashboard/settings/model/sections-misc.tsx`), so the hint is where the
user learns the toggle does nothing there; it names the platform and the
`EPHE_SHELL_BACKEND=docker` path that does isolate the command.

W4-25 owns the boundary itself and recorded the decision; this file holds the copy half.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_JSON = ROOT / "app" / "src" / "locales" / "en.json"
DE_JSON = ROOT / "app" / "src" / "locales" / "de.json"

PLATFORM = "macOS"
MECHANISM = "sandbox-exec"
ISOLATION_PATH = "EPHE_SHELL_BACKEND=docker"


def settings_of(path: Path) -> dict[str, str]:
    node = json.loads(path.read_text(encoding="utf-8"))
    return node["settings"]


def test_the_english_hint_states_the_platform_and_the_isolation_path() -> None:
    hint = settings_of(EN_JSON)["sandboxHint"]
    assert MECHANISM in hint
    assert PLATFORM in hint
    assert ISOLATION_PATH in hint


def test_the_german_hint_states_the_platform_and_the_isolation_path() -> None:
    hint = settings_of(DE_JSON)["sandboxHint"]
    assert MECHANISM in hint
    assert PLATFORM in hint
    assert ISOLATION_PATH in hint


def test_the_row_label_keeps_the_scope_out_of_the_switch_title() -> None:
    """A screen reader reads the switch label alone, and the title is that label."""
    for path in (EN_JSON, DE_JSON):
        assert PLATFORM not in settings_of(path)["sandboxTitle"]
