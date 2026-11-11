"""The browser cluster's no-dialog licence, and the condition it is written against.

Measured in this tree before this file existed: `browser_go`, `browser_click`,
`browser_type`, `browser_press` and `browser_screenshot` sat in `SELF_GATED_TOOLS`,
`browser_evaluate` sat in `CHAT_AUTO_RUN_TOOLS`, and the only thing holding that
licence up was a comment saying the cluster is "bounded by its reach". Reach bounds
which addresses load. It says nothing about *whose identity* travels in the request —
and while the session holds no credentials there is no identity to travel, so the
licence has been safe by accident of the launch, not by decision.

So this file pins three things, in the order the risk arrives:

1. the predicate answers from the same setting the launch reads, and one source of
   truth cannot drift into "profile on, exemption still on";
2. with a credential in the session, the browser names leave the no-confirm set —
   and `browser_evaluate`, the tool that turns a bounded cluster into an arbitrary
   one, is refused rather than waved through (asserted by name, on the gate the chat
   path actually calls);
3. the CLI posture flips with it, so the licence cannot survive by another route.

Everything here is asserted against the real functions. Nothing patches the gate's
own decision, because a test that stubs the branch it is checking proves the test.
"""
from __future__ import annotations

import pytest

from core import browser_url
from core.tools.approval import (
    ApprovalPolicy,
    browser_session_is_credentialed,
    chat_no_confirm_tools,
    chat_tool_requires_confirm,
    classify_tool,
    credential_licence_voided,
)

#: The names whose licence is the credential-free session (core/browser_url.py).
BROWSER_NAMES = (
    "browser_go",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_screenshot",
    "browser_scroll",
    "browser_evaluate",
)


@pytest.fixture(autouse=True)
def empty_profile():
    """Every unit starts from the state this build actually ships: no profile."""
    browser_url._BROWSER_PROFILE.clear()
    yield
    browser_url._BROWSER_PROFILE.clear()


def with_stored_sign_in(monkeypatch, value: str = "/tmp/session-state.json") -> None:
    """Put a credential in the session the way the persistence programme will."""
    monkeypatch.setitem(browser_url._BROWSER_PROFILE, "storage_state", value)


# 1. the predicate reads the launch's own setting


def test_the_shipped_session_holds_no_credentials():
    """The present tense of the licence: nothing stored, so nobody is signed in."""
    assert browser_session_is_credentialed() is False
    assert browser_url.browser_profile_settings() == {
        "user_data_dir": "",
        "storage_state": "",
    }


def test_a_stored_sign_in_is_the_condition_the_licence_is_written_against(monkeypatch):
    assert browser_session_is_credentialed() is False
    with_stored_sign_in(monkeypatch)
    assert browser_session_is_credentialed() is True
    assert credential_licence_voided("browser_go") is True
    assert credential_licence_voided("read_file") is False


def test_a_profile_directory_is_the_other_half_of_the_same_switch(monkeypatch):
    """A profile directory means the same thing to the gate, even unwired."""
    monkeypatch.setitem(browser_url._BROWSER_PROFILE, "user_data_dir", "/tmp/profile")
    assert browser_session_is_credentialed() is True
    assert chat_tool_requires_confirm("browser_click") is True


def test_an_unreadable_profile_counts_as_holding_something(monkeypatch):
    """Fail-closed: a licence that survives a failed check was never checked."""

    def unreadable() -> dict[str, str]:
        raise RuntimeError("the session shape cannot be read")

    monkeypatch.setattr(browser_url, "browser_profile_settings", unreadable)
    assert browser_session_is_credentialed() is True
    assert chat_tool_requires_confirm("browser_evaluate") is True


@pytest.mark.asyncio
async def test_the_launch_applies_the_same_setting_the_gate_asks(empty_profile):
    """One source of truth, proven on the launch path rather than asserted in prose.

    A stored sign-in reaches `new_context`, which is where a credential would
    actually live. A profile directory is refused before anything starts, because
    the decision the setting owes this tree has not been made (
    `core/browser_url.PERSISTENT_PROFILE_UNWIRED`).
    """
    from core.browser import PlaywrightBrowserManager

    seen: list[dict[str, object]] = []
    routes: list[str] = []

    class FakeContext:
        async def route(self, pattern, handler):
            routes.append(pattern)

        async def new_page(self):
            return object()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            seen.append(kwargs)
            return FakeContext()

    manager = PlaywrightBrowserManager()
    manager._browser = FakeBrowser()  # type: ignore[assignment]

    browser_url._BROWSER_PROFILE["storage_state"] = "/tmp/session-state.json"
    await manager._ensure_page("session-with-a-profile")
    assert seen[-1].get("storage_state") == "/tmp/session-state.json"

    browser_url._BROWSER_PROFILE.clear()
    await manager._ensure_page("session-without-one")
    assert "storage_state" not in seen[-1]
    assert len(seen) == 2
    assert routes == ["**/*", "**/*"]


@pytest.mark.asyncio
async def test_a_profile_directory_refuses_to_launch_as_if_it_were_wired():
    """Silently ignoring the setting would start an uncredentialed session under a
    credentialed licence — the one shape where both halves disagree out loud."""
    from core.browser import BrowserUnavailable, _launch_chromium

    browser_url._BROWSER_PROFILE["user_data_dir"] = "/tmp/profile"

    class FakeChromium:
        async def launch(self, **kwargs):
            raise AssertionError("must not start: the profile it was configured with is unwired")

    class FakePlaywright:
        chromium = FakeChromium()

    with pytest.raises(BrowserUnavailable) as raised:
        await _launch_chromium(FakePlaywright())  # type: ignore[arg-type]
    assert "who consents" in str(raised.value)


# 2. the chat path: the licence is dropped when the condition goes


def test_without_credentials_the_browser_cluster_runs_unasked():
    """The behaviour this branch ships today, pinned so the flip is the only change."""
    no_confirm = chat_no_confirm_tools()
    for name in BROWSER_NAMES:
        assert name in no_confirm, name
        assert chat_tool_requires_confirm(name) is False, name


@pytest.mark.parametrize("name", ["browser_go", "browser_click", "browser_evaluate"])
def test_a_credentialed_session_takes_them_out_of_the_no_confirm_set(monkeypatch, name):
    """The three that carry the argument: two reach-bounded tools and the expression."""
    with_stored_sign_in(monkeypatch)
    assert name not in chat_no_confirm_tools(), name
    assert chat_tool_requires_confirm(name) is True, name


def test_the_whole_cluster_leaves_the_set_together(monkeypatch):
    """No half-exempt cluster: a name that stays unasked would make the rest moot."""
    with_stored_sign_in(monkeypatch)
    no_confirm = chat_no_confirm_tools()
    for name in BROWSER_NAMES:
        assert name not in no_confirm, name


class _Setting:
    """The one field `forced_categories` reads, without the store behind it.

    This is a fact about the environment, the same kind `with_stored_sign_in` installs.
    The gate's own decision is never stubbed: a test that replaced the branch it is
    checking would prove the test.
    """

    def __init__(self, ask_categories) -> None:
        self.ask_categories = ask_categories


def test_the_gate_and_the_enumerated_set_never_disagree(monkeypatch):
    """Two views of the licence, one answer, under every condition the gate reads.

    Measured on 2026-11-05 in the CI-shape run (`-n auto`): one worker listed
    `execute_code` as auto-run while the gate demanded a dialog for it, because the
    enumerated set consulted two of the licence's conditions and the gate consults four.
    The set now reads the same runtime facts, so all eight shapes of them are stepped
    through here — stored sign-in, the cell carrying the turn or not, and the user's
    ask-more category — each through the environment rather than through the decision.

    The profile is written through `monkeypatch` rather than the module dict, because a
    neighbour in the same worker would otherwise decide what the pass starts from, and a
    gate test that inherits a credential measures the branch it did not name.
    """
    for credentialed in (False, True):
        for cell_carries_the_turn in (True, False):
            for ask_network in (False, True):
                if credentialed:
                    monkeypatch.setitem(
                        browser_url._BROWSER_PROFILE,
                        "storage_state",
                        "/tmp/session-state.json",
                    )
                else:
                    monkeypatch.delitem(
                        browser_url._BROWSER_PROFILE, "storage_state", raising=False
                    )
                monkeypatch.setattr(
                    "core.cpython_cell.code_runs_uncontained",
                    lambda: not cell_carries_the_turn,
                    raising=False,
                )
                monkeypatch.setattr(
                    "core.security_config.load_security_config",
                    lambda: _Setting(["NETWORK"] if ask_network else []),
                )

                no_confirm = chat_no_confirm_tools()
                for name in no_confirm:
                    assert chat_tool_requires_confirm(name) is False, (
                        name,
                        credentialed,
                        cell_carries_the_turn,
                        ask_network,
                    )
                for name in BROWSER_NAMES:
                    assert (name in no_confirm) is (chat_tool_requires_confirm(name) is False)
                if cell_carries_the_turn is False:
                    assert "execute_code" not in no_confirm
                if ask_network:
                    # The store's own spelling (`core/tools/approval_rules.classify_tool`
                    # answers the category as the name the settings write).
                    assert "web_search" not in no_confirm, "an asked-about category stayed exempt"


def test_a_tool_the_cell_does_not_carry_is_out_of_the_enumerated_set(monkeypatch):
    """`execute_code` is auto-run while the cell caps it, and the set says so both ways.

    The pair this pins is the one the measured drift split: the set listed it, the gate
    asked for it. One name, one runtime fact, checked in both states.
    """
    monkeypatch.delitem(browser_url._BROWSER_PROFILE, "storage_state", raising=False)
    monkeypatch.setattr(
        "core.cpython_cell.code_runs_uncontained", lambda: True, raising=False
    )
    assert "execute_code" not in chat_no_confirm_tools()
    assert chat_tool_requires_confirm("execute_code") is True

    monkeypatch.setattr(
        "core.cpython_cell.code_runs_uncontained", lambda: False, raising=False
    )
    assert "execute_code" in chat_no_confirm_tools()
    assert chat_tool_requires_confirm("execute_code") is False


@pytest.mark.asyncio
async def test_browser_evaluate_refuses_to_run_unasked_in_a_credentialed_session(monkeypatch):
    """The gate the chat path calls, by name, on the tool that makes the cluster arbitrary.

    `confirm_for_chat` is the function `core.chat_tools` consults before dispatch, and
    `on_confirm=None` is the no-dialog-shaped request: without a credential the call
    runs (approved, nothing asked); with one it comes back refused through
    `no_approval_channel`, so an arbitrary expression never executes as the user just
    because a profile landed.
    """
    from core.tools.chat_gate import confirm_for_chat

    args = {"js": "document.querySelector('#balance').textContent"}

    approved, denial = await confirm_for_chat("browser_evaluate", args, on_confirm=None)
    assert approved is True and denial == ""

    with_stored_sign_in(monkeypatch)
    approved, denial = await confirm_for_chat("browser_evaluate", args, on_confirm=None)
    assert approved is False, "browser_evaluate ran unasked in a credentialed session"
    assert "browser_evaluate" in str(denial)
    assert getattr(denial, "code", "") == "no_approval_channel", denial


@pytest.mark.asyncio
async def test_a_credentialed_session_asks_and_a_yes_is_enough(monkeypatch):
    """The exemption becomes a dialog: the user can still say yes, and it is asked."""
    from core.tools.chat_gate import confirm_for_chat

    with_stored_sign_in(monkeypatch)
    asked: list[str] = []

    async def approve(name, _args):
        asked.append(name)
        return True

    approved, denial = await confirm_for_chat("browser_go", {"url": "https://example.invalid"}, on_confirm=approve)
    assert approved is True and denial == ""
    assert asked == ["browser_go"]


def test_the_desktop_half_of_the_cluster_is_not_moved_by_this_condition(monkeypatch):
    """`vision_click`/`vision_type` ask through `core.vision.check_sandbox` already;
    the browser's credential question says nothing about them, and a flip that
    silently changed their classification would be a second, unexamined decision."""
    with_stored_sign_in(monkeypatch)
    for name in ("vision_click", "vision_type", "take_screenshot"):
        assert credential_licence_voided(name) is False, name


# 3. the CLI posture flips with it


def test_cli_auto_approval_of_a_browser_tool_does_not_outlive_the_licence(monkeypatch):
    """`browser_screenshot` sits in `SAFE_TOOLS`, so `--yes` waves it through.

    The chat gate alone would leave the second door open: the same name classified
    SAFE and auto-approved on the CLI path while the session holds the user's
    sign-in.
    """
    assert classify_tool("browser_screenshot").auto_approve_by_default is True
    assert classify_tool("browser_screenshot").is_mutating is False

    with_stored_sign_in(monkeypatch)
    classified = classify_tool("browser_screenshot")
    assert classified.auto_approve_by_default is False
    assert classified.is_mutating is True


@pytest.mark.asyncio
async def test_a_credentialed_browser_tool_no_longer_takes_the_read_only_route(monkeypatch):
    """`browser_screenshot` sits in `SAFE_TOOLS`, so step 1 of the CLI gate approves it
    before a human is ever asked. The condition has to reach that step too, or the chat
    gate closes one door and the CLI leaves the other open.

    What `--yes` means after that is the design's own answer, unchanged: whoever typed
    it consented to the run. What is no longer available is consent nobody gave.
    """
    from core.tools.approval import request_approval

    plain = ApprovalPolicy(interactive=False)
    exempt = await request_approval("browser_screenshot", {}, plain)
    assert exempt.approved is True and "[auto]" in exempt.report, exempt.report

    with_stored_sign_in(monkeypatch)
    asked = await request_approval("browser_screenshot", {}, plain)
    assert asked.approved is False, asked.report
    assert "non-interactive" in asked.report

    names: list[str] = []

    async def approve(name, _args):
        names.append(name)
        return True

    granted = await request_approval(
        "browser_screenshot", {}, ApprovalPolicy(on_confirm=approve)
    )
    assert granted.approved is True
    assert names == ["browser_screenshot"]
