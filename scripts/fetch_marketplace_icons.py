"""Fetch the publisher marks the marketplace tiers name.

The featured tier lists servers whose publisher ships an icon at a URL the row
names; the curated tier lists servers whose launch line is an endpoint on the
publisher's own domain. Either way this script fetches that mark once, stores a
64 px PNG beside the tier's data and records where each file came from, so the
surface never calls a third party at render time and the provenance stays in the
tree.

Run from the repository root::

    python scripts/fetch_marketplace_icons.py            # the featured tier
    python scripts/fetch_marketplace_icons.py --curated  # the curated tier

The curated pass asks each publisher host for `favicon.ico`, then falls back to
the `rel="icon"` link on its homepage, and refuses any mark above 8 KB. The
output is committed; a network failure leaves the previous file in place.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import catalog_discover  # noqa: E402

FEATURED = ROOT / "marketplace" / "featured.json"
CURATED = ROOT / "marketplace" / "registry-curated.json"
ICON_DIR = ROOT / "marketplace" / "icons" / "providers"
SOURCES = ICON_DIR / "SOURCES.json"
SIZE = 64
TIMEOUT_S = 20
USER_AGENT = "Ephe-Icon-Fetch/1.0"
#: A curated mark is a small tile beside a listing; anything the resize cannot fit
#: under this budget is a logo the shelf should not carry.
MAX_ICON_BYTES = 8192
#: One fetch run may add this much to the tree; past it the pass reports and stops
#: short of a commit rather than shrinking the budget to fit.
MAX_RUN_BYTES = 1_000_000
#: ~260 hosts over a shared pool finishes in minutes; a wider pool only invites a
#: publisher to see a burst it would rather not answer.
WORKERS = 8

_NOTE = (
    "Vendor icons, fetched from the publisher's own domain as brand identification. "
    "Regenerate with scripts/fetch_marketplace_icons.py."
)


def _fetch(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
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


def _load_sources() -> dict[str, dict[str, str]]:
    if not SOURCES.exists():
        return {}
    try:
        return dict(json.loads(SOURCES.read_text(encoding="utf-8")).get("icons", {}))
    except (OSError, ValueError):
        return {}


def _write_sources(sources: dict[str, dict[str, str]]) -> None:
    SOURCES.write_text(
        json.dumps({"note": _NOTE, "icons": sources}, indent=2) + "\n",
        encoding="utf-8",
    )


def _record(png: bytes, url: str) -> dict[str, str]:
    return {
        "source": url,
        "fetched": date.today().isoformat(),
        "sha256": hashlib.sha256(png).hexdigest(),
    }


def _featured_slugs() -> set[str]:
    try:
        entries = json.loads(FEATURED.read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError):
        return set()
    return {str(entry.get("icon") or "").strip() for entry in entries if entry.get("icon")}


def run_featured() -> int:
    featured = json.loads(FEATURED.read_text(encoding="utf-8"))["entries"]
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    previous = _load_sources()
    sources = dict(previous)
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
                sources[slug] = previous.get(slug) or {"source": url, "stale": "kept"}
            else:
                print(f"miss  {slug:<12} {url}")
            continue
        target.write_bytes(png)
        sources[slug] = _record(png, url)
        fetched += 1
        print(f"ok    {slug:<12} {len(png):>5} B  {url}")
    _write_sources(sources)
    print(f"{fetched}/{len(featured)} icons written")
    return 0 if fetched or sources else 1


_ICON_REL = re.compile(r"""rel\s*=\s*["']([^"']*)["']""", re.I)
_ICON_HREF = re.compile(r"""href\s*=\s*["']([^"']*)["']""", re.I)
_ICON_KINDS = {"icon", "apple-touch-icon", "shortcut", "fluid-icon", "mask-icon"}


def _parse_icon_href(page: str, host: str) -> str:
    """The first publisher-hosted icon href on a homepage, or "" when there is none.

    A relative href resolves against `https://<host>/`; a link to another domain is
    refused, so the mark stays the publisher's own rather than a CDN's."""
    base = f"https://{host}/"
    for tag in re.finditer(r"<link\b[^>]*>", page, re.I):
        attrs = tag.group(0)
        rel = _ICON_REL.search(attrs)
        href = _ICON_HREF.search(attrs)
        if not rel or not href:
            continue
        kinds = rel.group(1).lower().split()
        if "stylesheet" in kinds or not any(kind in _ICON_KINDS for kind in kinds):
            continue
        url = urllib.parse.urljoin(base, html.unescape(href.group(1)).strip())
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() != host.lower():
            continue
        return url
    return ""


def _accept(png: bytes | None) -> bool:
    return png is not None and 0 < len(png) <= MAX_ICON_BYTES


def _png_from(url: str) -> tuple[bytes, str] | None:
    raw = _fetch(url)
    if not raw:
        return None
    made = _png(raw)
    if not _accept(made):
        return None
    return made, url


def _resolve_icon(host: str) -> tuple[bytes, str] | None:
    """The publisher's mark for one host: the predictable favicon, then the homepage.

    A host that refuses, times out, 404s or ships nothing the resize accepts answers
    None and the slug simply gets no file."""
    got = _png_from(f"https://{host}/favicon.ico")
    if got:
        return got
    page = _fetch(f"https://{host}/")
    if not page:
        return None
    href = _parse_icon_href(page.decode("utf-8", "ignore"), host)
    if not href:
        return None
    return _png_from(href)


def curated_targets(entries: list[dict]) -> dict[str, str]:
    """One publisher host per curated icon slug, first by name when hosts collide.

    Distinct hosts fold to the same slug — a `www.` variant, or two long hosts cut to
    the length cap — and only one PNG stands behind that slug, so the pass keeps the
    alphabetically first host and no row steals another's file."""
    by_slug: dict[str, str] = {}
    for row in entries:
        hint = str(row.get("install_hint") or "")
        host = catalog_discover.icon_host(hint)
        slug = catalog_discover.icon_slug(hint)
        if not host or not slug:
            continue
        current = by_slug.get(slug)
        if current is None or host < current:
            by_slug[slug] = host
    return by_slug


def run_curated() -> int:
    try:
        entries = json.loads(CURATED.read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError) as exc:
        print(f"curated: {CURATED} unreadable: {exc}")
        return 1
    targets = curated_targets(entries)
    owned = _featured_slugs()
    sources = _load_sources()
    written = missed = skipped = 0
    new_bytes = 0
    ordered = sorted(targets.items())

    def work(item: tuple[str, str]):
        slug, host = item
        if slug in owned:
            return slug, host, None, "skip"
        got = _resolve_icon(host)
        return slug, host, got, "ok" if got else "miss"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for slug, host, got, status in pool.map(work, ordered):
            if status == "skip":
                skipped += 1
                print(f"skip  {slug:<44} owned by the featured tier")
                continue
            if status == "miss":
                missed += 1
                print(f"miss  {slug:<44} https://{host}/favicon.ico")
                continue
            png, url = got
            target = ICON_DIR / f"{slug}.png"
            fresh = not target.exists()
            target.write_bytes(png)
            sources[slug] = _record(png, url)
            written += 1
            if fresh:
                new_bytes += len(png)
            print(f"ok    {slug:<44} {len(png):>5} B  {url}")

    _write_sources(sources)
    print(
        f"curated: {len(targets)} host(s) -> {written} ok, {missed} miss, "
        f"{skipped} skip, {new_bytes} B new"
    )
    if new_bytes > MAX_RUN_BYTES:
        print(f"OVER BUDGET: {new_bytes} B exceeds the {MAX_RUN_BYTES} B run budget; do not commit")
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "--curated",
        action="store_true",
        help="fetch the curated tier's publisher hosts instead of the featured sources",
    )
    args = parser.parse_args(argv)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    return run_curated() if args.curated else run_featured()


if __name__ == "__main__":
    sys.exit(main())
