"""R48 — design-token gates for app/src/styles/globals.css (plan: ephe-plan-design-system.md).

Checks the presence of the new token layers (S1–S6) directly at the CSS source —
cheap, deterministic, no build. The 1:1 values are documented in the plan; what
matters here are the anchors that would disappear first in a regression.
"""
from __future__ import annotations

import re
from pathlib import Path

GLOBALS = Path(__file__).resolve().parent.parent / "app" / "src" / "styles" / "globals.css"


def _css() -> str:
    return GLOBALS.read_text(encoding="utf-8")


def test_text_ui_scale_present():
    """S1: the 7-step text-ui-* scale inside the @theme block."""
    css = _css()
    assert "--text-ui-" in css
    for token in (
        "--text-ui-xl",
        "--text-ui-lg",
        "--text-ui-base",
        "--text-ui-caption",
        "--text-ui-sm",
        "--text-ui-xs",
        "--text-ui-2xs",
    ):
        assert token in css, f"fehlende Skalen-Stufe {token}"
    # coupling of the scale to the appearance setting
    assert "--ui-font-size: 14px" in css


def test_z_index_ladder_present():
    """S4: the 4-step overlay z-ladder 0/10/20/30."""
    css = _css()
    assert "--z-index-modal" in css
    for token in ("--z-index-base", "--z-index-sticky", "--z-index-overlay", "--z-index-modal"):
        assert token in css, f"fehlende Z-Stufe {token}"


def test_elevation_levels_present():
    """S3: 3 elevation levels instead of 5 divergent shadow families."""
    css = _css()
    assert "--shadow-elevation-2" in css
    for token in ("--shadow-elevation-1", "--shadow-elevation-2", "--shadow-elevation-3"):
        assert token in css, f"fehlendes Elevation-Level {token}"


def test_status_aliases_present():
    """S5: 4 semantic status aliases (firefly/lichen/destructive/mist)."""
    css = _css()
    assert "--color-status-success" in css
    for token in (
        "--color-status-success",
        "--color-status-warning",
        "--color-status-danger",
        "--color-status-info",
    ):
        assert token in css, f"fehlender Status-Alias {token}"


def test_ios_input_token_fixed_16px():
    """S2: iOS focus-zoom threshold — the input token fixed at 16px/20px."""
    css = _css()
    assert "--text-ui-input: 16px" in css
    assert "font-size: 16px" in css  # the .ios-input fix cover (plan items 14, 15, 16)


def test_dead_radius_token_removed():
    """S6: the dead token --radius: 0.75rem is removed."""
    css = _css()
    assert "0.75rem" not in css
    assert "--radius: " not in css  # only the hardened --radius-* levels remain


def test_spacing_raster_documented():
    """S6: the spacing raster {0,2,4,6,8,10,12,16,20,24} is documented as a comment."""
    css = _css()
    assert "Spacing raster" in css
    assert "{0,2,4,6,8,10,12,16,20,24}" in css


# P1-7 (WCAG AA): the status-info contrast gate
# The token --color-status-info is dimmed by opacity across the whole repo
# (text-status-info/55../80). This gate recomputes the WCAG contrast ratio of the
# dimmed color (alpha compositing over the theme background) and
# blocks regression to the old, too-dark values (63% dark / 42%
# light, which fell below AA at /55..70 — finding 2026-10, P1-7).

def _hsl_values(prop: str) -> list[tuple[float, float, float]]:
    """All `--prop: hsl(H S% L%)` values in source order (dark first, then light)."""
    out: list[tuple[float, float, float]] = []
    for m in re.finditer(rf"--{re.escape(prop)}:\s*hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)", _css()):
        out.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
    return out


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    s /= 100.0
    l /= 100.0
    k = lambda n: (n + h / 30.0) % 12
    a = s * min(l, 1 - l)
    f = lambda n: l - a * max(-1, min(k(n) - 3, min(9 - k(n), 1)))
    return (f(0) * 255, f(8) * 255, f(4) * 255)


def _lum(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    l1, l2 = _lum(fg), _lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _blend(fg, bg, alpha: float):
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))


def test_status_info_dark_aa_at_dimmed_opacities():
    """Dark: status-info must hold AA-normal (>=4.5) at every dim step /55../100."""
    info = _hsl_values("color-status-info")
    bg = _hsl_values("color-background")
    assert len(info) >= 1 and len(bg) >= 1, "status-info/background Token fehlen"
    fg = _hsl_to_rgb(*info[0])           # @theme (dark)
    background = _hsl_to_rgb(*bg[0])     # @theme (dark) = hsl(0 0% 7%)
    for alpha in (1.0, 0.80, 0.70, 0.60, 0.55):
        ratio = _contrast(_blend(fg, background, alpha), background)
        assert ratio >= 4.5, f"dark status-info /{int(alpha*100)} = {ratio:.2f}:1 < AA 4.5:1"


def test_status_info_light_aa_floor():
    """Light: AA-normal (>=4.5) at /70../100; AA-large (>=3) at /55../60.

    On the ~white 97% base, AA-normal at /55 is physically unreachable for a muted
    gray (even pure black would land at ~4.7 at /55), so AA-large is the documented
    and achievable floor.
    """
    info = _hsl_values("color-status-info")
    bg = _hsl_values("color-background")
    assert len(info) >= 2 and len(bg) >= 2, "light-theme Token fehlen"
    fg = _hsl_to_rgb(*info[1])           # html.light
    background = _hsl_to_rgb(*bg[1])     # html.light = hsl(0 0% 97%)
    for alpha in (1.0, 0.80, 0.70):
        ratio = _contrast(_blend(fg, background, alpha), background)
        assert ratio >= 4.5, f"light status-info /{int(alpha*100)} = {ratio:.2f}:1 < AA 4.5:1"
    for alpha in (0.60, 0.55):
        ratio = _contrast(_blend(fg, background, alpha), background)
        assert ratio >= 3.0, f"light status-info /{int(alpha*100)} = {ratio:.2f}:1 < AA-Large 3:1"
