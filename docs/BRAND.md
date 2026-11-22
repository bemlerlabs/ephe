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
`app/public/favicon.svg` and `.png` (the bee the tab shows), the PWA `icon-192/512.png`, the tray
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
| `scripts/generate_social_preview.py`, drawn into `app/public/og-image.png` | kicker `THE EPHEMERAL SI AGENT`, headline `Work you can see.` / `A trace that disappears.` | `docs/media/ephe-social-preview-1200x630.png` is the tracked source asset the drawing reproduces; the card is redrawn by the generator, never edited as an image, and it carries no word the drawing does not render |
| The app's own hero, `welcome.heroSub` | the English leaf in `app/src/locales/en.json` and its German counterpart in `de.json` | `app/src/locales/completeness.test.ts` and `germanSurface.test.ts` |
| The terminal's start banner, `cmd_start` in `ephe_cli.py` | `◍ Ephe {version} — local & private`, then the headline, then the hero line | `tests/test_start_banner.py` for the three lines, `tests/test_device_folder_modes.py` and the `0600` modes in `core/persistence.py` for the second half of the first one |

The card keeps its own press-release pair — a claim about what a person can watch and about what
does not persist — because that is the sentence section 3 permits a share image to say, and it is
drawn by the generator rather than written into the page. The German wording of the app's pitch
lives only in the German bundle, per the rule in `app/AGENTS.md`.

A generated image enters the tree only when a committed document names the surface it targets and
the decision it is evidence for (root `AGENTS.md`, "Generated media"); every mark and screenshot on
this page's surfaces comes from the generators named above or from a capture of the built app.
