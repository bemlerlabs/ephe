#!/usr/bin/env python3
"""The large rungs from the cut-out actor, the swarm picture from the bee.

Same mechanic the bee wave used: below 48 px the vector rig draws the mark, from
48 px the app icons carry the rendered actor, cut out of its sheet by measurement
(`scripts/extract_moth_master.py`). This script owns that upper ladder; the vector
cuts, the tab vector, the tray template and the in-app vectors belong to
`scripts/generate_brand_assets.py` — run that one first.

The bee is not gone: it is the badge of the sub-agents that work in parallel, and
its 3D actor writes `docs/media/swarm-bee-512.png`.

Writes the PWA rungs from 48 px up, the Tauri PNG ladder, the Windows squares,
`icon.icns`, `icon.ico`, and the swarm picture.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
MOTH = ROOT / "docs" / "media" / "paper-moth-master.png"
BEE = ROOT / "app" / "public" / "onboarding" / "bee-3d-hero.png"
PUBLIC = ROOT / "app" / "public"
TAURI = ROOT / "app" / "src-tauri" / "icons"
MEDIA = ROOT / "docs" / "media"

#: Sizes where the rendered actor replaces the vector: below 48 the figure's
#: detail is dust and the vector cut is the sharper drawing.
RENDERED_FROM = 48
GROUND = (11, 11, 11)


def _actor(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    assert bbox, f"{path.name} has no opaque pixels"
    return image.crop(bbox)


def _tile(actor: Image.Image, size: int, padding: float = 0.10,
          rounded: bool = True) -> Image.Image:
    """The actor floating on the brand ground: a warm glow behind it and a soft
    contact shadow under it, so it reads as a body above the field rather than a
    pasted rectangle."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if rounded else GROUND + (255,))
    draw = ImageDraw.Draw(canvas)
    inset = max(1, round(size * 0.035)) if rounded else 0
    radius = round(size * 0.21) if rounded else 0
    draw.rounded_rectangle((inset, inset, size - inset, size - inset), radius=radius,
                           fill=GROUND + (255,))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (size * 0.10, size * 0.06, size * 0.90, size * 0.86), fill=(255, 191, 71, 34))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(size * 0.07)))

    box = round(size * (1 - 2 * padding))
    scale = min(box / actor.width, box / actor.height)
    body = actor.resize((max(1, round(actor.width * scale)),
                         max(1, round(actor.height * scale))), Image.LANCZOS)

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        (size * 0.18, size * 0.72, size * 0.82, size * 0.94), fill=(0, 0, 0, 120))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(size * 0.05)))

    canvas.alpha_composite(body, ((size - body.width) // 2, (size - body.height) // 2))
    return canvas


def _write(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main() -> int:
    if not MOTH.is_file():
        raise SystemExit(f"missing cut-out actor: {MOTH} (run scripts/extract_moth_master.py)")
    moth = _actor(MOTH)
    ladder = {
        PUBLIC / "icon-512.png": (512, 0.09, True),
        PUBLIC / "icon-192.png": (192, 0.09, True),
        PUBLIC / "icon-maskable-512.png": (512, 0.16, False),
        PUBLIC / "icon-maskable-192.png": (192, 0.16, False),
        PUBLIC / "apple-touch-icon-180.png": (180, 0.09, False),
        PUBLIC / "favicon.png": (48, 0.09, True),
        TAURI / "icon.png": (512, 0.09, True),
        TAURI / "128x128@2x.png": (256, 0.09, True),
        TAURI / "128x128.png": (128, 0.09, True),
    }
    for name, size in (
        ("Square310x310Logo.png", 310), ("Square284x284Logo.png", 284),
        ("Square150x150Logo.png", 150), ("Square142x142Logo.png", 142),
        ("Square107x107Logo.png", 107), ("Square89x89Logo.png", 89),
        ("Square71x71Logo.png", 71), ("Square44x44Logo.png", 44),
        ("Square30x30Logo.png", 30), ("StoreLogo.png", 50),
    ):
        ladder[TAURI / name] = (size, 0.09, True)
    for path, (size, padding, rounded) in ladder.items():
        _write(_tile(moth, size, padding, rounded), path)

    # Windows .ico: the rendered rungs from this ladder, the small ones from the
    # vector raster the brand script already wrote.
    frames = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        source = (_tile(moth, size) if size >= RENDERED_FROM
                  else Image.open(TAURI / "32x32.png").convert("RGBA").resize((size, size),
                                                                              Image.LANCZOS))
        frames.append(source)
    frames[-1].save(TAURI / "icon.ico", format="ICO", sizes=[(s, s) for s in
                                                             (16, 24, 32, 48, 64, 128, 256)])

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Ephe.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale, tag in ((1, f"{size}x{size}"), (2, f"{size}x{size}@2x")):
                px = size * scale
                base = (_tile(moth, px) if px >= RENDERED_FROM
                        else Image.open(TAURI / "32x32.png").convert("RGBA").resize((px, px),
                                                                                    Image.LANCZOS))
                _write(base, iconset / f"icon_{tag}.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(TAURI / "icon.icns")],
                       check=True)

    files = [str(p.relative_to(ROOT)) for p in ladder]
    files += [str((TAURI / "icon.ico").relative_to(ROOT)), str((TAURI / "icon.icns").relative_to(ROOT))]

    if BEE.is_file():
        path = MEDIA / "swarm-bee-512.png"
        _write(_tile(_actor(BEE), 512), path)
        files.append(str(path.relative_to(ROOT)))

    print(json.dumps({"actor": str(MOTH.relative_to(ROOT)), "rendered_from": RENDERED_FROM,
                      "files": files}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
