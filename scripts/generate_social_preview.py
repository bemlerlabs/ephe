"""Ephe — social preview card (1200x630).

scripts/generate_social_preview.py

One source for the share card: an HTML composition rendered through
Playwright/Chromium (the repo's reference renderer) straight at 2x and downscaled
to exactly 1200x630 — the Open Graph / Twitter `summary_large_image` size.

What it draws (all of it from tokens the app already ships):
- ground   = --color-canvas #15120F, lifted with a --color-surface #1D1917
             highlight and a darker falloff; the only ground the product offers
             since the paper theme was retired (2026-10-19)
- figure   = app/public/onboarding/bee-3d-hero.png, the shipped bee artwork the
             icon kit and the first-run scene carry, inlined as a data URI so the
             card cannot point at a file that moved. 2120x1504 at source, which is
             what the 2x render of this card needs
- type     = Space Grotesk (display), Inter (body), JetBrains Mono (kicker/footer),
             self-hosted @fontsource woff2 — never a system fallback
- colour   = --color-brand #E8543F for the kicker (5.13:1 on the canvas),
             --color-ink #F2EFE8 for the headline, --color-ink-soft / -faint for
             the body and footer; --color-hairline #2E2926 for the inset rule

Copy is the app's own, not invented: "researches, builds and delivers. You watch
live." is the welcome hero sub (app/src/locales/en.json welcome.heroSub); the
headline restates the brand press-release line (docs/BRAND.md section 4). No
"never / no trace / private" claim — the card says what Ephe does, and nothing it
cannot do.

Outputs (both the same bytes):
- docs/media/ephe-social-preview-1200x630.png   (the tracked asset)
- app/public/og-image.png                       (served copy for og:image)

Run:  .venv/bin/python scripts/generate_social_preview.py
Deterministic: no network, no system font, no hand-scaling — re-runs byte-identical
on the same Chromium revision.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
FONTS = APP / "node_modules" / "@fontsource"

#: The bee the product ships as its face: the same artwork the icon kit is cut
#: from and the first-run scene floats. Transparent, 2120x1504, already committed.
BEE_PNG = APP / "public" / "onboarding" / "bee-3d-hero.png"
BEE = "data:image/png;base64," + base64.b64encode(BEE_PNG.read_bytes()).decode()

OUT_ASSET = ROOT / "docs" / "media" / "ephe-social-preview-1200x630.png"
OUT_PUBLIC = APP / "public" / "og-image.png"

W, H = 1200, 630
SCALE = 2  # rendered at 2x, downscaled to 1x for clean anti-aliasing

# Tokens, copied verbatim from app/src/styles/globals.css (the one ground)
CANVAS = "#15120F"       # --color-canvas
SURFACE = "#1D1917"      # --color-surface
INK = "#F2EFE8"          # --color-ink
INK_SOFT = "hsl(30 9% 66%)"   # --color-ink-soft
INK_FAINT = "hsl(30 8% 53%)"  # --color-ink-faint
HAIRLINE = "#2E2926"     # --color-hairline
BRAND = "#E8543F"        # --color-brand (5.13:1 on the canvas)

HEADLINE = ("Work you can see.<br>"
            "A trace that disappears.")
KICKER = "THE EPHEMERAL SI AGENT"
SUB = ("Give Ephe a task — it researches, builds and delivers. "
       "You watch live.")
FOOT = "app.ephe.app  ·  github.com/bemlerlabs/ephe  ·  BUSL-1.1"


def _font_face(family: str, weight: int, slug: str, subdir: str) -> str:
    """A @font-face pointing at the self-hosted @fontsource woff2 (latin subset)."""
    f = FONTS / subdir / "files" / f"{slug}-latin-{weight}-normal.woff2"
    if not f.exists():
        raise SystemExit(f"missing font file: {f}")
    return (f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"font-style:normal;src:url('{f.as_uri()}') format('woff2');}}")


def html() -> str:
    faces = "".join(
        [
            _font_face("Space Grotesk", 600, "space-grotesk", "space-grotesk"),
            _font_face("Space Grotesk", 500, "space-grotesk", "space-grotesk"),
            _font_face("Inter", 400, "inter", "inter"),
            _font_face("Inter", 500, "inter", "inter"),
            _font_face("JetBrains Mono", 400, "jetbrains-mono", "jetbrains-mono"),
            _font_face("JetBrains Mono", 500, "jetbrains-mono", "jetbrains-mono"),
        ]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
{faces}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden}}
body{{font-family:'Inter',sans-serif;color:{INK};position:relative;
  background:radial-gradient(135% 135% at 10% -10%,{SURFACE} 0%,{CANVAS} 52%,#0F0D0B 100%);}}
/* dossier hairline — 1 px rules instead of shadows (BRAND section Type & tokens) */
.frame{{position:absolute;inset:22px;border:1px solid {HAIRLINE};border-radius:10px}}
.glow{{position:absolute;right:-90px;top:40px;width:680px;height:680px;border-radius:50%;
  background:radial-gradient(circle,rgba(232,84,63,.12) 0%,rgba(232,84,63,0) 66%)}}
.mark{{position:absolute;right:24px;top:92px;width:548px;height:452px}}
.mark img{{width:100%;height:100%;object-fit:contain;display:block}}
.lockup{{position:absolute;left:72px;top:60px;display:flex;align-items:center;gap:15px}}
.lockup .m{{width:64px;height:52px}}
.lockup .m img{{width:100%;height:100%;object-fit:contain;display:block}}
.wordmark{{font-family:'Space Grotesk';font-weight:600;font-size:41px;letter-spacing:-.015em;
  line-height:1}}
.kicker{{position:absolute;left:74px;top:228px;font-family:'JetBrains Mono';font-weight:500;
  font-size:16px;letter-spacing:.34em;color:{BRAND};text-transform:uppercase}}
h1{{position:absolute;left:71px;top:264px;width:648px;font-family:'Space Grotesk';
  font-weight:600;font-size:52px;line-height:1.09;letter-spacing:-.018em;color:{INK}}}
.sub{{position:absolute;left:74px;top:420px;width:566px;font-family:'Inter';font-weight:400;
  font-size:22px;line-height:1.5;color:{INK_SOFT}}}
.rule{{position:absolute;left:74px;top:520px;width:520px;height:1px;background:{HAIRLINE}}}
.foot{{position:absolute;left:74px;top:542px;font-family:'JetBrains Mono';font-weight:400;
  font-size:15px;letter-spacing:.01em;color:{INK_FAINT}}}
</style></head>
<body>
  <div class="glow"></div>
  <div class="frame"></div>
  <div class="mark"><img src="{BEE}" alt=""></div>
  <div class="lockup"><span class="m"><img src="{BEE}" alt=""></span><span class="wordmark">Ephe</span></div>
  <div class="kicker">{KICKER}</div>
  <h1>{HEADLINE}</h1>
  <div class="sub">{SUB}</div>
  <div class="rule"></div>
  <div class="foot">{FOOT}</div>
</body></html>"""


def chrome_path() -> str | None:
    """An installed ms-playwright Chromium. The pinned revision can be absent on a
    box that only fetched some builds (see docs/ARTIFACTS_PAGE_SCREENSHOTS_...)."""
    env = os.environ.get("EPHE_CHROME")
    if env and Path(env).exists():
        return env
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache.exists():  # linux CI layout
        cache = Path.home() / ".cache" / "ms-playwright"
    cands = sorted(cache.glob("chromium-*/chrome-*/Google Chrome for Testing.app/"
                             "Contents/MacOS/Google Chrome for Testing"))
    cands += sorted(cache.glob("chromium-*/chrome-linux*/chrome"))
    return str(cands[-1]) if cands else None


def main() -> int:
    OUT_ASSET.parent.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    raw = None
    with TemporaryDirectory() as tmp:
        page_html = Path(tmp) / "social_preview.html"
        page_html.write_text(html(), encoding="utf-8")
        with sync_playwright() as p:
            launch = {"executable_path": chrome_path()} if chrome_path() else {}
            browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": W, "height": H},
                                    device_scale_factor=SCALE)
            page.goto(page_html.as_uri())
            page.wait_for_timeout(350)  # woff2 settle
            raw = page.screenshot()
            browser.close()
    try:
        from io import BytesIO

        from PIL import Image
        img = Image.open(BytesIO(raw)).convert("RGB").resize((W, H), Image.LANCZOS)
        img.save(OUT_ASSET, format="PNG", optimize=True)
    except ImportError:
        OUT_ASSET.write_bytes(raw)
    OUT_PUBLIC.write_bytes(OUT_ASSET.read_bytes())
    for f in (OUT_ASSET, OUT_PUBLIC):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
