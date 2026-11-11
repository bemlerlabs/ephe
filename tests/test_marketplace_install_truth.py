"""QA residue 1 — the shipped listing only offers artifacts that can be installed.

`plugin-marketplace.json` carried three entries (`web-search`, `document-factory`,
`coding-suite`) whose `url` and `sha256` were empty. `ephe plugin install web-search`
therefore ended in `no_url` on every call. Those three names are the pre-v2 slugs of
plugins that ship with this repository (`core/plugin_store.LEGACY_SLUG_MAP`); no artifact
was ever hosted for them, and this tree publishes artifacts through the format-2 index
(`marketplace/index.json`) with its local/bundled sources instead.

A listing entry that cannot be fetched is not a listing entry: the file now declares no
v1 artifact, and the install command names the bundled plugin the id stands for and the
switch that turns it on.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LISTING = ROOT / "plugin-marketplace.json"

#: Old capability slugs, and the bundled plugins they are a name for. The mapping is
#: `core/plugin_store.LEGACY_SLUG_MAP`; this table only pins the answer a user sees.
LEGACY = {
    "web-search": ("web-research",),
    "coding-suite": ("code-shell",),
    "document-factory": ("documents", "spreadsheets", "presentations"),
}


def _listing() -> dict:
    return json.loads(LISTING.read_text(encoding="utf-8"))


def test_every_listed_artifact_carries_a_url_and_a_hash() -> None:
    """An entry without a fetchable URL is a promise the installer cannot keep."""
    for entry in _listing()["plugins"]:
        url = str(entry.get("url") or "")
        sha = str(entry.get("sha256") or "")
        assert re.fullmatch(r"https://\S+", url), entry
        assert re.fullmatch(r"[0-9a-f]{64}", sha), entry


def test_the_legacy_slugs_are_not_offered_as_installable() -> None:
    from core.plugin_store import LEGACY_SLUG_MAP

    listed = {str(entry.get("name")) for entry in _listing()["plugins"]}
    assert listed.isdisjoint(LEGACY_SLUG_MAP), (
        "a pre-v2 slug is a name for a bundled plugin, not an artifact URL: "
        f"{sorted(listed & set(LEGACY_SLUG_MAP))}"
    )


def test_the_listing_says_where_the_bundled_plugins_come_from() -> None:
    """The file stays, so it has to say what it is for instead of listing stubs."""
    data = _listing()
    assert data["plugins"] == []
    note = str(data.get("note") or "")
    assert "marketplace/index.json" in note, note
    assert "sha256" in note, note


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    plugin_id: str,
) -> tuple[int, str]:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    import ephe_cli

    args = argparse.Namespace(action="install", plugin_id=plugin_id, trust_local=False)
    rc = ephe_cli.cmd_plugin(args)
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


@pytest.mark.parametrize(("plugin_id", "successors"), sorted(LEGACY.items()))
def test_install_names_the_bundled_plugin_instead_of_no_url(
    plugin_id: str,
    successors: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, printed = _install(monkeypatch, tmp_path, capsys, plugin_id)
    assert rc == 1
    assert "no_url" not in printed, printed
    assert "ships with Ephe" in printed, printed
    for successor in successors:
        assert successor in printed, printed
    assert f"ephe plugin enable {successors[0]}" in printed, printed


def test_install_of_an_id_nobody_declares_keeps_the_listing_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc, printed = _install(monkeypatch, tmp_path, capsys, "no-such-plugin")
    assert rc == 1
    assert "plugin-marketplace.json" in printed, printed
