"""The three lines a person reads when they start Ephe, and what each one is allowed to say.

`docs/BRAND.md` section 4 lists the terminal's start banner as a surface with its own form of
the pitch. The orb line carries the version and the stance the folder modes make countable;
under it sit the headline the owner set and the hero line chosen for it. Before this file no
test read the banner at all, so a wording change reached `ephe start` unremarked.

The second assertion is section 3's claim boundary applied to a terminal string: `private`
survives on the orb line and nowhere else in the banner, because `core/persistence.py` writes
that folder `0600` and `tests/test_device_folder_modes.py` measures it — a word standing on a
`stat()` result is not the same word standing on a hope.
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import ephe_cli

BRAND_HEADLINE = "Where the light is, the work happens."
HERO_LINE = "Your agent. Your machine. Your memory."


def _start_args() -> argparse.Namespace:
    return argparse.Namespace(
        port=8899,
        host="127.0.0.1",
        lan=False,
        reload=False,
        open=False,
        model=None,
        skip_model_check=True,
        takeover=False,
    )


def _quiet_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """The start path down to the banner: no port probe, no engine, no build, no child."""
    monkeypatch.setattr(
        ephe_cli,
        "_start_preflight",
        lambda args: SimpleNamespace(allowed=True, message="", stopped=False, reused=False),
    )
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **kwargs: None)
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)
    monkeypatch.setattr(ephe_cli, "_run", lambda *args, **kwargs: SimpleNamespace(returncode=0))


def banner_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_the_start_banner_opens_with_orb_headline_and_hero_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _quiet_start(monkeypatch)

    assert ephe_cli.cmd_start(_start_args()) == 0
    assert banner_lines(capsys)[:3] == [
        f"◍ Ephe {ephe_cli.EPHE_VERSION} — local & private",
        BRAND_HEADLINE,
        HERO_LINE,
    ]


def test_only_the_measured_line_in_the_banner_says_private(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _quiet_start(monkeypatch)
    ephe_cli.cmd_start(_start_args())

    for line in banner_lines(capsys)[:3]:
        if "private" in line.lower():
            assert line.startswith("◍ Ephe"), f"an uncountable private claim in the banner: {line}"
