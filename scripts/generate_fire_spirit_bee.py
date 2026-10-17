#!/usr/bin/env python3
"""The fire-spirit bee as an in-app vector: calm and fierce.

The geometry is the drawing the design round settled (the review board of
2026-10-16): a soot-dark round bee whose comb belly lights through the seams, glass
wings in the calm register against fire-feather fans in the fierce one, ball-tip
antennae, a fibre brim and a staggered plume. Every paint is a role of
`scripts/brand_palette.py`, so one file serves both themes; the figure's own seven
material tokens stand in the dark block of the sheet and hold on paper, and only
the glass wing and the two brand roles bend with the ground.

The cuts follow the size, not the other way round (BEE_CUTS): the whole figure from
48 px, and the plain cut — head, blade and eye pair, one flat red — where the
figure's own texture would turn to dust and its soot body would vanish into the
icons' near-black ground. `mono` is the template modifier, one ink for the tray.

Writes `app/src/assets/fire-spirit-bee.svg` (calm), `…-fierce.svg` and
`…-mono.svg` (the one-ink template cut).
Usage: .venv/bin/python scripts/generate_fire_spirit_bee.py [--check]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from brand_palette import hex_for, paper_hex_for, token_for  # noqa: E402

ROOT = SCRIPTS.parent
OUT = ROOT / "app" / "src" / "assets"

VIEW = 512
CX, CY, R_BODY = 256.0, 314.0, 126.0

#: The bee's cuts, by declared size, the same table shape `MARK_CUTS` uses in
#: `scripts/generate_brand_assets.py` so both figures route identically.
#:   <=47 bee-micro — the plain cut: the head, the central blade and the eye pair,
#:                    one flat red. Below 48 px the figure's own texture (comb
#:                    seams, fur brim, glass wings, hairline antennae) is dust, and
#:                    on the icons' near-black ground the soot body measures 1.09:1
#:                    — invisible — so this is the cut the tab, the launcher tile
#:                    and the tray carry.
#:   >=48 bee       — the whole figure: the lit comb belly, the eyes with their
#:                    pupils and glints, the wings and the plume. The character
#:                    only arrives at 48 px (the icon judge, 2026-10-16).
BEE_CUTS = {
    "bee": (48, None),      # from 48 px
    "bee-micro": (0, 47),   # up to 47 px
}

#: Orthogonal to the size bands, exactly as `MARK_MODIFIERS` is: a modifier names
#: the asset and never the size, so the two can never collide. `mono` is the template
#: cut — one ink, tintable by the host, the tray image.
BEE_MODIFIERS = ("mono",)


def bee_for(size: int) -> str:
    """Cut name for a target size in px (thresholds: BEE_CUTS)."""
    for name, (low, high) in BEE_CUTS.items():
        if size >= low and (high is None or size <= high):
            return name
    return "bee-micro"


def bee_asset_for(size: int, *, mono: bool = False) -> str:
    """Asset name a target size routes to, with the modifier that was asked for."""
    cut = bee_for(size)
    return f"{cut}+mono" if mono else cut


#: The template raster crops to the glyph's own bounding box on the emblem canvas
#: (measured: x 130..382, y 80..440, antenna balls and the fat blade included) plus
#: a margin, so a 22 pt tray icon carries the figure and not the canvas around it.
#: Square, because the tray is: a non-square box would letterbox the glyph.
TRAY_VIEW = "48 52 416 416"

#: the two registers and the id prefix each one carries; the component rewrites the
#: prefix per instance, and the two prefixes differ so both can stand on one page
#: (the scene crossfades them, so they do).
REGISTERS = {"calm": "bspc", "fierce": "bspf"}

#: pointy-top plate layout: (dx, dy, r, rot), hand-jittered; the bottom centre stays
#: open as the vent the belly light comes through.
PLATES = ((-92, 32, 23, 44), (-46, 32, 22, 58), (0, 32, 24, 36), (46, 32, 23, 64),
          (92, 32, 24, 40), (-69, 72, 22, 20), (-100, 72, 21, 30), (-23, 72, 24, 48),
          (23, 72, 23, 66), (69, 72, 22, 32), (100, 72, 21, 60), (-48, 108, 15, 52),
          (48, 108, 16, 40))


def role(name: str) -> str:
    """The in-app spelling of a palette role: the custom property the sheet resolves."""
    return f"var({token_for(name)})"


def loop_frame(phase: float) -> dict[str, float]:
    """One frame of the alight loop, as factors. `phase` runs 0..1 once per loop.

    The clip is a breath, never a performance: the being lifts and settles, the plume
    lengthens and shortens, the glass shimmer and the inner glow follow with their own
    offsets so nothing moves in lockstep. Every factor returns to its phase-0 value at
    phase 1, so the loop closes on itself with no seam.
    """
    t = 2.0 * math.pi * phase
    return {
        "bob": -7.0 * math.sin(t),            # units on the 512 grid; up is negative
        "sway": 1.2 * math.sin(t + 0.6),      # degrees, about the plume's root
        "plume": 1.0 + 0.07 * math.sin(t + 0.9),
        "glow": 1.0 + 0.12 * math.sin(t + 1.7),
        "wing": 0.84 + 0.16 * math.sin(t + 2.4),
    }


def dim(element: str, factor: float) -> str:
    """Wrap one element so its own opacity scales. A no-op at factor 1."""
    if abs(factor - 1.0) < 1e-9:
        return element
    return f'<g opacity="{max(0.0, min(1.0, factor)):.3f}">{element}</g>'


def about(point: tuple[float, float], transform: str) -> str:
    """An SVG transform about `point`, so a group rotates or scales in place."""
    x, y = point
    return f"translate({x:.1f},{y:.1f}) {transform} translate({-x:.1f},{-y:.1f})"


def hex_cell(cx: float, cy: float, r: float, rot: float = 30.0, soft: float = 0.16) -> str:
    pts = []
    for i in range(6):
        a = math.radians(rot + i * 60.0)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d = []
    n = len(pts)
    for i in range(n):
        p_prev, p, p_next = pts[i - 1], pts[i], pts[(i + 1) % n]
        q1 = (p[0] + (p_prev[0] - p[0]) * soft, p[1] + (p_prev[1] - p[1]) * soft)
        q2 = (p[0] + (p_next[0] - p[0]) * soft, p[1] + (p_next[1] - p[1]) * soft)
        d.append(f"{'M' if i == 0 else 'L'}{q1[0]:.1f},{q1[1]:.1f}")
        d.append(f"Q{p[0]:.1f},{p[1]:.1f} {q2[0]:.1f},{q2[1]:.1f}")
    d.append("Z")
    return " ".join(d)


def leaf_wing(side: int, root_x: float, root_y: float, tip_x: float, tip_y: float,
              root_half: float, belly: float = 0.5, tip_r: float = 0.0) -> str:
    """A wing or flame as a curved leaf: root chord, belly bowed toward `side`."""
    ax, ay = tip_x - root_x, tip_y - root_y
    length = math.hypot(ax, ay)
    ux, uy = ax / length, ay / length
    px, py = -uy, ux
    if px * side < 0:
        px, py = -px, -py
    b1x, b1y = root_x + px * root_half, root_y + py * root_half
    b2x, b2y = root_x - px * root_half, root_y - py * root_half
    mx, my = root_x + ax * 0.45, root_y + ay * 0.45
    k1x, k1y = mx + px * belly * length * 0.55, my + py * belly * length * 0.55
    k2x, k2y = mx - px * belly * length * 0.38, my - py * belly * length * 0.38
    if tip_r > 0:
        sh, cap = tip_r * 0.5, tip_r
        tip_edge = (f"Q{k1x:.1f},{k1y:.1f} {tip_x - ux * sh:.1f},{tip_y - uy * sh:.1f} "
                    f"Q{tip_x + ux * cap:.1f},{tip_y + uy * cap:.1f} "
                    f"{tip_x - ux * sh:.1f},{tip_y - uy * sh:.1f}")
    else:
        tip_edge = f"Q{k1x:.1f},{k1y:.1f} {tip_x:.1f},{tip_y:.1f}"
    return (f"M{b1x:.1f},{b1y:.1f} {tip_edge} "
            f"Q{k2x:.1f},{k2y:.1f} {b2x:.1f},{b2y:.1f} Z")


def _svg(body: str) -> str:
    """The in-app `<svg>` root around a body: a 512 canvas, no text, no image."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" '
            f'role="img">{body}</svg>')


def _eye_holes() -> str:
    """The two eyes as subpaths of the head, punched by `fill-rule="evenodd"`.

    The field behind the cut shows the face, so the plain cut needs no ground role
    of its own — the same trick the mark's knockout eyes use, at the figure's own
    eye centres.
    """
    return "".join(
        f" M{CX + s * 47 - 35} {CY - 58} a35 41 0 1 0 70 0 a35 41 0 1 0 -70 0 Z"
        for s in (-1, 1))


def _plain_blade() -> str:
    """The plain cut's blade, wider at the root and shorter at the tip.

    The figure's own core tapers to a point that is already sub-pixel at 47 px, so
    the small cut fattens the flame where it meets the head — the same correction
    the fire-spirit micro applies to its neck.
    """
    return leaf_wing(-1, CX, CY - 98, CX - 4, 84, 46, 0.5, 30)


def micro_body(paint) -> str:
    """The plain cut: the head, the blade and the eye pair, one flat red.

    Below 48 px the figure's own texture — comb seams, fur brim, glass wings,
    hairline antennae — is dust, and on the icons' near-black ground the soot body
    measures 1.09:1, which is invisible. The plain cut is therefore the silhouette
    the brand paints on the ground it ships on: the round head, the central blade
    that makes it fire and not a ball, and the two eyes as knockouts. No antennae,
    no wings, no seams, no beads and no halo.
    """
    head = (f"M{CX - R_BODY},{CY} a{R_BODY},{R_BODY} 0 1 0 {2 * R_BODY},0 "
            f"a{R_BODY},{R_BODY} 0 1 0 {-2 * R_BODY},0 Z")
    red = paint("brand")
    return (f'<path d="{head}{_eye_holes()}" fill="{red}" fill-rule="evenodd"/>'
            f'<path d="{_plain_blade()}" fill="{red}"/>')


def mono_body(register: str) -> str:
    """The template cut: one ink, the head, the blade and the antennae.

    An alpha mask has no second colour to cut an eye out of the body with, so the
    face is the outline alone and the system tints the whole glyph — the contract
    `mark-mono.svg` holds. The antennae stay and the blade is the fat one, because
    a 22 pt tray image has room for neither detail nor a hairline tip.
    """
    antennae = ""
    for s in (-1, 1):
        bx, by = CX + s * 34, CY - 116
        tx, ty = CX + s * 90, CY - 212
        stalk = f"M{bx},{by} C{CX + s * 44},{CY - 164} {CX + s * 58},{CY - 194} {tx},{ty}"
        antennae += (f'<path d="{stalk}" stroke="currentColor" stroke-width="12" '
                     f'fill="none" stroke-linecap="round"/>'
                     f'<circle cx="{tx}" cy="{ty - 6}" r="16"/>')
    return (f'<g fill="currentColor"><circle cx="{CX}" cy="{CY}" r="{R_BODY}"/>'
            f'<path d="{_plain_blade()}"/>{antennae}</g>')


def bee_body(register: str, size: int = 512, *, mono: bool = False,
             ground: str = "ink") -> str:
    """The figure's body for a target size, in the concrete spelling, unwrapped.

    The kit generator composes an emblem around this: it hands the raster the hex
    spelling (`ground`) and the cut the icons route through for `size`.
    """
    svg = figure(register, cut=bee_for(size), mono=mono, ground=ground)
    return svg[svg.index(">", svg.index("<svg")) + 1: -len("</svg>")]


def figure(register: str, wave: dict[str, float] | None = None, groups: bool = False,
           cut: str = "bee", mono: bool = False, ground: str = "var") -> str:
    """The bee at `cut`, in the spelling `ground` asks for.

    With `wave` the same drawing is asked to move: the parts that lift, breathe and
    shimmer are wrapped in groups, so no coordinate and no paint changes with the
    frame. With `groups` the plume, the wings, the belly and the face carry a
    `data-part` hook, which is what the film stages its reveals with. Both flags
    off — the default — is the still, byte for byte, which is what `--check` holds.

    `cut` picks the size band (BEE_CUTS): the whole figure, or the plain cut the
    icons use up to 47 px. `mono` is the template modifier — one ink, the trunk
    silhouette an alpha mask can carry. `ground` decides the spelling: `var` is the
    in-app vector the stylesheet resolves, `ink`/`paper` concretise the roles to the
    hex a raster needs, because a raster has no stylesheet behind it.
    """
    if register not in REGISTERS:
        raise SystemExit(f"unknown register {register!r}")
    if cut not in BEE_CUTS:
        raise SystemExit(f"unknown cut {cut!r}")
    u = REGISTERS[register]
    fierce = register == "fierce"
    w = wave or {}

    def paint(name: str) -> str:
        if ground == "var":
            return role(name)
        return (hex_for if ground == "ink" else paper_hex_for)(name)

    if mono:
        return _svg(mono_body(register))
    if cut == "bee-micro":
        return _svg(micro_body(paint))

    def hook(body: str, name: str) -> str:
        return f'<g data-part="{name}">{body}</g>' if groups else body

    brand, glow = paint("brand"), paint("brand_glow")
    soot, plate = paint("figure_soot"), paint("figure_plate")
    fur, mou = paint("figure_fur"), paint("figure_mou")
    ember, cream, shine = paint("figure_ember"), paint("figure_cream"), paint("figure_shine")

    parts: list[str] = []
    plume: list[str] = []
    wings: list[str] = []
    face: list[str] = []

    halo = (f'<circle cx="{CX}" cy="{CY}" r="{R_BODY + (48 if fierce else 30)}" '
            f'fill="url(#{u}-halo)" opacity="{0.32 if fierce else 0.2:.2f}"/>')
    parts.append(dim(halo, w.get("glow", 1.0)))

    tongues: list[str] = []
    if fierce:
        for s in (-1, 1):
            tongues.append(leaf_wing(s, CX + s * 46, CY - 98, CX + s * 50, 70, 34, 0.5, 24))
            tongues.append(leaf_wing(s, CX + s * 74, CY - 90, CX + s * 118, CY - 176, 30, 0.55, 20))
        tongues.append(leaf_wing(-1, CX, CY - 104, CX - 10, 26, 44, 0.45, 28))
    else:
        for s in (-1, 1):
            tongues.append(leaf_wing(s, CX + s * 40, CY - 94, CX + s * 54, 74, 34, 0.5, 24))
            tongues.append(leaf_wing(s, CX + s * 72, CY - 86, CX + s * 112, CY - 144, 30, 0.55, 20))
        tongues.append(leaf_wing(-1, CX, CY - 100, CX - 6, 54, 46, 0.45, 30))
    plume.append(f'<path d="{" ".join(tongues)}" fill="{brand}"/>')
    core = (leaf_wing(-1, CX, CY - 100, CX - 6, 44, 34, 0.5, 24) if fierce
            else leaf_wing(-1, CX, CY - 98, CX - 4, 76, 36, 0.5, 26))
    plume.append(f'<path d="{core}" fill="{cream}" opacity="0.85"/>')

    if fierce:
        crest = [leaf_wing(-1, CX - 38, CY - 118, CX - 48, CY - 172, 20, 0.6, tip_r=12.4),
                 leaf_wing(1, CX, CY - 122, CX + 2, CY - 186, 20, 0.5, tip_r=13.6),
                 leaf_wing(1, CX + 38, CY - 118, CX + 48, CY - 172, 20, 0.6, tip_r=12.4)]
        plume.append(f'<path d="{" ".join(crest)}" fill="{glow}"/>')

    # the plume rides its own group, so the clip can sway it about its root
    if "sway" in w:
        sway_transform = about((CX, CY - 40), f"rotate({w['sway']:.2f})")
        parts.append(hook(f'<g transform="{sway_transform}">{"".join(plume)}</g>', "plume"))
    else:
        parts.append(hook("".join(plume), "plume"))

    if fierce:
        fan = []
        for s in (-1, 1):
            fan.append(leaf_wing(s, CX + s * 108, CY - 44, CX + s * 176, CY - 152, 22, 0.55))
            fan.append(leaf_wing(s, CX + s * 110, CY - 32, CX + s * 192, CY - 86, 24, 0.55))
            fan.append(leaf_wing(s, CX + s * 108, CY - 12, CX + s * 174, CY - 10, 22, 0.55))
        wings.append(f'<path d="{" ".join(fan)}" fill="{glow}"/>')
    else:
        wing_axes = [(s, CX + s * 92, CY - 32, CX + s * 226, CY - 110, 50.0) for s in (-1, 1)]
        wing_axes += [(s, CX + s * 88, CY + 6, CX + s * 198, CY + 84, 38.0) for s in (-1, 1)]
        for s, rx, ry, tx, ty, rh in wing_axes:
            d = leaf_wing(s, rx, ry, tx, ty, rh, 0.6, 28.0)
            wings.append(f'<path d="{d}" fill="url(#{u}-wing-{"r" if s > 0 else "l"})" '
                         f'stroke="{glow}" stroke-width="4" stroke-linejoin="round"/>')
        for s, rx, ry, tx, ty, rh in wing_axes:
            axs, ays = tx - rx, ty - ry
            ln = math.hypot(axs, ays)
            ux, uy = axs / ln, ays / ln
            px, py = -uy, ux
            if px * s < 0:
                px, py = -px, -py
            for f0, f1, wf, tr in ((0.22, 0.88, 0.55, 16.0), (0.48, 0.97, 0.26, 8.0)):
                d = leaf_wing(s, rx + axs * f0, ry + ays * f0,
                              rx + axs * f1, ry + ays * f1, rh * wf, 0.5, tr)
                wings.append(f'<path d="{d}" fill="none" stroke="{glow}" '
                             f'stroke-width="2.5" opacity="0.9"/>')
            for t, reach in ((0.52, 0.62), (0.74, 0.42)):
                x0 = rx + axs * t + px * 5
                y0 = ry + ays * t + py * 5
                x1 = rx + axs * t + px * rh * reach
                y1 = ry + ays * t + py * rh * reach
                wings.append(f'<path d="M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}" '
                             f'fill="none" stroke="{glow}" stroke-width="2.5" opacity="0.9"/>')

    parts.append(hook(dim("".join(wings), w.get("wing", 1.0)), "wings"))

    for s in (-1, 1):
        bx, by = CX + s * 34, CY - 116
        tx, ty = CX + s * 90, CY - 212
        dpath = f"M{bx},{by} C{CX + s * 44},{CY - 164} {CX + s * 58},{CY - 194} {tx},{ty}"
        parts.append(f'<path d="{dpath}" stroke="{mou}" stroke-width="12" '
                     f'fill="none" stroke-linecap="round" opacity="0.7"/>')
        parts.append(f'<path d="{dpath}" stroke="{soot}" stroke-width="8" '
                     f'fill="none" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{tx}" cy="{ty - 6}" r="16" fill="{plate}" '
                     f'stroke="{brand}" stroke-width="4"/>')
        parts.append(f'<circle cx="{tx - 9}" cy="{ty - 10}" r="4" fill="{shine}" opacity="0.9"/>')

    parts.append(f'<circle cx="{CX}" cy="{CY}" r="{R_BODY}" fill="{soot}" '
                 f'stroke="{mou}" stroke-width="4" stroke-opacity="0.85"/>')

    def spike(a_deg: float, length: float, base: float) -> str:
        a = math.radians(a_deg)
        da = base / (2 * R_BODY)
        x1 = CX + math.cos(a - da) * (R_BODY - 3)
        y1 = CY + math.sin(a - da) * (R_BODY - 3)
        x2 = CX + math.cos(a + da) * (R_BODY - 3)
        y2 = CY + math.sin(a + da) * (R_BODY - 3)
        xt = CX + math.cos(a) * (R_BODY + length)
        yt = CY + math.sin(a) * (R_BODY + length)
        return f"M{x1:.1f},{y1:.1f} L{xt:.1f},{yt:.1f} L{x2:.1f},{y2:.1f} Z"

    brim_lo = [spike(20 + i * (140 / 27), 7, 7) for i in range(28)]
    brim_hi = [spike(214 + i * (112 / 23), 8, 7.5) for i in range(24)]
    parts.append(f'<path d="{" ".join(brim_lo)}" fill="{fur}"/>')
    parts.append(f'<path d="{" ".join(brim_hi)}" fill="{mou}"/>')
    fur_glow = (f'<ellipse cx="{CX}" cy="{CY - 116}" rx="46" ry="16" fill="{glow}" '
                f'opacity="0.35" filter="url(#{u}-soft)"/>')
    parts.append(dim(fur_glow, w.get("glow", 1.0)))
    tuft = [spike(250 + i * (40 / 6), 20, 12) for i in range(7)]
    parts.append(f'<path d="{" ".join(tuft)}" fill="{mou}"/>')

    plates = [hex_cell(CX + dx, CY + dy, r, rot) for dx, dy, r, rot in PLATES]
    top = (f"M{CX - 128},{CY + 10} Q{CX},{CY - 6} {CX + 128},{CY + 10} "
           f"L{CX + 128},{CY + 210} L{CX - 128},{CY + 210} Z")
    parts.append(hook(f'<g clip-path="url(#{u}-clip)">'
                      f'<path d="{top}" fill="url(#{u}-belly)"/>'
                      f'<path d="{top}" fill="url(#{u}-dometop)"/>'
                      f'<g clip-path="url(#{u}-dome)">'
                      f'<path d="{" ".join(plates)}" fill="{plate}" stroke="{glow}" '
                      f'stroke-width="2.5" stroke-opacity="0.45" stroke-linejoin="round"/></g></g>',
                      "belly"))

    fringe = "".join(
        f'<circle cx="{CX + k * 30}" cy="{CY - 2 - abs(k) * 3}" r="13" fill="{soot}"/>'
        for k in (-3, -2, -1, 1, 2, 3))
    parts.append(fringe)
    skirt = ([spike(38 + i * 8, 13, 8) for i in range(6)]
             + [spike(102 + i * 8, 13, 8) for i in range(6)])
    parts.append(f'<path d="{" ".join(skirt)}" fill="{fur}"/>')
    belly_glow = (f'<ellipse cx="{CX}" cy="{CY + 2}" rx="64" ry="16" fill="{brand}" '
                  f'opacity="0.3" filter="url(#{u}-soft)"/>')
    parts.append(dim(belly_glow, w.get("glow", 1.0)))

    for s in (-1, 1):
        face.append(f'<ellipse cx="{CX + s * 47}" cy="{CY - 58}" rx="35" ry="41" '
                    f'fill="url(#{u}-eye)"/>')
    if fierce:
        for s in (-1, 1):
            face.append(f'<path d="M{CX + s * 84},{CY - 99} L{CX + s * 10},{CY - 99} '
                        f'L{CX + s * 10},{CY - 62} Z" fill="{soot}"/>')
    for s in (-1, 1):
        face.append(f'<circle cx="{CX + s * 53}" cy="{CY - 66}" r="13" fill="{soot}"/>')
        face.append(f'<circle cx="{CX + s * 53 - 6}" cy="{CY - 72}" r="4" fill="{shine}" '
                    f'opacity="0.95"/>')

    if fierce:
        face.append(f'<path d="M{CX - 30},{CY - 16} Q{CX},{CY + 14} {CX + 30},{CY - 16}" '
                    f'fill="none" stroke="{mou}" stroke-width="9" stroke-linecap="round"/>')
    else:
        face.append(f'<path d="M{CX - 21},{CY - 12} Q{CX},{CY + 6} {CX + 21},{CY - 12}" '
                    f'fill="none" stroke="{mou}" stroke-width="7" stroke-linecap="round"/>')
    parts.append(hook("".join(face), "face"))

    parts.append(f'<ellipse cx="{CX}" cy="{CY + 148}" rx="64" ry="14" fill="{brand}" '
                 f'opacity="0.35" filter="url(#{u}-soft)"/>')
    for s in (-1, 1):
        dpath = (f"M{CX + s * 36},{CY + 104} C{CX + s * 38},{CY + 128} "
                 f"{CX + s * 44},{CY + 140} {CX + s * 46},{CY + 145}")
        foot_glow = (f'<path d="{dpath}" stroke="{glow}" stroke-width="23" fill="none" '
                     f'stroke-linecap="round" opacity="0.5"/>')
        parts.append(dim(foot_glow, w.get("glow", 1.0)))
        parts.append(f'<path d="{dpath}" stroke="{fur}" stroke-width="15" fill="none" '
                     f'stroke-linecap="round"/>')

    if fierce:
        sparks = ((-208, -146, 8), (-172, -202, 6), (196, -182, 7), (220, -70, 8),
                  (-226, 44, 7), (178, 148, 6), (-148, 186, 6))
        for dx, dy, r in sparks:
            parts.append(f'<circle cx="{CX + dx}" cy="{CY + dy}" r="{r}" fill="{glow}"/>')

    # The eye gradient stands first: `scripts/mark_contract.py` reads the last stop of
    # the first gradient as the figure's red, and the eye is where the brand role is
    # the one on the outside.
    defs = [
        f'<radialGradient id="{u}-eye" cx="50%" cy="30%" r="85%">'
        f'<stop offset="0%" stop-color="{cream}"/>'
        f'<stop offset="42%" stop-color="{cream}"/>'
        f'<stop offset="78%" stop-color="{ember}"/>'
        f'<stop offset="100%" stop-color="{brand}"/></radialGradient>',
        f'<radialGradient id="{u}-halo" cx="50%" cy="58%" r="50%">'
        f'<stop offset="0%" stop-color="{glow}"/>'
        f'<stop offset="100%" stop-color="{glow}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="{u}-belly" cx="50%" cy="84%" r="66%">'
        f'<stop offset="0%" stop-color="{cream}"/>'
        f'<stop offset="75%" stop-color="{cream}"/>'
        f'<stop offset="100%" stop-color="{glow}"/></radialGradient>',
        f'<clipPath id="{u}-clip"><circle cx="{CX}" cy="{CY}" r="{R_BODY}"/></clipPath>',
        f'<clipPath id="{u}-dome"><path d="{top}"/></clipPath>',
        f'<linearGradient id="{u}-dometop" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{soot}" stop-opacity="0.5"/>'
        f'<stop offset="21%" stop-color="{soot}" stop-opacity="0"/></linearGradient>',
        f'<filter id="{u}-soft" x="-60%" y="-140%" width="220%" height="380%">'
        f'<feGaussianBlur stdDeviation="6"/></filter>',
    ]
    if not fierce:
        wstops = (f'<stop offset="0%" stop-color="{paint("figure_wing_root")}"/>'
                  f'<stop offset="45%" stop-color="{paint("figure_wing_mid")}"/>'
                  f'<stop offset="100%" stop-color="{paint("figure_wing_tip")}"/>')
        defs.append(f'<radialGradient id="{u}-wing-r" cx="0%" cy="50%" r="90%">{wstops}</radialGradient>')
        defs.append(f'<radialGradient id="{u}-wing-l" cx="100%" cy="50%" r="90%">{wstops}</radialGradient>')

    body = "".join(parts)
    if "bob" in w:
        body = f'<g transform="translate(0,{w["bob"]:.2f})">{body}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}" role="img">'
            f'<defs>{"".join(defs)}</defs>{body}</svg>')


def theme_tokens(theme: str) -> str:
    """The role values a raster needs, because a raster has no stylesheet behind it.

    A clip carries one spelling, so it ships twice — once per ground — exactly like the
    figure's PNG cuts. The seven material tokens are the same in both; the brand roles
    and the glass wing are the pair that bends.
    """
    pick = hex_for if theme == "ink" else paper_hex_for
    names = ("figure_soot", "figure_plate", "figure_fur", "figure_mou", "figure_ember",
             "figure_cream", "figure_shine", "figure_wing_root", "figure_wing_mid",
             "figure_wing_tip")
    body = "".join(f"{token_for(name)}: {pick(name)};" for name in names)
    return (f":root {{ {body} {token_for('brand')}: {pick('brand')}; "
            f"{token_for('brand_glow')}: {pick('brand_glow')}; }}")


def clip(register: str = "calm", theme: str = "ink", frames: int = 48, size: int = 512,
         fps: int = 24, scale: int = 2, out: Path | None = None) -> Path:
    """The alight loop as an animated WebP with alpha, beside its poster frame.

    Frames come from the same drawing at `scale` times the output size and are
    downsampled, so the clip carries the vector's edges rather than a screenshot of
    them, and the alpha channel rides through WebP untouched: the being can stand on
    any ground — the tokens of `theme` decide which reds it carries. The loop closes by
    construction, because `loop_frame` returns to its start.
    """
    from PIL import Image  # noqa: PLC0415
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    out = out or (ROOT / "videos" / "first-run-clips")
    out.mkdir(parents=True, exist_ok=True)
    rendered: list = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size},
                                device_scale_factor=scale)
        for index in range(frames):
            svg = figure(register, wave=loop_frame(index / frames))
            page.set_content(
                "<html><head><style>" + theme_tokens(theme) + "</style></head>"
                "<body style='margin:0;background:transparent'>"
                f"<div style='width:{size}px;height:{size}px'>{svg}</div></body></html>",
                wait_until="load")
            shot = out / f".frame-{index:03d}.png"
            page.screenshot(path=str(shot), omit_background=True)
            with Image.open(shot) as frame:
                rendered.append(frame.convert("RGBA").resize((size, size), resampling))
            shot.unlink()
        browser.close()

    webp = out / f"spirit-{register}-awake-{size}-{theme}.webp"
    rendered[0].save(webp, format="WEBP", save_all=True, append_images=rendered[1:],
                     duration=round(1000 / fps), loop=0, quality=92, method=6)
    poster = out / f"spirit-{register}-awake-{size}-{theme}-poster.png"
    rendered[0].save(poster)
    print(f"wrote {webp.name}: {frames} frames at {fps} fps, "
          f"{webp.stat().st_size / 1024:.0f} kB; poster {poster.name}")
    return webp


def targets() -> dict[Path, str]:
    out = {OUT / f"fire-spirit-bee{'-fierce' if r == 'fierce' else ''}.svg": figure(r)
           for r in ("calm", "fierce")}
    out[OUT / "fire-spirit-bee-mono.svg"] = figure("calm", mono=True)
    return out


#: The rungs the owner's rule (2026-10-09) asks a shipped visual to prove: 16 px to
#: 256 px. The icon set adds 192 and the 22 pt tray as its own sizes.
PROOF_RUNGS = (16, 24, 32, 48, 96, 192, 256)
PROOF_DIR = ROOT / "docs" / "brand" / "fire-spirit-bee" / "proof"


def _tile_svg(register: str, size: int) -> str:
    """The shipped icon around a cut: a rounded near-black tile and its glow."""
    glow = (f'<radialGradient id="pg" cx="38%" cy="42%" r="62%">'
            f'<stop offset="0%" stop-color="{hex_for("panel")}" stop-opacity="0.9"/>'
            f'<stop offset="100%" stop-color="{hex_for("panel")}" stop-opacity="0"/></radialGradient>'
            f'<rect width="{VIEW}" height="{VIEW}" fill="url(#pg)" rx="108"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}">'
            f'<rect x="18" y="18" width="{VIEW - 36}" height="{VIEW - 36}" rx="108" '
            f'fill="{hex_for("ground")}"/>{glow}'
            f'{bee_body(register, size)}</svg>')


def _ground_svg(register: str, size: int, ground: str) -> str:
    """The figure's own cut on one ground, for the ladder's legibility rows."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}">'
            f'{bee_body(register, size, ground=ground)}</svg>')


def proof(register: str = "calm") -> int:
    """The icon ladder and the tray one-plane proof, with the measured numbers.

    Three rows over the same rungs: the shipped tile, the figure on ink and the
    figure on paper — every rung the cut the surface itself routes to, so the proof
    and the product cannot drift. The tray is shown at its 22 pt render and at a
    16 px resample, where a template image has to stay one plane. The numbers are
    printed; the floors live in `scripts/asset_check.py`.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    cell, pad, label = 256, 22, 26
    rows = (("icon (shipped tile)", "#0b0b0b"), ("figure on ink", "#121212"),
            ("figure on paper", "#F0F0E6"))

    def shot(svg: str, size: int, out: Path, bg: str) -> None:
        html = ("<html><head><style>*{margin:0;padding:0}"
                f"svg{{width:{size}px;height:{size}px;display:block}}"
                f"body{{background:{bg}}}</style></head><body>{svg}</body></html>")
        page.set_viewport_size({"width": size, "height": size})
        page.set_content(html)
        page.screenshot(path=str(out), omit_background=(bg == "transparent"))

    width = pad + len(PROOF_RUNGS) * (cell + pad)
    height = pad + len(rows) * (cell + pad + label)
    sheet = Image.new("RGB", (width, height), "#0b0b0b")
    draw = ImageDraw.Draw(sheet)
    for r, (title, bg) in enumerate(rows):
        y = pad + r * (cell + pad + label)
        draw.text((pad, y - label + 6), title, fill=(205, 200, 195))
        for c, size in enumerate(PROOF_RUNGS):
            x = pad + c * (cell + pad)
            svg = (_tile_svg(register, size) if r == 0
                   else _ground_svg(register, size, "ink" if r == 1 else "paper"))
            tmp = PROOF_DIR / f".rung-{r}-{size}.png"
            shot(svg, size, tmp, bg)
            with Image.open(tmp) as tile:
                sheet.paste(tile.convert("RGB").resize((cell, cell), Image.LANCZOS), (x, y))
            tmp.unlink()
            draw.text((x + 4, y + cell + 4), f"{size} px", fill=(150, 145, 140))
    ladder = PROOF_DIR / "icon-ladder-16-256.png"
    sheet.save(ladder)

    tray = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{TRAY_VIEW}" role="img" '
            f'style="color:{hex_for("template")}">{mono_body(register)}</svg>')
    shot(tray, 44, PROOF_DIR / ".tray-44.png", "transparent")
    with Image.open(PROOF_DIR / ".tray-44.png") as big:
        resampled = big.convert("RGBA").resize((16, 16), Image.LANCZOS)
    sheet = Image.new("RGB", (pad + 2 * (cell + pad), pad + cell + label), "#e8e8e4")
    draw = ImageDraw.Draw(sheet)
    with Image.open(PROOF_DIR / ".tray-44.png") as big:
        sheet.paste(big.convert("RGBA").resize((cell, cell), Image.NEAREST), (pad, pad),
                    big.convert("RGBA").resize((cell, cell), Image.NEAREST))
    sheet.paste(resampled.resize((cell, cell), Image.NEAREST), (pad + cell + pad, pad),
                resampled.resize((cell, cell), Image.NEAREST))
    draw.text((pad, pad + cell + 6), "tray template, 44 px", fill=(60, 60, 60))
    draw.text((pad + cell + pad, pad + cell + 6), "the same, resampled to 16 px: one plane",
              fill=(60, 60, 60))
    tray_proof = PROOF_DIR / "tray-template-16.png"
    sheet.save(tray_proof)
    (PROOF_DIR / ".tray-44.png").unlink()

    pixels = list(resampled.get_flattened_data())
    visible = sum(1 for r, g, b, a in pixels if a > 128)
    planes = sorted({(r, g, b) for r, g, b, a in pixels if a > 128})
    for path in (ladder, tray_proof):
        print(f"wrote {path.relative_to(ROOT)}")
    print(f"  tray template at 16 px: {visible} visible px, plane(s) {planes}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 if a file on disk differs")
    parser.add_argument("--clip", metavar="REGISTER", nargs="?", const="calm",
                        help="render the alight loop as an animated WebP (calm|fierce)")
    parser.add_argument("--theme", choices=("ink", "paper"), default="ink",
                        help="which ground's reds the clip carries")
    parser.add_argument("--frames", type=int, default=48, help="frames in the loop")
    parser.add_argument("--size", type=int, default=512, help="clip edge in px")
    parser.add_argument("--out", type=Path, default=None, help="where the clip lands")
    parser.add_argument("--proof", action="store_true",
                        help="render the icon ladder and the tray one-plane proof")
    args = parser.parse_args(argv)
    if args.proof:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        global page
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(device_scale_factor=1)
            code = proof()
            browser.close()
        return code
    if args.clip:
        clip(args.clip, theme=args.theme, frames=args.frames, size=args.size, out=args.out)
        return 0
    drift = []
    for path, content in targets().items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != content:
                drift.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(content)} bytes)")
    if args.check and drift:
        for path in drift:
            print(f"drift: {path.relative_to(ROOT)} differs from the generator")
        return 1
    if args.check:
        print("fire-spirit-bee: every file matches the generator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
