"""The paper moth — the product mark, drawn from folded planes.

The figure is a moth folded from one sheet: two forewings swept up and out, two
hindwings trailing below, a slim slip of a body, and a crimson thread tied at each
wing root. It is drawn here in a 512 canvas from a mirrored 96-unit grid, so the
left and right halves are the same numbers and the silhouette stays balanced at
every size.

Three cuts follow the size bands the kit routes with (`MARK_CUTS` in
`generate_brand_assets.py`): the whole figure with creases and threads, the same
figure without creases, and the plain silhouette for the smallest tiles. The
colours are roles, never literals: `moth_body(vector=True)` writes the property
names `globals.css` resolves, the raster spelling comes from `brand_palette`.
"""
from __future__ import annotations

from brand_palette import hex_for, token_for

SVG = 512.0
UNIT = SVG / 96.0

#: The drawing sits in the 96 grid with a margin; this lifts it to the canvas middle.
LIFT = 34.0


def _p(x: float, y: float) -> tuple[float, float]:
    return (x * UNIT, y * UNIT + LIFT)


def _poly(points: list[tuple[float, float]], fill: str) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (_p(px, py) for px, py in points))
    return f'<polygon points="{pts}" fill="{fill}"/>'


def _path(d: str, stroke: str, width: float) -> str:
    return (
        f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width:.1f}" '
        'stroke-linecap="round"/>'
    )


def _left_forewing(fill: str, lit: str) -> str:
    return (
        _poly([(45, 47), (15, 7), (2, 29), (26, 49)], fill)
        + _poly([(45, 47), (26, 49), (37, 41)], lit)
    )


def _left_hindwing(fill: str) -> str:
    return _poly([(44, 53), (27, 54), (10, 80), (34, 70)], fill)


def _mirror(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(96 - x, y) for x, y in points]


def _crease_left(color: str) -> str:
    a = _p(45, 48)
    b = _p(8, 22)
    return _path(f"M{a[0]:.1f} {a[1]:.1f} L{b[0]:.1f} {b[1]:.1f}", color, 3.4)


def _body(fill: str) -> str:
    a, b = _p(44.4, 40.0), _p(51.6, 40.0)
    c, d = _p(50.2, 53.0), _p(48.0, 70.0)
    e = _p(45.4, 53.0)
    return (
        f'<path d="M{a[0]:.1f} {a[1]:.1f} L{b[0]:.1f} {b[1]:.1f} '
        f'L{c[0]:.1f} {c[1]:.1f} L{d[0]:.1f} {d[1]:.1f} '
        f'L{e[0]:.1f} {e[1]:.1f} Z" fill="{fill}"/>'
    )


def _head(fill: str) -> str:
    x, y = _p(48.0, 39.0)
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.6" fill="{fill}"/>'


def _threads(color: str) -> str:
    left = _p(42.0, 52)
    right = _p(54.0, 52)
    w = 7.2
    return (
        f'<g data-ephe-part="accent">'
        f'<path d="M{left[0]:.1f} {left[1]:.1f} q-26.7 16 -45.3 2.7" fill="none" '
        f'stroke="{color}" stroke-width="{w:.1f}" stroke-linecap="round"/>'
        f'<path d="M{right[0]:.1f} {right[1]:.1f} q26.7 16 45.3 2.7" fill="none" '
        f'stroke="{color}" stroke-width="{w:.1f}" stroke-linecap="round"/>'
        "</g>"
    )


def _roles(vector: bool) -> dict[str, str]:
    def role(name: str) -> str:
        return f"var({token_for(name)})" if vector else hex_for(name)

    return {
        "paper": role("figure_paper"),
        "lit": role("figure_paper_lit"),
        "shade": role("figure_paper_shade"),
        "body": role("figure_paper_body"),
        "thread": role("brand"),
    }


def _defs(colors: dict[str, str]) -> str:
    return (
        "<defs>"
        '<linearGradient id="bspc-paper" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{colors["paper"]}"/>'
        f'<stop offset="100%" stop-color="{colors["lit"]}"/>'
        "</linearGradient>"
        '<linearGradient id="bspc-shade" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{colors["shade"]}"/>'
        f'<stop offset="100%" stop-color="{colors["paper"]}"/>'
        "</linearGradient>"
        "</defs>"
    )


def moth_body(*, compact: bool = False, micro: bool = False, mono: bool = False,
              vector: bool = False) -> str:
    """The figure for one cut. Order matters: the cascade staggers `svg > *`."""
    if mono:
        ink = "currentColor"
        parts = (
            _left_forewing(ink, ink)
            + _left_hindwing(ink)
            + _poly(_mirror([(45, 47), (15, 7), (2, 29), (26, 49)]), ink)
            + _poly(_mirror([(44, 53), (27, 54), (10, 80), (34, 70)]), ink)
            + _body(ink)
            + _head(ink)
        )
        return parts

    colors = _roles(vector)
    fore = "url(#bspc-paper)"
    hind = "url(#bspc-shade)"
    crease = colors["shade"]
    parts = [
        _left_forewing(fore, colors["lit"]),
        _left_hindwing(hind),
        _poly(_mirror([(45, 47), (15, 7), (2, 29), (26, 49)]), fore)
        + _poly(_mirror([(45, 47), (26, 49), (37, 41)]), colors["lit"]),
        _poly(_mirror([(44, 53), (27, 54), (10, 80), (34, 70)]), hind),
        _body(colors["body"]) + _head(colors["shade"]),
    ]
    if not micro:
        parts[0] += _crease_left(crease)
    if not micro and not compact:
        parts[2] += _crease_left(crease)
    if not micro:
        parts.append(_threads(colors["thread"]))
    return _defs(colors) + "".join(parts)


#: The tray crops to the drawing plus a margin, so a 22 pt icon carries the moth
#: and not the canvas around it.
TRAY_VIEW = f"{2 * UNIT:.0f} {7 * UNIT + LIFT - 18:.0f} {92 * UNIT:.0f} {76 * UNIT:.0f}"
