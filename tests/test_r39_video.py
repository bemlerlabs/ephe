"""
Ephe — R39: reach video capability agentically.

Pins:
  1. ffmpeg/ffprobe are on the shell whitelist (segment-head check).
  2. create_video is a registered tool (TOOL_MAP + schema list).
  3. create_video without a case runs scripts/record_demo.py with no argument, and a
     missing recorder is refused before any subprocess starts.
  4. create_video(case) picks scripts/record_demo.py with the case argument.
  8. The recorder finds its Chromium and ffmpeg by lookup: newest cached browser
     wins, an override is honoured, and a missing tool names the way out.
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


def _recorder_placeholder(tmp_path):
    """A file at the recorder path: the wrapper refuses before it would shell out."""
    script = tmp_path / "scripts" / "record_demo.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# placeholder for the path check\n", encoding="utf-8")
    return script


@pytest.mark.asyncio
async def test_create_video_without_case_runs_the_recorder_over_every_case(monkeypatch, tmp_path):
    """GIVEN the recorder and no case
    WHEN create_video() runs against a fake subprocess.run
    THEN scripts/record_demo.py is invoked with no case argument, which is its own
    all-cases mode, and the stdout summary plus the PNG_FILE marker land in the result.

    The full-pipeline script this used to call was deleted in 3ccca950; the wrapper
    kept naming it, so the default call answered exit 2 on every machine.

    The hero is planted: the publication withholds the shipped banner by policy, and a
    test that reads it would pass only in the workshop."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    hero = tmp_path / "docs" / "screenshots" / "hero-banner.png"
    hero.parent.mkdir(parents=True)
    hero.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(video_tools, "_ROOT", str(tmp_path))
    monkeypatch.setattr(video_tools, "_RECORDER", str(_recorder_placeholder(tmp_path)))

    calls = []

    def fake_run(argv, capture_output=True, text=True, timeout=None):
        calls.append(list(argv))
        return SimpleNamespace(
            returncode=0,
            stdout="chat: video=/tmp/ephe_demo/raw/page@0a1b2c.webm\n"
            "WEBP chat: /tmp/ephe_demo/chat.webp (2150 KB, 150 Frames)\n",
            stderr="",
        )

    monkeypatch.setattr(video_tools.subprocess, "run", fake_run)
    result = await _cv()
    assert calls, "subprocess.run was never called"
    assert calls[0][1].endswith("record_demo.py")
    assert calls[0][2:] == [], "the all-cases call must not pass a case"
    assert "VIDEO_FILE:/tmp/ephe_demo/chat.webp" in result
    assert "PNG_FILE:" in result


@pytest.mark.asyncio
async def test_create_video_without_the_recorder_refuses_before_shelling_out(monkeypatch, tmp_path):
    """GIVEN a checkout whose recorder is gone
    WHEN create_video runs
    THEN the refusal names the missing path and no subprocess starts."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    monkeypatch.setattr(video_tools, "_ROOT", str(tmp_path))
    monkeypatch.setattr(video_tools, "_RECORDER", str(tmp_path / "scripts" / "record_demo.py"))

    started = []
    monkeypatch.setattr(
        video_tools.subprocess, "run",
        lambda *a, **k: started.append(a) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    result = await _cv(case="chat")
    assert "record_demo.py" in result
    assert not started


@pytest.mark.asyncio
async def test_create_video_case_selects_record_demo(monkeypatch, tmp_path):
    """GIVEN a single case ('chat')
    WHEN create_video('chat')
    THEN record_demo.py runs with the case argument."""
    from core.tools.video_tools import create_video as _cv
    from core.tools import video_tools

    calls = []
    monkeypatch.setattr(video_tools, "_RECORDER", str(_recorder_placeholder(tmp_path)))

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


# 8: the recorder resolves its own external tools

def _recorder_module():
    """The shipped recorder as a module: its lookups are the seam, its browser is not."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "record_demo.py"
    spec = importlib.util.spec_from_file_location("record_demo_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recorder_imports_with_more_than_one_cached_browser(monkeypatch):
    """GIVEN a machine whose Playwright was upgraded past the pinned revision
    WHEN scripts/record_demo.py is imported
    THEN the module loads — the pinned path used to raise IndexError at import."""
    monkeypatch.delenv("EPHE_CHROME_BIN", raising=False)
    module = _recorder_module()
    assert callable(module.find_chrome) and callable(module.preflight)


def test_recorder_picks_the_newest_cached_chromium(monkeypatch):
    """GIVEN two cached Chromium revisions
    WHEN find_chrome looks
    THEN the newest revision wins."""
    monkeypatch.delenv("EPHE_CHROME_BIN", raising=False)
    module = _recorder_module()
    monkeypatch.setattr(
        module.glob, "glob",
        lambda _pattern: ["/cache/chromium-1234/Google Chrome for Testing",
                          "/cache/chromium-1248/Google Chrome for Testing"],
    )
    assert module.find_chrome().endswith("chromium-1248/Google Chrome for Testing")


def test_recorder_takes_an_explicit_browser_and_distrusts_a_stale_one(monkeypatch, tmp_path):
    """GIVEN EPHE_CHROME_BIN
    WHEN find_chrome looks
    THEN an existing binary is taken and a path that leads nowhere is answered as none."""
    module = _recorder_module()
    binary = tmp_path / "chrome"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("EPHE_CHROME_BIN", str(binary))
    assert module.find_chrome() == str(binary)
    monkeypatch.setenv("EPHE_CHROME_BIN", str(tmp_path / "gone" / "chrome"))
    assert module.find_chrome() is None


def test_recorder_names_the_way_out_when_a_tool_is_missing(monkeypatch):
    """GIVEN a machine with neither a cached browser nor ffmpeg
    WHEN preflight runs before any browser opens
    THEN each refusal names the command that would fix it."""
    module = _recorder_module()
    monkeypatch.delenv("EPHE_CHROME_BIN", raising=False)
    monkeypatch.delenv("EPHE_FFMPEG_BIN", raising=False)
    monkeypatch.setattr(module.glob, "glob", lambda _pattern: [])
    with pytest.raises(SystemExit) as missing_browser:
        module.preflight()
    assert "playwright install chromium" in str(missing_browser.value)

    monkeypatch.setattr(module.glob, "glob", lambda _pattern: ["/cache/chromium-1248/chrome"])
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit) as missing_ffmpeg:
        module.preflight()
    assert "EPHE_FFMPEG_BIN" in str(missing_ffmpeg.value)


def test_recorder_films_the_served_app_by_default(monkeypatch):
    """GIVEN no override for the target
    WHEN the recorder is imported
    THEN it aims at the product server, because a capture shows the built app and the
    Vite dev server only exists during `pnpm run dev`."""
    monkeypatch.delenv("EPHE_DEMO_APP_URL", raising=False)
    module = _recorder_module()
    assert "8765" in module.APP and module.APP.endswith("#/chat")
