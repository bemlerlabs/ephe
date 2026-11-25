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
        note="the shade side of a fold, where the sheet turns away from the light",
    ),
    "figure_paper_body": Role(
        name="figure_paper_body",
        hex="#C8B591",
        token="--color-figure-paper-body",
        paper="#C8B591",
        note="the rolled slip that is the body, a shade under the sheet",
    ),
    "figure_cream": Role(
        name="figure_cream",
        hex="#F7F0E0",
        token="--color-figure-cream",
        paper="#F7F0E0",
        note="the hot core of the scene fire under the being (globals.css .ephe-scene-core)",
    ),
    "figure_head_shadow": Role(
        name="figure_head_shadow",
        hex="#120F0E",
        token="--color-figure-head-shadow",
        paper="#120F0E",
        note="the app-icon square the rendered hero sits on (shell/HeroMark.css)",
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
