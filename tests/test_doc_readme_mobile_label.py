"""The install walkthrough names the label the app actually renders.

The README's "Phone Via QR" step told a reader to ``Click **Connect Phone**``.
No such string exists in ``app/src``: the panel is headed by
``settings.mobileTitle`` (``app/src/locales/en.json:601``), rendered through
``PageHeader`` in ``app/src/components/dashboard/settings/model/sections-io.tsx``.
A step that names a control the UI does not show is a step the reader cannot
follow.

The label is read from the shipped locale, not hard-coded here, so the two can
only agree by the README quoting the app.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EN_LOCALE = REPO / "app" / "src" / "locales" / "en.json"

# The documents that tell a user what to click. The triage and audit notes quote
# the stale string as a finding, so they are deliberately not scanned.
INSTALL_DOCS = [
    REPO / "README.md",
    REPO / "README.es.md",
    REPO / "README.zh-CN.md",
    REPO / "docs" / "whitepaper-ephe.md",
]

PHONE_STEP_MARKER = "Click **"


def _mobile_title() -> str:
    return json.loads(EN_LOCALE.read_text(encoding="utf-8"))["settings"]["mobileTitle"]


def test_english_locale_carries_the_label_the_panel_renders() -> None:
    """GIVEN the shipped English copy WHEN read THEN the mobile panel's title is a real string."""
    assert _mobile_title() == "Connect mobile"


def test_readme_phone_step_names_that_label() -> None:
    """
    GIVEN the README's phone walkthrough
    WHEN step 3 names the control to click
    THEN it quotes the label the app renders
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"{PHONE_STEP_MARKER}{_mobile_title()}**" in readme


def test_no_install_doc_names_a_label_the_app_does_not_render() -> None:
    """
    GIVEN every document that tells a user what to click
    WHEN it names the mobile panel
    THEN it never uses the retired wording
    """
    offenders = [
        f"{doc.relative_to(REPO)}:{n}"
        for doc in INSTALL_DOCS
        # The whitepaper is a workshop document the published tree does not carry, and a
        # document that is not there names nothing.
        if doc.is_file()
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1)
        if "Connect Phone" in line
    ]
    assert offenders == []
