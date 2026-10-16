"""Ephe — brand-asset generator (the icon/branding wave).
scripts/generate_brand_assets.py

The shipped icon kit is the bee: the small fire-spirit being of
`scripts/generate_fire_spirit_bee.py`, whose lit comb belly, glass wings and flame
plume carry the brand (brand decision 2026-10-16,
`docs/brand/fire-spirit-decision-2026-10-16.md`). This script composes the emblems
and rasters around that figure, so the tab, the PWA tiles, the Tauri bundle and the
tray all carry the vector the app inlines. The cut follows the size, not the other
way round — the whole figure from 48 px, the plain red head-and-blade cut below —
and every file is rendered straight from the SVG at its target size through
Chromium, never scaled by hand.

`--variant=mark` still reaches the earlier figure (the forest-spirit "mark" of
docs/BRAND.md) and its `_mark` drawing is the source of the in-app vectors
`app/src/assets/mark.svg` and `mark-mono.svg`, which `EpheMark` inlines. Palette =
the repository roles from globals.css, read by name through scripts/brand_palette.py
(firefly / moss / black-forest).

Produces (deterministic, no network or font dependency — NO <text>):
- app/public/favicon.svg                     (bee, the tab vector)
- app/public/favicon.png                     (the tab icon a parser without SVG gets)
- app/public/icon-{192,512}.png              (PWA "any")
- app/public/icon-maskable-{192,512}.png     (PWA maskable, full bleed + safe zone)
- app/public/apple-touch-icon-180.png        (iOS, opaque)
- app/src-tauri/icons/tray-mono.png          (bee template raster for the tray)
- app/src-tauri/icons/*.png                  (32, 128, 128@2x, icon.png 512,
                                              Square* logos, StoreLogo)
- app/src-tauri/icons/icon.ico               (PIL, multi-size)
- app/src-tauri/icons/icon.icns              (iconutil over the iconset)
- app/src/assets/mark.svg / mark-mono.svg    (the forest-spirit in-app vectors)

Rasterised through Playwright/Chromium (the reference renderer) straight from
the SVG at each target size — no up- or downscaling. Run:  .venv/bin/python
scripts/generate_brand_assets.py
"""
from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "app" / "public"
SRC_ASSETS = ROOT / "app" / "src" / "assets"
TAURI_ICONS = ROOT / "app" / "src-tauri" / "icons"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_palette import hex_for, token_for  # noqa: E402  (path bootstrap above)

# Palette by role — brand_palette.py holds the table, globals.css holds the values.
# Before this, five frozen hexes sat here and the icon kit painted them: FIREFLY
# carried the paper spelling (#d83828), so every raster measured 4.03:1 on its own
# field where the ink red (#E8543F) measures 5.15:1. A raster needs a hex, so the
# build concretises a role at build time; the in-app vector asks for the property
# name through `token_for` and lets the stylesheet decide.
BLACK_FOREST = hex_for("ground")      # --color-black-forest: the icon field
MOSS_DEEP = hex_for("panel")          # --color-moss-deep
FIREFLY = hex_for("brand")            # --color-firefly: #E8543F ink, #B52E21 paper
FIREFLY_GLOW = hex_for("brand_glow")  # --color-firefly-glow

SVG = 512.0  # Emblemspace


def _dot_field() -> str:
    """Dots of the right (dissolving) half of the circle: a triangular lattice
    inside the right semicircle; radius and opacity fade out toward the right."""
    cx, cy, r_in = SVG / 2, SVG / 2, 148.0
    step = 21.0
    parts: list[str] = []
    y = cy - r_in + 12
    row = 0
    while y <= cy + r_in - 8:
        x0 = cx + (step / 2 if row % 2 else 0.0)
        x = x0 + 10
        while x <= cx + r_in:
            d = math.hypot(x - cx, y - cy)
            if d <= r_in:
                t = max(0.0, min(1.0, (x - cx) / r_in))  # 0=edge, 1=right
                rad = 7.2 - 5.6 * t
                op = 0.95 - 0.62 * t
                if rad >= 1.4:
                    color = FIREFLY_GLOW if row % 3 == 0 and t < 0.4 else FIREFLY
                    parts.append(
                        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" '
                        f'fill="{color}" fill-opacity="{op:.2f}"/>'
                    )
            x += step
        y += step * 0.87
        row += 1
    return "\n      ".join(parts)


def _dissolving_e() -> str:
    """Candidate 2 — "Dissolving e": a drawn lowercase e (strokes with round
    caps); the lower arc ends at the opening and breaks into dots that fade out
    along the direction of motion. The name AS the icon."""
    cx, cy, r, w = SVG / 2, SVG / 2 + 10, 148.0, 52.0
    left, right = cx - r, cx + r
    # Opening at ~40° (y-down): the lower arc ends here, the dots run on.
    import math as _m

    ang_end, ang_far = _m.radians(40), _m.radians(6)
    ex, ey = cx + r * _m.cos(ang_end), cy + r * _m.sin(ang_end)
    dots: list[str] = []
    a = ang_end
    step = _m.radians(4.2)
    i = 0
    while a > ang_far:
        a -= step
        t = i / 8.0
        rad = max(3.6, w * 0.46 * (1 - t * 0.78))
        op = max(0.2, 0.92 - t * 0.82)
        px, py = cx + r * _m.cos(a), cy + r * _m.sin(a)
        dots.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rad:.1f}" '
            f'fill="{FIREFLY}" fill-opacity="{op:.2f}"/>'
        )
        i += 1
    return (
        f'<g stroke="url(#ff)" stroke-width="{w}" fill="none">'
        f'<path d="M{left:.0f},{cy:.0f} A{r:.0f},{r:.0f} 0 0 1 {right:.0f},{cy:.0f}"/>'
        f'<path d="M{left:.0f},{cy:.0f} A{r:.0f},{r:.0f} 0 0 0 {ex:.1f},{ey:.1f}" '
        f'stroke-linecap="round"/>'
        f"</g>"
        # crossbar SOLID (a gradient on a 0-px-tall line would be invisible)
        f'<path d="M{left:.0f},{cy:.0f} L{right:.0f},{cy:.0f}" '
        f'stroke="{FIREFLY}" stroke-width="{w}" stroke-linecap="butt" fill="none"/>'
        f'<g>{"".join(dots)}</g>'
    )


def _breath() -> str:
    """Candidate 3 — "Breath": a minimal row of fading dots
    (the ellipse of vanishing). Extremely reduced, very strong at 16px."""
    cy = SVG / 2
    xs = [136, 208, 280, 344, 396]
    rs = [44, 36, 27, 18, 11]
    ops = [0.95, 0.8, 0.6, 0.4, 0.22]
    dots = "".join(
        f'<circle cx="{x}" cy="{cy}" r="{r}" fill="{FIREFLY}" fill-opacity="{o}"/>'
        for x, r, o in zip(xs, rs, ops)
    )
    return f'<g>{dots}</g>'


def _fade_dots(pts: list[tuple[float, float, float, float]], color: str = FIREFLY) -> str:
    """Helper dots: (x, y, r, opacity)."""
    return "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" '
        f'fill-opacity="{o:.2f}"/>'
        for x, y, r, o in pts
    )


def _mayfly() -> str:
    """Candidate "Eph" — the mayfly (Ephemeroptera): the insect that gave
    ephemerality its NAME. Glass wings (the liquid-glass of the UI), a solid
    body, two long tail filaments; wing and tail tips fade into dots =
    the clean disappearance."""
    import math as _m

    # Wings: two long forewings in resting posture (a tent), mirrored:
    #    right -52° (up-right), left 232° (up-left).
    wings: list[str] = []
    wing_dots: list[str] = []
    WING_LEN = 165
    for side in (1, -1):
        ang = -52 if side == 1 else 232
        rad = _m.radians(ang)
        sh_x, sh_y = 256, 208            # shoulder
        tip_x = sh_x + WING_LEN * _m.cos(rad)
        tip_y = sh_y + WING_LEN * _m.sin(rad)
        cxw, cyw = (sh_x + tip_x) / 2, (sh_y + tip_y) / 2
        rot = _m.degrees(_m.atan2(tip_y - sh_y, tip_x - sh_x))
        wings.append(
            f'<ellipse cx="{cxw:.1f}" cy="{cyw:.1f}" rx="92" ry="38" '
            f'transform="rotate({rot:.1f} {cxw:.1f} {cyw:.1f})" '
            f'fill="{FIREFLY}" fill-opacity="0.20" stroke="{FIREFLY}" '
            f'stroke-opacity="0.6" stroke-width="4"/>'
        )
        # dissolve behind the wing tip, along the axis
        pts = []
        for i in range(4):
            d = WING_LEN + 22 + i * 20
            pts.append((
                sh_x + d * _m.cos(rad), sh_y + d * _m.sin(rad),
                7.5 - i * 1.4, 0.85 - i * 0.19,
            ))
        wing_dots.append(_fade_dots(pts))

    # Body: head + slender drop (thorax -> abdomen).
    body = (
        f'<circle cx="256" cy="132" r="20" fill="url(#ff)"/>'
        f'<circle cx="249" cy="129" r="4" fill="{BLACK_FOREST}" fill-opacity="0.8"/>'
        f'<circle cx="263" cy="129" r="4" fill="{BLACK_FOREST}" fill-opacity="0.8"/>'
        f'<path d="M256,150 C284,170 292,198 286,226 C280,260 268,304 258,366 '
        f'C256,374 256,374 254,366 C244,304 232,260 226,226 '
        f'C220,198 228,170 256,150 Z" fill="url(#ff)"/>'
        f'<g stroke="{BLACK_FOREST}" stroke-opacity="0.28" stroke-width="3" '
        f'fill="none" stroke-linecap="round">'
        f'<path d="M240,272 C251,278 261,278 272,272"/>'
        f'<path d="M243,304 C252,310 260,310 269,304"/>'
        f'<path d="M247,336 C253,341 259,341 265,336"/>'
        f"</g>"
    )

    # Tail filaments (cerci): LONG and slender, slightly outward — the
    #    unmistakable mayfly signature, with dissolve.
    tails: list[str] = []
    tail_dots: list[str] = []
    for side in (1, -1):
        end_x = 256 + side * 66
        tails.append(
            f'<path d="M256,366 Q {256 + side * 16},{410} {end_x},{452}" '
            f'stroke="{FIREFLY}" stroke-opacity="0.85" stroke-width="4.5" '
            f'fill="none" stroke-linecap="round"/>'
        )
        pts = []
        for i in range(4):
            t = (i + 1) / 5.0
            # approximate the tangent of the Q curve at the end piece:
            qx = 256 + side * (16 + (66 - 16) * t)
            qy = 410 + (452 - 410) * t
            pts.append((qx + side * 10 * t, qy + 9 * t,
                        6 - i * 1.2, 0.8 - i * 0.18))
        tail_dots.append(_fade_dots(pts))

    return (
        f'<g>{"".join(wings)}{body}{"".join(tails)}'
        f'{"".join(wing_dots)}{"".join(tail_dots)}</g>'
    )


def _dandelion() -> str:
    """Candidate "Dandelion clock": seeds come loose and fade into dots —
    fleeting, organic, read instantly anywhere in the world."""
    import math as _m

    cx, cy, r = 256, 286, 92
    parts: list[str] = []
    for i in range(16):
        a = _m.radians(i * 22.5)
        ex, ey = cx + r * _m.cos(a), cy + r * _m.sin(a)
        parts.append(
            f'<path d="M{cx},{cy} L{ex:.1f},{ey:.1f}" stroke="{FIREFLY}" '
            f'stroke-opacity="0.75" stroke-width="3.5" stroke-linecap="round"/>'
        )
        # pappus crown at each tip: small fans
        for da in (-0.5, -0.25, 0.0, 0.25, 0.5):
            ax = ex + 16 * _m.cos(a + da)
            ay = ey + 16 * _m.sin(a + da)
            parts.append(
                f'<path d="M{ex:.1f},{ey:.1f} L{ax:.1f},{ay:.1f}" stroke="{FIREFLY}" '
                f'stroke-opacity="0.5" stroke-width="2.4" stroke-linecap="round"/>'
            )
    stem = (
        f'<path d="M256,286 C252,352 246,398 234,446" stroke="{FIREFLY}" '
        f'stroke-opacity="0.9" stroke-width="6" fill="none" stroke-linecap="round"/>'
    )
    # Two released seeds fading out toward the upper right
    drift: list[str] = []
    for sx, sy, s in ((338, 168, 1.0), (388, 116, 0.7)):
        for da in range(0, 360, 72):
            a = _m.radians(da)
            drift.append(
                f'<path d="M{sx},{sy} L{sx + 13 * s * _m.cos(a):.1f},'
                f'{sy + 13 * s * _m.sin(a):.1f}" stroke="{FIREFLY}" '
                f'stroke-opacity="0.6" stroke-width="2.2" stroke-linecap="round"/>'
            )
        drift.append(_fade_dots([
            (sx + 34 * s, sy - 10 * s, 6 * s, 0.7),
            (sx + 52 * s, sy - 22 * s, 4.4 * s, 0.45),
            (sx + 66 * s, sy - 32 * s, 3.0 * s, 0.25),
        ]))
    core = f'<circle cx="{cx}" cy="{cy}" r="10" fill="url(#ff)"/>'
    return f'<g>{"".join(parts)}{stem}{core}{"".join(drift)}</g>'


def _mark(*, compact: bool = False, micro: bool = False, mono: bool = False,
          vector: bool = False, beads: bool | None = None) -> str:
    """The "mark" brand — the forest spirit: the drop drawn as a being.

    Brand decision 2026-10-15, superseding the drop that carried a letter: the
    brand's own object gets two leaf ears, two eyes and a lower edge that leaves
    in three beads, because the product's motion is subtraction from the
    bottom-right and the mark leaves the same way. The ears are the whole
    difference between a creature and a blob, and a face survives 16 px where a
    letter laid on a field does not.

    `vector=True` writes the spelling the surface needs: `var(--token)` for every
    fill, so one asset serves the icons, the in-app vector and the terminal. The
    eyes are knockouts in both spellings, holes in the body rather than paint,
    which is how a vector that knows no theme keeps its face on the ink ground
    and on the paper. The default concretises each role into its hex, which is
    what a raster and the standalone favicon.svg need.

    `mono=True` is the template cut, a MODIFIER that multiplies any size band
    (MARK_MODIFIERS below): the creature's silhouette in one colour, because an
    alpha mask has no second colour to cut an eye out of the body with.

    `beads` states whether the dissolve trail is drawn. It defaults to the cut's
    own answer — the trail is here from the compact band up — and a target size
    overrides it, because the micro band reaches down to 16 px where a bead is
    dust and up to 32 px where it still reads as a bead. `_mark_for` reads it.

    The three size cuts live in MARK_CUTS; this docstring states no band.
    """
    if beads is None:
        beads = not micro

    def paint(role: str) -> str:
        """The fill for `role` in the spelling this build asked for."""
        if mono:
            return "currentColor"
        return f"var({token_for(role)})" if vector else hex_for(role)

    tag = "m" if micro else ("c" if compact else "f")
    # Ears: every cut below the mark band takes a thicker pair, and the smallest
    # one a taller pair again — a hairline ear is gone by 24 px and the mark
    # collapses back into a blob.
    if micro:
        ears = ("M182 214 C150 152 130 104 136 82 C168 96 198 148 214 218 Z",
                "M330 214 C362 152 382 104 376 82 C344 96 314 148 298 218 Z")
    elif compact:
        ears = ("M184 216 C152 172 128 128 134 98 C164 110 196 160 216 220 Z",
                "M328 216 C360 172 384 128 378 98 C348 110 316 160 296 220 Z")
    else:
        # Leaf geometry: broad at the base, short to the tip. Two earlier pairs
        # curved out and up, and read as horns at large sizes and as rabbit ears
        # after that.
        ears = ("M186 216 C150 172 128 138 132 108 C146 100 168 112 188 136 "
                "C204 156 214 184 218 218 Z",
                "M326 216 C362 172 384 138 380 108 C366 100 344 112 324 136 "
                "C308 156 298 184 294 218 Z")
    # The body: the drop, apex on the axis, belly on the circle that gives the
    # silhouette its weight. The eyes sit where the belly is widest.
    head = ("M256 122 C256 122 396 250 396 314 A140 140 0 0 1 116 314 "
            "C116 250 256 122 256 122 Z")
    # The eyes are subpaths of the head, punched by fill-rule="evenodd", so the
    # field behind the mark is what shows through: no second colour and no ground
    # role that the paper theme would have to contradict. Each keeps a glint.
    eyed = not (mono or compact or micro)
    # The veins belong to the leaf and to the mark band only: below 48 px they are
    # sub-pixel lines, and a tray template carries no fine detail at all.
    veins = "".join(
        f'<path d="{d}" stroke="{paint("brand_glow")}" stroke-width="5" fill="none" '
        f'opacity=".5" stroke-linecap="round"/>'
        for d in ("M164 136 C176 154 190 176 200 200",
                  "M348 136 C336 154 322 176 312 200")) if eyed else ""
    holes = "".join(
        f" M{cx - 24} 300 A24 30 0 0 1 {cx + 24} 300 A24 30 0 0 1 {cx - 24} 300 Z"
        for cx in (196, 316)) if eyed else ""
    glints = "".join(
        f'<ellipse cx="{cx + 8}" cy="290" rx="8" ry="10" '
        f'fill="{paint("brand")}" opacity=".55"/>' for cx in (196, 316)) if eyed else ""
    # The edge leaves in three beads, each smaller and fainter than the one
    # before: the first sits against the body, the last is nearly gone.
    trail = "".join(
        f'<circle cx="{266 + i * 22}" cy="{428 + i * 30}" r="{13 - i * 3}" '
        f'fill="{paint("brand")}" fill-opacity="{0.72 - i * 0.2:.2f}"/>'
        for i in range(3)) if beads else ""
    if mono:
        # One ink for the tray: the silhouette the system tints. The trail stays,
        # because a template image carries its fade in the alpha channel.
        parts = "".join(f'<path d="{data}"/>' for data in ears)
        return f'<g fill="currentColor">{parts}<path d="{head}"/>{trail}</g>'
    # One flat cut below the mark band: no gradient on the body there, because at
    # that size the ink red itself is the message (a gradient would spread it over
    # a hundred slightly different reds).
    body_fill = paint("brand") if micro else f"url(#mk{tag}b)"
    gradient = (
        ""
        if micro
        else f'<linearGradient id="mk{tag}b" x1="0.28" y1="0.06" x2="0.76" y2="0.98">'
             f'<stop offset="0%" stop-color="{paint("brand_glow")}"/>'
             f'<stop offset="100%" stop-color="{paint("brand")}"/></linearGradient>'
    )
    # The glow is a radial gradient with a transparent outer stop, so it has no
    # edge; a hard ellipse would read as a plate behind the creature.
    glow = (
        f'<radialGradient id="mk{tag}h" cx="50%" cy="56%" r="52%">'
        f'<stop offset="0%" stop-color="{paint("brand_glow")}" stop-opacity=".34"/>'
        f'<stop offset="60%" stop-color="{paint("brand_glow")}" stop-opacity=".12"/>'
        f'<stop offset="100%" stop-color="{paint("brand_glow")}" stop-opacity="0"/>'
        f"</radialGradient>"
    )
    halo = f'<ellipse cx="256" cy="308" rx="196" ry="192" fill="url(#mk{tag}h)"/>'
    body = "".join(f'<path d="{data}" fill="{body_fill}"/>' for data in ears)
    rule = ' fill-rule="evenodd"' if holes else ""
    return (
        f"<defs>{gradient}{glow}</defs>"
        f"{halo}{body}{veins}"
        f'<path d="{head}{holes}" fill="{body_fill}"{rule}/>' 
        f"{glints}{trail}"
    )


def mark_svg(size: int = 48, *, mono: bool = False, view_box: str | None = None,
             tint: str | None = None) -> str:
    """The in-app vector for `size`: the DOM root the surface can inline.

    The `<svg>` wrapper is what `EpheMark` reads — an `<img>` would have no
    children and the condensation would be decoration only. `tint` is how a raster
    build concretises the template role: the vector leaves `currentColor` to the
    host, and a screenshot has no stylesheet around it.
    """
    body = _mark_for(size, mono=mono, vector=True)
    box = view_box or f"0 0 {SVG} {SVG}"
    style = f' style="color:{tint}"' if tint else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}" '
            f'role="img"{style}>{body}</svg>')


VARIANTS = {
    "mayfly": _mayfly,
    "dandelion": _dandelion,
    "mark": lambda: _mark(compact=False),
    "mark-compact": lambda: _mark(compact=True),
    "mark-micro": lambda: _mark(micro=True),
    "circle": lambda: (
        f'<path d="M256,108 A148,148 0 0 0 256,404 Z" fill="url(#ff)"/>'
        f'<circle cx="256" cy="256" r="148" fill="none" stroke="{FIREFLY}" '
        f'stroke-opacity="0.28" stroke-width="3"/>'
        f'<g>{_dot_field()}</g>'
    ),
    "e": _dissolving_e,
    "breath": _breath,
}

# Size -> cut grid for the mark. Reviewed on the creature's own ladder
# (2026-10-15), the render the decision was taken on.
#   <=32  micro   — the pair of eyes is a pair of specks here, so this band is
#                  the silhouette, and a bead of the trail is a fraction of a
#                  pixel below 32 px.
#   33-47 compact — the eyes are still dirt and the halo has no room, so the
#                  compact cut is the heavier ears, the halo and the trail.
#   >=48  mark    — from 48 px the eyes read as a face and the halo as light.
# The table is the single statement of the three bands; the docstrings, the TSX
# and the stylesheet comment may name a band and are held to it by
# scripts/asset_check.py. Anyone who wants the cut size by size asks here:
# mark_variant_for(16) -> "mark-micro".
MARK_CUTS = {
    "mark": (48, None),        # from 48 px
    "mark-compact": (33, 47),  # 33-47 px
    "mark-micro": (0, 32),     # up to 32 px
}


def mark_variant_for(size: int) -> str:
    """Cut name for a target size in px (thresholds: MARK_CUTS)."""
    for name, (lo, hi) in MARK_CUTS.items():
        if size >= lo and (hi is None or size <= hi):
            return name
    return "mark-micro"


#: Orthogonal to the size bands: a modifier describes the asset, so it multiplies
#: the routing above and can never collide with it. `mono` is the template cut —
#: one colour, the E punched out, tintable by the host.
MARK_MODIFIERS = ("mono",)


def mark_asset_for(size: int, *, mono: bool = False) -> str:
    """Asset name a target size routes to, with the modifier that was asked for."""
    cut = mark_variant_for(size)
    return f"{cut}+mono" if mono else cut


def _mark_for(size: int, *, mono: bool = False, vector: bool = False) -> str:
    """The mark's body for a target size, with the cut and the trail it carries.

    The cut comes from `mark_variant_for`. The trail is routed separately, because
    the micro band spans the 32 px size that still carries a bead and the sizes
    below it where a bead is a fraction of a pixel.
    """
    cut = mark_variant_for(size)
    return _mark(compact=cut == "mark-compact", micro=cut == "mark-micro",
                 mono=mono, vector=vector, beads=size >= 32)


#: The template raster crops to the creature's own bounding box on the emblem
#: canvas (measured: x 116..396, y 76..495 with the trail) plus a margin, so a
#: 22 pt tray icon carries the glyph and not the canvas around it. Square,
#: because the tray is: a non-square box would letterbox the creature into the
#: middle of the icon.
TRAY_VIEWBOX = "41 70 430 430"


def emblem_svg(*, full_bleed: bool, scale: float = 0.84, variant: str = "circle",
               disc: str | None = None) -> str:
    """Emblem SVG. full_bleed=False: the rounded app-icon square (Tauri,
    favicon). full_bleed=True: a background that fills the frame for maskable /
    apple-touch (the OS masks by itself), emblem shrunk to `scale`.

    `disc` overrides the shape the variant draws: a render that knows its target
    size passes the cut for that size, trail included."""
    bg = (
        f'<rect width="{SVG}" height="{SVG}" fill="{BLACK_FOREST}"/>'
        if full_bleed
        else (
            f'<rect x="18" y="18" width="{SVG - 36}" height="{SVG - 36}" rx="108" '
            f'fill="{BLACK_FOREST}"/>'
        )
    )
    glow = (
        f'<radialGradient id="glow" cx="38%" cy="42%" r="62%">'
        f'<stop offset="0%" stop-color="{MOSS_DEEP}" stop-opacity="0.9"/>'
        f'<stop offset="100%" stop-color="{MOSS_DEEP}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<rect width="{SVG}" height="{SVG}" fill="url(#glow)" rx="108"/>'
    )
    grad = (
        f'<linearGradient id="ff" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{FIREFLY_GLOW}"/>'
        f'<stop offset="100%" stop-color="{FIREFLY}"/>'
        f"</linearGradient>"
    )
    shape = VARIANTS[variant]() if disc is None else disc
    transform = (
        f'translate({256 * (1 - scale)},{256 * (1 - scale)}) '
        f"scale({scale})"
        if full_bleed
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG:.0f} {SVG:.0f}">'
        f"<defs>{grad}</defs>"
        f"{bg}{glow}"
        f'<g transform="{transform}">{shape}</g>'
        f"</svg>"
    )


def _render(svg: str, size: int, out: Path, *, transparent: bool) -> None:
    """Raster the SVG through Chromium at the exact target size (vector → raster)."""
    html = (
        "<!doctype html><html><head><style>*{margin:0;padding:0}"
        f"svg{{width:{size}px;height:{size}px;display:block}}"
        "body{background:transparent}</style></head><body>"
        f"{svg}</body></html>"
    )
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(html)
    page.screenshot(path=str(out), omit_background=transparent)
    _force_rgba(out)


def _force_rgba(path: Path) -> None:
    """Write the PNG guaranteed as RGBA — tauri::generate_context! refuses
    non-RGBA icons (proc-macro panic "icon … is not RGBA")."""
    from PIL import Image

    with Image.open(path) as img:
        img.convert("RGBA").save(path)


def _icns() -> None:
    """Apple .icns via iconutil from a temporary iconset, the mark cut per size.

    The signature used to take a PNG it never read, so every entry came from the
    emblem's default candidate: the .icns was the one surface macOS draws (Dock,
    Finder, app switcher) and the only shipped one that carried a candidate
    instead of the mark.
    """
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        for tag, px in {
            "16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64,
            "128x128": 128, "128x128@2x": 256, "256x256": 256,
            "256x256@2x": 512, "512x512": 512, "512x512@2x": 1024,
        }.items():
            _render(emblem_svg(full_bleed=False, variant=mark_variant_for(px),
                               disc=_mark_for(px)), px, iconset / f"icon_{tag}.png",
                    transparent=True)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(TAURI_ICONS / "icon.icns")],
            check=True, capture_output=True,
        )


def _ico(png256: Path) -> None:
    """Multi-size .ico via PIL (16…256)."""
    from PIL import Image

    img = Image.open(png256).convert("RGBA")
    img.save(
        TAURI_ICONS / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


TAURI_SQUARES = {
    "Square30x30Logo.png": 30, "Square44x44Logo.png": 44, "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89, "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142, "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284, "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
}

def _kit_from_master(master_png: Path) -> None:
    """Builds the complete kit from ONE frozen PNG master
    (the locally generated mayfly artwork, docs/brand/eph-mayfly-master.png)."""
    from PIL import Image, ImageDraw, ImageFilter

    m = Image.open(master_png).convert("RGBA")

    def rs(size: int) -> Image.Image:
        # RGBA everywhere: tauri::generate_context! refuses non-RGBA PNGs
        # (proc-macro panic "icon … is not RGBA") — RGB saved nothing here.
        return m.resize((size, size), Image.LANCZOS)

    # PWA: any (opaque artwork) + maskable (scale 0.86 on black-forest,
    # feathered) + apple-touch (opaque) + raster favicon
    for size in (192, 512):
        rs(size).save(PUBLIC / f"icon-{size}.png")
    for size in (192, 512):
        canvas = Image.new("RGB", (size, size), (5, 5, 5))
        inner = rs(int(size * 0.86))
        mask = Image.new("L", inner.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, inner.size[0], inner.size[1]), radius=int(size * 0.18), fill=255
        )
        mask = mask.filter(ImageFilter.GaussianBlur(size // 64))
        canvas.paste(inner, ((size - inner.size[0]) // 2,) * 2, mask)
        canvas.save(PUBLIC / f"icon-maskable-{size}.png")
    rs(180).save(PUBLIC / "apple-touch-icon-180.png")
    rs(48).save(PUBLIC / "favicon.png")

    # Social avatar (circle) for the brand kit
    avatar = rs(512)
    am = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(am).ellipse((0, 0, 511, 511), fill=255)
    rgba = avatar.convert("RGBA")
    rgba.putalpha(am)
    (ROOT / "docs" / "media" / "eph-avatar-512.png").parent.mkdir(exist_ok=True)
    rgba.save(ROOT / "docs" / "media" / "eph-avatar-512.png")

    # Tauri: standard set + Windows squares
    rs(32).save(TAURI_ICONS / "32x32.png")
    rs(128).save(TAURI_ICONS / "128x128.png")
    rs(256).save(TAURI_ICONS / "128x128@2x.png")
    rs(512).save(TAURI_ICONS / "icon.png")
    for name, size in TAURI_SQUARES.items():
        rs(size).save(TAURI_ICONS / name)

    # icns via iconutil from a temporary iconset
    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        for tag, px in {
            "16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64,
            "128x128": 128, "128x128@2x": 256, "256x256": 256,
            "256x256@2x": 512, "512x512": 512, "512x512@2x": 1024,
        }.items():
            rs(px).save(iconset / f"icon_{tag}.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(TAURI_ICONS / "icon.icns")],
            check=True, capture_output=True,
        )
    _ico(TAURI_ICONS / "128x128@2x.png")
    print("icon kit written from master:", master_png)


def _bee_icns() -> None:
    """Apple .icns via iconutil, the bee cut per size — Dock, Finder, app switcher."""
    from generate_fire_spirit_bee import bee_body  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        for tag, px in {
            "16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64,
            "128x128": 128, "128x128@2x": 256, "256x256": 256,
            "256x256@2x": 512, "512x512": 512, "512x512@2x": 1024,
        }.items():
            _render(emblem_svg(full_bleed=False, disc=bee_body("calm", px)),
                    px, iconset / f"icon_{tag}.png", transparent=True)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(TAURI_ICONS / "icon.icns")],
            check=True, capture_output=True,
        )


def _bee_kit() -> None:
    """The shipped icon and brand kit, drawn from the fire-spirit bee.

    `scripts/generate_fire_spirit_bee.py` owns the figure and its cuts; this
    composes the emblems and rasters around it, so the tab, the PWA tiles, the
    Tauri bundle and the tray all carry the vector the app inlines. The grounds are
    the ones the mark shipped on — a rounded near-black tile for the tab and the
    app, a full bleed for maskable and apple-touch — and the cut follows the size,
    because below 48 px the figure's texture is dust and its soot body would vanish
    into the near-black field.
    """
    from generate_fire_spirit_bee import TRAY_VIEW, bee_body, mono_body  # noqa: PLC0415

    def disc(size_px: int, scale: float = 1.0) -> str:
        return bee_body("calm", int(round(size_px * scale)))

    (PUBLIC / "favicon.svg").write_text(
        emblem_svg(full_bleed=False, disc=disc(16)), encoding="utf-8")
    _render(emblem_svg(full_bleed=False, disc=disc(48)), 48,
            PUBLIC / "favicon.png", transparent=True)
    _render(emblem_svg(full_bleed=False, disc=disc(192)), 192,
            PUBLIC / "icon-192.png", transparent=True)
    _render(emblem_svg(full_bleed=False, disc=disc(512)), 512,
            PUBLIC / "icon-512.png", transparent=True)
    for size in (192, 512):
        _render(emblem_svg(full_bleed=True, scale=0.72, disc=disc(size, 0.72)), size,
                PUBLIC / f"icon-maskable-{size}.png", transparent=False)
    _render(emblem_svg(full_bleed=True, scale=0.78, disc=disc(180, 0.78)), 180,
            PUBLIC / "apple-touch-icon-180.png", transparent=False)

    tray = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{TRAY_VIEW}" role="img" '
            f'style="color:{hex_for("template")}">{mono_body("calm")}</svg>')
    _render(tray, 44, TAURI_ICONS / "tray-mono.png", transparent=True)

    _render(emblem_svg(full_bleed=False, disc=disc(32)), 32,
            TAURI_ICONS / "32x32.png", transparent=True)
    _render(emblem_svg(full_bleed=False, disc=disc(128)), 128,
            TAURI_ICONS / "128x128.png", transparent=True)
    _render(emblem_svg(full_bleed=False, disc=disc(256)), 256,
            TAURI_ICONS / "128x128@2x.png", transparent=True)
    _render(emblem_svg(full_bleed=False, disc=disc(512)), 512,
            TAURI_ICONS / "icon.png", transparent=True)
    for name, size in TAURI_SQUARES.items():
        _render(emblem_svg(full_bleed=True, scale=0.9, disc=disc(size, 0.9)), size,
                TAURI_ICONS / name, transparent=False)

    _bee_icns()
    _ico(TAURI_ICONS / "128x128@2x.png")

    # The brand mark the README shows, and the social avatar: the same emblem, the
    # avatar rounded to the circle a profile picture wants.
    from PIL import Image, ImageDraw  # noqa: PLC0415

    mark = ROOT / "docs" / "media" / "ephe-bee-512.png"
    mark.parent.mkdir(parents=True, exist_ok=True)
    _render(emblem_svg(full_bleed=False, disc=disc(512)), 512, mark, transparent=True)
    with Image.open(mark) as image:
        avatar = image.convert("RGBA")
    mask = Image.new("L", avatar.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, avatar.size[0] - 1, avatar.size[1] - 1), fill=255)
    avatar.putalpha(mask)
    avatar.save(ROOT / "docs" / "media" / "eph-avatar-512.png")
    print("brand assets written (variant=bee):", PUBLIC, "and", TAURI_ICONS)


def _requested_variant() -> str:
    """The `--variant` the CLI asked for; the bee when none was given.

    The bee is the shipped figure (brand decision 2026-10-16). The older candidate
    draws stay reachable behind an explicit `--variant` for comparisons.
    """
    for arg in sys.argv[1:]:
        if arg.startswith("--variant="):
            return arg.split("=", 1)[1]
    return "bee"


if __name__ != "__main__":
    # The body of this script runs at module level — a plain import has
    # therefore already overwritten the shipped icons in app/public and
    # app/src-tauri/icons. Preview without the side effect: --sheet.
    raise RuntimeError(
        "generate_brand_assets.py writes the icon-kit files when imported. "
        "Call it as a CLI instead: --sheet (preview, shipped assets untouched) or "
        "without a flag (rewrite the kit), optional --variant=<name>."
    )


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    master_png = None
    for arg in sys.argv[1:]:
        if arg.startswith("--master="):
            master_png = Path(arg.split("=", 1)[1])

    if master_png is not None:
        _kit_from_master(master_png)
    elif "--sheet" in sys.argv:
        # Decision sheet: candidates × sizes on dark & light,
        # SHIPPED assets untouched.
        from PIL import Image, ImageDraw

        sheet_path = ROOT / "docs" / "screenshots" / "icon-candidates.png"
        cell, pad = 256, 26
        cols = len(VARIANTS)  # scales along, otherwise new candidates run off
        # Grid jump: the cut between micro and mark is the question
        # this sheet answers — so every cut edge gets rendered
        # (16/24/32/40/48), including the sizes never proven.
        small = (48, 40, 32, 24, 16)
        row_h = cell + sum(s * 2 + 8 for s in small) + pad
        sheet = Image.new("RGB", (cols * (cell + pad) + pad, 2 * row_h + 3 * pad), "#0b0b0b")
        draw = ImageDraw.Draw(sheet)

        def sheet_disc(size_px: int) -> str | None:
            """The disc the sheet shows for a mark cut at this size; a candidate
            draws itself."""
            return _mark_for(size_px) if variant in MARK_CUTS else None
        labels = {
            "mayfly": "1 · Eph (Eintagsfliege)", "dandelion": "2 · Pusteblume",
            "e": "3 · Dissolving e", "circle": "4 · Fading Circle (alt)",
            "breath": "5 · Breath",
            "mark": "6 · Mark (Waldgeist, ≥48 px)",
            "mark-compact": "7 · Mark compact (33–47 px)",
            "mark-micro": "8 · Mark micro (≤32 px)",
        }
        for r, bg_mode in enumerate(("dark", "light")):
            bg_hex = "#0b0b0b" if bg_mode == "dark" else "#e8e8e4"
            row_y = pad + r * (row_h + pad)
            draw.text((pad, row_y - 2), bg_mode.upper(), fill="#ffffff")
            for c, variant in enumerate(VARIANTS):
                x0 = pad + 30 + c * (cell + pad)
                y0 = row_y + 20
                with tempfile.TemporaryDirectory() as td:
                    tmp_png = Path(td) / "c.png"
                    _render(emblem_svg(full_bleed=False, variant=variant,
                                       disc=sheet_disc(cell)), cell, tmp_png,
                            transparent=False)
                    img = Image.open(tmp_png)
                    sheet.paste(img, (x0, y0))
                    for i, s in enumerate(small):
                        _render(emblem_svg(full_bleed=False, variant=variant,
                                           disc=sheet_disc(s)), s, tmp_png,
                                transparent=False)
                        sheet.paste(Image.open(tmp_png),
                                    (x0 + i * (s + 10), y0 + cell + 8))
                draw.text((x0 + 4, y0 + cell + 64), labels[variant], fill="#9adfae")
        sheet.save(sheet_path)
        print("comparison sheet:", sheet_path)
    elif _requested_variant() == "bee":
        # The shipped kit is the bee (brand decision 2026-10-16). The candidate
        # draws below stay reachable with an explicit --variant for comparisons.
        _bee_kit()
    else:
        # Legacy draws, reachable with --variant=mark|mayfly|dandelion|circle|e|breath:
        # the drop-spirit "mark" is still the source of the in-app vectors.
        variant = "mark"
        for arg in sys.argv[1:]:
            if arg.startswith("--variant="):
                variant = arg.split("=", 1)[1]
        assert variant in VARIANTS, f"unknown variant: {variant}"

        # The mark is cut per size; scaling alone fails: below 33 px the full face
        # runs into a blob, up to 47 px the ears need the thicker pair.
        def cut(size_px: int, scale: float = 1.0) -> str:
            if variant not in MARK_CUTS:
                return variant
            return mark_variant_for(int(round(size_px * scale)))

        def mark_disc(size_px: int, scale: float = 1.0) -> str | None:
            """The disc a render at `size_px` carries: the cut for that size with
            the trail the size can hold. A candidate draws itself."""
            if variant not in MARK_CUTS:
                return None
            rendered = int(round(size_px * scale))
            return _mark_for(rendered)

        # Master emblem (one SVG source in the repo, hand-editable). The browser
        # renders favicon.svg at 16 px — that file is the micro cut.
        (PUBLIC / "favicon.svg").write_text(
            emblem_svg(full_bleed=False, variant=cut(16), disc=mark_disc(16)), encoding="utf-8")
        # The brand as source code of the surface: `EpheMark` inlines this file
        # so the condensation of the mark has real SVG children — an `<img>`
        # would have none. Deliberately not in public/: from there it would be an image.
        # The vector carries no colour beyond the roles: var(--token) for every
        # fill and the eyes as knockouts, so one asset serves the icons, this
        # surface and the terminal, and the stylesheet tints it per theme.
        SRC_ASSETS.mkdir(parents=True, exist_ok=True)
        (SRC_ASSETS / "mark.svg").write_text(mark_svg(512), encoding="utf-8")
        # The template cut, shipped twice from the same shape: the vector an
        # in-app brand-tinted surface inlines, and the raster the tray imports.
        # The tray takes the mark's own bounding box (TRAY_VIEWBOX) so the glyph
        # fills a 22 pt tray icon instead of the 512 canvas.
        (SRC_ASSETS / "mark-mono.svg").write_text(
            mark_svg(44, mono=True), encoding="utf-8")
        _render(mark_svg(44, mono=True, view_box=TRAY_VIEWBOX,
                         tint=hex_for("template")), 44,
                TAURI_ICONS / "tray-mono.png", transparent=True)

        # index.html also attaches a PNG (a parser without SVG support). Without
        # this branch the old orb PNG stayed in the tab for two waves.
        # 48 px is the measured contract (tests/test_r68_brand_icons.py); the
        # crisp small corner up to 32 px is carried by favicon.svg, which gets
        # the micro cut above.
        _render(emblem_svg(full_bleed=False, variant=cut(48), disc=mark_disc(48)), 48,
                PUBLIC / "favicon.png", transparent=True)

        # PWA: any + maskable + apple-touch (opaque)
        _render(emblem_svg(full_bleed=False, variant=cut(192), disc=mark_disc(192)), 192,
                PUBLIC / "icon-192.png", transparent=True)
        _render(emblem_svg(full_bleed=False, variant=cut(512), disc=mark_disc(512)), 512,
                PUBLIC / "icon-512.png", transparent=True)
        for size in (192, 512):
            _render(emblem_svg(full_bleed=True, scale=0.72, variant=cut(size, 0.72),
                               disc=mark_disc(size, 0.72)), size,
                    PUBLIC / f"icon-maskable-{size}.png", transparent=False)
        _render(emblem_svg(full_bleed=True, scale=0.78, variant=cut(180, 0.78),
                           disc=mark_disc(180, 0.78)), 180,
                PUBLIC / "apple-touch-icon-180.png", transparent=False)

        # Tauri: standard set + Windows squares
        _render(emblem_svg(full_bleed=False, variant=cut(32), disc=mark_disc(32)), 32,
                TAURI_ICONS / "32x32.png", transparent=True)
        _render(emblem_svg(full_bleed=False, variant=cut(128), disc=mark_disc(128)), 128,
                TAURI_ICONS / "128x128.png", transparent=True)
        _render(emblem_svg(full_bleed=False, variant=cut(256), disc=mark_disc(256)), 256,
                TAURI_ICONS / "128x128@2x.png", transparent=True)
        _render(emblem_svg(full_bleed=False, variant=cut(512), disc=mark_disc(512)), 512,
                TAURI_ICONS / "icon.png", transparent=True)
        for name, size in TAURI_SQUARES.items():
            _render(emblem_svg(full_bleed=True, scale=0.9, variant=cut(size, 0.9),
                               disc=mark_disc(size, 0.9)), size,
                    TAURI_ICONS / name, transparent=False)

        _icns()
        _ico(TAURI_ICONS / "128x128@2x.png")
        print(f"brand assets written (variant={variant}):", PUBLIC, "and", TAURI_ICONS)
    browser.close()
