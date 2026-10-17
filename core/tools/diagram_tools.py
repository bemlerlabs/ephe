"""Ephe – diagram_tools: create_diagram (mindmap / timeline / flowchart).

Deterministic premium SVGs in the Black Forest design (dark, green
accents) — no renderer dependency, pure string generation. The
SVG_FILE: marker flows into the existing file_result/preview flow.

Layout rule: fixed slot widths + text truncation — never overlapping
labels (the same discipline as the chat-UI fixes from round 9/10).
"""
from __future__ import annotations

import asyncio
import html
import math
import re
from pathlib import Path

# Black-Forest palette (identical to the app/src/styles/globals.css tokens)
_BG_TOP = "#0b1512"
_BG_BOTTOM = "#060a09"
_ACCENT = "#4ade80"
_ACCENT_DIM = "#22c55e"
_NODE_FILL = "#12211b"
_NODE_STROKE = "#2e5c43"
_TEXT = "#e7f0ea"
_TEXT_DIM = "#8fa89b"

_FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _clip(text: str, maxlen: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def _parse_items(items: object) -> list[tuple[str, str]]:
    """items: list[str] | list[dict] | JSON/CSV-String → [(label, desc)]."""
    parsed: list = items  # type: ignore[assignment]
    if isinstance(items, str):
        import json

        text = items.strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = [line.strip() for line in text.splitlines() if line.strip()]
    result: list[tuple[str, str]] = []
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("title") or "")
                desc = str(entry.get("desc") or entry.get("description") or entry.get("date") or "")
            elif isinstance(entry, (list, tuple)) and entry:
                label = str(entry[0])
                desc = str(entry[1]) if len(entry) > 1 else ""
            else:
                raw = str(entry)
                if "|" in raw:
                    label, desc = raw.split("|", 1)
                else:
                    label, desc = raw, ""
            label = label.strip().lstrip("-*• ").strip()
            if label:
                result.append((label, desc.strip()))
    return result


def _svg_doc(width: int, height: int, body: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' "
        f"width='{width}' height='{height}' role='img'>"
        "<defs>"
        f"<linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'>"
        f"<stop offset='0%' stop-color='{_BG_TOP}'/><stop offset='100%' stop-color='{_BG_BOTTOM}'/>"
        "</linearGradient>"
        f"<radialGradient id='glow' cx='50%' cy='50%' r='50%'>"
        f"<stop offset='0%' stop-color='{_ACCENT}' stop-opacity='0.18'/>"
        f"<stop offset='100%' stop-color='{_ACCENT}' stop-opacity='0'/>"
        "</radialGradient>"
        "</defs>"
        f"<rect width='{width}' height='{height}' fill='url(#bg)' rx='16'/>"
        f"<rect width='{width}' height='{height}' fill='url(#glow)' rx='16'/>"
        f"{body}"
        "</svg>"
    )


def _header(title: str, width: int) -> str:
    if not title:
        return ""
    return (
        f"<text x='{width // 2}' y='40' text-anchor='middle' {_FONT} "
        f"font-size='20' font-weight='700' fill='{_TEXT}'>{_esc(_clip(title, 70))}</text>"
    )


def _mindmap_svg(title: str, items: list[tuple[str, str]]) -> str:
    n = len(items)
    width, height = 960, max(560, 220 + n * 34)
    cx, cy = width // 2, height // 2 + 12
    body = [_header(title, width)]
    rx, ry = cx - 110, cy - 70
    for i, (label, desc) in enumerate(items):
        angle = (2 * 3.14159265 * i / max(n, 1)) - (3.14159265 / 2)
        x = cx + int(rx * math.cos(angle))
        y = cy + int(ry * math.sin(angle))
        body.append(
            f"<line x1='{cx}' y1='{cy}' x2='{x}' y2='{y}' stroke='{_NODE_STROKE}' stroke-width='2' opacity='0.7'/>"
        )
    for i, (label, desc) in enumerate(items):
        angle = (2 * 3.14159265 * i / max(n, 1)) - (3.14159265 / 2)
        x = cx + int(rx * math.cos(angle))
        y = cy + int(ry * math.sin(angle))
        max(150, min(int(len(_clip(label, 30)) * 8.4) + 36, 260))
        anchor = "middle"
        tx = x
        if x < cx - 120:
            anchor, tx = "end", x - 14
        elif x > cx + 120:
            anchor, tx = "start", x + 14
        else:
            y += 0 if math.sin(angle) >= 0 else 0
        body.append(
            f"<circle cx='{x}' cy='{y}' r='7' fill='{_ACCENT}'/>"
            f"<text x='{tx}' y='{y - (14 if desc else 0)}' text-anchor='{anchor}' {_FONT} "
            f"font-size='15' font-weight='600' fill='{_TEXT}'>{_esc(_clip(label, 34))}</text>"
        )
        if desc:
            body.append(
                f"<text x='{tx}' y='{y + 6}' text-anchor='{anchor}' {_FONT} "
                f"font-size='12' fill='{_TEXT_DIM}'>{_esc(_clip(desc, 40))}</text>"
            )
    body.append(
        f"<circle cx='{cx}' cy='{cy}' r='58' fill='{_NODE_FILL}' stroke='{_ACCENT_DIM}' stroke-width='2'/>"
        f"<text x='{cx}' y='{cy + 5}' text-anchor='middle' {_FONT} font-size='14' "
        f"font-weight='700' fill='{_ACCENT}'>{_esc(_clip(title or 'Thema', 16))}</text>"
    )
    return _svg_doc(width, height, "".join(body))


def _timeline_svg(title: str, items: list[tuple[str, str]]) -> str:
    n = len(items)
    width = max(880, 200 + n * 170)
    height = 460
    mid = height // 2 + 20
    left, right = 90, width - 90
    body = [_header(title, width),
            f"<line x1='{left - 30}' y1='{mid}' x2='{right + 30}' y2='{mid}' "
            f"stroke='{_NODE_STROKE}' stroke-width='3'/>"]
    step = (right - left) / max(n - 1, 1) if n > 1 else 0
    for i, (label, desc) in enumerate(items):
        x = left if n == 1 else left + step * i
        above = i % 2 == 0
        ly = mid - 46 if above else mid + 66
        body.append(f"<circle cx='{x:.0f}' cy='{mid}' r='9' fill='{_ACCENT}'/>")
        body.append(
            f"<line x1='{x:.0f}' y1='{mid}' x2='{x:.0f}' y2='{mid - 18 if above else mid + 18}' "
            f"stroke='{_NODE_STROKE}' stroke-width='2'/>"
        )
        anchor = "middle"
        tx = x
        if i == 0:
            anchor, tx = "start", x - 8
        elif i == n - 1:
            anchor, tx = "end", x + 8
        if desc:
            body.append(
                f"<text x='{tx:.0f}' y='{ly - 20}' text-anchor='{anchor}' {_FONT} "
                f"font-size='13' font-weight='700' fill='{_ACCENT}'>{_esc(_clip(desc, 26))}</text>"
            )
        body.append(
            f"<text x='{tx:.0f}' y='{ly}' text-anchor='{anchor}' {_FONT} "
            f"font-size='15' font-weight='600' fill='{_TEXT}'>{_esc(_clip(label, 26))}</text>"
        )
    return _svg_doc(width, height, "".join(body))


def _flowchart_svg(title: str, items: list[tuple[str, str]]) -> str:
    n = len(items)
    width = 760
    box_h, gap, top = 92, 44, 84
    height = top + n * box_h + (n - 1) * gap + 50
    cx = width // 2
    body = [_header(title, width)]
    for i, (label, desc) in enumerate(items):
        y = top + i * (box_h + gap)
        body.append(
            f"<rect x='{cx - 240}' y='{y}' width='480' height='{box_h}' rx='14' "
            f"fill='{_NODE_FILL}' stroke='{_NODE_STROKE}' stroke-width='2'/>"
            f"<text x='{cx}' y='{y + (36 if desc else 52)}' text-anchor='middle' {_FONT} "
            f"font-size='16' font-weight='700' fill='{_TEXT}'>{_esc(_clip(label, 44))}</text>"
        )
        if desc:
            body.append(
                f"<text x='{cx}' y='{y + 62}' text-anchor='middle' {_FONT} "
                f"font-size='13' fill='{_TEXT_DIM}'>{_esc(_clip(desc, 56))}</text>"
            )
        if i < n - 1:
            ay = y + box_h
            body.append(
                f"<line x1='{cx}' y1='{ay}' x2='{cx}' y2='{ay + gap - 8}' "
                f"stroke='{_ACCENT_DIM}' stroke-width='2.5'/>"
                f"<path d='M {cx - 7} {ay + gap - 18} L {cx} {ay + gap - 6} L {cx + 7} {ay + gap - 18}' "
                f"fill='none' stroke='{_ACCENT_DIM}' stroke-width='2.5'/>"
            )
    return _svg_doc(width, height, "".join(body))


_KINDS = {"mindmap": _mindmap_svg, "timeline": _timeline_svg, "flowchart": _flowchart_svg}


async def create_diagram(
    kind: str,
    title: str,
    items: object,
    filename: str = "ephe_diagramm.svg",
) -> str:
    """Creates a deterministic SVG diagram in the Black Forest design.

    kind: 'mindmap' | 'timeline' | 'flowchart'
    items: a list of points — optionally 'Label | description' per point.
    """
    kind_normalized = (kind or "").strip().lower()
    aliases = {"mind-map": "mindmap", "mind_map": "mindmap", "map": "mindmap",
               "prozess": "flowchart", "process": "flowchart", "flow": "flowchart",
               "zeitstrahl": "timeline", "zeitlinie": "timeline", "roadmap": "timeline"}
    kind_normalized = aliases.get(kind_normalized, kind_normalized)
    builder = _KINDS.get(kind_normalized)
    if builder is None:
        return f"[diagram error: unknown kind '{kind}' — allowed: mindmap, timeline, flowchart]"
    parsed = _parse_items(items)
    if not parsed:
        return "[diagram error: no items detected — please pass items as a list]"

    def _build() -> str:
        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "ephe_diagramm.svg").name)
        if not safe.lower().endswith(".svg"):
            safe += ".svg"
        out = downloads / safe
        out.write_text(builder(title or "", parsed), encoding="utf-8")
        return f"SVG_FILE:{out}"

    try:
        return await asyncio.to_thread(_build)
    except Exception as exc:
        return f"[diagram error: {exc}]"
