#!/usr/bin/env python3
"""The large app icons from the cut-out 3D bee.

The onboarding hero (`app/public/onboarding/bee-3d-hero.png`) is the hero frame's bee
with its wings and forehead flame. The vector rig stays the source for the 16–47 px cut,
the tray template and the in-app mark; from 48 px the app icons carry the rendered bee,
which is the look the owner asked the large icon to show.

Writes the PWA icons, the Tauri PNG ladder, `icon.icns`, `icon.ico` and
`docs/media/ephe-bee-512.png`. Run `scripts/generate_brand_assets.py` first — this script
replaces its large rasters and leaves the small ones alone.
"""
from __future__ import annotations

import io
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ACTOR = ROOT / "app/public/onboarding/bee-3d-hero.png"
PUBLIC = ROOT / "app/public"
TAURI = ROOT / "app/src-tauri/icons"
MEDIA = ROOT / "docs/media"

#: Sizes where the rendered bee replaces the vector: below 48 the cut is dust and the
#: ink red of the small cut is the surface the tests hold.
RENDERED_FROM = 48


def _actor() -> Image.Image:
    image = Image.open(ACTOR).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    assert bbox, "the actor has no opaque pixels"
    return image.crop(bbox)


def _tile(size: int, padding: float = 0.11, rounded: bool = True) -> Image.Image:
    # An opaque tile is the maskable/touch surface: no transparent corner may survive,
    # because the OS paints those icons on its own ground.
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if rounded else (11, 11, 11, 255))
    draw = ImageDraw.Draw(canvas)
    inset = max(1, round(size * 0.035)) if rounded else 0
    radius = round(size * 0.21) if rounded else 0
    draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=radius,
        fill=(11, 11, 11, 255),
    )
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        (size * 0.12, size * 0.08, size * 0.88, size * 0.84),
        fill=(255, 191, 71, 30),
    )
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(size * 0.06)))

    bee = _actor()
    box = round(size * (1 - 2 * padding))
    scale = min(box / bee.width, box / bee.height)
    bee = bee.resize((max(1, round(bee.width * scale)), max(1, round(bee.height * scale))), Image.LANCZOS)
    canvas.alpha_composite(bee, ((size - bee.width) // 2, (size - bee.height) // 2))
    return canvas


def _write(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main() -> int:
    if not ACTOR.is_file():
        raise SystemExit(f"missing actor: {ACTOR}")
    ladder = {
        PUBLIC / "icon-512.png": (512, 0.10, True),
        PUBLIC / "icon-192.png": (192, 0.10, True),
        PUBLIC / "apple-touch-icon-180.png": (180, 0.09, False),
        PUBLIC / "icon-maskable-512.png": (512, 0.16, False),
        PUBLIC / "icon-maskable-192.png": (192, 0.16, False),
        TAURI / "icon.png": (512, 0.10, True),
        TAURI / "128x128@2x.png": (256, 0.10, True),
        TAURI / "128x128.png": (128, 0.10, True),
        TAURI / "Square310x310Logo.png": (310, 0.10, True),
        TAURI / "Square284x284Logo.png": (284, 0.10, True),
        TAURI / "Square150x150Logo.png": (150, 0.10, True),
        TAURI / "Square142x142Logo.png": (142, 0.10, True),
        TAURI / "Square107x107Logo.png": (107, 0.10, True),
        TAURI / "Square89x89Logo.png": (89, 0.10, True),
        TAURI / "Square71x71Logo.png": (71, 0.10, True),
        TAURI / "StoreLogo.png": (50, 0.10, True),
        MEDIA / "ephe-bee-512.png": (512, 0.10, True),
    }
    for path, (size, padding, rounded) in ladder.items():
        _write(_tile(size, padding, rounded), path)

    # Windows .ico: every rung, the small ones from the vector raster the brand script
    # already wrote, the rendered ones from this ladder.
    ico_sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = []
    for size in ico_sizes:
        source = _tile(size, 0.10, True) if size >= RENDERED_FROM else Image.open(TAURI / "32x32.png").convert("RGBA").resize((size, size), Image.LANCZOS)
        frames.append(source)
    frames[-1].save(TAURI / "icon.ico", format="ICO", sizes=[(s, s) for s in ico_sizes])

    # macOS .icns through iconutil, which expects the iconset names.
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Ephe.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            base = _tile(size, 0.10, True) if size >= RENDERED_FROM else Image.open(TAURI / "32x32.png").convert("RGBA").resize((size, size), Image.LANCZOS)
            _write(base, iconset / f"icon_{size}x{size}.png")
            double = _tile(size * 2, 0.10, True) if size * 2 >= RENDERED_FROM else Image.open(TAURI / "32x32.png").convert("RGBA").resize((size * 2, size * 2), Image.LANCZOS)
            _write(double, iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(TAURI / "icon.icns")], check=True)

    report = {
        "source": str(ACTOR.relative_to(ROOT)),
        "rendered_from": RENDERED_FROM,
        "files": [str(p.relative_to(ROOT)) for p in ladder],
        "ico": str((TAURI / "icon.ico").relative_to(ROOT)),
        "icns": str((TAURI / "icon.icns").relative_to(ROOT)),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
