"""
◑ Ephe – Wave G2 · TDD
tests/test_browser_url_policy.py

RULE: the tests were written BEFORE the implementation.

The headless browser does not gate itself through a dialog (SELF_GATED_TOOLS
claims that but never calls check_sandbox — core/browser.py does not know it).
It gates itself through what it is allowed to load at all. As long as ``go()``
explicitly whitelisted file: and data: (core/browser.py:70), that was a local file
reader: "open file:///Users/x/.ssh/id_rsa" + get_text delivers the content to the
model — without a question, without a workspace boundary.

New: http/https and data: run, file: only inside the artifact roots, everything
else is refused. The refusal is an answer, not a crash.
"""
from __future__ import annotations

import asyncio
import types
from pathlib import Path

import pytest

from core.browser import PlaywrightBrowserManager
from core.browser_url import navigation_guard, url_policy
from core.tool_markers import BROWSER_DENIED_MARKER


class FakePage:
    """Minimal page that records every navigation."""

    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.viewport_size = {"width": 1280, "height": 800}

    async def goto(self, url: str, **_kwargs):
        self.goto_urls.append(url)

    async def evaluate(self, expression, arg=None):
        return "Seiteninhalt"


def _manager(fake: FakePage) -> PlaywrightBrowserManager:
    mgr = PlaywrightBrowserManager()
    mgr._playwright = object()
    mgr._browser = object()
    mgr._page = fake
    return mgr


class TestUrlPolicy:
    """The decision is a pure function — without Playwright, without a dialog."""

    def test_public_schemes_pass(self):
        for url in ("https://example.com/a", "http://example.org"):
            ok, reason = url_policy(url)
            assert ok, (url, reason)

    def test_a_bare_host_gets_https(self):
        """Existing behaviour: without a scheme, https:// is prepended."""
        ok, resolved = url_policy("example.com/docs")
        assert ok and resolved == "https://example.com/docs"

    def test_data_url_is_allowed(self):
        """Rendering self-generated HTML stays possible (opaque origin, no host reader)."""
        ok, _ = url_policy("data:text/html,<h1>Hallo</h1>")
        assert ok

    def test_file_inside_an_allowed_root_is_allowed(self, tmp_path: Path, monkeypatch):
        html = tmp_path / "deck.html"
        html.write_text("<h1>deck</h1>")
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [tmp_path])
        ok, resolved = url_policy(f"file://{html}")
        assert ok and Path(resolved.removeprefix("file://")).is_file()

    def test_file_outside_the_roots_is_refused(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [tmp_path])
        outside = Path("/etc/passwd")
        ok, reason = url_policy(f"file://{outside}")
        assert ok is False
        assert "passwd" in reason or "außerhalb" in reason

    def test_symlink_escape_does_not_open_the_door(self, tmp_path: Path, monkeypatch):
        """relative_to on the resolved path: a link into /etc stays a link."""
        root = tmp_path / "root"
        root.mkdir()
        (root / "sneaky").symlink_to(Path("/etc/passwd"))
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [root])
        ok, _ = url_policy(f"file://{root / 'sneaky'}")
        assert ok is False

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "gopher://127.0.0.1:70/",
            "ftp://internal/shadow",
            "chrome://version",
            "jar:some:thing",
            "ws://127.0.0.1:9222/json",
            "about:blank",
        ],
    )
    def test_other_schemes_are_refused(self, url: str):
        ok, reason = url_policy(url)
        assert ok is False, url
        assert reason

    def test_empty_url_is_refused_not_loaded(self):
        ok, reason = url_policy("   ")
        assert ok is False
        assert reason


class TestAddressReach:
    """SEC-5: the fetch channel's address rules, applied to browser navigation.

    A scheme whitelist says nothing about where an http URL lands. The browser
    resolves on its own, so it asks the same two questions `core.net_guard.py`
    asks: which class is this name/address, and has the private opt-in been given.
    """

    @pytest.mark.parametrize(
        ("url", "code"),
        [
            ("http://169.254.169.254/latest/meta-data/", "browser_address_blocked"),
            ("http://[fd00:ec2::254]/x", "browser_address_blocked"),
            ("http://169.254.1.1/", "browser_address_blocked"),
            ("http://0.0.0.0/", "browser_address_blocked"),
            ("http://127.0.0.1:8765/api/settings", "browser_private_blocked"),
            ("http://[::1]:8765/api/audit?limit=500", "browser_private_blocked"),
            ("http://192.168.1.1/", "browser_private_blocked"),
            ("http://localhost:8765/", "browser_private_blocked"),
            ("http://metadata.google.internal/computeMetadata/v1/", "browser_metadata_host"),
            ("http://db.internal/x", "browser_internal_name"),
        ],
    )
    def test_the_fetch_address_classes_are_refused_by_default(self, url, code):
        ok, decision = url_policy(url)
        assert ok is False, url
        assert getattr(decision, "code", "") == code, decision

    def test_a_public_name_stays_allowed(self):
        ok, resolved = url_policy("https://example.com/docs")
        assert ok and resolved == "https://example.com/docs"

    def test_a_data_url_is_unchanged(self):
        ok, resolved = url_policy("data:text/html,<h1>x</h1>")
        assert ok and resolved == "data:text/html,<h1>x</h1>"

    def test_the_opt_in_opens_loopback_and_rfc1918_only(self, monkeypatch):
        monkeypatch.setenv("EPHE_FETCH_ALLOW_PRIVATE", "1")
        for url in ("http://127.0.0.1:8765/", "http://[::1]:8765/", "http://192.168.1.1/"):
            ok, decision = url_policy(url)
            assert ok, (url, decision)
        for url in ("http://169.254.169.254/latest/meta-data/", "http://169.254.1.1/"):
            ok, decision = url_policy(url)
            assert ok is False, url
            assert getattr(decision, "code", "") == "browser_address_blocked"

    def test_a_public_name_that_resolves_into_loopback_is_refused(self):
        ok, decision = asyncio.run(
            navigation_guard("https://rebind.test/", resolver=lambda _host: ["127.0.0.1"])
        )
        assert ok is False
        assert getattr(decision, "code", "") == "browser_private_blocked"

    def test_a_public_name_that_resolves_public_stays_allowed(self):
        ok, decision = asyncio.run(
            navigation_guard("https://docs.test/a", resolver=lambda _host: ["93.184.216.34"])
        )
        assert ok is True
        assert decision == "https://docs.test/a"


class _RouteStub:
    def __init__(self, url: str) -> None:
        self.request = types.SimpleNamespace(url=url)
        self.continued = False
        self.aborted = False

    async def continue_(self) -> None:
        self.continued = True

    async def abort(self) -> None:
        self.aborted = True


class TestRouteGuard:
    """Every request is checked, so a 302 onto loopback cannot ride the first answer."""

    def test_a_redirect_onto_loopback_is_aborted(self):
        route = _RouteStub("http://127.0.0.1:8765/api/settings")
        asyncio.run(PlaywrightBrowserManager()._guard_route(route))
        assert route.aborted is True
        assert route.continued is False

    def test_a_metadata_subresource_is_aborted(self):
        route = _RouteStub("http://169.254.169.254/latest/meta-data/iam/security-credentials/")
        asyncio.run(PlaywrightBrowserManager()._guard_route(route))
        assert route.aborted is True

    def test_a_public_request_continues(self):
        route = _RouteStub("https://93.184.216.34/")
        asyncio.run(PlaywrightBrowserManager()._guard_route(route))
        assert route.continued is True
        assert route.aborted is False

    def test_an_in_memory_scheme_is_not_network_reach(self):
        route = _RouteStub("blob:https://example.com/9f2c")
        asyncio.run(PlaywrightBrowserManager()._guard_route(route))
        assert route.continued is True
        assert route.aborted is False


class TestGoUsesThePolicy:
    """go() is the only navigation entry point among the core operations."""

    def test_a_local_file_never_reaches_the_page(self, tmp_path: Path, monkeypatch):
        fake = FakePage()
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [tmp_path])
        mgr = _manager(fake)

        out = asyncio.run(mgr.go("file:///etc/passwd"))
        assert fake.goto_urls == [], "the page loaded although the policy said no"
        assert out.startswith(BROWSER_DENIED_MARKER), out

    def test_an_allowed_file_url_still_loads(self, tmp_path: Path, monkeypatch):
        html = tmp_path / "preview.html"
        html.write_text("<h1>hi</h1>")
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [tmp_path])
        fake = FakePage()
        mgr = _manager(fake)

        asyncio.run(mgr.go(f"file://{html}"))
        assert fake.goto_urls and fake.goto_urls[0].startswith("file://")

    def test_http_url_loads_and_returns_text(self):
        fake = FakePage()
        mgr = _manager(fake)
        out = asyncio.run(mgr.go("https://example.com"))
        assert fake.goto_urls == ["https://example.com"]
        assert "Seiteninhalt" in out

    def test_a_refused_url_is_an_answer_not_an_exception(self):
        fake = FakePage()
        mgr = _manager(fake)
        out = asyncio.run(mgr.go("gopher://127.0.0.1:70/"))
        assert isinstance(out, str) and out.strip()
        assert fake.goto_urls == []

    def test_a_metadata_address_never_reaches_the_page(self):
        fake = FakePage()
        mgr = _manager(fake)
        out = asyncio.run(mgr.go("http://169.254.169.254/latest/meta-data/"))
        assert fake.goto_urls == []
        assert out.startswith(BROWSER_DENIED_MARKER), out

    def test_new_tab_and_goto_url_helpers_inherit_the_policy(self, tmp_path: Path, monkeypatch):
        """The browser_exec helpers are the same go() door, not a second one without a lock."""
        fake = FakePage()
        monkeypatch.setattr("core.browser_url._artifact_roots", lambda: [tmp_path])
        mgr = _manager(fake)

        asyncio.run(mgr.new_tab("file:///etc/hosts"))
        asyncio.run(mgr.goto_url("chrome://version"))
        assert fake.goto_urls == []


class TestBrowserExecTimeout:
    """browser_exec promised a time budget and did not use it."""

    def test_the_declared_budget_is_actually_enforced(self):
        from core.tools.browser_tools import browser_exec

        out = asyncio.run(
            browser_exec(code="import time\nprint('vorher')\ntime.sleep(30)\nprint('nachher')",
                         session="g2-timeout", timeout_s=1)
        )
        assert "vorher" in out
        assert "nachher" not in out
        assert "timeout" in out.lower() or "zeitbudget" in out.lower()

    def test_a_fast_block_is_untouched(self):
        from core.tools.browser_tools import browser_exec

        out = asyncio.run(browser_exec(code="print(2 + 2)", session="g2-fast", timeout_s=30))
        assert out.strip() == "4"

    def test_the_budget_is_clamped_into_a_sane_range(self):
        """A timeout settable by the model must not switch the gate off."""
        from core.tools.browser_tools import budget_seconds

        assert budget_seconds(0) >= 1
        assert budget_seconds(10**9) <= 300
        assert budget_seconds(None) == pytest.approx(120.0, abs=1)
        assert budget_seconds("viel") == pytest.approx(120.0, abs=1)


class TestClusterInvariant:
    """For the browser cluster SELF_GATED means: no dialog, in exchange its reach."""

    def test_no_dialog_is_paid_for_with_a_url_policy(self):
        from core.tools.approval import SELF_GATED_TOOLS, chat_tool_requires_confirm

        browser_names = {n for n in SELF_GATED_TOOLS if n.startswith("browser_")}
        assert browser_names
        for name in browser_names:
            assert chat_tool_requires_confirm(name) is False, name
        # The other half of the deal: without a dialog only reach is left, and
        # that one has to refuse every host address — including the one a model invents.
        for probe in ("file:///etc/passwd", "file:///Users/x/.ssh/id_rsa", "chrome://version"):
            ok, reason = url_policy(probe)
            assert ok is False and reason, probe
