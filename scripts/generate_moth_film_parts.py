"""The film's moth, split into the parts the choreography animates.

The intro moves three pieces independently — left wing, right wing, body — and one
glow. The bee's parts were rendered separately; the moth comes out of one cut-out
master, so the parts are derived from it: the matte is cut at the body's own axis,
the widest column run near the middle of the alpha box, and each half keeps the
full canvas so a rotation turns around the wing root and not around its own box.

Writes, into `app/public/onboarding/`:
  paper-moth-actor.[png|webp]   the whole figure, for the hero slots
  paper-moth-wing-l.[png|webp]  everything left of the body axis
  paper-moth-wing-r.[png|webp]  everything right of it
  paper-moth-thread.[png|webp]  the crimson ties, the one red the film carries
  paper-moth-body.[png|webp]    the body strip, so a flap can turn the wings alone
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs" / "media" / "paper-moth-master.png"
OUT = ROOT / "app" / "public" / "onboarding"

#: A tie is crimson: red well above green, and dark enough not to be paper.
THREAD_RED = 1.35


def _alpha_box(alpha: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.where(alpha.max(axis=1) > 0.06)[0]
    cols = np.where(alpha.max(axis=0) > 0.06)[0]
    assert len(rows) and len(cols), "the master has no opaque pixels"
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def _body_axis(image: Image.Image) -> int:
    """The column where the body sits: the tallest opaque run near the middle."""
    alpha = np.asarray(image, dtype=np.float64)[:, :, 3] / 255.0
    x0, y0, x1, y1 = _alpha_box(alpha)
    middle = (x0 + x1) // 2
    band = alpha[:, middle - 4:middle + 5].max(axis=1) > 0.5
    runs, start = [], None
    for y, filled in enumerate(band):
        if filled and start is None:
            start = y
        elif not filled and start is not None:
            runs.append((start, y - start))
            start = None
    assert runs, "no body run on the middle column"
    return middle


def _crop(image: Image.Image) -> Image.Image:
    alpha = np.asarray(image, dtype=np.float64)[:, :, 3] / 255.0
    x0, y0, x1, y1 = _alpha_box(alpha)
    return image.crop((x0, y0, x1, y1))


def _masked(image: Image.Image, columns: slice) -> Image.Image:
    """A half on the master's own canvas: both halves then share one geometry, so a
    placement at 0/0/100%/100% lines them up instead of guessing per-crop offsets."""
    px = np.asarray(image, dtype=np.uint8).copy()
    px[:, columns, 3] = 0
    return Image.fromarray(px, mode="RGBA")


def _thread(image: Image.Image) -> Image.Image:
    """The crimson ties alone — the only red the figure carries."""
    px = np.asarray(image, dtype=np.float64)
    red, green, blue, alpha = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    tie = (alpha > 0) & (red > green * THREAD_RED) & (red > blue * THREAD_RED) & (alpha > 24)
    if not tie.any():
        raise SystemExit("the master carries no crimson thread to lift")
    out = np.zeros_like(px, dtype=np.uint8)
    out[tie] = px[tie].astype(np.uint8)
    return _crop(Image.fromarray(out, mode="RGBA"))


def _body(master: Image.Image, axis: int, half: int = 60) -> Image.Image:
    """The body strip around the axis, on the master's canvas for the same reason."""
    px = np.asarray(master, dtype=np.uint8).copy()
    px[:, : max(0, axis - half), 3] = 0
    px[:, axis + half :, 3] = 0
    return Image.fromarray(px, mode="RGBA")


def main() -> int:
    if not MASTER.is_file():
        raise SystemExit(f"missing master: {MASTER} (run scripts/extract_moth_master.py)")
    OUT.mkdir(parents=True, exist_ok=True)
    master = Image.open(MASTER).convert("RGBA")
    axis = _body_axis(master)

    parts = {
        "paper-moth-actor": master,
        "paper-moth-wing-l": _masked(master, slice(axis, master.width)),
        "paper-moth-wing-r": _masked(master, slice(0, axis)),
        "paper-moth-thread": _thread(master),
        "paper-moth-body": _body(master, axis),
    }
    written = []
    for name, image in parts.items():
        png = OUT / f"{name}.png"
        image.save(png)
        webp = OUT / f"{name}.webp"
        image.save(webp, format="WEBP", quality=92, method=6)
        written.append({"name": name, "size": image.size})
    print(json.dumps({"axis_x": axis, "parts": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
