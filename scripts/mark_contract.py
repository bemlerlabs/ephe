"""What the mark's own files have to satisfy before the kit ships.

`app/src/assets/` is the surface's art: `mark.svg` inlines into `EpheMark` and
`mark-mono.svg` is the template cut. Nothing used to look at that directory, the
vector carried literal hexes, and the icon kit painted the paper red on a
near-black field. The checks below are the contract that stops each of those:

* reach — every `app/src/assets/*.svg` is in the set a scanner reads, and the
  directory carries the mark the component inlines.
* provenance — a mark vector paints no literal; `var()` and `currentColor` are how
  one asset serves two themes.
* contrast — the mark red against the ground of its own theme, floor 4.5:1.
* the template cut — it exists as a vector and as a raster, and the raster is one
  visible plane after a 16 px resample.
* geometry — every cut's silhouette mass centre sits on one shared optical axis.
* one statement — MARK_CUTS holds the bands, and the prose that names one agrees.

`scripts/asset_check.py` calls these; `tests/test_mark_roles_and_template.py`
proves each by breaking a planted copy.
"""
from __future__ import annotations

import re
from pathlib import Path

from brand_geometry import silhouette_centre
from theme_contrast import THEMES, contrast, resolved, rgb_of, theme_tables

#: The in-app vector family and the template raster, all written by
#: `scripts/generate_brand_assets.py`. The names are the contract the generator and
#: the checks share.
MARK_VECTOR = "app/src/assets/mark.svg"
TEMPLATE_VECTOR = "app/src/assets/mark-mono.svg"
TEMPLATE_RASTER = "tray-mono.png"
#: A template image is one plane by construction, so the 16 px contrast proof
#: cannot judge it; the template check below measures it instead.
TEMPLATE_RASTERS = (TEMPLATE_RASTER,)

#: Paint attributes that carry a colour outright. The in-app vector reaches its
#: colour through `var()` or `currentColor`, so every entry here is a finding.
LITERAL_PAINT = re.compile(
    r'(?:fill|stroke|stop-color)="(#[0-9a-fA-F]{3,8}|rgba?\([^"]*\)|hsla?\([^"]*\))"')
STOP_COLOR = re.compile(r'stop-color="([^"]+)"')
GRADIENT = re.compile(r"<(?:linear|radial)Gradient[^>]*>(.*?)</(?:linear|radial)Gradient>", re.S)
FLAT_FILL = re.compile(r'fill="(var\(--[a-zA-Z0-9-]+\)|#[0-9a-fA-F]{3,8})"')
VAR_LINK = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)\s*\)")

#: The mark red against the field of its theme. Measured on this tree 2026-10-15:
#: #E8543F on the ink ground #15120F is 5.13:1 and #B52E21 on paper #F0F0E6 is
#: 5.42:1, while the frozen literal #d83828 measured 4.01:1 on the ink ground —
#: under the floor, which is why the shipped icons stopped reading as the brand.
MARK_RED_TOKEN = "--color-firefly"
MARK_FIELD_TOKEN = "--color-canvas"
MIN_MARK_CONTRAST = 4.5

#: The silhouette of every cut is centred on one vertical axis. The drops measure
#: x=256.0 and the micro cut's dome and belly circles share that centre, so a
#: tolerance of one emblem unit (0.2 % of the canvas) catches a cut that leans in
#: the title bar without failing on the lattice rounding.
OPTICAL_AXIS_X = 256.0
OPTICAL_AXIS_TOLERANCE = 1.0

#: A band stated in prose: a range with a dash, or a bound with an operator. The
#: generator docstrings, the TSX prop and the stylesheet comment may name a band,
#: and every number they name has to be a boundary of MARK_CUTS. Numbers below
#: this floor describe pixels (the apex tip, a bar's width) rather than a band.
BOUNDARY_CLAIM = re.compile(
    r"(?:(\d+)\s*[-–]\s*(\d+)|(<=|>=|<|>|≤|≥|from|up to|below|above)\s*(\d+))\s*px")
BOUNDARY_FLOOR = 8


def rel(root: Path, path: Path) -> str:
    """A path as the message should name it."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def mark_vectors(root: Path) -> list[Path]:
    """The in-app vectors this tree carries."""
    directory = root / "app" / "src" / "assets"
    return sorted(directory.glob("*.svg")) if directory.is_dir() else []


def only_two(root: Path) -> bool:
    """Whether the tree ships the in-app vector family at all (a fixture does not)."""
    directory = root / "app" / "src" / "assets"
    return directory.is_dir() and (directory / "mark.svg").is_file()


def css_of(root: Path) -> str:
    """The shipped stylesheet, which is where the roles resolve."""
    sheet = root / "app" / "src" / "styles" / "globals.css"
    return sheet.read_text(encoding="utf-8") if sheet.is_file() else ""


def mark_red_reference(text: str) -> str | None:
    """The colour at the base of the drop: the outer stop of the first gradient.

    The drop is filled with a gradient, and its last stop is the red the mark
    stands on. A flat cut (the template) has no gradient and no red of its own.
    """
    gradient = GRADIENT.search(text)
    if gradient is not None:
        stops = STOP_COLOR.findall(gradient.group(1))
        if stops:
            return stops[-1]
    flat = FLAT_FILL.search(text)
    return flat.group(1) if flat is not None else None


def check_mark_reach(root: Path, svgs: list[Path]) -> list[str]:
    """Every in-app vector is in the scanned set, and the set carries the mark."""
    problems = []
    for path in mark_vectors(root):
        if path not in svgs:
            problems.append(f"{rel(root, path)}: sits in app/src/assets but outside "
                            f"the scanned set")
    directory = root / "app" / "src" / "assets"
    if directory.is_dir() and not (directory / "mark.svg").is_file():
        problems.append("app/src/assets carries no mark.svg: the surface inlines that file, "
                        "so an absent one leaves the mark without a source")
    return problems


def check_mark_provenance(root: Path, paths: list[Path]) -> list[str]:
    """A mark vector paints no literal colour, so both themes can tint one asset."""
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        literals = sorted({match.group(1).lower() for match in LITERAL_PAINT.finditer(text)})
        if literals:
            problems.append(f"{rel(root, path)}: paints the literal(s) {', '.join(literals)}; "
                            f"a mark vector reaches its colour through var()/currentColor")
        if "var(--" not in text and "currentColor" not in text:
            problems.append(f"{rel(root, path)}: names no role — no var() and no currentColor")
    return problems


def check_mark_contrast(root: Path, paths: list[Path]) -> tuple[list[str], list[str]]:
    """The mark red against the field of each theme, floor 4.5:1."""
    sheet = css_of(root)
    if not sheet:
        return [], []
    tables = theme_tables(sheet)
    problems: list[str] = []
    notes: list[str] = []
    for path in paths:
        reference = mark_red_reference(path.read_text(encoding="utf-8"))
        if reference is None or reference == "currentColor":
            notes.append(f"{rel(root, path)}: a flat cut — the host tints it, so no red "
                         f"of its own is measured")
            continue
        link = VAR_LINK.fullmatch(reference)
        for theme in THEMES:
            table = tables[theme]
            value = resolved(table, link.group(1)) if link else reference
            field = resolved(table, MARK_FIELD_TOKEN)
            red, ground = rgb_of(value or ""), rgb_of(field or "")
            if red is None or ground is None:
                problems.append(f"{rel(root, path)}: the mark red {reference} does not resolve "
                                f"in the {theme} theme")
                continue
            ratio = contrast(red, ground)
            notes.append(f"{rel(root, path)}: {theme} mark red {value} on {field} "
                         f"= {ratio:.2f}:1")
            if ratio < MIN_MARK_CONTRAST:
                problems.append(f"{rel(root, path)}: {theme} mark red {value} measures "
                                f"{ratio:.2f}:1 on {field}, floor is {MIN_MARK_CONTRAST}:1")
    return problems, notes


def visible_planes(path: Path, size: int) -> set[tuple[int, int, int]] | None:
    """The distinct visible RGB triples of a raster after a resample to `size`."""
    from PIL import Image  # noqa: PLC0415

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    try:
        with Image.open(path) as image:
            small = image.convert("RGBA").resize((size, size), resampling)
            raw = small.tobytes()
    except (OSError, ValueError):
        return None
    return {(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 4) if raw[i + 3] > 128}


def check_mark_template(root: Path, resample: int) -> tuple[list[str], list[str]]:
    """The template cut exists as a vector and as a raster, and carries one plane."""
    if not only_two(root):
        return [], []
    problems: list[str] = []
    notes: list[str] = []
    if not (root / TEMPLATE_VECTOR).is_file():
        problems.append(f"{TEMPLATE_VECTOR}: absent, so the mark has no monochrome cut to "
                        f"inline on a brand-tinted surface")
    raster = root / "app" / "src-tauri" / "icons" / TEMPLATE_RASTER
    if not raster.is_file():
        problems.append(f"app/src-tauri/icons/{TEMPLATE_RASTER}: absent, so the tray has no "
                        f"template image")
        return problems, notes
    planes = visible_planes(raster, resample)
    if planes is None:
        problems.append(f"{rel(root, raster)}: does not decode as an image")
    elif len(planes) > 1:
        problems.append(f"{rel(root, raster)}: {len(planes)} visible colour(s) after a "
                        f"{resample} px resample, a template carries one")
    else:
        notes.append(f"{rel(root, raster)}: one visible plane {sorted(planes)[0]} at "
                     f"{resample} px")
    return problems, notes


def generator_definitions(root: Path) -> dict | None:
    """The generator's definitions, without its write phase.

    The script writes the whole kit at import, so the CLI body would fire; the
    definition prefix is the part that answers routing and geometry questions.
    """
    path = root / "scripts" / "generate_brand_assets.py"
    if not path.is_file():
        return None
    src = path.read_text(encoding="utf-8")
    src = src[: src.index('if __name__ != "__main__":')]
    src = src.replace("from playwright.sync_api import sync_playwright", "")
    namespace: dict = {"__name__": "brand_prefix", "__file__": str(path)}
    exec(compile(src, "brand_prefix", "exec"), namespace)  # noqa: S102
    return namespace


def check_mark_geometry(root: Path) -> tuple[list[str], list[str]]:
    """Every cut's silhouette mass centre sits on the one shared optical axis."""
    if not only_two(root):
        return [], []
    namespace = generator_definitions(root)
    if namespace is None:
        return [], []
    problems: list[str] = []
    notes: list[str] = []
    for name in namespace["MARK_CUTS"]:
        for mono in (False, True):
            label = f"{name}{'+mono' if mono else ''}"
            body = namespace["_mark"](compact=name == "mark-compact",
                                      micro=name == "mark-micro", mono=mono)
            centre = silhouette_centre(body)
            if centre is None:
                problems.append(f"{label}: no silhouette geometry to measure")
                continue
            offset = abs(centre[0] - OPTICAL_AXIS_X)
            notes.append(f"{label}: silhouette mass centre x={centre[0]:.2f}, y={centre[1]:.2f}")
            if offset > OPTICAL_AXIS_TOLERANCE:
                problems.append(f"{label}: silhouette mass centre x={centre[0]:.2f} is "
                                f"{offset:.2f} off the optical axis at x={OPTICAL_AXIS_X:.0f} "
                                f"(tolerance {OPTICAL_AXIS_TOLERANCE})")
    return problems, notes


def boundary_claims(text: str) -> list[list[int]]:
    """Every size band `text` states: the numbers of a range or of a bound."""
    claims = []
    for match in BOUNDARY_CLAIM.finditer(text):
        low, high, _operator, single = match.groups()
        numbers = [int(number) for number in (low, high) if number is not None]
        if not numbers:
            numbers = [int(single)]
        if min(numbers) >= BOUNDARY_FLOOR:
            claims.append(numbers)
    return claims


def leading_comment(sheet: str, selector: str) -> str:
    """The comment block directly above the first `selector` rule."""
    at = sheet.find(selector)
    if at < 0:
        return ""
    above = sheet[:at]
    opened = above.rfind("/*")
    return above[opened:] if opened >= 0 else ""


def check_mark_boundaries(root: Path) -> tuple[list[str], list[str]]:
    """MARK_CUTS is the single statement; every prose band has to agree with it."""
    if not css_of(root):
        return [], []
    namespace = generator_definitions(root)
    if namespace is None:
        return [], []
    allowed = {number for low, high in namespace["MARK_CUTS"].values() for number in (low, high)
               if number is not None}
    sites = {
        "scripts/generate_brand_assets.py": root / "scripts" / "generate_brand_assets.py",
        "app/src/components/shell/EpheMark.tsx": (root / "app" / "src" / "components"
                                                  / "shell" / "EpheMark.tsx"),
        "app/src/styles/globals.css": root / "app" / "src" / "styles" / "globals.css",
    }
    problems: list[str] = []
    notes: list[str] = []
    for label, path in sites.items():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "globals.css":
            text = leading_comment(text, ".ephe-mark {")
        for numbers in boundary_claims(text):
            notes.append(f"{label}: states the band {numbers}")
            stray = [number for number in numbers if number not in allowed]
            if stray:
                problems.append(f"{label}: names {stray} px, which is no boundary of MARK_CUTS "
                                f"({sorted(allowed)}) — the table is the single statement")
    return problems, notes
