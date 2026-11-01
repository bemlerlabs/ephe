"""Cut the paper moth out of its white sheet, by measurement.

The bee's large rungs came from a rendered 3D actor, cut out with its background
gone. The moth owner reference (`paper-moth.webp`) is photographed on a plain
white sheet, so the cut is the same problem: recover, per pixel, how much of the
pixel is the moth and how much is the sheet, and hand the kit a clean straight-
alpha master.

The reference ships its own matte (61 % of the file is fully transparent), so
that matte is the one that is used — a second guess would only move a correct
edge. What the cut adds is what a stored matte cannot be trusted for:

* the composite model `C = a·F + (1-a)·B` is still solved where the source has no
  alpha, `a = 1 - min_c(C_c / B_c)` in linear light, and the colour is unmixed
  out of the sheet `F = (C - (1-a)·B)/a` — that is what removes a white fringe,
  which a threshold cut keeps as a halo on a dark tile;
* matte noise below 6 % is dropped rather than feathered into a grey film;
* the edge is feathered by 0.6 px, so a hand-cut contour does not stair-step at
  512 px.

Writes `docs/media/paper-moth-master.png` (1024 square, transparent, the moth
floating in the middle) and a proof sheet at `docs/media/paper-moth-cut.png`
(checkerboard, tile ground, and the edge measurements the cut is held to).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path.home() / "Downloads" / "paper-moth.webp"
MEDIA = ROOT / "docs" / "media"
MASTER = MEDIA / "paper-moth-master.png"
PROOF = MEDIA / "paper-moth-cut.png"

SIZE = 1024
FIT = 0.94
RING = 6
#: Below this the pixel is sheet noise, above it the pixel is the moth's own paper.
FLOOR = 0.06
CEIL = 0.97


def _linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def _srgb(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def _background(rgb: np.ndarray) -> np.ndarray:
    ring = np.concatenate([
        rgb[:RING].reshape(-1, 3), rgb[-RING:].reshape(-1, 3),
        rgb[:, :RING].reshape(-1, 3), rgb[:, -RING:].reshape(-1, 3),
    ])
    return np.median(ring, axis=0)


def _source(source: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Colour in sRGB 0..1, the matte the cut starts from, and the sheet it came on."""
    with Image.open(source) as image:
        has_alpha = image.mode in ("RGBA", "LA", "P")
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float64) / 255.0
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3]
    if has_alpha and (alpha == 0.0).mean() > 0.02:
        return rgb, alpha, None
    sheet = _background(rgb)
    b = np.maximum(_linear(sheet), 1e-5)
    c = _linear(rgb)
    return rgb, np.clip(1.0 - (c / b).min(axis=2), 0.0, 1.0), sheet


def cut(source: Path) -> tuple[Image.Image, dict[str, float]]:
    rgb, alpha, sheet = _source(source)
    b_srgb = sheet if sheet is not None else _background(rgb)
    alpha = np.where(alpha < FLOOR, 0.0, np.where(alpha > CEIL, 1.0, alpha))

    if sheet is not None:
        # Unmix the sheet out of the colour: a matte cut by alpha alone keeps the
        # sheet's light in every edge pixel.
        b = np.maximum(_linear(sheet), 1e-5)
        safe = np.maximum(alpha, 1e-3)[:, :, None]
        fg = np.clip(_srgb((_linear(rgb) - (1.0 - safe) * b) / safe), 0.0, 1.0)
    else:
        fg = rgb
    fg = np.where(alpha[:, :, None] > 0.0, fg, 0.0)

    matte = Image.fromarray((alpha * 255).astype(np.uint8), mode="L")
    matte = matte.filter(ImageFilter.GaussianBlur(0.6))
    alpha = np.asarray(matte, dtype=np.float64) / 255.0

    out = np.dstack([fg * 255.0, alpha * 255.0]).astype(np.uint8)
    image = Image.fromarray(out, mode="RGBA")

    box = image.getchannel("A").point(lambda v: 255 if v > 5 else 0).getbbox()
    assert box, "the reference produced an empty matte"
    image = image.crop(box)

    scale = min(SIZE * FIT / image.width, SIZE * FIT / image.height)
    image = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # Icons read level when the mass sits a touch above the middle.
    x = (SIZE - image.width) // 2
    y = int((SIZE - image.height) / 2 - SIZE * 0.01)
    canvas.alpha_composite(image, (x, y))
    return canvas, _measure(canvas, b_srgb)


def _measure(image: Image.Image, background: np.ndarray) -> dict[str, float]:
    """The two numbers an extracted matte is held to, plus what it covers."""
    px = np.asarray(image, dtype=np.float64)
    alpha = px[:, :, 3] / 255.0
    rgb = px[:, :, :3] / 255.0
    edge = (alpha > 0.25) & (alpha < 0.75)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    # A sheet fringe is neutral and bright; paper cream is warm and darker.
    fringe = edge & (chroma < 0.035) & (luma > 0.72)
    pixels = float(alpha.size)
    return {
        "coverage": round(float((alpha > 0.5).sum()) / pixels, 4),
        "edge_share": round(float(edge.sum()) / pixels, 4),
        "fringe_share_of_edge": round(float(fringe.sum()) / max(1, edge.sum()), 4),
        "background": [round(float(v), 4) for v in background],
    }


def proof(master: Image.Image) -> None:
    tile = 300
    sheet = Image.new("RGB", (tile * 3, tile), "#0b0b0b")
    board = Image.new("RGB", (tile, tile), "#d8d8d8")
    draw = ImageDraw.Draw(board)
    for cy in range(0, tile, 20):
        for cx in range(0, tile, 20):
            if (cx // 20 + cy // 20) % 2:
                draw.rectangle((cx, cy, cx + 19, cy + 19), fill="#b8b8b8")
    sheet.paste(board, (0, 0))
    sheet.paste(Image.new("RGB", (tile, tile), "#121212"), (tile, 0))
    sheet.paste(Image.new("RGB", (tile, tile), "#F0F0E6"), (tile * 2, 0))
    icon = master.resize((tile, tile), Image.LANCZOS)
    for slot in range(3):
        sheet.paste(icon, (slot * tile, 0), icon)
    sheet.save(PROOF)


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"missing reference: {SOURCE}")
    MEDIA.mkdir(parents=True, exist_ok=True)
    master, measured = cut(SOURCE)
    master.save(MASTER)
    proof(master)
    print(json.dumps({"master": str(MASTER.relative_to(ROOT)), "size": master.size, **measured},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
