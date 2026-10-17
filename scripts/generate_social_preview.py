"""◑ Ephe — social preview card (1200x630).

scripts/generate_social_preview.py

One source for the share card: an HTML composition rendered through
Playwright/Chromium (the repo's reference renderer) straight at 2x and downscaled
to exactly 1200x630 — the Open Graph / Twitter `summary_large_image` size.

What it draws (all of it from tokens the app already ships):
- ground   = --color-canvas  #F0F0E6 (paper, the light default) with a soft
             --color-surface #FAFAF5 highlight and a warm paper falloff
- figure   = the fire-spirit bee (scripts/generate_fire_spirit_bee.py), inlined
             in the paper hex spelling its generator owns (`bee_body`), so the card
             and the app cannot drift. It is the brand's face now (brand decision
             2026-10-16); the card carries it whole — the panel on the right and the
             small lockup beside the wordmark
- type     = Space Grotesk (display), Inter (body), JetBrains Mono (kicker/footer),
             self-hosted @fontsource woff2 — never a system fallback
- colour   = --color-brand-deep #B42D21 for the kicker (AA red text on paper),
             --color-ink #1A1614 for the headline, --color-ink-soft / -faint for
             the body and footer

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

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_palette import ROLES  # noqa: E402  (path bootstrap above)
from generate_fire_spirit_bee import bee_body  # noqa: E402  (same directory)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
FONTS = APP / "node_modules" / "@fontsource"
#: The bee on the paper column of scripts/brand_palette.py: the card is a paper
#: surface, so the figure is inlined in the paper hex spelling the generator owns
#: (`bee_body`): the card carries hex, and no stylesheet resolves a role.
BEE = bee_body("calm", 512, ground="paper")

#: The card's own roles, all paper, for the small rule and text tokens.
PAPER_ROLES = "".join(
    f"{ROLES[role].token}:{ROLES[role].paper};"
    for role in ("brand", "brand_glow", "ink", "ground")
)

OUT_ASSET = ROOT / "docs" / "media" / "ephe-social-preview-1200x630.png"
OUT_PUBLIC = APP / "public" / "og-image.png"

W, H = 1200, 630
SCALE = 2  # rendered at 2x, downscaled to 1x for clean anti-aliasing

# Tokens, copied verbatim from app/src/styles/globals.css (html.light)
PAPER = "#F0F0E6"        # --color-canvas
SURFACE = "#FAFAF5"      # --color-surface
INK = "#1A1614"          # --color-ink
INK_SOFT = "hsl(25 8% 35%)"   # --color-ink-soft
INK_FAINT = "hsl(25 7% 40%)"  # --color-ink-faint
HAIRLINE = "#D8D4C8"     # --color-hairline
BRAND_DEEP = "#B42D21"   # --color-brand-deep (AA red text on paper)

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
    # The bee is inlined twice — the panel and the lockup — so the second copy gets
    # its own id prefix; two figures that shared one set of gradient ids would both
    # read the first set, which is invalid markup even when it happens to paint right.
    panel = f'<svg viewBox="0 0 512 512" role="img">{BEE}</svg>'
    lockup = f'<svg viewBox="0 0 512 512" role="img">{BEE.replace("bspc-", "bspl-")}</svg>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
:root{{{PAPER_ROLES}}}
{faces}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden}}
body{{font-family:'Inter',sans-serif;color:{INK};position:relative;
  background:radial-gradient(135% 135% at 10% -10%,{SURFACE} 0%,{PAPER} 50%,#E7E6DA 100%);}}
/* dossier hairline — 1 px rules instead of shadows (BRAND section Type & tokens) */
.frame{{position:absolute;inset:22px;border:1px solid {HAIRLINE};border-radius:10px}}
.glow{{position:absolute;right:-90px;top:40px;width:680px;height:680px;border-radius:50%;
  background:radial-gradient(circle,rgba(216,56,40,.09) 0%,rgba(216,56,40,0) 66%)}}
/* the mark: its right lobe decays into the paper — ephemeral made visible */
.mark{{position:absolute;right:40px;top:112px;width:420px;height:420px}}
.mark svg{{width:100%;height:100%;display:block}}
.lockup{{position:absolute;left:72px;top:60px;display:flex;align-items:center;gap:15px}}
.lockup .m{{width:58px;height:58px}}
.lockup .m svg{{width:100%;height:100%;display:block}}
.wordmark{{font-family:'Space Grotesk';font-weight:600;font-size:41px;letter-spacing:-.015em;
  line-height:1}}
.kicker{{position:absolute;left:74px;top:228px;font-family:'JetBrains Mono';font-weight:500;
  font-size:16px;letter-spacing:.34em;color:{BRAND_DEEP};text-transform:uppercase}}
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
  <div class="mark">{panel}</div>
  <div class="lockup"><span class="m">{lockup}</span><span class="wordmark">Ephe</span></div>
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
