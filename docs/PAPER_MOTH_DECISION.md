# The paper moth is the product mark

Owner decision 2026-10-29, taken on the origami moth reference the owner supplied.
The figure replaces the bee as Ephe's mark on every surface outside the swarm. The
bee stays, in one role only: the badge of the sub-agents that work in parallel
(`app/src/components/dashboard/bubble/SwarmDeck.tsx`).

## Why this figure

The moth is folded from one sheet: two forewings swept up and out, two hindwings
trailing below, a slip of a body, and a crimson thread tied at each wing root.
That is the product's own story in one shape — one cell folds into an answer, and
the thread is the custody chain that keeps it attached.

## Surfaces

| Surface | Asset | Drawn by |
| --- | --- | --- |
| Browser tab | `app/public/favicon.svg`, `favicon.png` | `scripts/generate_brand_assets.py` |
| PWA tiles | `app/public/icon-{192,512}.png`, `icon-maskable-*`, `apple-touch-icon-180.png` | same |
| Desktop app (macOS) | `app/src-tauri/icons/icon.icns`, `*.png` | same |
| Desktop app (Windows) | `app/src-tauri/icons/Square*.png`, `StoreLogo.png`, `icon.ico` | same |
| Tray | `app/src-tauri/icons/tray-mono.png` | same, mono cut |
| In-app vector | `app/src/assets/mark.svg`, `mark-mono.svg` (`EpheMark`) | same, vector spelling |
| Welcome hero, setup card | `app/public/onboarding/paper-moth-actor.webp` (`HeroMark`) | actor cut |
| First-open film | `app/public/onboarding/paper-moth-{actor,wing-l,wing-r,thread}.webp` | `scripts/generate_moth_film_parts.py` |
| Companion, guide | the same four layers | as the film |

One generator writes all of them, so no surface can carry a drawing the others do
not have.

## The cut ladder

`MARK_CUTS` in `scripts/generate_brand_assets.py` stays the one table of bands:

- **≤32 px (micro)** — the silhouette alone. The crease and the thread are below a
  pixel at this size, so the cut drops them rather than blurring them.
- **33–47 px (compact)** — the planes and the thread, no crease.
- **≥48 px (mark)** — the folded planes, the crease on both forewings, the thread.

## Colours

Four roles in `scripts/brand_palette.py` and `app/src/styles/globals.css`:
`figure-paper` (#EFE6D2, the sheet), `figure-paper-lit` (#FBF5E6, the lit face of a
fold), `figure-paper-shade` (#D8C9AC, the turned-away face and the crease), and
`figure-paper-body` (#C8B591, the rolled body). The thread is the product red
(`--color-firefly`, #E8543F) — the one accent the mark spends, so the custody
colour is the same colour the interface uses for it.

## How the actor is cut

The owner reference is a photograph on a plain sheet with its own matte; the cut
keeps that matte (a second guess would move a correct edge), drops matte noise
below 6 %, feathers the contour by 0.6 px, and — where a source arrives without
alpha — solves `C = a·F + (1-a)·B` in linear light and unmixes the sheet out of
the colour so no white rim survives on a dark tile. The matte is then fitted into
a 1024 square and floats: the tile adds a warm glow behind the figure and a soft
contact shadow under it.

## Proof

`scripts/asset_check.py` measures every raster at 16 px: the weakest of the 20
assets carries a luminance spread of 249.8 against a floor of 20.0 (measured
2026-10-29 on this tree). The size ladder was reviewed as a rendered sheet at
16/24/32/48/96/192 px before the kit was written.

## What this replaces

The fire-spirit bee (`scripts/generate_fire_spirit_bee.py`) remains in the tree as
provenance: it is the drawing the 2026-10-16 decision shipped, and the comparison
sheet still renders it. It no longer writes any shipped asset.
