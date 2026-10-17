"""Ephe – generate_chart tool (SVG fallback).

The answer is read by a model that then tells the user what it made, so every
shortcut this renderer takes is named in the answer instead of staying silent:
a colour that was not applied, labels that were shortened, a pie whose slices
were negative. The file is written as SVG (the tool schema still advertises a
PNG — see core/tools/_schemas.py, ``generate_chart``).
"""

from __future__ import annotations

import html
import math
import re
import time
import uuid
from pathlib import Path

#: Longest label the axis can show; anything past it is cut and reported.
MAX_LABEL_CHARS = 32


async def generate_chart(
    chart_type: str,
    title: str,
    labels: list,
    values: list,
    xlabel: str = "",
    ylabel: str = "",
    color: str = "#22c55e",
) -> str:
    return _generate_svg_chart(chart_type, title, labels, values, xlabel=xlabel, ylabel=ylabel, color=color)


def _as_list(raw: object, name: str) -> tuple[list, str]:
    """Coerces one series argument to a list: (list, error).

    A model that means three categories often sends ``"Q1, Q2, Q3"`` as a
    string. Iterating that gives one entry per character, and the length check
    then blamed the labels for a problem in the type.
    """
    if raw is None:
        return [], ""
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()], ""
    if isinstance(raw, (list, tuple)):
        return list(raw), ""
    return [], f"{name} must be a list, got {type(raw).__name__}"


def _to_numbers(values: list) -> tuple[list, str]:
    """Converts a series to finite floats: (numbers, error)."""
    numbers: list[float] = []
    for index, raw in enumerate(values):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return [], (
                f"values[{index}] is not a number: {raw!r} — pass plain numbers, "
                f"e.g. values=[{', '.join(repr(v) for v in values[:2])}]"
            )
        if math.isnan(value):
            return [], f"values[{index}] is NaN — a chart cannot draw it; leave that point out"
        if math.isinf(value):
            return [], f"values[{index}] is infinite — no axis scales to it; give a finite number"
        numbers.append(value)
    return numbers, ""


def _generate_svg_chart(
    chart_type: str,
    title: str,
    labels: list,
    values: list,
    xlabel: str = "",
    ylabel: str = "",
    color: str = "#16a34a",
) -> str:
    try:
        label_list, labels_error = _as_list(labels, "labels")
        value_list, values_error = _as_list(values, "values")
        if labels_error or values_error:
            return "[chart: " + "; ".join(m for m in (labels_error, values_error) if m) + "]"
        if not value_list:
            return "[chart: values must not be empty — pass at least one number]"
        vals, number_error = _to_numbers(value_list)
        if number_error:
            return f"[chart: {number_error}]"
        clean_labels = [str(label)[:MAX_LABEL_CHARS] for label in label_list]
        if len(clean_labels) != len(vals):
            return (
                "[chart: labels and values must have equal length "
                f"(got {len(clean_labels)} labels, {len(vals)} values)]"
            )
        if not vals:
            return "[chart: labels and values must have equal length and must not be empty]"
        notes: list[str] = []
        if len(label_list) != len(clean_labels):
            notes.append(
                f"{len(label_list) - len(clean_labels)} empty label(s) dropped — "
                f"now {len(clean_labels)} categories"
            )
        truncated = sum(1 for label in label_list if len(str(label)) > MAX_LABEL_CHARS)
        if truncated:
            notes.append(f"{truncated} label(s) shortened to {MAX_LABEL_CHARS} characters")

        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", str(title).strip())[:48].strip("_") or "chart"
        # The second-resolution timestamp alone made two charts of the same title
        # in one second answer with the SAME path — the second call overwrote the
        # first and the model reported two files that were one.
        out = downloads / f"ephe_chart_{safe_title}_{int(time.time())}_{uuid.uuid4().hex[:6]}.svg"
        width, height = 960, 600
        margin_left, margin_bottom, margin_top, margin_right = 94, 88, 92, 54
        plot_w = width - margin_left - margin_right
        plot_h = height - margin_top - margin_bottom
        max_val = max(vals) or 1.0
        min_val = min(0.0, min(vals))
        val_span = max(max_val - min_val, 1.0)
        default_accent = "#16a34a"
        accent = color if re.match(r"^#[0-9a-fA-F]{6}$", str(color)) else default_accent
        if accent == default_accent and color and not re.match(r"^#[0-9a-fA-F]{6}$", str(color)):
            notes.append(f"color '{color}' is not a #rrggbb hex — used the Ephe green {default_accent}")

        def sx(index: int) -> float:
            if len(vals) == 1:
                return margin_left + plot_w / 2
            return margin_left + index * (plot_w / (len(vals) - 1))

        def sy(value: float) -> float:
            return margin_top + plot_h - ((value - min_val) / val_span) * plot_h

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
            '<rect width="960" height="600" fill="#fbfcfb"/>',
            '<rect x="0" y="0" width="960" height="10" fill="#101820"/>',
            f'<text x="54" y="58" font-family="Arial, sans-serif" font-size="30" font-weight="700" fill="#101820">{html.escape(title)}</text>',
            f'<text x="54" y="86" font-family="Arial, sans-serif" font-size="13" fill="#53606f">{html.escape(ylabel or "Values")} by {html.escape(xlabel or "Category")}</text>',
            f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
        ]
        for tick in range(5):
            value = min_val + val_span * tick / 4
            y = sy(value)
            parts.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_w}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
            parts.append(f'<text x="{margin_left - 14}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#53606f">{value:g}</text>')

        ct = str(chart_type).lower()
        if ct == "bar":
            step = plot_w / max(len(vals), 1)
            bar_w = min(82, step * 0.58)
            for index, (label, value) in enumerate(zip(clean_labels, vals)):
                x = margin_left + index * step + (step - bar_w) / 2
                y = sy(value)
                h = margin_top + plot_h - y
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{accent}"/>')
                parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#101820">{value:g}</text>')
                parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{margin_top + plot_h + 28}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#53606f">{html.escape(label)}</text>')
        elif ct == "line":
            points = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals))
            if len(vals) == 1:
                # A polyline of one point draws nothing — the marker carries it.
                notes.append("one data point — a line needs two; the point is drawn as a marker")
            parts.append(f'<polyline points="{points}" fill="none" stroke="{accent}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>')
            for index, (label, value) in enumerate(zip(clean_labels, vals)):
                x, y = sx(index), sy(value)
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#fbfcfb" stroke="{accent}" stroke-width="3"/>')
                parts.append(f'<text x="{x:.1f}" y="{margin_top + plot_h + 28}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#53606f">{html.escape(label)}</text>')
        elif ct == "pie":
            total = sum(abs(v) for v in vals) or 1.0
            negatives = sum(1 for v in vals if v < 0)
            if negatives:
                notes.append(
                    f"{negatives} negative value(s) — a share cannot be negative, "
                    f"plotted by absolute size"
                )
            x0, y0 = margin_left + 250, margin_top + 220
            start = -90.0
            palette = [accent, "#0891b2", "#d97706", "#64748b", "#22c55e", "#0f766e"]
            for index, (label, value) in enumerate(zip(clean_labels, vals)):
                angle = abs(value) / total * 360
                end = start + angle
                large = 1 if angle > 180 else 0
                fill = palette[index % len(palette)]
                if angle >= 359.999:
                    # An arc whose start equals its end is not rendered at all —
                    # a single-slice pie used to come out as an empty chart.
                    parts.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="150" fill="{fill}"/>')
                else:
                    x1 = x0 + 150 * math.cos(math.radians(start))
                    y1 = y0 + 150 * math.sin(math.radians(start))
                    x2 = x0 + 150 * math.cos(math.radians(end))
                    y2 = y0 + 150 * math.sin(math.radians(end))
                    parts.append(f'<path d="M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f} A150,150 0 {large},1 {x2:.1f},{y2:.1f} Z" fill="{fill}"/>')
                parts.append(f'<rect x="650" y="{150 + index * 28}" width="14" height="14" fill="{fill}"/><text x="674" y="{162 + index * 28}" font-family="Arial, sans-serif" font-size="13" fill="#101820">{html.escape(label)} ({value:g})</text>')
                start = end
        else:
            return f"[chart: unknown type '{chart_type}'. Allowed: bar, line, pie]"

        parts.append('<text x="54" y="568" font-family="Arial, sans-serif" font-size="12" fill="#53606f">Generated locally by Ephe - SVG fallback renderer</text>')
        parts.append("</svg>")
        out.write_text("\n".join(parts), encoding="utf-8")
        answer = f"CHART_FILE:{out}"
        if notes:
            answer += "".join(f"\nnote: {note}" for note in notes)
        return answer
    except Exception as exc:
        return f"[chart-error: {exc}]"
