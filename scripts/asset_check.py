#!/usr/bin/env python3
"""The shipped icon and asset surface: references resolve, files decode, marks survive 16 px.

`docs/CI_HYBRID_CAPACITY_2026-10-11.md` rows 19 and 20 slot hermes' `icons-freshness-check.yml` and
`infographic-check.yml` here. The parity half already lives inside the tracked suite
(`tests/test_r68_brand_icons.py`: the Tauri set, the PWA sizes, manifest entries that exist, RGBA where
`tauri::generate_context!` panics otherwise) and this script does not repeat it. What nothing checks is
the three things below, which is why the leg is a job that names the failing asset rather than a second
copy of an existing assertion:

* **References resolve.** `app/public/manifest.json`, `app/index.html` and the `<image href>` inside the
  shipped SVGs point at paths; a renamed file leaves the reference behind and the install ships no icon.
* **Files are what their extension says.** PNG, ICO, ICNS and SVG headers read back, so a truncated
  write or a copy of the wrong format fails here rather than in a browser.
* **The mark is still there at 16 px.** Each icon is resampled to 16x16 and the surviving pixels must
  carry contrast. Measured 2026-10-11 on this tree, the weakest of the 20 icons sits at luminance spread
  180.9 with all 256 pixels visible under both Pillow 12.2.0 and the locked 12.3.0; the floor sits an
  order of magnitude below that, because an asset that renders blank, or washed to one flat colour, is a
  product defect no size assertion catches.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mark_contract  # noqa: E402  (path bootstrap above)

#: 16 px is a browser tab's favicon and the smallest Android launcher tile. The owner rule (2026-10-09)
#: is that a visual asset ships with a rendered proof across 16-256 px; this is the half of that which a
#: machine can decide without a browser.
PROOF_SIZE = 16
MIN_VISIBLE_PIXELS = 64
MIN_LUMINANCE_SPREAD = 20.0
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ICNS_MAGIC = b"icns"
ICO_MAGIC = b"\x00\x00\x01\x00"
HEADER_MAGIC = {"png": PNG_MAGIC, "ico": ICO_MAGIC, "icns": ICNS_MAGIC}
PWA_SET = {"favicon.png", "icon-192.png", "icon-512.png", "icon-maskable-192.png",
           "icon-maskable-512.png", "apple-touch-icon-180.png"}


class AssetError(RuntimeError):
    pass


class Surface:
    """One tree's asset paths, so a planted fixture is judged exactly as the repository is."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.public = root / "app" / "public"
        self.tauri_icons = root / "app" / "src-tauri" / "icons"
        self.src_assets = root / "app" / "src" / "assets"
        self.index_html = root / "app" / "index.html"
        self.manifest = self.public / "manifest.json"

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


def raster_assets(surface: Surface) -> list[Path]:
    public = sorted(p for p in surface.public.glob("*.png") if p.name in PWA_SET)
    missing = PWA_SET - {p.name for p in public}
    if missing:
        raise AssetError(f"app/public carries no {sorted(missing)}: the PWA icon set moved or vanished")
    return public + sorted(p for p in surface.tauri_icons.glob("*.png")
                           if p.name not in mark_contract.TEMPLATE_RASTERS)


def svg_assets(surface: Surface) -> list[Path]:
    """Every shipped vector, including the in-app art the surface inlines."""
    return sorted(list(surface.public.glob("*.svg")) + list(surface.tauri_icons.glob("*.svg"))
                  + list(surface.src_assets.glob("*.svg")))


def proof_at_16(surface: Surface, path: Path) -> tuple[int, float, float] | None:
    """Visible pixels, luminance spread and standard deviation after a 16 px resample.

    Pillow comes in here so the header and reference checks still answer on a machine without it; the
    project depends on Pillow already, so the leg installs nothing. Pixels are read off `tobytes()`
    because `getdata()` is deprecated in the pinned release and a warning per asset would bury the
    verdict line.
    """
    import statistics  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    try:
        with Image.open(path) as image:
            small = image.convert("RGBA").resize((PROOF_SIZE, PROOF_SIZE), resampling)
            raw = small.tobytes()
    except (OSError, ValueError):
        # A file whose bytes are not the format its extension claims is a finding the caller names, and
        # never an exception that ends the run with one message.
        return None
    rgba = [(raw[i], raw[i + 1], raw[i + 2], raw[i + 3]) for i in range(0, len(raw), 4)]
    visible = [(r, g, b) for r, g, b, a in rgba if a > 128]
    if not visible:
        return 0, 0.0, 0.0
    lums = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in visible]
    return len(visible), max(lums) - min(lums), statistics.pstdev(lums)


def check_headers(surface: Surface, paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        magic = HEADER_MAGIC.get(path.suffix.lstrip(".").lower())
        if magic is None:
            continue
        with path.open("rb") as handle:
            head = handle.read(len(magic))
        if head != magic:
            problems.append(f"{surface.rel(path)}: does not start with the {path.suffix} magic bytes")
    return problems


def check_svgs(surface: Surface, paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            problems.append(f"{surface.rel(path)}: XML does not parse ({exc})")
            continue
        if "viewBox" not in root.attrib:
            problems.append(f"{surface.rel(path)}: no viewBox, so it scales with its container")
    return problems


def referenced_paths(surface: Surface) -> list[tuple[str, str]]:
    """(referrer, target) for every asset the shipped surfaces name."""
    out: list[tuple[str, str]] = []
    data = json.loads(surface.manifest.read_text(encoding="utf-8"))
    for key in ("icons", "screenshots"):
        for entry in data.get(key, []):
            if entry.get("src"):
                out.append((surface.rel(surface.manifest), str(entry["src"])))

    html = surface.index_html.read_text(encoding="utf-8")
    for match in re.finditer(r'(?:href|src)="([^"]+\.(?:png|svg|ico|icns|webp|css|js|tsx?))"', html):
        out.append((surface.rel(surface.index_html), match.group(1)))

    for svg in svg_assets(surface):
        for match in re.finditer(r'<image[^>]+(?:href|xlink:href)="([^"]+)"',
                                 svg.read_text(encoding="utf-8")):
            out.append((surface.rel(svg), match.group(1)))
    return out


def candidates(surface: Surface, target: str) -> list[Path]:
    """Where a shipped reference is allowed to resolve to.

    `/favicon.svg` in `app/index.html` is Vite's public root, which is `app/public`; `/src/main.tsx` is
    a source path under `app/`. A bare name in `manifest.json` is relative to the manifest's own
    directory. A target that lands in none of them is the finding.
    """
    bare = target.lstrip("/")
    if target.startswith("/"):
        return [surface.public / bare, surface.root / "app" / bare, surface.root / bare]
    return [surface.public / target, surface.root / "app" / target, surface.root / target]


def resolve_references(surface: Surface, pairs: list[tuple[str, str]]) -> list[str]:
    problems = []
    for referrer, target in pairs:
        if target.startswith(("http://", "https://", "data:")):
            continue
        if not any(path.is_file() for path in candidates(surface, target)):
            problems.append(f"{referrer}: references {target}, which resolves to none of "
                            + ", ".join(surface.rel(c) for c in candidates(surface, target)))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="write the per-asset measurements here")
    parser.add_argument("--quiet", action="store_true", help="only the verdict line")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="the tree to judge")
    args = parser.parse_args(argv)
    surface = Surface(args.root)

    rasters = raster_assets(surface)
    svgs = svg_assets(surface)
    pairs = referenced_paths(surface)
    root = args.root
    vectors = mark_contract.mark_vectors(root)
    templates = sorted(p for p in surface.tauri_icons.glob("*.png")
                       if p.name in mark_contract.TEMPLATE_RASTERS)

    problems: list[str] = []
    notes: list[str] = []
    measurements: list[dict[str, float | str]] = []
    spreads: list[tuple[str, float]] = []
    for path in rasters:
        proof = proof_at_16(surface, path)
        if proof is None:
            problems.append(f"{surface.rel(path)}: does not decode as an image")
            continue
        visible, spread, deviation = proof
        name = surface.rel(path)
        measurements.append({
            "asset": name, "visible_pixels": visible,
            "luminance_spread": round(spread, 2), "luminance_stdev": round(deviation, 2),
        })
        spreads.append((name, spread))
        if visible < MIN_VISIBLE_PIXELS:
            problems.append(f"{surface.rel(path)}: {visible} visible pixel(s) at {PROOF_SIZE} px, "
                            f"floor is {MIN_VISIBLE_PIXELS}")
        elif spread < MIN_LUMINANCE_SPREAD:
            problems.append(f"{surface.rel(path)}: luminance spread {spread:.1f} at {PROOF_SIZE} px, "
                            f"floor is {MIN_LUMINANCE_SPREAD}")

    problems += check_headers(surface, rasters + svgs)
    problems += check_svgs(surface, svgs)
    problems += resolve_references(surface, pairs)
    problems += mark_contract.check_mark_reach(root, svgs)
    problems += mark_contract.check_mark_provenance(root, vectors)
    for check in (lambda: mark_contract.check_mark_contrast(root, vectors),
                  lambda: mark_contract.check_mark_template(root, PROOF_SIZE),
                  lambda: mark_contract.check_mark_geometry(root),
                  lambda: mark_contract.check_mark_boundaries(root)):
        found, recorded = check()
        problems += found
        notes += recorded

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"proof": measurements, "notes": notes,
                                         "problems": problems},
                                        indent=2, sort_keys=True) + "\n", encoding="utf-8")

    weakest = min(spreads, key=lambda item: item[1], default=None)
    if not args.quiet:
        for row in measurements:
            print(f"  {row['asset']}: {row['visible_pixels']} px visible, "
                  f"spread {row['luminance_spread']}, stdev {row['luminance_stdev']}")
        for note in notes:
            print(f"  {note}")
    import PIL  # noqa: PLC0415
    print(f"asset-check: {len(rasters)} raster asset(s), {len(svgs)} svg(s), "
          f"{len(templates)} template asset(s), {len(pairs)} reference(s) resolved, "
          f"{len(problems)} problem(s), Pillow {PIL.__version__}")
    if weakest and not args.quiet:
        print(f"  weakest at {PROOF_SIZE} px: {weakest[0]} spread {weakest[1]:.1f} "
              f"(floor {MIN_LUMINANCE_SPREAD})")
    for problem in problems:
        print(f"asset-check: FAIL {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (AssetError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"asset-check: FAIL {exc}")
        sys.exit(2)
