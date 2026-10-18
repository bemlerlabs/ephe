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
CX, CY = 256.0, 236.0
HEAD_RX, HEAD_RY = 96.0, 88.0
BELLY_CY, BELLY_RX, BELLY_RY = 368.0, 106.0, 98.0
R_BODY = 96.0

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
    """The two eyes as subpaths of the head, punched by `fill-rule="evenodd"`."""
    return "".join(
        f" M{CX + s * 46 - 28} {CY + 2} a28 33 0 1 0 56 0 a28 33 0 1 0 -56 0 Z"
        for s in (-1, 1)
    )


def _plain_blade() -> str:
    """The plain cut's centre flame, wider at the root and shorter at the tip."""
    return leaf_wing(-1, CX, CY - 70, CX - 4, 34, 44, 0.5, 30)


def _micro_crown() -> str:
    """The v2 silhouette's crown for the small cuts: two leaf ears and a flame."""
    ears = (leaf_wing(-1, CX - 35, CY - 74, CX - 64, CY - 158, 24, 0.5, 16)
            + leaf_wing(1, CX + 35, CY - 74, CX + 64, CY - 158, 24, 0.5, 16))
    flame = leaf_wing(-1, CX, CY - 78, CX - 2, CY - 172, 28, 0.45, 18)
    return ears + flame


def micro_body(paint) -> str:
    """The plain cut: the head, the v2 crown and the eye pair, one flat red."""
    head = (f"M{CX - HEAD_RX},{CY} a{HEAD_RX},{HEAD_RY} 0 1 0 {2 * HEAD_RX},0 "
            f"a{HEAD_RX},{HEAD_RY} 0 1 0 {-2 * HEAD_RX},0 Z")
    red = paint("brand")
    # The icon tile is the small cut's frame: scale the silhouette to its own bounding
    # box so the 32 px raster still carries the brand red at a readable mass.
    return (f'<g transform="translate({CX},{CY}) scale(1.34) translate({-CX},{-CY})">'
            f'<path d="{_micro_crown()}" fill="{red}"/>'
            f'<path d="{head}{_eye_holes()}" fill="{red}" fill-rule="evenodd"/></g>')


def mono_body(register: str) -> str:
    """The template cut: one ink, the head, the crown, the blade and the antennae."""
    antennae = ""
    for s in (-1, 1):
        bx, by = CX + s * 30, CY - 82
        tx, ty = CX + s * 76, CY - 174
        stalk = f"M{bx},{by} C{CX + s * 40},{CY - 128} {CX + s * 54},{CY - 154} {tx},{ty}"
        antennae += (f'<path d="{stalk}" stroke="currentColor" stroke-width="12" '
                     f'fill="none" stroke-linecap="round"/>'
                     f'<circle cx="{tx}" cy="{ty - 6}" r="16"/>')
    return (f'<g fill="currentColor"><ellipse cx="{CX}" cy="{CY}" rx="{HEAD_RX}" ry="{HEAD_RY}"/>'
            f'<path d="{_micro_crown()}"/><path d="{_plain_blade()}"/>{antennae}</g>')


def figure(register: str, wave: dict[str, float] | None = None, groups: bool = False,
           cut: str = "bee", mono: bool = False, ground: str = "var") -> str:
    """The bee at `cut`, in the spelling `ground` asks for.

    A plastic volume anatomy: a sphere head with a rim light and a bottom bounce, a fur
    collar between head and belly, a lantern belly whose honey-gold light runs from
    white-gold to ember through live comb cells and three chitin bands, four wing groups
    hung at their own shoulders, and the expressive amber eyes with a pupil group the
    live guide can move. `groups` adds the `data-part` hooks; `wave` moves the parts
    without touching a coordinate.
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

    def wing_group(body: str, name: str, ox: float, oy: float) -> str:
        if not groups:
            return body
        return (f'<g data-part="{name}" style="transform-box:view-box;'
                f'transform-origin:{ox:.1f}px {oy:.1f}px">{body}</g>')

    brand, glow = paint("brand"), paint("brand_glow")
    soot, plate = paint("figure_soot"), paint("figure_plate")
    fur, mou = paint("figure_fur"), paint("figure_mou")
    ember, cream, shine = paint("figure_ember"), paint("figure_cream"), paint("figure_shine")

    parts: list[str] = []
    plume: list[str] = []
    wings: list[str] = []
    head_parts: list[str] = []

    halo = (f'<circle cx="{CX}" cy="{BELLY_CY - 16}" r="188" fill="url(#{u}-halo)" '
            f'opacity="{0.34 if fierce else 0.22:.2f}"/>')
    parts.append(dim(halo, w.get("glow", 1.0)))

    ears = (leaf_wing(-1, CX - 46, CY - 74, CX - 104, CY - 196, 30, 0.52, 18)
            + leaf_wing(1, CX + 46, CY - 74, CX + 104, CY - 196, 30, 0.52, 18))
    flame = leaf_wing(-1, CX, CY - 80, CX - 4, CY - 222, 34, 0.45, 20)
    plume.append(f'<path d="{ears + flame}" fill="url(#{u}-plume)"/>')
    plume.append(f'<path d="{leaf_wing(-1, CX, CY - 84, CX - 2, CY - 172, 20, 0.5, 12)}" '
                 f'fill="{cream}" opacity="0.85"/>')
    if fierce:
        crest = [leaf_wing(-1, CX - 70, CY - 96, CX - 112, CY - 158, 18, 0.6, tip_r=10),
                 leaf_wing(1, CX + 70, CY - 96, CX + 112, CY - 158, 18, 0.6, tip_r=10)]
        plume.append(f'<path d="{" ".join(crest)}" fill="{glow}"/>')
    if "sway" in w:
        transform = about((CX, CY - 40), f"rotate({w['sway']:.2f})")
        parts.append(hook(f'<g transform="{transform}">{"".join(plume)}</g>', "plume"))
    else:
        parts.append(hook("".join(plume), "plume"))

    antennae = ""
    for s in (-1, 1):
        bx, by = CX + s * 28, CY - 82
        tx, ty = CX + s * 80, CY - 190
        dpath = f"M{bx},{by} C{CX + s * 38},{CY - 128} {CX + s * 54},{CY - 160} {tx},{ty}"
        antennae += (f'<path d="{dpath}" stroke="{mou}" stroke-width="9" fill="none" '
                     f'stroke-linecap="round" opacity="0.75"/>'
                     f'<circle cx="{tx}" cy="{ty - 4}" r="12" fill="url(#{u}-pearl)" '
                     f'stroke="{ember}" stroke-width="2.5"/>')
    parts.append(hook(antennae, "antennae"))

    if fierce:
        for s in (-1, 1):
            fan = []
            for dx, dy, tx, ty, rh in ((96, 262, 190, 140, 24), (98, 276, 206, 208, 26),
                                       (94, 292, 188, 292, 22)):
                fan.append(leaf_wing(s, CX + s * dx, dy, CX + s * tx, ty, rh, 0.55))
            side = "l" if s < 0 else "r"
            upper = fan[:2]
            lower = fan[2:]
            wings.append(wing_group(
                f'<path d="{" ".join(upper)}" fill="{glow}" opacity="0.85"/>',
                f"wing-f{side}", CX + s * 96, 276))
            wings.append(wing_group(
                f'<path d="{" ".join(lower)}" fill="{glow}" opacity="0.85"/>',
                f"wing-b{side}", CX + s * 96, 300))
    else:
        wing_defs = (
            ("wing-fl", -1, CX - 88, 262, CX - 236, 150, 48.0),
            ("wing-fr", 1, CX + 88, 262, CX + 236, 150, 48.0),
            ("wing-bl", -1, CX - 82, 304, CX - 202, 396, 36.0),
            ("wing-br", 1, CX + 82, 304, CX + 202, 396, 36.0),
        )
        for name, s, rx, ry, tx, ty, rh in wing_defs:
            d = leaf_wing(s, rx, ry, tx, ty, rh, 0.62, 26.0)
            body = (f'<path d="{d}" fill="url(#{u}-wing-{"r" if s > 0 else "l"})" '
                    f'stroke="{glow}" stroke-width="2.5" stroke-linejoin="round" opacity="0.9"/>')
            # specular sheet and branched veins
            spec = leaf_wing(s, rx + (tx - rx) * 0.18, ry + (ty - ry) * 0.18,
                             rx + (tx - rx) * 0.62, ry + (ty - ry) * 0.62, rh * 0.45, 0.5, 12)
            body += f'<path d="{spec}" fill="{shine}" opacity="0.16"/>'
            for f0, f1, wf in ((0.18, 0.92, 0.46), (0.44, 0.98, 0.22)):
                vein = leaf_wing(s, rx + (tx - rx) * f0, ry + (ty - ry) * f0,
                                 rx + (tx - rx) * f1, ry + (ty - ry) * f1, rh * wf, 0.5, 8)
                body += (f'<path d="{vein}" fill="none" stroke="{glow}" '
                         f'stroke-width="2" opacity="0.85"/>')
            wings.append(wing_group(body, name, rx, ry))
    parts.append(hook(dim("".join(wings), w.get("wing", 1.0)), "wings"))

    def spike(a_deg: float, length: float, base: float, cy: float, rx: float, ry: float) -> str:
        a = math.radians(a_deg)
        da = base / (2 * max(rx, ry))
        x1 = CX + math.cos(a - da) * rx
        y1 = cy + math.sin(a - da) * ry
        x2 = CX + math.cos(a + da) * rx
        y2 = cy + math.sin(a + da) * ry
        xt = CX + math.cos(a) * (rx + length)
        yt = cy + math.sin(a) * (ry + length)
        return f"M{x1:.1f},{y1:.1f} L{xt:.1f},{yt:.1f} L{x2:.1f},{y2:.1f} Z"

    outer_spikes = []
    inner_spikes = []
    for i in range(46):
        a = 12 + i * (156 / 45)
        outer_spikes.append(spike(a, 12 + (i % 4) * 3, 7.5, 300, 88, 34))
    for i in range(30):
        a = 22 + i * (136 / 29)
        inner_spikes.append(spike(a, 9 + (i % 3) * 2, 6.5, 300, 74, 28))
    collar = [f'<ellipse cx="{CX}" cy="300" rx="94" ry="36" fill="{soot}" opacity="0.9"/>',
              f'<path d="{" ".join(outer_spikes)}" fill="{fur}"/>',
              f'<path d="{" ".join(inner_spikes)}" fill="{mou}" opacity="0.9"/>']
    tips = "".join(
        f'<circle cx="{CX + math.cos(math.radians(a)) * (88 + 10):.1f}" '
        f'cy="{300 + math.sin(math.radians(a)) * (34 + 10):.1f}" r="{3.4 + (i % 3)}" '
        f'fill="{glow}" opacity="0.9"/>'
        for i, a in enumerate((24, 40, 56, 72, 90, 108, 124, 140, 156))
    )
    collar.append(dim(tips, w.get("glow", 1.0)))
    collar.append(f'<ellipse cx="{CX}" cy="330" rx="88" ry="16" fill="{brand}" '
                  f'opacity="0.25" filter="url(#{u}-soft)"/>')
    parts.append(hook(dim("".join(collar), w.get("glow", 1.0)), "collar"))

    belly_clip = f'<clipPath id="{u}-bellyclip"><ellipse cx="{CX}" cy="{BELLY_CY}" rx="{BELLY_RX}" ry="{BELLY_RY}"/></clipPath>'
    plates = [hex_cell(CX + dx * 0.85, BELLY_CY + (dy - 42), r * 0.92, rot)
              for dx, dy, r, rot in PLATES]
    bands = (
        f"M{CX - 104},{BELLY_CY - 52} Q{CX},{BELLY_CY - 74} {CX + 104},{BELLY_CY - 52} "
        f"L{CX + 104},{BELLY_CY - 34} Q{CX},{BELLY_CY - 56} {CX - 104},{BELLY_CY - 34} Z "
        f"M{CX - 106},{BELLY_CY + 14} Q{CX},{BELLY_CY - 8} {CX + 106},{BELLY_CY + 14} "
        f"L{CX + 106},{BELLY_CY + 32} Q{CX},{BELLY_CY + 10} {CX - 106},{BELLY_CY + 32} Z "
        f"M{CX - 98},{BELLY_CY + 78} Q{CX},{BELLY_CY + 58} {CX + 98},{BELLY_CY + 78} "
        f"L{CX + 98},{BELLY_CY + 96} Q{CX},{BELLY_CY + 76} {CX - 98},{BELLY_CY + 96} Z"
    )
    belly = (
        f'<ellipse cx="{CX}" cy="{BELLY_CY}" rx="{BELLY_RX}" ry="{BELLY_RY}" '
        f'fill="url(#{u}-belly)"/>'
        f'<g clip-path="url(#{u}-bellyclip)">'
        f'<path d="{" ".join(plates)}" fill="url(#{u}-cell)" stroke="{glow}" '
        f'stroke-width="2" stroke-opacity="0.55" stroke-linejoin="round"/>'
        f'<path d="{bands}" fill="{soot}" opacity="0.85"/>'
        f'<path d="{bands}" fill="none" stroke="{glow}" stroke-width="1.2" opacity="0.28"/>'
        f'</g>'
        f'<ellipse cx="{CX}" cy="{BELLY_CY}" rx="{BELLY_RX}" ry="{BELLY_RY}" '
        f'fill="none" stroke="{brand}" stroke-width="2.5" opacity="0.65"/>'
        f'<ellipse cx="{CX}" cy="{BELLY_CY - 58}" rx="62" ry="18" fill="{cream}" '
        f'opacity="0.22" filter="url(#{u}-soft)"/>'
    )
    parts.append(hook(dim(belly, w.get("glow", 1.0)), "belly"))

    for s in (-1, 1):
        dpath = (f"M{CX + s * 40},{BELLY_CY + 62} C{CX + s * 44},{BELLY_CY + 88} "
                 f"{CX + s * 52},{BELLY_CY + 102} {CX + s * 54},{BELLY_CY + 110}")
        parts.append(f'<path d="{dpath}" stroke="{fur}" stroke-width="13" fill="none" '
                     f'stroke-linecap="round"/>')

    head_parts.append(
        f'<ellipse cx="{CX}" cy="{CY}" rx="{HEAD_RX}" ry="{HEAD_RY}" fill="url(#{u}-head)"/>'
    )
    head_parts.append(
        f'<path d="M{CX - 88},{CY - 26} A94 86 0 0 1 {CX - 24},{CY - 84}" '
        f'fill="none" stroke="{glow}" stroke-width="3" opacity="0.5" stroke-linecap="round"/>'
    )
    head_parts.append(
        f'<ellipse cx="{CX}" cy="{CY + 62}" rx="62" ry="18" fill="{ember}" '
        f'opacity="0.28" filter="url(#{u}-soft)"/>'
    )
    # a few fur strokes on the head top
    for i in range(7):
        x = CX - 54 + i * 18
        y = CY - 74 + (i % 2) * 4
        head_parts.append(f'<path d="M{x},{y} q4,-10 10,-14" stroke="{mou}" '
                          f'stroke-width="2" fill="none" opacity="0.45"/>')
    parts.append(hook("".join(head_parts), "head"))

    eyes = []
    pupils = []
    for s in (-1, 1):
        cx = CX + s * 46
        eyes.append(f'<g transform="rotate({s * 8} {cx} {CY + 2})">'
                    f'<ellipse cx="{cx}" cy="{CY + 2}" rx="30" ry="35" fill="url(#{u}-eye)" '
                    f'stroke="{ember}" stroke-width="2.5"/>'
                    f'<path d="M{cx - 28},{CY - 20} Q{cx},{CY - 44} {cx + 28},{CY - 20}" '
                    f'fill="none" stroke="{soot}" stroke-width="10" opacity="0.5" '
                    f'stroke-linecap="round"/></g>')
        pupils.append(f'<circle cx="{cx}" cy="{CY + 5}" r="19" fill="{soot}"/>')
        pupils.append(f'<circle cx="{cx - 6}" cy="{CY - 2}" r="6.5" fill="{shine}"/>')
        pupils.append(f'<circle cx="{cx + 7}" cy="{CY + 15}" r="3" fill="{shine}" opacity="0.85"/>')
    face = [hook("".join(eyes), "eyes"), hook("".join(pupils), "pupils")]
    face.append(f'<path d="M{CX - 18},{CY + 58} Q{CX},{CY + 72} {CX + 18},{CY + 58}" '
                f'fill="none" stroke="{mou}" stroke-width="6" stroke-linecap="round"/>')
    for s in (-1, 1):
        face.append(f'<ellipse cx="{CX + s * 48}" cy="{CY + 54}" rx="14" ry="7" '
                    f'fill="{brand}" opacity="0.22"/>')
    parts.append(hook("".join(face), "face"))

    if fierce:
        sparks = ((-214, -120, 7), (-176, -176, 5), (198, -150, 6), (218, -44, 7),
                  (-224, 76, 6), (180, 140, 5), (-150, 206, 5))
        for dx, dy, r in sparks:
            parts.append(f'<circle cx="{CX + dx}" cy="{CY + dy}" r="{r}" fill="{glow}"/>')

    defs = [
        f'<radialGradient id="{u}-eye" cx="50%" cy="24%" r="78%">'
        f'<stop offset="0%" stop-color="{cream}"/>'
        f'<stop offset="14%" stop-color="{paint("figure_honey_mid")}"/>'
        f'<stop offset="58%" stop-color="{paint("figure_iris")}"/>'
        f'<stop offset="100%" stop-color="{brand}"/></radialGradient>',
        f'<radialGradient id="{u}-head" cx="34%" cy="24%" r="82%">'
        f'<stop offset="0%" stop-color="{paint("figure_head_hi")}"/>'
        f'<stop offset="48%" stop-color="{paint("figure_head_core")}"/>'
        f'<stop offset="100%" stop-color="{paint("figure_head_shadow")}"/></radialGradient>',
        f'<radialGradient id="{u}-belly" cx="50%" cy="42%" r="66%">'
        f'<stop offset="0%" stop-color="{paint("figure_shine")}"/>'
        f'<stop offset="42%" stop-color="{paint("figure_honey_mid")}"/>'
        f'<stop offset="78%" stop-color="{paint("figure_honey_deep")}"/>'
        f'<stop offset="100%" stop-color="{brand}"/></radialGradient>',
        f'<radialGradient id="{u}-cell" cx="50%" cy="34%" r="70%">'
        f'<stop offset="0%" stop-color="{paint("figure_shine")}"/>'
        f'<stop offset="55%" stop-color="{paint("figure_honey_mid")}"/>'
        f'<stop offset="100%" stop-color="{paint("figure_honey_deep")}"/></radialGradient>',
        f'<linearGradient id="{u}-plume" x1="0" y1="1" x2="0" y2="0">'
        f'<stop offset="0%" stop-color="{brand}"/>'
        f'<stop offset="48%" stop-color="{ember}"/>'
        f'<stop offset="100%" stop-color="{glow}"/></linearGradient>',
        f'<radialGradient id="{u}-pearl" cx="35%" cy="30%" r="70%">'
        f'<stop offset="0%" stop-color="{cream}"/>'
        f'<stop offset="60%" stop-color="{glow}"/>'
        f'<stop offset="100%" stop-color="{brand}"/></radialGradient>',
        f'<radialGradient id="{u}-halo" cx="50%" cy="56%" r="50%">'
        f'<stop offset="0%" stop-color="{glow}"/>'
        f'<stop offset="100%" stop-color="{glow}" stop-opacity="0"/></radialGradient>',
        belly_clip,
        f'<filter id="{u}-soft" x="-60%" y="-140%" width="220%" height="380%">'
        f'<feGaussianBlur stdDeviation="6"/></filter>',
    ]
    if not fierce:
        gold = (f'<stop offset="0%" stop-color="{cream}" stop-opacity="0.92"/>'
                f'<stop offset="35%" stop-color="{glow}" stop-opacity="0.66"/>'
                f'<stop offset="72%" stop-color="{paint("figure_honey_deep")}" stop-opacity="0.5"/>'
                f'<stop offset="100%" stop-color="{ember}" stop-opacity="0.42"/>')
        defs.append(f'<radialGradient id="{u}-wing-r" cx="0%" cy="50%" r="92%">{gold}</radialGradient>')
        defs.append(f'<radialGradient id="{u}-wing-l" cx="100%" cy="50%" r="92%">{gold}</radialGradient>')

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
             "figure_wing_tip", "figure_head_hi", "figure_head_core", "figure_head_shadow",
             "figure_honey_mid", "figure_honey_deep", "figure_iris")
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


def bee_body(register: str, size: int = 512, *, mono: bool = False,
             ground: str = "ink") -> str:
    """The figure's body for a target size, unwrapped, for the icon kit."""
    svg = figure(register, cut=bee_for(size), mono=mono, ground=ground)
    return svg[svg.index(">", svg.index("<svg")) + 1: -len("</svg>")]


def targets() -> dict[Path, str]:
    # App assets carry data-part hooks for the CSS poses.
    out = {OUT / f"fire-spirit-bee{'-fierce' if r == 'fierce' else ''}.svg":
           figure(r, groups=True)
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
