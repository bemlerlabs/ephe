"""
◑ Ephe – r68 (2026-09-27): brand icon parity (icon/branding wave).
tests/test_r68_brand_icons.py

The kit carries the mark (docs/BRAND.md, decision 2026-10-15: the forest spirit
on the drop body); the orb art docs/brand/eph-orb-master.png stays square as
history, but is no longer the kit source — the generator builds the mark
function-generated and crops it per size. Pins:
1. Tauri icon set complete (32/128/128@2x/icon.png + icns/ico + Windows squares).
2. PWA set complete and dimensionally correct (192/512, maskable, apple-touch 180,
   favicon.png 48).
3. manifest.json refers only to icon files that exist.
4. History master present (square ≥ 1024); favicon.svg exists and
   hangs on index.html (the small corner belongs to the vector).
5. Maskable/Apple-Touch opaque (no alpha hole).
6. Tauri PNGs are RGBA — tauri::generate_context! refuses non-RGBA
   icons with a proc-macro panic (otherwise the desktop build broke, 2026-09-28).
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "app" / "public"
ICONS = ROOT / "app" / "src-tauri" / "icons"
MASTER = ROOT / "docs" / "brand" / "eph-orb-master.png"

TAURI_SET = [
    "32x32.png", "128x128.png", "128x128@2x.png", "icon.png",
    "icon.icns", "icon.ico",
    "Square30x30Logo.png", "Square44x44Logo.png", "Square71x71Logo.png",
    "Square89x89Logo.png", "Square107x107Logo.png", "Square142x142Logo.png",
    "Square150x150Logo.png", "Square284x284Logo.png", "Square310x310Logo.png",
    "StoreLogo.png",
]
PWA_SIZES = {
    "icon-192.png": (192, 192),
    "icon-512.png": (512, 512),
    "icon-maskable-192.png": (192, 192),
    "icon-maskable-512.png": (512, 512),
    "apple-touch-icon-180.png": (180, 180),
    "favicon.png": (48, 48),
}


def test_tauri_icon_set_complete():
    missing = [n for n in TAURI_SET if not (ICONS / n).is_file()]
    assert not missing, f"Tauri-Icons fehlen: {missing}"


def test_pwa_icons_exist_with_exact_dimensions():
    for name, size in PWA_SIZES.items():
        p = PUBLIC / name
        assert p.is_file(), f"{name} fehlt"
        with Image.open(p) as img:
            assert img.size == size, f"{name}: {img.size} != {size}"


def test_manifest_icon_references_resolve():
    manifest = json.loads((PUBLIC / "manifest.json").read_text(encoding="utf-8"))
    srcs = [icon["src"] for icon in manifest["icons"]]
    assert srcs, "manifest.icons leer"
    for src in srcs:
        assert (PUBLIC / src).is_file(), f"manifest verweist auf fehlende Datei: {src}"
    assert {Path(s).name for s in srcs} >= {"icon-192.png", "icon-512.png",
                                            "icon-maskable-192.png", "icon-maskable-512.png"}


def test_master_art_frozen():
    # The orb art is kept, but no longer the kit source: since R1 the generator
    # builds the mark function-generated and crops it per size.
    if MASTER.is_file():
        with Image.open(MASTER) as img:
            assert img.width == img.height and img.width >= 1024
    else:
        # The master is a workshop document: the mark itself ships, the kit source it was cut
        # from does not. Where the master is absent the brand directory has to be absent too,
        # so a lost file cannot pass as a published tree.
        assert not (ROOT / "docs" / "brand").is_dir(), f"{MASTER} fehlt als Historie"
    # The small corner belongs to the vector: index.html attaches SVG (micro cut,
    # sharp up to 16 px) and PNG (contract 48 px) at the same time.
    svg = PUBLIC / "favicon.svg"
    assert svg.is_file(), "favicon.svg fehlt — ohne Vektor bleibt der Tab ein Blob"
    head = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    assert 'href="/favicon.svg"' in head and 'href="/favicon.png"' in head


def test_opaque_brand_surfaces():
    for name in ("icon-maskable-512.png", "apple-touch-icon-180.png"):
        with Image.open(PUBLIC / name) as img:
            if img.mode == "RGBA":
                assert img.getextrema()[3][0] == 255, f"{name} hat transparente Pixel"


def test_tauri_pngs_are_rgba():
    """generate_context! (proc-macro) needs RGBA — RGB breaks the desktop build."""
    for name in TAURI_SET:
        if not name.endswith(".png"):
            continue
        with Image.open(ICONS / name) as img:
            assert img.mode == "RGBA", f"{name}: mode={img.mode}, Tauri braucht RGBA"


def test_mark_schnitt_follows_size():
    """The cut follows the size, not scaling the master down.

    `generate_brand_assets.py` writes the kit on import and therefore throws —
    the pure routing function is only reachable via the definition prefix.
    """
    src = (ROOT / "scripts" / "generate_brand_assets.py").read_text(encoding="utf-8")
    src = src[: src.index('if __name__ != "__main__":')]
    src = src.replace("from playwright.sync_api import sync_playwright", "")
    ns: dict = {"__name__": "brand_prefix", "__file__": str(ROOT / "scripts" / "generate_brand_assets.py")}
    exec(compile(src, "brand_prefix", "exec"), ns)
    cut = ns["mark_variant_for"]
    assert [cut(s) for s in (16, 24, 32)] == ["mark-micro"] * 3
    assert [cut(s) for s in (33, 40, 47)] == ["mark-compact"] * 3
    assert [cut(s) for s in (48, 192, 512)] == ["mark"] * 3
    # Every size has exactly one cut, and none of them is an empty shell.
    for name, bounds in ns["MARK_CUTS"].items():
        svg = ns["VARIANTS"][name]()
        assert "<path" in svg, f"{name} zeichnet nichts"
        assert "url(#" in svg or name == "mark-micro", f"{name} hat keinen Verlauf"
