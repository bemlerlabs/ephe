"""R61: the three glass layers, and what the ink on each of them is worth.

Wave 1 of docs/UI_4X_PROGRAM_2026-10-11.md measured this grid over the two translucent
classes the stylesheet then carried; work item #67 (U3) replaced those with three layers
named by role, and the grid follows. Section 8 of the programme holds the rule, this file
holds the arithmetic that enforces it.

A glass panel fills with an alpha colour over the theme canvas, so the text on it sits on a
colour no token names: the fill blended at the fill's own alpha. The model below is the same
relative luminance and compositing arithmetic `tests/test_r48_design_tokens.py:111-126`
carries, applied one layer further. r48's own cases composite a role against the flat canvas
and stop there, which is why the muted role reads 5.31:1 in that gate (`globals.css:68-69`)
and read 4.43:1 on the panel a user was looking at.

Backdrop assumption, and it bounds the ratio: what lies under a panel is a theme ground, one
flat colour at a time. The canvas is the first. The glass material in `globals.css` names the
second (`--color-surface`, where the sidebar rows and the settings register sit) and the two
lit steps a pane is kept off, so the grid here runs every column on every one of them, alone
and stacked. Over content brighter than a declared ground the same veil costs more, the 3x
dossier computes 1.19:1 for primary ink behind a 22% fill in the dark theme, and seeing it
needs composited pixels from the built bundle. That is the instrument the programme names
wave 5, so the bright-backdrop case is absent here on purpose and the lit steps carry the
recorded figures that mark the boundary.

Coverage: 3 ink roles x 6 columns x 2 themes = 36 pairs on the canvas, the same 36 on the
surface ground, and the lit steps as a recorded boundary. The count of pairs below 4.5:1 on a
rest ground is the programme's falling value and it stands at 0. The last cases pin each
layer's own binding figure and each ground's binding column too, so a veil that gets lighter
again fails with its number while it is still above the floor.

Nothing outside this file changes: the stylesheet is read and never written.
"""
from __future__ import annotations

import re
from pathlib import Path

GLOBALS = Path(__file__).resolve().parent.parent / "app" / "src" / "styles" / "globals.css"

AA_NORMAL = 4.5
# The programme's single falling value: computed role/surface/theme pairs under AA_NORMAL.
# Measured 1 of 12 on 2026-10-11 (muted ink behind the 38% dark veil), 0 of 18 since U3
# moved that veil to 26%. A pair falling back under 4.5:1 is a new defect, so the ceiling
# is 0 and there is nothing left to leave unpinned.
SUB_AA_CEILING = 0
INK_ROLES = ("color-ink", "color-ink-soft", "color-ink-faint")
GLASS_LAYERS = (
    ("glass-reading-fill", ".glass-reading"),
    ("glass-control-fill", ".glass-control"),
    ("glass-float-fill", ".glass-float"),
)
# Measured on the applied sheet at the forest-material landing: the lowest of the three role
# ratios a layer shows. The muted role is the binding one in both themes. A layer is allowed
# to get quieter than this only by a deliberate edit that lands the new figure here, in the
# same commit.
LAYER_FLOORS = {
    ("dark", ".glass-reading"): 5.06,
    ("dark", ".glass-control"): 5.00,
    ("dark", ".glass-float"): 5.42,
    ("light", ".glass-reading"): 5.63,
    ("light", ".glass-control"): 5.63,
    ("light", ".glass-float"): 5.61,
}
# The columns a pane is built from, bottom to top the way the markup nests them. The three
# single layers are the material; the three stacked ones are the two rules the material
# states about resting a pane on another pane.
GLASS_COLUMNS = (
    ("reading", ("glass-reading-fill",)),
    ("control", ("glass-control-fill",)),
    ("float", ("glass-float-fill",)),
    ("reading+control", ("glass-reading-fill", "glass-control-fill")),
    ("reading+float", ("glass-reading-fill", "glass-float-fill")),
    ("reading+control+float", ("glass-reading-fill", "glass-control-fill", "glass-float-fill")),
)
# The two grounds the sheet declares as somewhere a pane may rest. The lit steps
# (`--color-surface-raised`, the hover and selection states) stay off this list: they
# already spend the lightness budget the muted role needs, and the two closing cases
# below record that.
REST_GROUNDS = ("color-background", "color-surface")
# Measured: the binding column and its muted-role ratio on each rest ground. Every figure
# clears AA_NORMAL, so a column that falls is a regression whatever it looks like on screen.
GROUND_FLOORS = {
    ("dark", "color-background"): ("reading+control", 4.84),
    ("dark", "color-surface"): ("reading+control", 4.72),
    ("light", "color-background"): ("float", 5.61),
    ("light", "color-surface"): ("float", 5.68),
}
# The lit steps of the ink theme, as (token, white veil over the surface, bare muted ratio,
# the binding single-veil column's ratio, the ratio with both veils stacked). The first two
# figures are below AA_NORMAL: the step is under the floor before any glass touches it, and a
# translucent veil moves it by hundredths. Recorded so that a later change which makes a veil
# opaque enough to move these numbers has to come back through this file and say so.
LIT_STEPS = (
    ("--color-surface-raised", 0.04, 4.47, 4.49, 4.57),
    ("--color-surface-interactive", 0.08, 3.97, 4.20, 4.42),
)
# The rounding the figures in the stylesheet are written to.
TOLERANCE = 0.02

_HSL = "hsl\\(\\s*([\\d.]+)\\s+([\\d.]+)%\\s+([\\d.]+)%\\s*\\)"
_HSLA = "hsla\\(\\s*([\\d.]+)\\s+([\\d.]+)%\\s+([\\d.]+)%\\s*/\\s*([\\d.]+)\\s*\\)"


def _css() -> str:
    return GLOBALS.read_text(encoding="utf-8")


def _block(css: str, opener: str, marker: str) -> str:
    """One top-level rule body, from its opener to the first brace at column zero.

    `marker` names the token that identifies which rule: `:root` opens more than once in
    globals.css (the motion tokens at :995 and :1101 stand in later ones) and only the block
    at :362 carries the dark glass fills.
    """
    start = css.index(opener)
    body = css[start : css.index("\n}", start)]
    assert marker in body, f"{opener} does not hold --{marker}"
    return body


def _hsl_in(body: str, prop: str) -> tuple[float, float, float]:
    match = re.search(rf"--{re.escape(prop)}:\s*{_HSL}", body)
    assert match, f"--{prop} is not an hsl() triple in this block"
    return (float(match.group(1)), float(match.group(2)), float(match.group(3)))


def _hsla_in(body: str, prop: str) -> tuple[tuple[float, float, float], float]:
    match = re.search(rf"--{re.escape(prop)}:\s*{_HSLA}", body)
    assert match, f"--{prop} is not an hsla() fill with an alpha"
    fill = (float(match.group(1)), float(match.group(2)), float(match.group(3)))
    return fill, float(match.group(4))


def _rgb(triple: tuple[float, float, float]) -> tuple[float, float, float]:
    h, s, l = triple
    s /= 100.0
    l /= 100.0
    k = lambda n: (n + h / 30.0) % 12
    a = s * min(l, 1.0 - l)
    f = lambda n: l - a * max(-1.0, min(k(n) - 3.0, min(9.0 - k(n), 1.0)))
    return (f(0.0) * 255.0, f(8.0) * 255.0, f(4.0) * 255.0)


def _lum(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    l1, l2 = _lum(fg), _lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _over(
    fill: tuple[float, float, float], ground: tuple[float, float, float], alpha: float
) -> tuple[float, float, float]:
    """`fill` at `alpha` over `ground`: the one compositing step every figure rests on."""
    return (
        fill[0] * alpha + ground[0] * (1.0 - alpha),
        fill[1] * alpha + ground[1] * (1.0 - alpha),
        fill[2] * alpha + ground[2] * (1.0 - alpha),
    )


def _themes() -> list[tuple[str, str, str]]:
    """(label, role block, fill block) for both themes.

    Dark roles live in the `@theme` block at globals.css:3 and their fills in the `:root`
    default at :362; light roles and light fills share the `html.light` block at :248.
    """
    css = _css()
    dark = _block(css, "@theme {", "color-ink:")
    light = _block(css, "html.light {", "glass-reading-fill:")
    dark_glass = _block(css, ":root {", "glass-reading-fill:")
    return [("dark", dark, dark_glass), ("light", light, light)]


def _panel(theme: tuple[str, str, str], fill_prop: str) -> tuple[float, float, float]:
    """The colour a reader sees under the text: the glass fill composited on its own canvas."""
    _, roles, fills = theme
    canvas = _rgb(_hsl_in(roles, "color-background"))
    fill, alpha = _hsla_in(fills, fill_prop)
    return _over(_rgb(fill), canvas, alpha)


def _column(
    theme: tuple[str, str, str], base: tuple[float, float, float], props: tuple[str, ...]
) -> tuple[float, float, float]:
    """A stack of glass fills over `base`, applied bottom to top the way the markup nests."""
    fills = theme[2]
    panel = base
    for prop in props:
        fill, alpha = _hsla_in(fills, prop)
        panel = _over(_rgb(fill), panel, alpha)
    return panel


def _lit_step(theme: tuple[str, str, str], lift: float) -> tuple[float, float, float]:
    """A `--color-surface-*` hover or selection step: a white veil over the surface."""
    surface = _rgb(_hsl_in(theme[1], "color-surface"))
    return _over((255.0, 255.0, 255.0), surface, lift)


def _muted(theme: tuple[str, str, str], panel: tuple[float, float, float]) -> float:
    """The muted ink role on `panel`, which binds every figure in this file."""
    return _ratio(_rgb(_hsl_in(theme[1], "color-ink-faint")), panel)


def _pairs() -> list[tuple[str, str, str, float]]:
    """Theme, glass layer, ink role, computed contrast ratio, for all 18 combinations."""
    rows: list[tuple[str, str, str, float]] = []
    for theme in _themes():
        label = theme[0]
        for fill_prop, css_class in GLASS_LAYERS:
            panel = _panel(theme, fill_prop)
            for role in INK_ROLES:
                rows.append((label, css_class, role, _ratio(_rgb(_hsl_in(theme[1], role)), panel)))
    return rows


def _report(rows: list[tuple[str, str, str, float]]) -> str:
    lines = [f"{t:5s} {c:16s} {r:16s} {v:6.2f}:1 {'sub-AA' if v < AA_NORMAL else ''}".rstrip()
             for t, c, r, v in rows]
    return "\n".join(lines)


def test_glass_grid_is_complete():
    """18 pairs, which is 3 ink roles x 3 layers x 2 themes, so a renamed token fails here."""
    rows = _pairs()
    assert len(rows) == 18, f"expected 18 glass pairs, computed {len(rows)}"
    for theme, css_class, role, value in rows:
        assert value > 1.0, f"{theme} {css_class} {role} collapsed to {value:.2f}:1"
        assert value < 21.0, f"{theme} {css_class} {role} reads {value:.2f}:1, past any sRGB pair"


def test_arithmetic_matches_the_ratios_recorded_in_the_stylesheet():
    """globals.css:66-69 carries four measured figures. Reproducing them is the check that this
    file's model is r48's model: status-info dimmed to /55 and /60 on the dark canvas at 4.96 and
    5.69, the muted role at 4.98 on paper and 5.31 on ink. Recorded rounding is 0.02 wide."""
    dark, light = _themes()
    dark_canvas = _rgb(_hsl_in(dark[1], "color-background"))
    info_dark = _rgb(_hsl_in(dark[1], "color-status-info"))
    for alpha, recorded in ((0.55, 4.96), (0.60, 5.69)):
        dimmed = _over(info_dark, dark_canvas, alpha)
        assert abs(_ratio(dimmed, dark_canvas) - recorded) <= TOLERANCE, f"status-info /{int(alpha * 100)}"
    light_canvas = _rgb(_hsl_in(light[1], "color-background"))
    for theme, canvas, recorded, which in (
        (light, light_canvas, 4.98, "paper"),
        (dark, dark_canvas, 5.31, "ink"),
    ):
        faint = _rgb(_hsl_in(theme[1], "color-ink-faint"))
        assert abs(_ratio(faint, canvas) - recorded) <= TOLERANCE, f"muted on {which}"


def test_every_pair_holds_aa_on_every_layer():
    """The floor U3 landed the tokens against: 4.5:1 is WCAG 2.2 SC 1.4.3 for normal text, and
    the smallest type the glass carries is the 11-12 px muted step, so the floor applies to all
    18 pairs with no role exempt. Today they run from 5.00:1 to 17.68:1."""
    rows = _pairs()
    for theme, css_class, role, value in rows:
        assert value >= AA_NORMAL, f"{theme} {role} on {css_class} = {value:.2f}:1 < {AA_NORMAL}:1"


def test_layers_hold_their_recorded_lift():
    """The ratchet under the floor: each layer's binding pair may not fall, so a veil cannot be
    lightened a step at a time while every run still reads green at 4.5:1."""
    worst: dict[tuple[str, str], tuple[str, float]] = {}
    for theme, css_class, role, value in _pairs():
        if (theme, css_class) not in worst or value < worst[(theme, css_class)][1]:
            worst[(theme, css_class)] = (role, value)
    assert set(worst) == set(LAYER_FLOORS), f"layers moved: {sorted(worst)}"
    for (theme, css_class), (role, value) in sorted(worst.items()):
        recorded = LAYER_FLOORS[(theme, css_class)]
        assert value >= recorded - TOLERANCE, (
            f"{theme} {css_class} binds at {value:.2f}:1 ({role}), recorded {recorded:.2f}:1"
        )


def test_sub_aa_count_does_not_climb_off_zero():
    """The count the programme ratchets. It reached 0 when U3 moved the dark reading veil from
    38% to 26%, and a pair climbing back under the floor is the defect the count exists to see."""
    rows = _pairs()
    below = [row for row in rows if row[3] < AA_NORMAL]
    print("R61 glass contrast grid, canvas backdrop, AA floor 4.5:1\n" + _report(rows))
    assert len(below) <= SUB_AA_CEILING, (
        f"{len(below)} pairs under {AA_NORMAL}:1, ceiling {SUB_AA_CEILING}\n" + _report(below)
    )


def test_a_pane_holds_aa_on_every_ground_it_may_rest_on():
    """Rule 1 of the material: a pane rests on --color-canvas or on --color-surface, alone or in
    a stack, and the muted role clears 4.5:1 on every one of those columns. The binding pair is
    reading over control on the surface at 4.72:1."""
    for theme in _themes():
        label = theme[0]
        for ground in REST_GROUNDS:
            base = _rgb(_hsl_in(theme[1], ground))
            for column, props in GLASS_COLUMNS:
                panel = _column(theme, base, props)
                for role in INK_ROLES:
                    value = _ratio(_rgb(_hsl_in(theme[1], role)), panel)
                    assert value >= AA_NORMAL, (
                        f"{label} {role} on {column} over {ground} = {value:.2f}:1 < {AA_NORMAL}:1"
                    )


def test_the_binding_column_of_each_rest_ground_is_recorded():
    """The ratchet under rule 1, one figure per ground. A veil spends the ground's own lightness
    budget, so the column that binds the ground is the number worth holding."""
    for theme in _themes():
        label = theme[0]
        for ground in REST_GROUNDS:
            base = _rgb(_hsl_in(theme[1], ground))
            worst: tuple[str, float] | None = None
            for column, props in GLASS_COLUMNS:
                value = _muted(theme, _column(theme, base, props))
                if worst is None or value < worst[1]:
                    worst = (column, value)
            assert worst is not None
            recorded_column, recorded = GROUND_FLOORS[(label, ground)]
            assert worst[0] == recorded_column, (
                f"{label} on {ground} binds on {worst[0]}, recorded {recorded_column}"
            )
            assert worst[1] >= recorded - TOLERANCE, (
                f"{label} on {ground} binds at {worst[1]:.2f}:1, recorded {recorded:.2f}:1"
            )


def test_a_lit_step_is_out_of_budget_for_a_translucent_veil():
    """Rule 1's boundary, and the answer to where a glass layer may not sit. A hover step already
    lifts the surface, so the muted role sits under the floor before any glass lands on it and a
    translucent veil moves that figure by hundredths in either direction. The recorded pair is
    what keeps a veil from being quietly thickened until these steps read green."""
    dark = _themes()[0]
    for token, lift, recorded_bare, recorded_veiled, _ in LIT_STEPS:
        ground = _lit_step(dark, lift)
        bare = _muted(dark, ground)
        assert abs(bare - recorded_bare) <= TOLERANCE, f"{token} bare {bare:.2f}:1"
        assert bare < AA_NORMAL, f"{token} clears AA bare at {bare:.2f}:1, so rule 1 needs review"
        worst: tuple[str, float] | None = None
        for column, props in GLASS_COLUMNS:
            if "float" in column:
                continue
            value = _muted(dark, _column(dark, ground, props))
            if worst is None or value < worst[1]:
                worst = (column, value)
        assert worst is not None
        assert abs(worst[1] - recorded_veiled) <= TOLERANCE, (
            f"{token}: {worst[0]} reads {worst[1]:.2f}:1, recorded {recorded_veiled:.2f}:1"
        )
        assert worst[1] < AA_NORMAL


def test_the_float_rests_on_anything_and_the_two_veils_only_over_a_ground():
    """Rule 2. --glass-float-fill is darker than every ground the sheet declares, so a float
    column only ever lowers its panel and clears AA even on a lit step. The reading and control
    veils are lighter than the page, so two of them stacked on --color-surface-interactive settle
    past the ceiling: they may rest on a ground, and on each other only over the canvas, the
    surface and the raised step."""
    dark = _themes()[0]
    for ground_name in REST_GROUNDS:
        base = _rgb(_hsl_in(dark[1], ground_name))
        value = _muted(dark, _column(dark, base, ("glass-reading-fill", "glass-control-fill")))
        assert value >= AA_NORMAL, f"two veils over {ground_name} = {value:.2f}:1"
    for token, lift, _, _, recorded_stack in LIT_STEPS:
        lit = _lit_step(dark, lift)
        stacked = _muted(dark, _column(dark, lit, ("glass-reading-fill", "glass-control-fill")))
        assert abs(stacked - recorded_stack) <= TOLERANCE, (
            f"{token}: two veils read {stacked:.2f}:1, recorded {recorded_stack:.2f}:1"
        )
        for column, props in GLASS_COLUMNS:
            if "float" not in column:
                continue
            value = _muted(dark, _column(dark, lit, props))
            assert value >= AA_NORMAL, f"the float column {column} on {token} = {value:.2f}:1"
    interactive = _lit_step(dark, 0.08)
    stacked = _muted(
        dark, _column(dark, interactive, ("glass-reading-fill", "glass-control-fill"))
    )
    assert stacked < AA_NORMAL, (
        f"two veils over --color-surface-interactive read {stacked:.2f}:1, so rule 2 moved"
    )
