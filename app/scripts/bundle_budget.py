#!/usr/bin/env python3
"""Per-chunk budget gate for the frontend JS/CSS chunks.

bundle_audit.py checks the aggregate initial gzip total (< 500 KB). That total
can hide a regression: one chunk doubling while a sibling shrinks keeps the sum
green. This gate measures every JS/CSS chunk in dist and holds each to a ceiling:
a chunk with a row in BUDGETS_GZIP_KB is held to that number, every other chunk
to SMALL_CHUNK_KB. A chunk that outgrows the small ceiling must earn its own row,
so no chunk ships unwatched.

Budgets are gzip kilobytes, measured from app/dist on the day they were set
(MEASURED_GZIP_KB below) with ~10% headroom. A budget is raised or lowered by
measuring again, never to make a red go away.

Usage:  python3 scripts/bundle_budget.py [dist_dir]
Exit 0 when every chunk is within its ceiling, 1 on any breach or a first-paint
chunk without a number (fail-closed: a main chunk must get a number).
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

# Every chunk with no row of its own is held to this ceiling (gzip kB). A chunk
# that grows past it fails until it earns a row, so small chunks are gated too.
SMALL_CHUNK_KB = 12.0

# Logical chunk key (name without the content hash, plus extension) -> gzip ceiling.
BUDGETS_GZIP_KB: dict[str, float] = {
    "index.js": 160.0,       # React 19 runtime + App shell, the entry chunk
    "ChatPage.js": 112.0,    # chat shell only — wave-3 split moved the panes out
    "AgentPanel.js": 118.0,  # W3-1: agent panel + xterm, its own lazy chunk
    "markdown.js": 136.0,    # react-markdown + rehype/remark, lazy
    "motion.js": 30.8,       # framer-motion core + domAnimation (2026-10-15: 48.0 before the `m` conversion)
    "ui-vendor.js": 40.0,    # lucide-react, i18next
    # tailwind output (2026-10-15: 42.0 before the font subsets were named).
    # Raised on 2026-10-18 for the model picker: its panel, filter chips, capability
    # chips and phone sheet are one new surface in the entry stylesheet, and the row
    # had been read against a catalog that predated it. Measured 23.05 kB gzip after
    # the trim that was owed anyway — `max-h-[26rem]` onto the `max-h-96` step, and
    # `max-h-full` in place of the `h-[100dvh]`/`max-h-[100dvh]` pair, where only the
    # second of the three was actually doing work against the dialog's own 90dvh.
    # 20.94 -> 23.05 is the picker; the row is the number, not the measurement.
    "index.css": 23.5,
    "app-vendor.js": 28.0,   # react-router, zustand, tanstack, clsx, cva
    "radix.js": 39.0,        # P1-8: 33 @radix-ui packages + @floating-ui + the tail
    "ui.js": 17.0,           # P1-8: src/components/ui/* (Dialog, Tabs, CommandPalette)
    "dates.js": 6.4,         # P1-8: date-fns + the de/en-US locale modules (2026-10-15: 9.0 before the format split)
    "dates-format.js": 3.0,  # 2026-10-15: `format()` + `_lib/format/*`, the sidebar's dated list
    # WD-33: the two translation catalogs, one chunk each. `i18n.ts` awaits the
    # catalog `storedLanguage()` picked before the first paint and fetches the other
    # only on a switch, so the row is what ONE reader of that language downloads,
    # never a page weight. The split that made them chunks left both past
    # SMALL_CHUNK_KB, and a chunk past the ceiling earns the row the gate asks for.
    # 2026-10-16: the update dialog gained a Details block (the versions, the
    # download size, the package, the notes the feed carried) and the browser
    # and held-back-restart sentences, so one German reader downloads 0.19 kB
    # more than the old ceiling allowed. Measured again from app/dist:
    # de.js 35.57 kB, en.js 32.24 kB; both rows carry ~9% headroom.
    "de.js": 38.8,           # measured 35.57
    "en.js": 35.2,           # measured 32.24
    # 2026-10-14: the chat's fence highlighter is on demand, so these are lazy
    # chunks like any route chunk — but each one that passes the small ceiling
    # ships unwatched without a row here. A fence fetches core, the JS engine,
    # the theme and its one grammar; the rest of the grammars stay under
    # SMALL_CHUNK_KB. Two keys cover two consumers: `core.js` is the app's
    # src/lib/core chunk (0.9 kB) and the engine's core, `markdown.js` the
    # markdown pipeline and the markdown grammar (5.5 kB) — the key is the
    # chunk name, and Rollup named both after their module.
    "core.js": 28.0,
    "engine-javascript.js": 23.0,
    "php.js": 31.0,
    "objective-c.js": 25.0,
    "javascript.js": 17.5,
    "jsx.js": 17.5,
    "tsx.js": 17.5,
    "typescript.js": 17.0,
    "less.js": 16.0,
    "swift.js": 16.0,
    "css.js": 13.5,
    # The two on-demand renderers and, below them, mermaid's own diagram chunks.
    # Each of those is fetched only for the diagram type a message actually uses, so
    # the numbers are ceilings per diagram, not a page weight. `katex.js` covers two
    # chunks of the same name, measured 2026-10-14 at 75.35 kB each: the copy the
    # formula loader pulls (katex 0.19.0) and the copy mermaid reaches for math in
    # labels (mermaid asks for katex ^0.18.0; pnpm resolved 0.18.11 beside ours). They
    # do not merge, because they are two package versions with two dependency
    # contracts — and the config lever that would force one breaks the laziness
    # instead. Measured: `resolve.dedupe: ['katex']` folded katex into the markdown
    # chunk, markdown.js 123.49 -> 198.96 kB gzip (over its own row), so every
    # markdown route paid the parser whether or not a formula was on screen. The
    # duplication is two lazy chunks, one per feature, and this single row holds each
    # of them. The trailing id in a mermaid name comes from mermaid's own build — an
    # upgrade renames the chunk, and the gate then asks for the row again rather than
    # passing on a stale number.
    "katex.js": 84.0,
    "mermaid.core.js": 154.0,
    "elk-QONTBCTQ.js": 484.0,               # the ELK layout engine, architecture diagrams only
    "cytoscape.esm.js": 152.0,              # graph layout, mindmap/timeline/ishikawa
    "cynefin-EF2NZ3EQ.js": 149.0,
    "usecaseDiagram-WPOLBNNX.js": 55.0,
    "architectureDiagram-ZHVYKT53.js": 46.0,
    "swimlanes-B3ENRKFQ.js": 44.0,
    "sequenceDiagram-BLEHNHQU.js": 34.5,
    "diagram-TYUNFSNR.js": 27.5,            # mermaid's shared sequence-diagram runtime
    "ganttDiagram-R7GPNTJY.js": 25.5,
    "cose-bilkent-JH36ORCC.js": 24.0,
    "flowDiagram-IUGLLWBU.js": 22.0,
    "c4Diagram-XDPPPE54.js": 20.5,
    "dagre-NK4GIZVX.js": 18.0,
    "classDiagram-v2-4MYWR3UA.js": 17.5,
    "vennDiagram-Q3Y3IDCW.js": 17.0,
    "blockDiagram-RJAE7QA3.js": 15.5,
    "stateDiagram-v2-A6IESKWZ.js": 15.5,
    "xychartDiagram-4URNHDU4.js": 14.0,
}

# Measured on 2026-10-14 from app/dist (vite build, gzip -9), after WD-33 moved the
# two translation catalogs out of the entry into chunks of their own: index.js
# 148.28 -> 88.62 kB, and `de.js`/`en.js` appear with rows of their own. The gate
# compares against the budget, not this baseline; the numbers document the headroom.
# Earlier, for the record: P1-8 split the 608 kB entry so `radix`, `ui` and `dates`
# (all three modulepreloaded by index.html) are their own chunks; W3-1 split the
# ChatPage chunk by lazy-loading the agent panel and the artifact rail inside the
# chat layout, ChatPage 208.03 -> 101.18 kB with the panel its own 107.04 kB lazy
# chunk. The math and fence wave added two lazy renderers, so the entry did not grow
# for them: markdown.js is where the remark-math tokenizer and the formula/diagram
# components landed, and index.css did not move — the KaTeX stylesheet rides with
# the KaTeX chunk.
MEASURED_GZIP_KB: dict[str, float] = {
    "index.js": 88.62,
    "ChatPage.js": 97.55,
    "AgentPanel.js": 105.94,
    "markdown.js": 123.49,
    # 2026-10-15 (n21-bundle): `m` + `LazyMotion features={domAnimation}` for every
    # animated surface (the root mounts the feature set once, App.tsx) — the drag
    # controls and the layout projection engine the `motion` component carried went
    # with it: 40.99 -> 27.96 kB gzip.
    "motion.js": 27.96,
    "ui-vendor.js": 35.22,
    # 2026-10-15, same wave: the font imports name their subsets, so the entry CSS
    # no longer declares cyrillic/cyrillic-ext/greek/greek-ext/vietnamese faces for
    # eleven faces that only en/de can use: 34.28 -> 20.94 kB gzip.
    "index.css": 23.03,
    "app-vendor.js": 23.17,
    "radix.js": 34.6,
    "ui.js": 15.09,
    # 2026-10-15: `dates-format` carries `format()` + `_lib/format/*`, which only the
    # sidebar's dated list reads; the entry keeps the locales and relative time.
    "dates.js": 5.8,
    "dates-format.js": 3.63,
    "de.js": 35.57,
    "en.js": 32.24,
    # 2026-10-14, same instrument and day as the budgets above.
    "core.js": 24.01,
    "engine-javascript.js": 20.26,
    "php.js": 27.88,
    "objective-c.js": 22.76,
    "jsx.js": 15.85,
    "tsx.js": 15.76,
    "javascript.js": 15.76,
    "typescript.js": 15.34,
    "less.js": 14.33,
    "swift.js": 14.3,
    "css.js": 12.15,
}

HASH = re.compile(r"^(?P<name>.+?)-[A-Za-z0-9_-]{8}\.(?P<ext>js|css)$")
HTML_REF = re.compile(r"""(?:src|href)=["'](?:/assets/|\./assets/)([\w.\-]+)["']""")


def logical_key(filename: str) -> str | None:
    """index-BBvxx5rb.js -> index.js; returns None when the name has no hash."""
    m = HASH.match(filename)
    return f"{m.group('name')}.{m.group('ext')}" if m else None


def gzip_kb(p: Path) -> float:
    return round(len(gzip.compress(p.read_bytes(), 9)) / 1024, 2)


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not dist.is_dir():
        print(f"dist dir not found: {dist} (run `npm run build` first)")
        return 2

    html = (dist / "index.html").read_text()
    main_refs = {f for f in HTML_REF.findall(html) if f.endswith((".js", ".css"))}
    main_keys = {k for f in main_refs if (k := logical_key(f))}

    rows: list[tuple[str, str, str, float, float]] = []  # filename, key, tier, budget, size
    problems: list[str] = []
    gated: set[str] = set()
    for p in sorted((dist / "assets").glob("*")):
        if not p.is_file() or p.suffix not in (".js", ".css"):
            continue
        key = logical_key(p.name)
        if key is None:
            problems.append(f"chunk not budgetable (no content hash): {p.name}")
            continue
        size = gzip_kb(p)
        is_main = p.name in main_refs
        row = BUDGETS_GZIP_KB.get(key)
        if is_main:
            if row is None:
                problems.append(
                    f"unbudgeted main chunk {p.name} ({size} kB) "
                    f"— add {key!r} to BUDGETS_GZIP_KB"
                )
                continue
            budget, tier = row, "main "
        elif key in main_keys:
            # A name shared with a first-paint chunk (Vite emits several
            # index-*.js barrels): hold the sibling to the small ceiling, never
            # to the neighbour's bigger number.
            if size > SMALL_CHUNK_KB:
                problems.append(
                    f"chunk {p.name} ({size} kB) shares the {key!r} name with a "
                    "first-paint chunk — rename it or split it"
                )
                continue
            budget, tier = SMALL_CHUNK_KB, "small"
        elif row is None:
            if size > SMALL_CHUNK_KB:
                problems.append(
                    f"unbudgeted large chunk {p.name} ({size} kB) "
                    f"— add {key!r} to BUDGETS_GZIP_KB"
                )
                continue
            budget, tier = SMALL_CHUNK_KB, "small"
        else:
            budget, tier = row, "route"
        gated.add(key)
        rows.append((p.name, key, tier, budget, size))
        if size > budget:
            problems.append(f"{key} over budget: {size} kB > {budget} kB  ({p.name})")

    print(f"Gated chunks (main = first paint, route = budgeted, small <= {SMALL_CHUNK_KB:.0f} kB), gzip:")
    for filename, key, tier, budget, size in sorted(rows, key=lambda r: -r[4]):
        flag = "OK " if size <= budget else "OVER"
        print(f"  [{flag}] {tier} {filename:32s} {size:>7} kB / {budget:>6} kB budget  ({key})")

    for key in sorted(BUDGETS_GZIP_KB):
        if key not in gated:
            print(f"  [--]  {key:32s} not in this build (stale budget, re-measure)")

    if problems:
        print()
        for prob in problems:
            print(f"FAIL: {prob}")
        return 1

    print()
    print(f"All gated chunks within budget ({len(rows)} checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
