#!/usr/bin/env python3
"""Ephe PWA live demo recorder: Playwright record_video -> animated WebPs.

Usage: .venv/bin/python scripts/record_demo.py [case ...]
Cases: chat shell help edit  (default: all)
"""
import asyncio
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

#: The recorder films the built app. The product server serves it on :8765; the Vite
#: dev server on :5173 only exists while someone runs `pnpm run dev`.
APP = os.environ.get("EPHE_DEMO_APP_URL", "http://127.0.0.1:8765/#/chat")
OUT = Path("/tmp/ephe_demo")

#: Playwright names its cached browsers by revision, and the revision moves on every
#: Playwright upgrade. A pinned number kills this script at import with an IndexError
#: (measured: chromium-1228 gone, 1234 and 1248 present), so the newest match wins.
_CHROME_GLOB = (
    "Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)


def find_chrome() -> str | None:
    """The Chromium to launch: an explicit override, else the newest cached build."""
    override = str(os.environ.get("EPHE_CHROME_BIN") or "").strip()
    if override:
        return override if os.path.isfile(override) else None
    found = sorted(glob.glob(str(Path.home() / _CHROME_GLOB)))
    return found[-1] if found else None


def find_ffmpeg() -> str | None:
    """ffmpeg for the frame extraction; Playwright's own build has no PNG encoder."""
    override = str(os.environ.get("EPHE_FFMPEG_BIN") or "").strip()
    if override:
        return override if os.path.isfile(override) else None
    return shutil.which("ffmpeg")


def preflight() -> tuple[str, str]:
    """Resolve the two external tools before a browser opens, or say what is missing."""
    chrome = find_chrome()
    if chrome is None:
        raise SystemExit(
            "record_demo: no Chromium in the Playwright cache — run "
            "`playwright install chromium` or set EPHE_CHROME_BIN to the binary"
        )
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise SystemExit(
            "record_demo: no ffmpeg on PATH — install ffmpeg or set EPHE_FFMPEG_BIN"
        )
    return chrome, ffmpeg



async def approve_loop(page, rounds=4):
    """Wait for the 'Zulassen' button and click it (tool approvals in the demo)."""
    clicked = 0
    for _ in range(rounds):
        btn = page.locator("button", has_text="Zulassen").first
        try:
            await btn.wait_for(state="visible", timeout=45000)
            await btn.click()
            clicked += 1
            await page.wait_for_timeout(4000)
        except Exception:
            break
    return clicked


async def record_case(p, case: str, chrome: str):
    b = await p.chromium.launch(headless=True, executable_path=chrome)
    ctx = await b.new_context(
        viewport={"width": 2560, "height": 1600},  # native 2K
        record_video_dir=str(OUT / "raw"),
        record_video_size={"width": 2560, "height": 1600},
    )
    page = await ctx.new_page()
    await page.goto(APP)
    await page.wait_for_timeout(4500)  # UI boot + stream connection
    ta = page.locator("textarea")
    await ta.click()

    if case == "chat":
        await page.keyboard.type("Erkläre in zwei Sätzen, was Ephe ist und warum Offline-KI sinnvoll ist.")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(60000)  # DGX TTFB + streaming
    elif case == "shell":
        await page.keyboard.type("Führe aus: echo EPHE_LIVE && uname -s")
        await page.keyboard.press("Enter")
        await approve_loop(page, 1)
        await page.wait_for_timeout(20000)
    elif case == "help":
        await page.keyboard.type("/help")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(15000)
    elif case == "edit":
        await page.keyboard.type("Ersetze in /tmp/ephe_demo_notiz.txt den Text ALT durch NEU mit edit_file. Lege die Datei vorher mit run_shell an (echo ALT > Datei).")
        await page.keyboard.press("Enter")
        await approve_loop(page, 3)
        await page.wait_for_timeout(18000)

    await ctx.close()  # flushes the video
    await b.close()
    vids = sorted(glob.glob(str(OUT / "raw" / "*.webm")), key=lambda p: Path(p).stat().st_mtime)
    return vids[-1]


def to_webp(video: str, case: str, ffmpeg: str):
    out = OUT / f"{case}.webp"
    subprocess.run([ffmpeg, "-y", "-i", video, "-vf", "fps=5",
                    str(OUT / f"{case}_f%04d.png")], check=True, capture_output=True)
    from PIL import Image
    frames = sorted(OUT.glob(f"{case}_f*.png"))
    step = max(1, len(frames) // 150)
    # keep native 2K; 256-colour palette + hq method = the sharpest WebP export
    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE, colors=255) for p in frames[::step]]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=200, loop=0, quality=75, method=6)
    for p in frames:
        p.unlink()
    print(f"WEBP {case}: {out} ({out.stat().st_size // 1024} KB, {len(imgs)} Frames)")


async def main():
    chrome, ffmpeg = preflight()
    cases = sys.argv[1:] or ["chat", "shell", "help", "edit"]
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        for case in cases:
            v = await record_case(p, case, chrome)
            print(f"{case}: video={v}")
            to_webp(v, case, ffmpeg)


if __name__ == "__main__":
    asyncio.run(main())
