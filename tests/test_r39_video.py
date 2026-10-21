"""
Ephe — R39: reach video capability agentically.

Pins:
  1. ffmpeg/ffprobe are on the shell whitelist (segment-head check).
  2. create_video is a registered tool (TOOL_MAP + schema list).
  3. create_video(None) wraps scripts/create_demo_media.py (the v4 pipeline).
  4. create_video(case) picks scripts/record_demo.py with the case argument.
  5. An invalid case => an honest error string, no abort.
  6. The video-creator skill (/video) resolves and declares that tool.
  7. create_video is mutating (not in SAFE_TOOLS / CHAT_AUTO_RUN) — the
     conservative approval gate stays exactly as strict.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# 1: ffmpeg on the whitelist

def test_ffmpeg_and_ffprobe_are_whitelisted():
    """GIVEN the shell segment whitelist
    WHEN ffmpeg/ffprobe are checked as the segment head
    THEN both are admitted (None = allowed)."""
    from core.tools.base import ALLOWED_COMMANDS
    from core.tools.shell_tools import validate_shell_command

    assert "ffmpeg" in ALLOWED_COMMANDS
    assert "ffprobe" in ALLOWED_COMMANDS
    assert validate_shell_command("ffmpeg -y -i a.webm b.gif") is None
    # Redirects stay blocked (the existing guard, 1:1 next to ffmpeg).
    assert validate_shell_command("ffmpeg -y -i a.webm > b.gif") is not None


# 2 + 3 + 4 + 5: the create_video tool

def test_create_video_registered_in_tool_map_and_schemas():
    """GIVEN the tool registry
    WHEN TOOL_MAP and get_tool_schemas() are read
    THEN create_video exists in both."""
    from core.tools import create_video  # noqa: F401
    from core.tools.registry import TOOL_MAP, get_tool_schemas

    assert "create_video" in TOOL_MAP
    names = [s["function"]["name"] for s in get_tool_schemas()]
    assert "create_video" in names


@pytest.mark.asyncio
async def test_create_video_full_pipeline(monkeypatch):
    """GIVEN the v4 demo pipeline (no case)
    WHEN create_video(None) runs against a fake subprocess.run
    THEN scripts/create_demo_media.py is invoked and the
    stdout summary plus the PNG_FILE marker land in the result."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    calls = []

    def fake_run(argv, capture_output=True, text=True, timeout=None):
        calls.append(list(argv))
        return SimpleNamespace(
            returncode=0,
            stdout="chat.webp\n  ephe-demo-chat.webp: 2.10 MB (1280px @30fps)\n"
            "Done. README assets refreshed in docs/media/ + docs/screenshots/hero-banner.png",
            stderr="",
        )

    monkeypatch.setattr(video_tools.subprocess, "run", fake_run)
    result = await _cv()
    assert calls, "subprocess.run wurde nicht aufgerufen"
    assert "create_demo_media.py" in calls[0][1]
    assert "ephe-demo-chat.webp" in result
    assert "PNG_FILE:" in result


@pytest.mark.asyncio
async def test_create_video_case_selects_record_demo(monkeypatch):
    """GIVEN a single case ('chat')
    WHEN create_video('chat')
    THEN record_demo.py runs with the case argument."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    calls = []

    def fake_run(argv, capture_output=True, text=True, timeout=None):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="captured chat.webm\n", stderr="")

    monkeypatch.setattr(video_tools.subprocess, "run", fake_run)
    result = await _cv(case="chat")
    assert calls[0][1].endswith("record_demo.py")
    assert "chat" in calls[0]
    assert "chat" in result


@pytest.mark.asyncio
async def test_create_video_unknown_case_is_honest_error(monkeypatch):
    """GIVEN an unknown case
    WHEN create_video('bogus')
    THEN the result is an honest error string, not an abort."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    monkeypatch.setattr(
        video_tools.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="x", stderr=""),
    )
    result = await _cv(case="bogus")
    assert "[video" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_create_video_timeout_is_honest_error(monkeypatch):
    """GIVEN a pipeline timeout
    WHEN create_video raises a timeout exception
    THEN an honest error string instead of a pseudo-complete."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    def fake_run(argv, capture_output=True, text=True, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(video_tools.subprocess, "run", fake_run)
    result = await _cv()
    assert "timeout" in result.lower() or "error" in result.lower()


# 6: the video-creator skill

def test_video_skill_resolves_and_declares_tool():
    """GIVEN the video-creator pack
    WHEN resolve_trigger('/video')
    THEN it resolves and declares create_video."""
    from pathlib import Path

    from core.skills import BUILTIN_SKILLS_DIR, SkillLoader

    loader = SkillLoader(skills_dir=Path("/tmp/ephe-no-user-skills"), builtin_dir=BUILTIN_SKILLS_DIR)
    skill = loader.resolve_trigger("/video")
    assert skill is not None
    assert "create_video" in (skill.tools or [])


# 7: the approval classification stays conservative

def test_create_video_is_mutating_for_approval():
    """GIVEN the approval classification
    WHEN create_video is classified
    THEN it is mutating (not auto-approved) — same as the other creators."""
    from core.tools.approval import SAFE_TOOLS, CHAT_AUTO_RUN_TOOLS, classify_tool

    assert "create_video" not in SAFE_TOOLS
    assert "create_video" not in CHAT_AUTO_RUN_TOOLS
    cls = classify_tool("create_video")
    assert cls.is_mutating is True
    assert cls.auto_approve_by_default is False
