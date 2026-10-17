"""Measuring a mark silhouette: a path and its circles as a covered area.

`scripts/mark_contract.py` asks this module where the mass centre of a cut sits,
so a size band that leans in the title bar fails before it ships. Nothing here
reads a file: the input is the SVG body the generator builds, the output is one
point in emblem units.

The scanline is the whole method. A silhouette is the union of its outer subpaths
plus its circles; each row of a 256 cell lattice is filled from the x ranges the
row crosses, and the covered cells give the mass centre. A lattice rather than an
exact integral, because the shapes are curves whose area has no closed form worth
writing, and one cell is 2 emblem units — inside the tolerance the caller states.
"""
from __future__ import annotations

import math
import re

#: The lattice the covered area is sampled on, and the canvas those cells span.
GEOMETRY_CELLS = 256
SVG_SPAN = 512.0
CIRCLE = re.compile(r'<circle cx="([\d.-]+)" cy="([\d.-]+)" r="([\d.-]+)"')
PATH_DATA = re.compile(r'<path d="([^"]+)"')
PATH_TOKEN = re.compile(r"[MmLlHhVvCcAaZz]|-?\d*\.?\d+(?:[eE]-?\d+)?")


def arc_points(start: tuple[float, float], rx: float, ry: float, rotation: float,
               large: int, sweep: int, end: tuple[float, float],
               steps: int = 24) -> list[tuple[float, float]]:
    """Points along an elliptical arc (SVG 1.1 F.6.5 endpoint parameterisation)."""
    phi = math.radians(rotation % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (start[0] - end[0]) / 2.0, (start[1] - end[1]) / 2.0
    x1 = cos_phi * dx + sin_phi * dy
    y1 = -sin_phi * dx + cos_phi * dy
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [end]
    scale = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
    factor = 0.0
    if denominator:
        numerator = max(0.0, rx * rx * ry * ry - denominator)
        factor = math.sqrt(numerator / denominator)
    if large == sweep:
        factor = -factor
    centre_x1, centre_y1 = factor * rx * y1 / ry, -factor * ry * x1 / rx
    centre_x = cos_phi * centre_x1 - sin_phi * centre_y1 + (start[0] + end[0]) / 2.0
    centre_y = sin_phi * centre_x1 + cos_phi * centre_y1 + (start[1] + end[1]) / 2.0

    def angle(x: float, y: float) -> float:
        return math.atan2(y / ry, x / rx)

    theta = angle(x1 - centre_x1, y1 - centre_y1)
    delta = angle(-x1 - centre_x1, -y1 - centre_y1) - theta
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    out = []
    for step in range(1, steps + 1):
        at = theta + delta * step / steps
        out.append((centre_x + rx * math.cos(at) * cos_phi - ry * math.sin(at) * sin_phi,
                    centre_y + rx * math.cos(at) * sin_phi + ry * math.sin(at) * cos_phi))
    return out


def flatten_path(path_data: str, steps: int = 16) -> list[list[tuple[float, float]]]:
    """A path as one polygon per subpath: every command the mark writes.

    The silhouette is an outer contour; the letter rides along as further
    subpaths. Keeping them apart is what lets the outer one be told from the
    letter, and the template cut punches the letter out of that same contour.
    """
    tokens = PATH_TOKEN.findall(path_data)
    polygons: list[list[tuple[float, float]]] = []
    points: list[tuple[float, float]] = []
    index = 0
    here = (0.0, 0.0)
    start = here

    def numbers(count: int) -> list[float]:
        nonlocal index
        values = [float(token) for token in tokens[index:index + count]]
        index += count
        return values

    def close() -> None:
        if len(points) > 2:
            polygons.append(list(points))
        points.clear()

    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token in "Mm":
            close()
            x, y = numbers(2)
            here = (x, y) if token == "M" else (here[0] + x, here[1] + y)
            start = here
            points.append(here)
        elif token in "LlHhVv":
            if token in "Hh":
                x = numbers(1)[0]
                here = (x if token == "H" else here[0] + x, here[1])
            elif token in "Vv":
                y = numbers(1)[0]
                here = (here[0], y if token == "V" else here[1] + y)
            else:
                x, y = numbers(2)
                here = (x, y) if token == "L" else (here[0] + x, here[1] + y)
            points.append(here)
        elif token in "Cc":
            x1, y1, x2, y2, x, y = numbers(6)
            if token == "c":
                x1, y1 = here[0] + x1, here[1] + y1
                x2, y2 = here[0] + x2, here[1] + y2
                x, y = here[0] + x, here[1] + y
            for step in range(1, steps + 1):
                t = step / steps
                u = 1 - t
                points.append((
                    u ** 3 * here[0] + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x,
                    u ** 3 * here[1] + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y,
                ))
            here = (x, y)
        elif token in "Aa":
            rx, ry, rotation, large, sweep, x, y = numbers(7)
            if token == "a":
                x, y = here[0] + x, here[1] + y
            points.extend(arc_points(here, rx, ry, rotation, int(large), int(sweep), (x, y)))
            here = (x, y)
        elif token in "Zz":
            points.append(start)
            close()
    close()
    return polygons


def polygon_area(polygon: list[tuple[float, float]]) -> float:
    """The absolute area of a polygon (shoelace)."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def inside_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Whether `point` falls inside `polygon` (even-odd ray cast)."""
    x, y = point
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def outer_polygons(polygons: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """The subpaths that outline a silhouette: none another subpath encloses.

    The letter's bars are drawn as subpaths of their own, and they sit inside the
    drop; the outline is the drop. The two dome circles of the micro cut stick
    out of one another, so both survive and the silhouette stays their union.
    """
    outlines = []
    for index, polygon in enumerate(polygons):
        enclosed = any(
            other != index and polygon_area(polygons[other]) > polygon_area(polygon)
            and all(inside_polygon(point, polygons[other]) for point in polygon)
            for other in range(len(polygons))
        )
        if not enclosed:
            outlines.append(polygon)
    return outlines


def row_spans(polygon: list[tuple[float, float]], y: float) -> list[tuple[float, float]]:
    """The x ranges a scanline at `y` crosses inside `polygon` (even-odd rule)."""
    crossings = []
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y):
            crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    crossings.sort()
    return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Overlapping x ranges joined, so a cell is counted once."""
    merged: list[list[float]] = []
    for low, high in sorted(spans):
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]


def silhouette_centre(body: str) -> tuple[float, float] | None:
    """The mass centre of a silhouette on a 256 cell lattice, in emblem units."""
    circles = [(float(x), float(y), float(r)) for x, y, r in CIRCLE.findall(body)]
    polygons = [outline
                for data in PATH_DATA.findall(body) if data.strip().endswith("Z")
                for outline in outer_polygons(flatten_path(data))]
    step = SVG_SPAN / GEOMETRY_CELLS
    cells = 0
    sum_x = 0.0
    sum_y = 0.0
    for row in range(GEOMETRY_CELLS):
        y = (row + 0.5) * step
        spans: list[tuple[float, float]] = []
        for polygon in polygons:
            spans.extend(row_spans(polygon, y))
        for cx, cy, radius in circles:
            if abs(y - cy) <= radius:
                half = math.sqrt(max(0.0, radius * radius - (y - cy) ** 2))
                spans.append((cx - half, cx + half))
        for low, high in merge_spans(spans):
            first = max(0, int(low / step))
            last = min(GEOMETRY_CELLS, int(high / step) + 1)
            for col in range(first, last):
                x = (col + 0.5) * step
                if low <= x <= high:
                    cells += 1
                    sum_x += x
                    sum_y += y
    if not cells:
        return None
    return sum_x / cells, sum_y / cells
