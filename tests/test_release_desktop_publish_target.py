"""The desktop release publishes to one named repository, with one release body.

`scripts/release_desktop.sh` runs where a checkout's first remote is not the repository the
release belongs to: on the release machine `origin` is the private development history, so a
bare `gh release create` publishes the updater artifacts there while the feed it writes points
at the public repository. The script therefore names its target, and the feed's URL and the
`gh` calls read one variable.

The same script writes the updater feed's `notes`. It used to slice CHANGELOG.md by hand and
take the block under the first `## ` header, which is `[Unreleased]`, so the update window
showed a sha inventory instead of the release being installed. The release workflow already
owns the right instrument for that text, and the script defers to it.

And it signs with the key the app trusts. Measured on 2026-11-01: this machine's key carries id
`6cf6767f2631dfdd` while `tauri.conf.json` pins `e01157dba5c1d5b5` — the release environment's
key, the one that signed the published 0.5.2 artifact. A bundle signed with the other key
uploads cleanly and no client installs it, so the run stops on a probe signature before the
build starts.
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


def test_the_feed_notes_come_from_the_release_body_instrument():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python3 scripts/release_notes.py" in text, (
        "the feed's notes and the release description are the text the workflow cuts"
    )
    assert "split('\n## ')" not in text, (
        "the hand slice read [Unreleased], which is not the release being installed"
    )


def test_the_key_guard_runs_before_the_bundle_is_built():
    text = SCRIPT.read_text(encoding="utf-8")
    probe = text.find("key-probe")
    build = text.find("npx tauri build")
    assert probe != -1 and build != -1, "the probe sign and the bundle build are both here"
    assert probe < build, "a wrong key has to stop the run before the build spends its minutes"
    assert "pinned updater key" in text or "the app pins" in text, (
        "the refusal names both ids, because the reader cannot tell a stale feed from a "
        "foreign key without them"
    )
