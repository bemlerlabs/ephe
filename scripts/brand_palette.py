"""Brand roles — the palette the icon kit, the in-app vector and the terminal share.

One role, two spellings. The generator asks `hex_for(role)` and concretises the
role into a hex at build time, which is what a raster needs; the in-app vector in
`app/src/assets/` names `token_for(role)` (or `currentColor`) instead, so the
stylesheet decides what the role resolves to on the ground. The terminal reads the
same red through `ui/palette.py`.

The frozen five (`BLACK_FOREST`, `MOSS_DEEP`, `FIREFLY`, `FIREFLY_GLOW`, `WHITE`)
carried the paper brand `#d83828` into every raster and into the in-app vector:
the icon painted 4.03:1 on its own field where the ink brand `#E8543F` measures
5.15:1, and the vector carried the same literal, where no `currentColor` reaches
it. A role carries the measured spelling and the property name.

The mark's red is the one role with a job bigger than a name: it has to clear the
4.5:1 floor of `scripts/asset_check.py` on the ground. Since 2026-10-19 that is one
ground — the guardian alias `--color-firefly`, equal to `--color-brand` in `@theme`
(5.13:1 on the ink ground). The `paper` step (`#B52E21`, 5.4:1 on the retired paper
sheet) survives only for the archived proof rungs, which the generator still renders
by name. The vector takes the token; the raster takes the ink hex, so the icon paints
what the app paints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    """One colour: the concrete build spelling, its property name, and the paper step."""

    name: str
    hex: str
    token: str
    paper: str
    note: str


ROLES: dict[str, Role] = {
    "ground": Role(
        name="ground",
        hex="#121212",
        token="--color-black-forest",
        paper="#F0F0E6",
        note="the icon field, the raster cut of the sheet's ground role",
    ),
    "panel": Role(
        name="panel",
        hex="#1f1f1f",
        token="--color-moss-deep",
        paper="#FAFAF5",
        note="the raised step behind the emblem",
    ),
    "brand": Role(
        name="brand",
        hex="#E8543F",
        token="--color-firefly",
        paper="#B52E21",
        note="the product red, AA on the ground of both themes",
    ),
    "brand_glow": Role(
        name="brand_glow",
        hex="#F1705F",
        token="--color-firefly-glow",
        paper="#D83828",
        note="the hover step of the brand red, the drop's upper stop",
    ),
    "ink": Role(
        name="ink",
        hex="#f7f7f7",
        token="--color-ink",
        paper="#1A1614",
        note="the positive E and the rim light",
    ),
    "figure_paper": Role(
        name="figure_paper",
        hex="#EFE6D2",
        token="--color-figure-paper",
        paper="#EFE6D2",
        note="the moth's sheet: the folded paper the figure is made of",
    ),
    "figure_paper_lit": Role(
        name="figure_paper_lit",
        hex="#FBF5E6",
        token="--color-figure-paper-lit",
        paper="#FBF5E6",
        note="the lit face of a fold, where the sheet turns to the light",
    ),
    "figure_paper_shade": Role(
        name="figure_paper_shade",
        hex="#D8C9AC",
        token="--color-figure-paper-shade",
        paper="#D8C9AC",
        note="the turned-away face and the crease line",
    ),
    "figure_paper_body": Role(
        name="figure_paper_body",
        hex="#C8B591",
        token="--color-figure-paper-body",
        paper="#C8B591",
        note="the rolled slip that is the body, a shade under the sheet",
    ),
    "figure_soot": Role(
        name="figure_soot",
        hex="#221A15",
        token="--color-figure-soot",
        paper="#221A15",
        note="the fire spirit's body: soot, and the same soot on paper — the figure does not "
             "change with the ground",
    ),
    "figure_plate": Role(
        name="figure_plate",
        hex="#33221A",
        token="--color-figure-plate",
        paper="#33221A",
        note="the comb plates and the antenna balls",
    ),
    "figure_fur": Role(
        name="figure_fur",
        hex="#563323",
        token="--color-figure-fur",
        paper="#563323",
        note="the brim and the foot stubs",
    ),
    "figure_mou": Role(
        name="figure_mou",
        hex="#9A5730",
        token="--color-figure-mou",
        paper="#9A5730",
        note="fur lit by the figure's own flame: antenna rods, crown tuft, mouth",
    ),
    "figure_ember": Role(
        name="figure_ember",
        hex="#F2A274",
        token="--color-figure-ember",
        paper="#F2A274",
        note="the ember step of the eye gradient",
    ),
    "figure_cream": Role(
        name="figure_cream",
        hex="#F7F0E0",
        token="--color-figure-cream",
        paper="#F7F0E0",
        note="the eyes and the hot core of the plume",
    ),
    "figure_shine": Role(
        name="figure_shine",
        hex="#FFFDF6",
        token="--color-figure-shine",
        paper="#FFFDF6",
        note="the catchlight on an eye and on an antenna ball",
    ),
    "figure_head_hi": Role(
        name="figure_head_hi",
        hex="#2C2523",
        token="--color-figure-head-hi",
        paper="#2C2523",
        note="the head sphere's upper-left highlight",
    ),
    "figure_head_core": Role(
        name="figure_head_core",
        hex="#191311",
        token="--color-figure-head-core",
        paper="#191311",
        note="the head sphere's velvet core",
    ),
    "figure_head_shadow": Role(
        name="figure_head_shadow",
        hex="#120F0E",
        token="--color-figure-head-shadow",
        paper="#120F0E",
        note="the head sphere's lower shadow",
    ),
    "figure_honey_mid": Role(
        name="figure_honey_mid",
        hex="#FFD166",
        token="--color-figure-honey-mid",
        paper="#FFD166",
        note="the honey lantern's middle gold",
    ),
    "figure_honey_deep": Role(
        name="figure_honey_deep",
        hex="#FF9F1C",
        token="--color-figure-honey-deep",
        paper="#FF9F1C",
        note="the honey lantern's deep amber",
    ),
    "figure_iris": Role(
        name="figure_iris",
        hex="#F5A623",
        token="--color-figure-iris",
        paper="#F5A623",
        note="the amber iris of the eye",
    ),
    "figure_wing_root": Role(
        name="figure_wing_root",
        hex="#452718",
        token="--color-figure-wing-root",
        paper="#D5A183",
        note="the glass wing's root stop: dark glass on ink, warm glass on paper",
    ),
    "figure_wing_mid": Role(
        name="figure_wing_mid",
        hex="#8A5232",
        token="--color-figure-wing-mid",
        paper="#E4BFA2",
        note="the glass wing's middle stop",
    ),
    "figure_wing_tip": Role(
        name="figure_wing_tip",
        hex="#D9A87C",
        token="--color-figure-wing-tip",
        paper="#F6E0CB",
        note="the glass wing's tip stop, the end that catches the light",
    ),
    "template": Role(
        name="template",
        hex="#000000",
        token="currentColor",
        paper="#000000",
        note="a template image is an alpha mask: black, tinted by the host",
    ),
}

#: The one role whose spellings the raster proves against a field: the mark red.
MARK_RED = "brand"


def hex_for(role: str) -> str:
    """The concrete build spelling of `role`, for the rasters."""
    return ROLES[role].hex


def token_for(role: str) -> str:
    """The property (or `currentColor`) the in-app vector names for `role`."""
    return ROLES[role].token


def paper_hex_for(role: str) -> str:
    """The paper spelling of `role`, for the surfaces that render on the light ground."""
    return ROLES[role].paper


def roles() -> tuple[str, ...]:
    """Every role name, for the bridge test and the checks that walk them."""
    return tuple(ROLES)
