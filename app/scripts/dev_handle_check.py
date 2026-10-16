#!/usr/bin/env python3
"""The dev store handle must not ship: no served script in dist/ may assign `window.__epheStore`.

`src/store/chatStore.ts` assigns `window.__epheStore` under `import.meta.env.DEV`
so the fifteen Playwright specs that seed real state through it can run against a
Vite dev server. `import.meta.env.DEV` is `false` in a production build, so the
branch is dead there and the assignment never reaches the bundle — which is the
whole reason the handle is allowed to exist: a writable store on the `window` of
a shipped build puts every action, the sandbox-approval ones included, within
reach of any script in the page (register #68).

"Never reaches the bundle" is a claim about a build artefact, so it is checked on
the artefact: `pnpm run build` writes dist/, and this walks every served script in
it and fails when the assignment is there. Two other checks keep the answer from
being vacuously clean — the pattern is first matched against the real
`src/store/chatStore.ts`, and the scanned set must contain a file that carries the
store's own state keys, so an empty walk or a renamed chunk cannot pass quietly.

The `.js.map` files are reported, not failed. A source map carries the source
*text*, so the property name appears in it; a page script can fetch the map and
read the string, and that is not a capability — it holds no store object and no
`setState`.

Usage:  python3 scripts/dev_handle_check.py [dist_dir]
Exit 0 when no served script assigns the handle, 1 when one does, 2 when dist/ is
missing or the scan cannot be trusted.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# The name in each assignment shape a refactor could take — `__epheStore =`,
# `window['__epheStore'] =`, `window["__epheStore"] =` — but not a `__epheStore?:`
# annotation and not a `==`/`===` compare. (A `Reflect.set(window, '__epheStore', …)`
# would slip this; the source test's grep over src/ is the half that would see it.)
ASSIGN = re.compile(r"""__epheStore['"]?\]?\s*=(?!=)""")
# A ChatState key only the store defines: if it is in a served chunk, the store's
# module is in the scanned set.
STORE_MARK = "activeSessionId"
SERVED_SUFFIXES = (".js", ".html")
SOURCE = Path(__file__).resolve().parent.parent / "src" / "store" / "chatStore.ts"


def served_files(dist: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(dist.rglob("*")):
        # *.js.map ends in `.map`, so the served-list test does not catch it.
        if p.is_file() and p.name.endswith(SERVED_SUFFIXES):
            out.append(p)
    return out


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not dist.is_dir():
        print(f"dist dir not found: {dist} (run `npm run build` first)")
        return 2

    # Instrument check: the pattern must match the assignment in the source it is
    # meant to catch. A renamed property would otherwise turn this gate into a
    # green gate that looks for nothing.
    if not SOURCE.is_file():
        print(f"source not found: {SOURCE} (the instrument cannot be trusted)")
        return 2
    source_sites = len(ASSIGN.findall(SOURCE.read_text(encoding="utf8")))
    if source_sites != 1:
        print(f"instrument: {SOURCE} carries {source_sites} assignment sites, expected 1")
        return 2

    files = served_files(dist)
    js = [p for p in files if p.name.endswith(".js")]
    html = [p for p in files if p.name.endswith(".html")]
    if not js:
        print(f"no served .js found under {dist} (the scan cannot be trusted)")
        return 2

    hits: list[str] = []
    marked: list[str] = []
    total_bytes = 0
    for p in files:
        text = p.read_text(encoding="utf8", errors="ignore")
        total_bytes += len(text)
        rel = p.relative_to(dist)
        if p.name.endswith(".js") and STORE_MARK in text:
            marked.append(str(rel))
        for match in ASSIGN.finditer(text):
            start = max(0, match.start() - 60)
            hits.append(f"{rel}: …{text[start:match.end() + 60].strip()}…")

    if not marked:
        print(f"no served .js carries `{STORE_MARK}` — the store is not in the scanned set")
        return 2

    maps = [p for p in dist.rglob("*.js.map")]
    maps_with_name = [p for p in maps if "__epheStore" in p.read_text(encoding="utf8", errors="ignore")]

    # The map proves which chunk the store's source compiled into: its sibling
    # script is served to the browser, and that script may not carry the name at
    # all. This is the tight half — it names the file the handle would have
    # shipped in rather than trusting a tree-wide miss.
    named_siblings: list[str] = []
    for map_file in maps_with_name:
        sibling = map_file.with_suffix("").name
        rel = (map_file.parent / sibling).relative_to(dist)
        text = (map_file.parent / sibling).read_text(encoding="utf8", errors="ignore")
        if "__epheStore" in text:
            named_siblings.append(str(rel))

    print(f"dev-handle-check: dist = {dist}")
    print(f"  served scripts scanned : {len(js)} .js, {len(html)} .html, {total_bytes / 1024:.0f} KB")
    print(f"  instrument             : pattern matches {SOURCE.name} ({source_sites} site)")
    print(f"  store in scanned set   : {' '.join(marked)}")
    if maps_with_name:
        print(f"  map says the store is in: {' '.join(m.relative_to(dist).name for m in maps_with_name)}")
        print(f"  those scripts carry the name: {named_siblings or 'none'}")
    else:
        print("  source maps            : none carries the name — no map/sibling cross-check this run")

    if hits or named_siblings:
        print("dev-handle-check: FAIL — the handle reached a served file")
        for h in hits:
            print(f"  assignment: {h}")
        for s in named_siblings:
            print(f"  name in the served sibling of a map that carries it: {s}")
        return 1

    print("dev-handle-check: PASS — no served script assigns window.__epheStore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
