"""The documented opt-out stops every update check, not only the daily one."""
from __future__ import annotations

import pytest


def test_the_release_fetch_respects_the_opt_out(monkeypatch):
    """`EPHE_NO_UPDATE_CHECK=1` stops the release feed as well."""
    from core import update_check

    monkeypatch.setenv(update_check.OPT_OUT_ENV, "1")
    # The suite's own offline trap replaces `_fetch_latest`; this test is about the gate
    # inside it, so the real function has to be restored for the call.
    monkeypatch.undo()
    monkeypatch.setenv(update_check.OPT_OUT_ENV, "1")
    with pytest.raises(RuntimeError, match="switched off"):
        update_check._fetch_latest()


def test_the_doctor_path_reports_no_update_when_switched_off(monkeypatch):
    """A doctor run with the opt-out says "off" instead of asking GitHub."""
    from core import update_check

    monkeypatch.setenv(update_check.OPT_OUT_ENV, "1")
    answer = update_check.daily_check()
    assert answer == {"enabled": False, "available": False}, answer
