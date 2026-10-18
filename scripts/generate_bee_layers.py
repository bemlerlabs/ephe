#!/usr/bin/env python3
"""Extract the 2x Super-Resolved (2120x1504) 3D bee rig layers from scene-4-awakening.jpg.

Pipeline:
1. Apple Vision foreground mask + topological hole filling (binary_fill_holes) so translucent
   wing cells have zero holes while keeping the exact outer sub-pixel contour.
2. Exact anatomical shoulder seam separation (LEFT_WING_ZONE / RIGHT_WING_ZONE) so 100% of all
   four wings belong to wing-l / wing-r and zero wing stubs stick to the cheek on bee-3d-actor.
3. Local background color field estimation (distance_transform_edt + Gaussian smoothing) and
   true Foreground Color Decontamination: C_fg = (C - (1 - alpha) * C_bg) / alpha, removing all
   cold blue/teal forest background bleed from semi-transparent wing glass, fur, and flame edges.
4. Pure warm golden fire bloom extraction around the leaf-flame ears, floating crown flame, and
   stinger tip without dark forest blocks.
5. Premultiplied Lanczos-4 2x Super-Resolution (2120 x 1504, preserving the exact 1060:752 aspect
   ratio) with fine unsharp micro-contrast enhancement.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import (
    binary_erosion,
    binary_fill_holes,
    distance_transform_edt,
    gaussian_filter,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/public/onboarding/scene-4-awakening.jpg"
OUT = ROOT / "app/public/onboarding"
SWIFT = ROOT / "scripts/vision_cutout.swift"

HERO_BOX = (160, 0, 1220, 752)
FLAME_BOX = (640, 20, 744, 172)

LEFT_WING_ZONE = [
    (160, 130), (520, 130), (556, 255),
    (558, 276), (555, 300), (554, 320), (555, 340), (557, 360), (562, 380), (566, 396), (552, 420),
    (360, 460), (160, 460),
]
RIGHT_WING_ZONE = [
    (810, 296), (850, 240), (960, 140), (1220, 120),
    (1220, 470), (840, 440), (822, 414), (808, 382), (809, 355), (811, 325),
]


def _vision_cutout(source: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / "vision_cutout"
        out = Path(tmp) / "cutout.png"
        subprocess.run(["swiftc", "-O", str(SWIFT), "-o", str(binary)], check=True)
        subprocess.run([str(binary), str(source), str(out)], check=True, stdout=subprocess.DEVNULL)
        return Image.open(out).convert("RGBA")


def _polygon_mask(size: tuple[int, int], polygons: list[list[tuple[int, int]]]) -> Image.Image:
    scale = 2
    mask = Image.new("L", (size[0] * scale, size[1] * scale), 0)
    draw = ImageDraw.Draw(mask)
    for polygon in polygons:
        draw.polygon([(x * scale, y * scale) for x, y in polygon], fill=255)
    return mask.resize(size, Image.LANCZOS)


def _smoothstep(values: np.ndarray, low: float, high: float) -> np.ndarray:
    t = np.clip((values - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _flame_alpha(source: Image.Image) -> np.ndarray:
    rgb = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
    luminance = rgb[:, :, 0] * 0.2126 + rgb[:, :, 1] * 0.7152 + rgb[:, :, 2] * 0.0722
    alpha = np.zeros(luminance.shape, dtype=np.float32)
    left, top, right, bottom = FLAME_BOX
    crop = _smoothstep(luminance[top:bottom, left:right], 0.42, 0.78)
    crop[crop < 0.08] = 0.0
    reach = crop > 0.12
    labels = np.zeros(reach.shape, dtype=np.int32)
    best, best_area = 0, 0
    current = 0
    for y0, x0 in zip(*np.nonzero(reach)):
        if labels[y0, x0]:
            continue
        current += 1
        area = 0
        stack = [(y0, x0)]
        labels[y0, x0] = current
        while stack:
            y, x = stack.pop()
            area += 1
            for ny in range(max(0, y - 1), min(reach.shape[0], y + 2)):
                for nx in range(max(0, x - 1), min(reach.shape[1], x + 2)):
                    if reach[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        stack.append((ny, nx))
        if area > best_area:
            best, best_area = current, area
    keep = gaussian_filter((labels == best).astype(np.float32), sigma=1.5)
    crop = crop * np.clip(keep * 1.6, 0.0, 1.0)
    alpha[top:bottom, left:right] = crop
    return gaussian_filter(alpha, sigma=0.9)


def _extend_wing_root(c_rgb: np.ndarray, w_alpha: np.ndarray, direction: str, px: int = 12) -> tuple[np.ndarray, np.ndarray]:
    ext_rgb = c_rgb.copy()
    ext_a = w_alpha.copy()
    amber = np.array([0.88, 0.62, 0.30], dtype=np.float32)
    w_weight = np.clip(w_alpha / 0.5, 0.0, 1.0)[:, :, None]
    pure_wing_rgb = c_rgb * w_weight + amber * (1.0 - w_weight)
    for step in range(1, px + 1):
        decay = (1.0 - step / (px + 1)) * 0.88
        shift = step if direction == "right" else -step
        shifted_a = np.roll(w_alpha, shift, axis=1) * decay
        shifted_rgb = np.roll(pure_wing_rgb, shift, axis=1)
        replace = shifted_a > ext_a
        ext_a = np.where(replace, shifted_a, ext_a)
        ext_rgb = np.where(replace[:, :, None], shifted_rgb, ext_rgb)
    return ext_rgb, ext_a


def _upscale_2x_rgba(c_rgb: np.ndarray, a_mask: np.ndarray) -> Image.Image:
    l, t, r, b = HERO_BOX
    c_crop = c_rgb[t:b, l:r]
    a_crop = a_mask[t:b, l:r]
    ch, cw = a_crop.shape
    up_w, up_h = cw * 2, ch * 2
    premult = c_crop * a_crop[:, :, None]
    up_premult = cv2.resize(premult, (up_w, up_h), interpolation=cv2.INTER_LANCZOS4)
    up_a = np.clip(cv2.resize(a_crop, (up_w, up_h), interpolation=cv2.INTER_LANCZOS4), 0.0, 1.0)
    safe_a = np.maximum(up_a[:, :, None], 1e-4)
    up_rgb = np.where(up_a[:, :, None] > 1e-4, np.clip(up_premult / safe_a, 0.0, 1.0), 0.0)
    blur = cv2.GaussianBlur(up_rgb, (0, 0), sigmaX=1.0)
    up_rgb = np.clip(up_rgb + (up_rgb - blur) * 0.48, 0.0, 1.0)
    out = np.zeros((up_h, up_w, 4), dtype=np.uint8)
    out[:, :, :3] = np.clip(np.round(up_rgb * 255.0), 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(np.round(up_a * 255.0), 0, 255).astype(np.uint8)
    out[out[:, :, 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


def main() -> None:
    src = Image.open(SOURCE).convert("RGB")
    w, h = src.size
    rgb = np.asarray(src, dtype=np.float32) / 255.0

    v = _vision_cutout(SOURCE)
    va = np.asarray(v, dtype=np.float32)[:, :, 3] / 255.0
    filled = binary_fill_holes(va > 0.14).astype(np.float32)
    interior = binary_erosion(filled > 0.5, iterations=3)
    base_alpha = np.where(interior, 1.0, np.maximum(va, gaussian_filter(filled, sigma=1.1)))
    flame_a = _flame_alpha(src)

    wing_l_zone = gaussian_filter(np.asarray(_polygon_mask((w, h), [LEFT_WING_ZONE]), dtype=np.float32) / 255.0, sigma=0.9)
    wing_r_zone = gaussian_filter(np.asarray(_polygon_mask((w, h), [RIGHT_WING_ZONE]), dtype=np.float32) / 255.0, sigma=0.9)

    bg_mask = (base_alpha < 0.02) & (flame_a < 0.02)
    _, indices = distance_transform_edt(~bg_mask, return_indices=True)
    bg_field = rgb[indices[0], indices[1]]
    for c in range(3):
        bg_field[:, :, c] = gaussian_filter(bg_field[:, :, c], sigma=22.0)

    warmth = np.clip(rgb[:, :, 0] * 0.65 + rgb[:, :, 1] * 0.45 - rgb[:, :, 2] * 0.85, 0.0, 1.0)
    color_diff = np.linalg.norm(rgb - bg_field, axis=-1)
    wing_translucency = np.clip(0.66 + 0.34 * np.clip(warmth * 1.8 + color_diff * 0.7, 0.0, 1.0), 0.66, 1.0)

    wing_l_alpha = base_alpha * wing_l_zone * wing_translucency
    wing_r_alpha = base_alpha * wing_r_zone * wing_translucency

    wing_clear = np.clip(
        np.asarray(_polygon_mask((w, h), [LEFT_WING_ZONE, RIGHT_WING_ZONE]), dtype=np.float32) / 255.0,
        0.0,
        1.0,
    )
    body_alpha = base_alpha * (1.0 - gaussian_filter(wing_clear, sigma=0.8))

    dist_to_body = distance_transform_edt(body_alpha < 0.25)
    dist_to_flame = distance_transform_edt(flame_a < 0.20)
    warm_excess = np.clip((rgb[:, :, 0] - np.maximum(bg_field[:, :, 0], rgb[:, :, 2] * 0.92)) * 2.1, 0.0, 1.0)

    body_halo = gaussian_filter(warm_excess * np.exp(-dist_to_body / 7.5) * (body_alpha < 0.5), sigma=1.8) * 0.55
    flame_halo = gaussian_filter(warm_excess * np.exp(-dist_to_flame / 7.0) * (flame_a < 0.5), sigma=1.8) * 0.65

    core_alpha = np.clip(body_alpha + wing_l_alpha + wing_r_alpha + flame_a, 0.0, 1.0)
    total_halo = np.maximum(body_halo, flame_halo)

    safe_a = np.maximum(core_alpha[:, :, None], 0.18)
    fg = np.clip((rgb - (1.0 - core_alpha[:, :, None]) * bg_field) / safe_a, 0.0, 1.0)
    edge_w = np.clip((0.90 - core_alpha) / 0.90, 0.0, 1.0)[:, :, None] * (core_alpha > 0.0)[:, :, None]
    clean_rgb = rgb * (1.0 - edge_w * 0.82) + fg * (edge_w * 0.82)
    semi = (core_alpha < 0.78) & (core_alpha > 0.0)
    clean_rgb[:, :, 2] = np.where(semi, np.minimum(clean_rgb[:, :, 2], clean_rgb[:, :, 1] * 0.80), clean_rgb[:, :, 2])

    amber_glow = np.array([1.0, 0.70, 0.24], dtype=np.float32)
    halo_w = np.clip((total_halo - core_alpha * 0.6) / np.maximum(total_halo, 1e-4), 0.0, 1.0)[:, :, None] * (total_halo > 0.01)[:, :, None]
    clean_rgb = clean_rgb * (1.0 - halo_w) + amber_glow * halo_w

    body_with_halo = np.clip(np.maximum(body_alpha, body_halo), 0.0, 1.0) * (1.0 - np.clip(flame_a * 1.4, 0.0, 1.0))
    flame_with_halo = np.clip(np.maximum(flame_a, flame_halo), 0.0, 1.0)
    hero_alpha = np.clip(body_with_halo + wing_l_alpha + wing_r_alpha + flame_with_halo, 0.0, 1.0)

    xs = np.arange(w)[None, :]
    wl_base_rgb = clean_rgb.copy()
    seam_l = (xs > 542) & (wing_l_alpha > 0)
    dark_cheek = np.clip((wl_base_rgb[:, :, 2] - wl_base_rgb[:, :, 0] * 0.85) * 3.0, 0.0, 1.0)
    amber_vein = np.array([0.92, 0.68, 0.36], dtype=np.float32)
    wl_base_rgb = np.where(
        seam_l[:, :, None],
        wl_base_rgb * (1.0 - dark_cheek[:, :, None]) + amber_vein * dark_cheek[:, :, None],
        wl_base_rgb,
    )

    wl_rgb, wl_a = _extend_wing_root(wl_base_rgb, wing_l_alpha, direction="right", px=12)
    wr_rgb, wr_a = _extend_wing_root(clean_rgb, wing_r_alpha, direction="left", px=12)

    empty_2x = Image.new("RGBA", (2120, 1504), (0, 0, 0, 0))
    layers = {
        "hero": _upscale_2x_rgba(clean_rgb, hero_alpha),
        "actor": _upscale_2x_rgba(clean_rgb, body_with_halo),
        "wing_l": _upscale_2x_rgba(wl_rgb, wl_a),
        "wing_r": _upscale_2x_rgba(wr_rgb, wr_a),
        "flame": _upscale_2x_rgba(clean_rgb, flame_with_halo),
        "hand_l": empty_2x,
        "hand_r": empty_2x,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, layer in layers.items():
        stem = f"bee-3d-{name.replace('_', '-')}"
        layer.save(OUT / f"{stem}.png")
        layer.save(OUT / f"{stem}.webp", quality=95, method=6)
        print(f"{stem}: {layer.size}")


if __name__ == "__main__":
    main()
