#!/usr/bin/env python3
"""The swarm bee, rendered from the cut-out 3D actor.

The onboarding hero (`app/public/onboarding/bee-3d-hero.png`) is the hero frame's bee
with its wings and forehead flame; the same actor is the badge of the sub-agents that
work in parallel. The product mark is the paper moth and belongs to
`scripts/generate_brand_assets.py` — this script writes the swarm picture and no
product icon, so the two drawings cannot overwrite each other.

Writes `docs/media/swarm-bee-512.png`.
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
    path = MEDIA / "swarm-bee-512.png"
    _write(_tile(512, 0.10, True), path)
    report = {
        "source": str(ACTOR.relative_to(ROOT)),
        "files": [str(path.relative_to(ROOT))],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
