#!/usr/bin/env python3
"""The bee as a character grid, sampled from the shipped vector.

`app/src/assets/mark-mono.svg` is the template cut of the mark: one plane, no
colour, which is the same constraint a terminal cell has. This reads that file's
shapes, covers them on a supersampled lattice, and folds the lattice into a grid
of shade characters, so the terminal mark is the product's silhouette measured
rather than a picture of a bee drawn by hand.

Aspect: a terminal cell is about twice as tall as it is wide, so the grid is
twice as wide as it is tall in cells.

Usage
    ./.venv/bin/python scripts/generate_terminal_mark.py            # print
    ./.venv/bin/python scripts/generate_terminal_mark.py --write    # update ui/terminal_mark.py
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "src" / "assets" / "mark-mono.svg"
TARGET = ROOT / "ui" / "terminal_mark.py"

#: Supersamples per axis before the grid is folded, and the shade ramp from full
#: ink to paper. Five steps survive a 16-colour terminal without banding into noise.
SUPER = 4
RAMP = ("█", "▓", "", "░", " ")

ELEMENT = re.compile(r"<(circle|ellipse|path)\b([^>]*)/>")
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
PATH_DATA = re.compile(r"[MLQCZ]|-?\d*\.?\d+")


def _attrs(text: str) -> dict[str, str]:
    return dict(ATTR.findall(text))


def _polygons(data: str, steps: int = 24) -> list[list[tuple[float, float]]]:
    """A path body as one polygon per subpath, over the commands the mark writes."""
    tokens = PATH_DATA.findall(data)
    polygons: list[list[tuple[float, float]]] = []
    points: list[tuple[float, float]] = []
    index = 0
    here = (0.0, 0.0)
    start = here
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token == "M":
            if len(points) > 2:
                polygons.append(list(points))
            points.clear()
            here = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            start = here
            points.append(here)
        elif token == "L":
            here = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            points.append(here)
        elif token == "Q":
            x1, y1, x, y = (float(v) for v in tokens[index:index + 4])
            index += 4
            for step in range(1, steps + 1):
                t = step / steps
                u = 1 - t
                points.append((
                    u * u * here[0] + 2 * u * t * x1 + t * t * x,
                    u * u * here[1] + 2 * u * t * y1 + t * t * y,
                ))
            here = (x, y)
        elif token == "C":
            x1, y1, x2, y2, x, y = (float(v) for v in tokens[index:index + 6])
            index += 6
            for step in range(1, steps + 1):
                t = step / steps
                u = 1 - t
                points.append((
                    u ** 3 * here[0] + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x,
                    u ** 3 * here[1] + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y,
                ))
            here = (x, y)
        elif token == "Z":
            points.append(start)
            if len(points) > 2:
                polygons.append(list(points))
            points.clear()
    if len(points) > 2:
        polygons.append(points)
    return polygons


def _spans_at(polygons: list[list[tuple[float, float]]], y: float) -> list[tuple[float, float]]:
    """Even-odd crossings of one subpath set at row `y`."""
    crossings: list[float] = []
    for polygon in polygons:
        for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
            if (y0 > y) != (y1 > y):
                crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    crossings.sort()
    return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def _stroke_spans(segments: list[tuple[float, float]], y: float, half: float):
    """A stroked polyline covers a band: every segment whose y range meets the row."""
    spans = []
    for (x0, y0), (x1, y1) in zip(segments, segments[1:]):
        low, high = min(y0, y1) - half, max(y0, y1) + half
        if not low <= y <= high:
            continue
        if y0 == y1:
            centre = (x0 + x1) / 2 if y == y0 else None
            if centre is None:
                continue
            spans.append((min(x0, x1) - half, max(x0, x1) + half))
        else:
            t = (y - y0) / (y1 - y0)
            x = x0 + t * (x1 - x0)
            slope = abs((x1 - x0) / (y1 - y0))
            reach = half * math.sqrt(1 + slope * slope)
            spans.append((x - reach, x + reach))
    return spans


def coverages(svg: str) -> list[dict]:
    """Every painted shape of the cut, as the row test the rasteriser needs."""
    shapes = []
    for kind, raw in ELEMENT.findall(svg):
        attrs = _attrs(raw)
        if kind == "circle":
            shapes.append({"circle": (
                float(attrs["cx"]), float(attrs["cy"]), float(attrs["r"]))})
        elif kind == "ellipse":
            shapes.append({"ellipse": (
                float(attrs["cx"]), float(attrs["cy"]),
                float(attrs["rx"]), float(attrs["ry"]))})
        else:
            polygons = _polygons(attrs.get("d", ""))
            if not polygons:
                continue
            if attrs.get("fill") == "none" and "stroke-width" in attrs:
                half = float(attrs["stroke-width"]) / 2.0
                shapes.append({"stroke": polygons, "half": half})
            else:
                shapes.append({"fill": polygons})
    return shapes


def row_covers(shapes: list[dict], y: float) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    for shape in shapes:
        if "circle" in shape:
            cx, cy, r = shape["circle"]
            if abs(y - cy) <= r:
                half = math.sqrt(r * r - (y - cy) ** 2)
                spans.append((cx - half, cx + half))
        elif "ellipse" in shape:
            cx, cy, rx, ry = shape["ellipse"]
            if abs(y - cy) <= ry:
                half = rx * math.sqrt(max(0.0, 1 - ((y - cy) / ry) ** 2))
                spans.append((cx - half, cx + half))
        elif "fill" in shape:
            spans.extend(_spans_at(shape["fill"], y))
        else:
            for polygon in shape["stroke"]:
                spans.extend(_stroke_spans(polygon, y, shape["half"]))
    return spans


def merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for low, high in sorted(spans):
        if out and low <= out[-1][1]:
            out[-1][1] = max(out[-1][1], high)
        else:
            out.append([low, high])
    return [(low, high) for low, high in out]


def render(shapes: list[dict], cols: int, rows: int, span: float = 512.0) -> list[str]:
    """The cut folded into a `cols` x `rows` shade grid."""
    cell_w = span / cols
    cell_h = span / rows
    lines = []
    for row in range(rows):
        line = []
        for col in range(cols):
            left = col * cell_w
            right = (col + 1) * cell_w
            covered = 0.0
            for sy in range(SUPER):
                y = (row + (sy + 0.5) / SUPER) * cell_h
                for low, high in merge(row_covers(shapes, y)):
                    covered += max(0.0, min(right, high) - max(left, low))
            ratio = covered / (cell_w * SUPER)
            line.append(RAMP[min(len(RAMP) - 1, int((1.0 - ratio) * len(RAMP)))])
        lines.append("".join(line))
    return _crop(lines)


def _crop(lines: list[str]) -> list[str]:
    """Empty rows and columns trimmed, so the mark carries ink and not canvas."""
    if not lines:
        return []
    width = max(len(line) for line in lines)
    grid = [line.ljust(width) for line in lines]
    inked = [(row, col) for row, line in enumerate(grid) for col, ch in enumerate(line)
             if ch != " "]
    if not inked:
        return []
    top, bottom = min(r for r, _ in inked), max(r for r, _ in inked)
    left, right = min(c for _, c in inked), max(c for _, c in inked)
    return [grid[row][left:right + 1].rstrip() for row in range(top, bottom + 1)]


BANNER = (
    '"""The bee from `app/src/assets/mark-mono.svg`, folded into a character grid.\n'
    "\n"
    'Generated by `scripts/generate_terminal_mark.py --write`; edit the vector or the\n'
    "generator, never this file.\n"
    '"""\n'
    "\n"
    "#: The grid the generator was run at, so the provenance test re-renders the\n"
    "#: same cut instead of guessing a size.\n"
    "MARK_GRID: tuple[int, int] = ({cols}, {rows})\n"
    "\n"
    "#: Rows top to bottom, one string per terminal line, in the ramp of the generator.\n"
    "MARK_ROWS: tuple[str, ...] = (\n"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cols", type=int, default=34)
    parser.add_argument("--rows", type=int, default=18)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    lines = render(coverages(SOURCE.read_text(encoding="utf-8")), args.cols, args.rows)
    if args.write:
        body = BANNER.format(cols=args.cols, rows=args.rows) + \
            "".join(f"    {line!r},\n" for line in lines) + ")\n"
        TARGET.write_text(body, encoding="utf-8")
        print(f"wrote {TARGET.relative_to(ROOT)} ({args.cols}x{args.rows})")
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
