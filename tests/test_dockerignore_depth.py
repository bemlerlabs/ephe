"""The private-state entries `.dockerignore` names are anchored so they match at any depth.

`.dockerignore` opens by stating its own rule: patterns are `**`-anchored so they match at any
depth, because a bare `node_modules` only matches the context root, which is how `app/node_modules`
leaked into every build. Three entries went against that promise until 2026-11-01 — `.env`,
`.DS_Store` and `*.log` were bare, so `app/.env`, the dotenv a developer is most likely to hold,
rode into the image with the rest of the build context. The test reads the file a build would use,
so the header and the entries cannot drift apart again.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE = ROOT / ".dockerignore"

#: Classes the hygiene gate refuses as tracked artifacts and a build context can equally carry: a
#: dotenv holds a credential, a `.DS_Store` is a directory listing, a log is session text.
PRIVATE_STATE = [".env", ".DS_Store", "*.log"]


def entries() -> list[str]:
    return [line.strip() for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def to_regex(pattern: str) -> str:
    """Docker's matcher: `**` spans any number of path segments including none, `*` stays inside
    one segment, and a pattern with no slash is anchored to the context root."""
    pieces = []
    segments = pattern.split("/")
    for index, segment in enumerate(segments):
        if segment == "**":
            pieces.append("(?:[^/]+/)*")
            continue
        token = "".join({"*": "[^/]*", "?": "[^/]"}.get(ch, re.escape(ch)) for ch in segment)
        pieces.append(token + ("/" if index < len(segments) - 1 else ""))
    return "^" + "".join(pieces) + "$"


def matches(pattern: str, path: str) -> bool:
    return bool(re.match(to_regex(pattern), path))


class TestDepthAnchoring:
    def test_every_private_state_entry_is_anchored(self):
        present = entries()
        for name in PRIVATE_STATE:
            assert f"**/{name}" in present, name
            assert name not in present, f"{name} still matches only at the context root"

    def test_the_anchored_entry_reaches_the_nested_file(self):
        assert matches("**/.env", "app/.env")
        assert matches("**/.env", "core/deep/nested/.env")
        assert matches("**/*.log", "server/logs/run.log")

    def test_the_promise_holds_at_the_root_too(self):
        """`**` means any number of segments, so the same entry must still catch the root file."""
        assert matches("**/.env", ".env")
        assert matches("**/.DS_Store", ".DS_Store")

    def test_the_templates_a_build_needs_stay_in_the_context(self):
        """`.env.example` ships so a newcomer can copy it; an over-broad dotenv rule would strip
        the file the README points at."""
        assert not matches("**/.env", ".env.example")
        assert not matches("**/.env", "app/.env.example")

    def test_the_header_still_states_the_rule_the_entries_follow(self):
        text = "\n".join(DOCKERIGNORE.read_text(encoding="utf-8").splitlines()[:3])
        assert "Patterns are **-anchored" in text
