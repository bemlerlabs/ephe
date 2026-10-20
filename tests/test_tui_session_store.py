"""The TUI reads and writes the one server store, switches it, and keeps old transcripts."""
from __future__ import annotations

import pytest

from core import multi_session as ms


def _message(text: str) -> dict[str, str]:
    return {"role": "user", "content": text}


@pytest.mark.asyncio
async def test_tui_loads_active_session_switches_and_keeps_the_old_one() -> None:
    alpha = ms.create_session("Alpha")
    ms.save_messages(alpha["id"], [_message("from alpha")])
    beta = ms.create_session("Beta")
    ms.save_messages(beta["id"], [_message("from beta")])
    ms.switch_to(alpha["id"])

    from ui.app import EpheApp

    app = EpheApp(model="test-model", reset=False)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app._session_id == alpha["id"]
        assert app._session[0]["content"] == "from alpha"

        assert app._switch_session(beta["id"]) is True
        assert app._session_id == beta["id"]
        assert app._session[0]["content"] == "from beta"
        assert ms.get_active_id() == beta["id"]

        app.action_reset_session()
        await pilot.pause()
        assert app._session_id not in {alpha["id"], beta["id"]}
        assert ms.get_active_id() == app._session_id

    # Ctrl+R created a new session; the two old transcripts are still on disk.
    assert ms.load_messages(alpha["id"])[0]["content"] == "from alpha"
    assert ms.load_messages(beta["id"])[0]["content"] == "from beta"
