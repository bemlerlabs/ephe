#!/usr/bin/env python3
"""Render the first-open choreography to a 60 fps film.

`IntroFilm` renders an exact frame for any timestamp (`__epheIntroSeek`), so this
script seeks the 768 frames of the 12.8 s film, captures each one, and encodes MP4
and WebM from the same frame sequence. Run it after changing the choreography.

    python3 scripts/render_onboarding_film.py [--fps 60] [--viewport 1280x720]
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
OUT = APP / "public/onboarding"
PORT = 5199
BASE = f"http://127.0.0.1:{PORT}"
FILM_SECONDS = 12.8


def wait_for_server(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except OSError:
            time.sleep(0.25)
    raise SystemExit(f"dev server did not answer on {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--viewport", default="1280x720")
    parser.add_argument("--base-url", help="use a running dev server instead of starting one")
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("python playwright is not installed")

    width, height = (int(part) for part in args.viewport.lower().split("x"))
    frames_dir = Path(tempfile.mkdtemp(prefix="ephe-film-"))
    server = None
    try:
        if not args.base_url:
            server = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", str(PORT), "--strictPort"],
                cwd=APP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            wait_for_server(BASE)
        base = args.base_url or BASE

        total = round(FILM_SECONDS * args.fps)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.emulate_media(reduced_motion="no-preference")
            page.goto(f"{base}/?film=capture", wait_until="load")
            page.wait_for_function("typeof window.__epheIntroSeek === 'function'", timeout=30_000)
            page.wait_for_function(
                "Array.from(document.images).every((img) => img.complete && img.naturalWidth > 0)",
                timeout=30_000,
            )
            page.evaluate("document.documentElement.style.background = '#020504'")
            for index in range(total):
                stamp = index * 1000 / args.fps
                page.evaluate("(ms) => window.__epheIntroSeek(ms)", stamp)
                page.screenshot(path=str(frames_dir / f"f{index:04d}.png"))
                if index % 60 == 0:
                    print(f"frame {index}/{total}", flush=True)
            browser.close()

        score = frames_dir / "score.wav"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/generate_onboarding_audio.py"), "--out", str(score)],
            check=True,
        )

        OUT.mkdir(parents=True, exist_ok=True)
        mp4 = OUT / "first-run-film.mp4"
        webm = OUT / "first-run-film.webm"
        subprocess.run(
            [
                "ffmpeg", "-y", "-framerate", str(args.fps),
                "-i", str(frames_dir / "f%04d.png"),
                "-i", str(score),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(mp4),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "31",
                "-row-mt", "1", "-cpu-used", "3",
                "-c:a", "libopus", "-b:a", "160k", "-shortest", str(webm),
            ],
            check=True,
        )
        print(f"{mp4} {mp4.stat().st_size / 1e6:.1f} MB")
        print(f"{webm} {webm.stat().st_size / 1e6:.1f} MB")
        return 0
    finally:
        if server is not None:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if args.keep_frames:
            print(f"frames kept in {frames_dir}")
        else:
            shutil.rmtree(frames_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
