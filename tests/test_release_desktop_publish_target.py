"""The desktop release publishes to one named repository.

`scripts/release_desktop.sh` runs where a checkout's first remote is not the repository the
release belongs to: on the release machine `origin` is the private development history, so a
bare `gh release create` publishes the updater artifacts there while the feed it writes points
at the public repository. The script therefore names its target, and the feed's URL and the
`gh` calls read one variable.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_desktop.sh"


def commands() -> list[str]:
    """The script with every backslash continuation folded into one line."""
    text = SCRIPT.read_text(encoding="utf-8")
    folded = re.sub(r"\\\s*\n\s*", " ", text)
    return [line.strip() for line in folded.splitlines()]


def test_the_publish_target_is_a_variable_with_a_default():
    pattern = re.compile(r'^RELEASE_REPO="\$\{EPHE_RELEASE_REPO:-[^}]+\}"$')
    assert any(pattern.match(line) for line in commands()), (
        "the release repository must default in the script and take an override from the caller"
    )


def test_every_gh_release_call_names_the_repository():
    calls = [line for line in commands() if re.search(r"\bgh release\b", line)]
    assert calls, "the script still publishes through gh release"
    # The quoted form runs the call; the bare one appears in the lines the script
    # prints for an operator to paste. Both must carry the target, because a
    # suggested command that resolves to the wrong repository is still a wrong command.
    targeted = re.compile(r'--repo "?\$RELEASE_REPO"?')
    untargeted = [line for line in calls if not targeted.search(line)]
    assert not untargeted, f"gh release call without a target: {untargeted}"


def test_the_feed_url_and_the_publish_call_read_the_same_value():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "https://github.com/${repo}/releases/download/" in text, (
        "the updater URL must come from the same repository the artifacts are uploaded to"
    )
    feed = [line for line in commands() if line.startswith("node - ") and "$FEED" in line]
    assert feed and '"$RELEASE_REPO"' in feed[0], (
        "the block that writes latest.json is handed the repository, not a literal"
    )
    assert "github.com/bemlerlabs/ephe/releases" not in text, (
        "no second copy of the target may sit in the script"
    )
