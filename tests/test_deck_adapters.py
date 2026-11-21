"""tests/test_deck_adapters.py — the env -> optional-adapter decision.

`core/deck_adapters.py` is the discovery layer of Deck Engine v2: the local renderer
stays the default and every external engine is opt-in through one env var. Both opt-ins
used to read their variable TWICE (`get(X) or get(X, ...)`) and the two operands did not
agree, so the value the user typed lost whenever it was truthy-but-not-what-the-second
call-wanted. Measured before the fix:

    EPHE_PRESENTON_URL="   "           -> presenton reported as AVAILABLE
    EPHE_ENABLE_PPTXGENJS="false"      -> pptxgenjs ENABLED (a disable was an enable)
    EPHE_ENABLE_PPTXGENJS="   "        -> pptxgenjs ENABLED

These are env-level pins, so the node dependency that `available` also carries is stubbed
out on PATH instead of being left to whatever the machine has installed.
"""
from __future__ import annotations

import logging

import pytest

from core.deck_adapters import optional_adapter_status

PRESENTON = "EPHE_PRESENTON_URL"
PPTXGENJS = "EPHE_ENABLE_PPTXGENJS"


@pytest.fixture(autouse=True)
def _clean_adapter_env(monkeypatch):
    """The status reads the process env at CALL time — a value inherited from the
    developer's shell or from an earlier test would decide the assertion for us."""
    for name in (PRESENTON, PPTXGENJS):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def node_installed(tmp_path, monkeypatch):
    """A deterministic `node` on PATH: `available` is the AND of the flag and the
    binary, and only a stubbed binary lets these tests speak about the flag."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "node"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return stub


@pytest.fixture
def node_missing(tmp_path, monkeypatch):
    """The other half: PATH without a node binary."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


def _adapters() -> dict:
    return optional_adapter_status()["adapters"]


class TestPresentonDiscovery:
    def test_given_unset_url_when_status_then_unavailable(self):
        """GIVEN nobody configured Presenton
        THEN the adapter is not available and names no configuration source."""
        adapter = _adapters()["presenton"]
        assert adapter["available"] is False
        assert adapter["configured_by"] == ""

    @pytest.mark.parametrize("value", ["", "   ", " \t ", "  \n "])
    def test_given_blank_url_when_status_then_whitespace_reads_unset(self, monkeypatch, value):
        """GIVEN EPHE_PRESENTON_URL holding only whitespace
        THEN the adapter stays unavailable — the .strip() that would have caught this
        sat on the SECOND read, and the un-stripped "   " of the first one is truthy."""
        monkeypatch.setenv(PRESENTON, value)
        assert _adapters()["presenton"]["available"] is False

    def test_given_configured_url_when_status_then_available(self, monkeypatch):
        """GIVEN a real value (surrounded by the whitespace a shell tends to add)
        THEN the adapter is available and points at the variable that enabled it.

        The value is a sentinel, not an endpoint: nothing here dials a host, and no
        address belongs in the repository."""
        monkeypatch.setenv(PRESENTON, "  presenton-sentinel-value  ")
        adapter = _adapters()["presenton"]
        assert adapter["available"] is True
        assert adapter["configured_by"] == PRESENTON
        assert adapter["hard_dependency"] is False

    def test_given_unset_var_when_status_then_no_host_is_invented(self):
        """GIVEN no Presenton configuration at all
        THEN the discovery layer neither claims an adapter nor names another one — the
        local engine stays the only active strategy (no silent default)."""
        status = optional_adapter_status()
        assert status["active"] == "local_engine_v2"
        assert status["hard_dependency"] is False
        assert status["adapters"]["presenton"]["available"] is False


class TestPptxgenjsEnablement:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " Yes "])
    def test_given_trueish_flag_when_status_then_enabled(self, monkeypatch, node_installed, value):
        """GIVEN an unambiguous affirmative value and node on PATH
        THEN the adapter is available and says which variable turned it on."""
        monkeypatch.setenv(PPTXGENJS, value)
        adapter = _adapters()["pptxgenjs"]
        assert adapter["available"] is True
        assert adapter["configured_by"] == PPTXGENJS

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", "  No  "])
    def test_given_negative_flag_when_status_then_disabled(self, monkeypatch, node_installed, value):
        """GIVEN the user DISABLES the adapter
        THEN it is disabled — even though "false" is a non-empty string.

        The defect this pins: the second operand produced a bool, so the truthy STRING
        "false" won the `or` and a disable came back as an enable."""
        monkeypatch.setenv(PPTXGENJS, value)
        adapter = _adapters()["pptxgenjs"]
        assert adapter["available"] is False
        assert adapter["configured_by"] == ""

    @pytest.mark.parametrize("value", ["", "   ", " \t "])
    def test_given_blank_flag_when_status_then_disabled_without_a_warning(self, monkeypatch, node_installed, caplog, value):
        """GIVEN a blank EPHE_ENABLE_PPTXGENJS
        THEN the adapter is off and nothing is shouted: blank reads as unset, not as a
        value somebody needs to be corrected about."""
        monkeypatch.setenv(PPTXGENJS, value)
        adapter = _adapters()["pptxgenjs"]
        assert adapter["available"] is False
        assert adapter["configured_by"] == ""
        with caplog.at_level(logging.WARNING):
            assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    @pytest.mark.parametrize("value", ["banana", "2", "maybe", "enable", "y"])
    def test_given_unparseable_flag_when_status_then_disabled_with_reason(self, monkeypatch, node_installed, caplog, value):
        """GIVEN a value that is neither yes nor no
        THEN the adapter is DISABLED and the log says why — an odd input never opts a
        cost- and supply-relevant external engine in, it fails closed."""
        monkeypatch.setenv(PPTXGENJS, value)
        with caplog.at_level(logging.WARNING, logger="core.deck_adapters"):
            adapter = _adapters()["pptxgenjs"]
        assert adapter["available"] is False
        assert adapter["configured_by"] == ""
        reasons = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert reasons, "the rejected value has to stay visible"
        assert PPTXGENJS in reasons[0]
        assert value in reasons[0]

    def test_given_enabled_flag_without_node_when_status_then_hard_dependency_stays_false(
        self, monkeypatch, node_missing
    ):
        """GIVEN the flag says yes but no node binary exists
        THEN the adapter is unavailable while the variable stays the configuration
        source, and nothing becomes a hard dependency."""
        monkeypatch.setenv(PPTXGENJS, "true")
        adapter = _adapters()["pptxgenjs"]
        assert adapter["available"] is False
        assert adapter["configured_by"] == PPTXGENJS
        assert adapter["hard_dependency"] is False

    def test_given_both_vars_unset_when_status_then_shape_is_untouched(self):
        """GIVEN the plain default state
        THEN the reported shape is the one the deck spec embeds — an added key or a
        renamed adapter would break every consumer at once."""
        status = optional_adapter_status()
        assert set(status) == {"active", "hard_dependency", "adapters"}
        assert set(status["adapters"]) == {"presenton", "pptxgenjs"}
        for adapter in status["adapters"].values():
            assert set(adapter) == {"available", "configured_by", "hard_dependency"}
