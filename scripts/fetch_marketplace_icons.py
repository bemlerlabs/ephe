"""Fetch the vendor icons named by the featured marketplace tier.

The featured tier lists servers whose publisher ships an icon on the publisher's
own domain. This script fetches that icon once, stores a 64 px PNG beside the
tier's data and records where each file came from, so the surface never calls a
third party at render time and the provenance stays in the tree.

Run from the repository root::

    python scripts/fetch_marketplace_icons.py

The output is committed; a network failure leaves the previous file in place.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FEATURED = ROOT / "marketplace" / "featured.json"
ICON_DIR = ROOT / "marketplace" / "icons" / "providers"
SOURCES = ICON_DIR / "SOURCES.json"
SIZE = 64
TIMEOUT_S = 20


def _fetch(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": "Ephe-Icon-Fetch/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return response.read()
    except OSError:
        return None


def _rasterize_svg(raw: bytes) -> bytes | None:
    """SVG needs a renderer; Quick Look is the one macOS always has."""
    import shutil
    import subprocess
    import tempfile

    tool = shutil.which("qlmanage")
    if tool is None:
        return None
    with tempfile.TemporaryDirectory() as work:
        source = Path(work) / "icon.svg"
        source.write_bytes(raw)
        done = subprocess.run(
            [tool, "-t", "-s", "128", "-o", work, str(source)],
            capture_output=True,
            check=False,
        )
        rendered = Path(work) / "icon.svg.png"
        if done.returncode != 0 or not rendered.exists():
            return None
        return rendered.read_bytes()


def _png(raw: bytes) -> bytes | None:
    if raw.lstrip()[:4] == b"<svg" or b"<svg" in raw[:400]:
        raw = _rasterize_svg(raw)
        if raw is None:
            return None
    try:
        image = Image.open(io.BytesIO(raw))
        image = image.convert("RGBA")
        image.thumbnail((SIZE, SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2), image)
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except (OSError, ValueError):
        return None


def main() -> int:
    featured = json.loads(FEATURED.read_text(encoding="utf-8"))["entries"]
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    previous = {}
    if SOURCES.exists():
        previous = json.loads(SOURCES.read_text(encoding="utf-8")).get("icons", {})
    sources: dict[str, dict[str, str]] = {}
    fetched = 0
    for entry in featured:
        slug = str(entry.get("icon") or "").strip()
        url = str(entry.get("icon_source") or "").strip()
        if not slug or not url:
            continue
        target = ICON_DIR / f"{slug}.png"
        raw = _fetch(url)
        png = _png(raw) if raw else None
        if png is None:
            if target.exists():
                sources[slug] = previous.get(slug, {"source": url, "stale": "kept"})
            else:
                print(f"miss  {slug:<12} {url}")
            continue
        target.write_bytes(png)
        sources[slug] = {
            "source": url,
            "fetched": date.today().isoformat(),
            "sha256": hashlib.sha256(png).hexdigest(),
        }
        fetched += 1
        print(f"ok    {slug:<12} {len(png):>5} B  {url}")
    SOURCES.write_text(
        json.dumps(
            {
                "note": "Vendor icons, fetched from the publisher's own domain as brand "
                "identification. Regenerate with scripts/fetch_marketplace_icons.py.",
                "icons": sources,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{fetched}/{len(featured)} icons written")
    return 0 if fetched or sources else 1


if __name__ == "__main__":
    sys.exit(main())
