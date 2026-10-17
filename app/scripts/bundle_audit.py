#!/usr/bin/env python3
"""Bundle size audit: initial vs lazy (route-split) gzip sizes from dist/.

DoD metric (Sprint2-F1): total initial bundle gzip (what the browser really
fetches on the first load: index.html + all statically reachable chunks +
HTML-linked CSS) < 500 KB. Lazy route chunks do NOT count against the budget,
because they are loaded on demand.

Usage:  python3 scripts/bundle_audit.py [dist_dir]
Exit 0 when the initial budget is met, otherwise exit 1.
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

BUDGET_KB = 500.0


def gzsize(p: Path) -> tuple[int, int]:
    d = p.read_bytes()
    return len(d), len(gzip.compress(d, 9))


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not dist.is_dir():
        print(f"dist dir not found: {dist} (run `npm run build` first)")
        return 2

    chunks: dict[str, dict] = {}
    for p in sorted((dist / "assets").glob("*.js")):
        raw, g = gzsize(p)
        chunks[p.name] = {"raw_kb": round(raw / 1024, 2), "gzip_kb": round(g / 1024, 2)}
    for p in sorted((dist / "assets").glob("*.css")):
        raw, g = gzsize(p)
        chunks[p.name] = {"raw_kb": round(raw / 1024, 2), "gzip_kb": round(g / 1024, 2), "css": True}

    # Static deps: `import ... from "./X"` / `export ... from "./X"` / bare `from "./X"`.
    # Dynamic deps (route code-splitting): `import("./X")` — on-demand, NOT initial.
    importers: dict[str, set[str]] = {}
    lazy_importers: dict[str, set[str]] = {}
    static_re = re.compile(r"""(?:^|[;&]\s*)(?:import|export)\s+(?:[\w*{},\s]+?\s+from\s+)?["']\./([\w-]+\.(?:js|css))["']""", re.M)
    dynamic_re = re.compile(r"""\bimport\s*\(\s*["']\./([\w-]+\.(?:js|css))["']\s*\)""")
    for name in chunks:
        if chunks[name].get("css"):
            importers[name] = set()
            lazy_importers[name] = set()
            continue
        text = (dist / "assets" / name).read_text(errors="ignore")
        importers[name] = set(static_re.findall(text))
        lazy_importers[name] = set(dynamic_re.findall(text))

    html = (dist / "index.html").read_text()
    html_refs = re.findall(r"""(?:src|href)=["'](?:/assets/|\./assets/)([\w.-]+)["']""", html)
    entry_js = [f for f in html_refs if f.endswith(".js")]

    visited: set[str] = set()
    stack = list(entry_js)
    while stack:
        n = stack.pop()
        if n in visited:
            continue
        visited.add(n)
        for d in importers.get(n, set()):
            if d not in visited:
                stack.append(d)

    css_initial = {f for f in html_refs if f.endswith(".css")}
    initial = visited | css_initial
    lazy = set(chunks) - initial

    def kb(names) -> float:
        return round(sum(chunks[n].get("gzip_kb", 0) for n in names), 2)

    rawkb = lambda names: round(sum(chunks[n].get("raw_kb", 0) for n in names), 2)

    print("INITIAL chunks (index.html + static import closure):")
    for n in sorted(initial):
        print(f"  {n:42s} raw={chunks[n]['raw_kb']:>8} kB  gzip={chunks[n]['gzip_kb']:>7} kB")
    print(f"INITIAL TOTAL: raw={rawkb(initial)} kB  gzip={kb(initial)} kB")
    print()
    print("LAZY chunks (route-split, on demand):")
    for n in sorted(lazy):
        print(f"  {n:42s} raw={chunks[n]['raw_kb']:>8} kB  gzip={chunks[n]['gzip_kb']:>7} kB")
    print(f"LAZY TOTAL:    raw={rawkb(lazy)} kB  gzip={kb(lazy)} kB")
    print(f"GRAND TOTAL:   raw={rawkb(set(chunks))} kB  gzip={kb(set(chunks))} kB")

    budget = kb(initial)
    ok = budget < BUDGET_KB
    print()
    print(f"Initial-Bundle gzip = {budget} kB  (Budget: < {BUDGET_KB:.0f} kB)  ->  {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
