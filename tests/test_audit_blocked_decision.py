"""Wave I1-9: the audit log can say that something was blocked.

"The cell dies, the log stays" is only worth as much as the log tells. Until here a
blockade stood in the line as `tool_exec run_shell status=ok decision=""` — the
information lived only in the detail text, which nobody searches. A log in which
"refused" and "executed" carry the same status word is no proof, but a vocabulary
problem.

Fix: `core.quality.result_decision` recognises the lines in which a tool states its
own blockade, and the registry writes `decision="blocked"`. The status stays what it
is (the call ran through without an error), the *decision* is the new axis — exactly
as with approval/channel entries.

Given / When / Then — tests first.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core import audit_log
from core.browser import browser_manager
from core.quality import BLOCKED_RESULT_PREFIXES, result_decision
from core.tool_markers import (
    BROWSER_DENIED_MARKER,
    CURRENT_REFUSAL_MARKERS,
    FETCH_REFUSED_MARKER,
    LEGACY_BROWSER_DENIED_MARKER,
    LEGACY_FETCH_REFUSED_MARKER,
)
from core.tools.fetch_tools import fetch_url
from core.tools.registry import execute_tool


def _tool_exec_lines() -> list[dict]:
    return audit_log.tail(kind="tool_exec")


class TestResultDecision:
    @pytest.mark.parametrize(
        "raw",
        [
            "⚠️ Security: shell redirects (> >> <) are blocked — change files via edit_file.",
            f"{BROWSER_DENIED_MARKER} javascript: is code on your page, not a page",
            f"{FETCH_REFUSED_MARKER} loopback is out of reach",
            "[TOOL-DENIED] write_file wurde nicht ausgeführt.",
            # The retired German wordings: rows already on disk carry them, and a
            # matcher that stops reading them would call those blockades ordinary
            # runs. Same guarantee as TestRetiredWordingsStillClassify below, one
            # line earlier in the table.
            f"{LEGACY_BROWSER_DENIED_MARKER} javascript: ist keine Seite, sondern Code auf deiner Seite",
            f"{LEGACY_FETCH_REFUSED_MARKER} loopback ist ausserhalb der Reichweite",
        ],
    )
    def test_a_spoken_refusal_is_blocked(self, raw):
        assert result_decision(raw) == "blocked"

    @pytest.mark.parametrize(
        "raw",
        [
            "hello world\n",
            "[execute_code] runtime=cpython-cell/3.13.16 status=OK exit=0",
            "[TOOL-ERROR] read_file: fehlende Pflicht-Parameter: path",
            "",
        ],
    )
    def test_nothing_else_is_called_blocked(self, raw):
        """An error is not a blockade and success even less so — three axes."""
        assert result_decision(raw) == ""

    def test_the_cell_refusal_is_a_blockade_not_a_crash(self):
        """status=GUEST_UNVERIFIED says: no code ran. That is the answer to the question."""
        assert (
            result_decision(
                "[execute_code] runtime=cpython-cell/3.13.16 status=GUEST_UNVERIFIED exit=-"
            )
            == "blocked"
        )

    def test_no_marker_in_the_table_is_fiction(self):
        """A prefix table nobody emits is a superstition with commas."""
        root = Path(__file__).resolve().parents[1] / "core"
        source = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.py"))
        for marker in BLOCKED_RESULT_PREFIXES:
            assert marker in source, f"{marker!r} is written by no tool"


class TestAuditRecordsTheBlockade:
    def test_blocked_shell_command_leaves_a_blocked_line(self):
        """The everyday case of the finding: redirection blocked, audit says 'ok'."""
        out = asyncio.run(execute_tool("run_shell", {"command": "echo test > /tmp/ephe-i1-9.txt"}))
        assert out.startswith("⚠️ Security:")
        line = _tool_exec_lines()[-1]
        assert line["tool"] == "run_shell"
        assert line["decision"] == "blocked"

    def test_allowed_command_is_not_marked_blocked(self):
        out = asyncio.run(execute_tool("run_shell", {"command": "echo ephe-i1-9"}))
        assert "ephe-i1-9" in out
        line = _tool_exec_lines()[-1]
        assert line["decision"] == ""

    def test_refused_url_is_a_blockade_for_the_fetch_tool(self):
        """The scope guard raises FetchRefused — reporting it as a tool error would be a lie."""
        out = asyncio.run(execute_tool("fetch_url", {"url": "http://127.0.0.1:9/x"}))
        assert out.startswith(FETCH_REFUSED_MARKER), out
        assert _tool_exec_lines()[-1]["decision"] == "blocked"

    def test_the_audit_api_carries_the_field(self):
        """What stands in the log, the display has to be able to show as well. `tail()`
        reads the file and parses JSON — what gets through here also gets through the
        API; a field that does not survive the roundtrip is gone from the display."""
        asyncio.run(execute_tool("run_shell", {"command": "echo x > /tmp/ephe-i1-9-b.txt"}))
        entry = _tool_exec_lines()[-1]
        assert entry["decision"] == "blocked", "decision='' in the file would be the old lie"
        assert json.loads(json.dumps(entry))["decision"] == "blocked"


class TestProducerAndDetectorAreOnePair:
    """The finding this wave is about: the marker was one string in two files.

    Every check above reads `BLOCKED_RESULT_PREFIXES`, so translating the tool
    alone left them all green while the audit silently stopped calling a refusal
    blocked. These tests take the line a *live* tool produces and hand it to the
    detector — the only arrangement where a one-sided edit fails a test instead of
    shipping. No fixture text, no marker typed out twice.
    """

    def test_a_live_browser_refusal_is_blocked(self):
        """url_policy says no before Playwright is ever asked for a page."""
        out = asyncio.run(browser_manager.go("javascript:alert(1)"))
        assert out.startswith(BROWSER_DENIED_MARKER), out
        assert result_decision(out) == "blocked"

    def test_a_live_fetch_refusal_is_blocked(self):
        """The metadata endpoint is refused whatever EPHE_FETCH_ALLOW_PRIVATE says."""
        out = asyncio.run(fetch_url("http://169.254.169.254/latest/meta-data/"))
        assert out.startswith(FETCH_REFUSED_MARKER), out
        assert result_decision(out) == "blocked"

    def test_a_live_refusal_marker_carries_no_leftover_german(self):
        """The head of the line is the contract: it must be one of the constants.

        Scoped to the marker on purpose. The reason text behind it is still German
        (`core/browser_url.py`, `core/net_guard.py`) — other producers, another
        wave, and not something this assertion may quietly bless or break.
        """
        for out in (
            asyncio.run(browser_manager.go("javascript:alert(1)")),
            asyncio.run(fetch_url("http://169.254.169.254/latest/meta-data/")),
        ):
            marker = out.partition("]")[0] + "]"
            assert marker in CURRENT_REFUSAL_MARKERS, out
            assert marker not in (LEGACY_BROWSER_DENIED_MARKER, LEGACY_FETCH_REFUSED_MARKER)


class TestRetiredWordingsStillClassify:
    """The German markers are out of the tools, not out of the matcher.

    Deleting them is a deliberate later step (see the comment at
    `BLOCKED_RESULT_PREFIXES`); until then an old row on disk has to keep reading
    as the blockade it was.
    """

    def test_the_retired_markers_are_still_matched(self):
        assert LEGACY_BROWSER_DENIED_MARKER in BLOCKED_RESULT_PREFIXES
        assert LEGACY_FETCH_REFUSED_MARKER in BLOCKED_RESULT_PREFIXES

    def test_a_historical_row_is_still_blocked(self):
        assert result_decision(f"{LEGACY_BROWSER_DENIED_MARKER} javascript:") == "blocked"
        assert result_decision(f"{LEGACY_FETCH_REFUSED_MARKER} loopback") == "blocked"
