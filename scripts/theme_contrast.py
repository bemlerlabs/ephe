"""Reading the one ground out of the stylesheet and taking the WCAG ratio of two colours.

`app/src/styles/globals.css` spells its role literals in `@theme` and bends nothing per
theme: the forest is the only ground the product ships (owner decision 2026-10-19). A
token either spells a colour or points at another token, so resolving one means following
the links the sheet writes. `scripts/mark_contract.py` uses this to recompute the mark red
against that ground, which is the number the frozen literal used to fail.

The ratios here are the same arithmetic `tests/test_r48_design_tokens.py` and
`tests/test_tui_black_forest.py` apply, kept in one place so a gate and a test can never
disagree about what 4.5:1 means.
"""
from __future__ import annotations

import re

CSS_DECLARATION = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;{}]+);")
VAR_LINK = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)\s*\)")
HSL_LITERAL = re.compile(r"hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)")


def declarations(text: str) -> dict[str, str]:
    """The first `--token: value;` of every token in `text`, in source order."""
    out: dict[str, str] = {}
    for match in CSS_DECLARATION.finditer(text):
        out.setdefault(match.group(1), match.group(2).strip())
    return out


def forest_table(sheet: str) -> dict[str, str]:
    """{--token: value} for the ground the product ships."""
    return declarations(sheet)


def resolved(table: dict[str, str], token: str, hops: int = 4) -> str | None:
    """The literal `token` ends at, following the var() links the sheet writes."""
    value = table.get(token)
    for _ in range(hops):
        if value is None:
            return None
        link = VAR_LINK.fullmatch(value)
        if link is None:
            return value
        value = table.get(link.group(1))
    return None


def hsl_rgb(hue: float, sat: float, light: float) -> tuple[float, float, float]:
    """An `hsl()` literal as RGB, quantised to the 8-bit channel a browser paints."""
    sat, light = sat / 100.0, light / 100.0
    a = sat * min(light, 1 - light)

    def channel(n: float) -> float:
        k = (n + hue / 30.0) % 12
        return round((light - a * max(-1.0, min(k - 3, min(9 - k, 1.0)))) * 255)

    red, green, blue = (channel(n) for n in (0, 8, 4))
    return red, green, blue


def rgb_of(value: str) -> tuple[float, float, float] | None:
    """RGB for a hex or hsl() literal; None for anything this leg cannot read."""
    text = value.strip()
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        if len(digits) != 6:
            return None
        red, green, blue = (float(int(digits[i:i + 2], 16)) for i in (0, 2, 4))
        return red, green, blue
    match = HSL_LITERAL.fullmatch(text)
    if match is None:
        return None
    return hsl_rgb(*(float(group) for group in match.groups()))


def contrast(one: tuple[float, float, float], two: tuple[float, float, float]) -> float:
    """The WCAG ratio of two colours."""
    def linear(channel: float) -> float:
        channel /= 255.0
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    def luminance(rgb: tuple[float, float, float]) -> float:
        r, g, b = (linear(channel) for channel in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted((luminance(one), luminance(two)), reverse=True)
    return (high + 0.05) / (low + 0.05)
