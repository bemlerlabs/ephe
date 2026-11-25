# Ephe — the brand, in the words the code ships

Ten comments in eight files cite this page by path and section: the CLI's banner, the icon kit's
generator, the social-preview generator, the app-shell header, and three test files that enforce the
claim boundary in section 3. Those citations were written against a page that had
left the tree. This page is that page, and it states only what a file in this checkout already
does — a brand document that says more than the code is the version that goes stale.

A word here is a word its pinner enforces. Changing one is a change to the test in the same patch,
and the PR review is the diff between the two.

## 1. The name

Ephe, capital E, one word. `app/src-tauri/tauri.conf.json` carries it as `productName` and as the
window title; `app/public/manifest.json` carries it as `name` and `short_name`; `app/index.html`
carries it as `apple-mobile-web-app-title` and `og:site_name`. A third-party product name stays out
of those fields, out of filenames, module paths, identifiers and setting keys, and appears in prose
only as the prior art it is cited for (root `AGENTS.md`, "English in the tree").

The colour of the retired name does not come back: `#c084fc` and `#7c3aed` are named and refused in
`tests/test_tui_black_forest.py`. `LICENSE` names who to write about usage.

## 2. The marks

`scripts/generate_brand_assets.py` is the only source of a raster or a tab vector. It renders from
the SVG at each target size through Chromium, so no file is scaled by hand, and it is deterministic:
no network, no font dependency, no `<text>` element anywhere in the output. What it writes is
`app/public/favicon.svg` and `.png` (the moth the tab shows), the PWA `icon-192/512.png`, the tray
icon, and — under `--variant=mark` — the forest-spirit figure whose `_mark` drawing is the source of
the in-app vectors `app/src/assets/mark.svg` and `mark-mono.svg`, inlined by `EpheMark`.

`tests/test_r68_brand_icons.py` holds the kit's shape; the cut follows the size (the whole figure
from 48 px, the plain head-and-blade cut below it), a decision recorded 2026-10-15.

## 3. Palette and the claim boundary

The palette has four roles, declared as tokens in `app/src/styles/globals.css` and read back by name
in `scripts/brand_palette.py`: `--color-black-forest`, `--color-moss-deep`, `--color-firefly` and
`--color-firefly-glow`. `--color-brand` is the guardian alias of `--color-firefly` in `@theme`, and
the names are the repository's own (firefly, moss, black-forest).

The terminal quotes a contrast ratio per colour against its ground in `ui/palette.py`, and
`tests/test_tui_black_forest.py` re-measures them (measured 2026-11-16: TEXT 16.25, DIM 5.31,
ACCENT 5.13). A colour that stops holding its ratio against the ground stops being readable, which
is the condition the test fails on.

### Claim boundary

Sayable is what is countable or provable. The strings that never appear in shipped copy are
`private`, `never`, `without a trace` — the tuple in `tests/test_tui_black_forest.py` — and
`no data leaves`, added to the same rule for the description surfaces by
`tests/test_index_html_description.py`.

The word `private` is allowed exactly where it is countable. `tests/test_tui_black_forest.py`
and `tests/test_index_html_description.py` refuse it as marketing copy in a terminal string or a
meta description, while the start banner prints `local & private` because
`tests/test_device_folder_modes.py` measures the folder modes behind it. Same word, different
standing: one is a promise nobody checks, the other is a `stat()` result.

An optional path is named as optional wherever it appears: web search, a foreign engine, the
Telegram link, public mobile access. `README.md`'s opening lines carry the same rule for the public
surface, and `scripts/readme_check.py --public` is the check that the links it promises resolve.

## 4. What Ephe says about itself

The pitch has a headline and a line under it. The headline is the light sentence the owner
set, `Where the light is, the work happens.`; the line under it is the hero line, `Your agent.
Your machine. Your memory.` Each surface below carries its own form of them, and the pinner is
the file that fails when the wording drifts. A wording change and its pinner move in the same
patch.

| Surface | The words | Pinned by |
| --- | --- | --- |
| The three READMEs, under the mark | the headline as `###`, the hero line in bold under it, each README in its own language | `tests/test_brand_headline_surfaces.py`, which also pins the two canonical English terms inside the first 1500 characters of the Spanish and Chinese files |
| The three READMEs, the sentence the installer contract quotes | `local-first workspace for an AI agent`, `Online paths are opt-in` | `tests/test_installer_cli.py` and `scripts/readme_check.py` |
| `app/index.html` `<title>`, `og:title`, `twitter:title` | `Ephe — Where the light is, the work happens.` | `tests/test_index_html_description.py` |
| `app/index.html` `meta description`, `og:description`, `twitter:description` and `app/public/manifest.json` `description` | the pinned description, and the social pair opens with the hero line: Give it a task; it researches, builds and delivers while you watch. Runs locally on the engine you choose. | the same file, against both locale bundles and the manifest |
| `scripts/generate_social_preview.py`, drawn into `app/public/og-image.png` | kicker `THE EPHEMERAL SI AGENT`, headline `Work you can see.` / `A trace that disappears.` | `docs/media/ephe-social-preview-1200x630.png` is the tracked twin of that copy, byte for byte; the card is redrawn by the generator, never edited as an image, and it carries no word the drawing does not render |
| The app's own hero, `welcome.heroSub` | the English leaf in `app/src/locales/en.json` and its German counterpart in `de.json` | `app/src/locales/completeness.test.ts` and `germanSurface.test.ts` |
| The terminal's start banner, `cmd_start` in `ephe_cli.py` | `◍ Ephe {version} — local & private`, then the headline, then the hero line | `tests/test_start_banner.py` for the three lines, `tests/test_device_folder_modes.py` and the `0600` modes in `core/persistence.py` for the second half of the first one |

The card keeps its own press-release pair — a claim about what a person can watch and about what
does not persist — because that is the sentence section 3 permits a share image to say, and it is
drawn by the generator rather than written into the page. The German wording of the app's pitch
lives only in the German bundle, per the rule in `app/AGENTS.md`.

A generated image enters the tree only when a committed document names the surface it targets and
the decision it is evidence for (root `AGENTS.md`, "Generated media"); every mark and screenshot on
this page's surfaces comes from the generators named above or from a capture of the built app.

## 5. The thinking sign

While a turn reasons, the chat line that names the state carries a figure instead of a spinner: the
letter `E` of the Ephe name, which turns on its vertical axis into the paper moth, holds there, turns
back into the letter, and keeps turning while the phase is open.
`app/src/components/brand/ThinkingMark.tsx` draws it, `ThinkingMark.css` moves it, and
`ThinkingMark.test.tsx` reads that sheet the way `app/src/styles/globals.runState.test.ts` reads the
run layer. The animation is CSS on a mounted element: no timer, no library, no canvas.

| Property | The value | Where it lives |
| --- | --- | --- |
| The cycle | 3.6 s — six scene beats, `calc(var(--ephe-scene-beat) * 6)`, no literal duration, so the sign keeps the workbench's tempo when the beat moves | `--ephe-think-cycle` in `ThinkingMark.css` |
| The four states | letter 0–20 %, turn 20–30 %, moth 30–70 %, turn 70–80 %, letter 80–100 %: two holds and two turns, one quarter-turn per swap, the swap landing on the edge-on frame | `@keyframes ephe-think-turn` |
| Cadence | `linear` across the cycle, so no part of the rotation runs faster than another; the curve sits inside each turn, where `var(--ease-organic)` carries the figure into and out of the edge-on frame | the same keyframe block |
| What moves | `transform` and `opacity` only. Both faces stand in one grid cell of a `preserve-3d` stage with `backface-visibility: hidden`, so the swap costs nothing to the line: nothing shifts, repaints, or reflows | `.ephe-think-stage`, `.ephe-think-frame`; pinned by `ThinkingMark.test.tsx` |
| Size in chat | 1.125 rem (18 px) — the same square the workbench bar's moth holds at `size="18px"`, so one figure reads the same weight in both places | the `size` default of `ThinkingMark` |
| Ground | painted from the figure roles alone — `--color-figure-paper`, `-lit`, `-shade` — plus the figure's own `--color-firefly`. No `--color-brand`, so no accent and no ground recolours it; measured equal under `mono`, the accent that drops the brand red | `PaperMothGlyph.tsx`, `ThinkingMark.test.tsx`, `thinking-mark.spec.ts` |
| Reduced motion | the standing letter with the word beside it and no motion: `animation: none`, `transform: none`, the moth put away at `opacity: 0`, under `@media (prefers-reduced-motion: reduce)` and under `html.no-motion`, the product's own switch | the two switch blocks; both measured in `app/tests/playwright/thinking-mark.spec.ts` |

The word is the locale's (`chat.thinkingNow`), never the component's: the sign is `aria-hidden` and
sits in the `role="status"` `aria-live="polite"` line `ThinkingBlock.tsx` renders, so a reader hears
the sentence and not the figure. A run without the motion window says that same sentence, which the
browser case measures by reading the line under both switches. The per-second tick stands outside the
live region, so nobody is asked to read a clock.

Nothing else wears it, because nothing else is this state. An open thinking phase is the one case:
a finished thought is a record with its own label, a tool about to run is `chat.awaitingTool`, an
answer that streams is the bar's working moth in `AgenticBar.tsx`, and the composer's thinking chip
is a reasoning-mode switch rather than a run state.

**Provenance.** The moth is not redrawn — it is `PaperMothGlyph`, the workbench bar's figure, reused.
The letter is `PaperLetterGlyph`, drawn by hand by brand-eng on 2026-11-24 on the same 96-unit grid
with the same fold the wings carry, taking its folding language from
`docs/media/paper-moth-master.png`; no generated graphic, no screenshot and no foreign source
contributed to it, and both faces are vectors in one file beside the moth's.

