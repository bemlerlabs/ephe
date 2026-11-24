# Ephe — the design, in the tokens the sheet ships

Five comments in three files cite this page by path and section: the theme-parity gate cites §3 for the
one ground, §12 for how a baseline moves and §8 for what a control's edge is allowed to be, the
filter-chip test cites §8 for the same rule at the class list, and the settings row cites the page for
its list pattern. Those citations were written against a page that had left the tree. This page is that
page, and it states only what a file in this checkout already does — a design page that says more than
the code is the version that goes stale, which is the rule `docs/BRAND.md` opens with.

Two neighbours hold facts this page does not copy (root `AGENTS.md`, "One home per fact"):
`docs/ACCESSIBILITY.md` owns the contrast floors, the axe matrix and the target-size floors, and
`docs/BRAND.md` owns the name, the marks and the four palette roles. What is here is the stylesheet:
which token carries which role, which guardian refuses its absence, and which number was measured
where.

## 1. One sheet, one ground, nothing to bend

`app/src/styles/globals.css` is the sheet the app builds with. The `@theme` block carries the forest
role literals and `:root` holds the theme-neutral defaults, so there is no second block a value could
come back through (`app/src/styles/globals.tokens.test.ts:1-9`). That file refuses a `html.light` block
outright, and `tests/test_forest_only.py` refuses the same shape at the source.

## 2. A token spells a colour or points at one

Every declaration is either a literal or a `var()` link, so resolving a role means following the links
the sheet writes — the resolution and the WCAG arithmetic live in `scripts/theme_contrast.py:1-11`, and
`scripts/mark_contract.py` recomputes the mark against the ground through it. The ten constitution
tokens the palette called by another name are aliases, declared once with that reason beside them
(`app/src/styles/globals.css:157-166`); the alias names are frozen by
`tests/test_r2b_alias_names_are_frozen.py`.

## 3. The forest is the only ground

```
const GROUNDS = ['forest'] as const                                    theme-parity.spec.ts:724
const THEME_GROUNDS: [string, Map<string, string>][] = [['forest', ink]]   globals.boundaryContrast.test.ts:51
```

The product ships one visual language and one ground: no light theme, no system follow, no theme
toggle. Paper was tried as the default and rejected on 2026-10-16, kept as a user choice until the
owner removed it on 2026-10-19 (`tests/test_forest_only.py:3-5`, recorded in
`docs/decisions/owner-decisions.md`). Three files hold that from coming back: the sweep's matrix is
written from `GROUNDS` so a second entry is a deliberate edit that doubles the baseline
(`app/tests/playwright/theme-parity.spec.ts:722-724`), the walk asserts the document carries no second
ground (`app/tests/playwright/theme-parity.spec.ts:713-719`), and `tests/test_forest_only.py` refuses
eight doors a second ground could return through — the stylesheet block, the paper literal, the paper
grain on a card, a stored mode, a toggle, the manifest canvas, a `theme` field on the settings API, and
a `theme` key on `AppSettings` — with a meta-test that makes each refusal hit its own example and
another that checks the scan really walks the product sources.

Committed counts as measured 2026-11-24 from `app/tests/playwright/theme-parity.baseline.json`: 163
rows, every one of them `forest`, 6 rows above zero carrying 10 metric entries.

## 4. Text is measured against what it is composited onto

The ink roles are `--color-ink`, `--color-ink-soft` and `--color-ink-faint`
(`app/src/styles/globals.css:153-155`). The instrument that judges them walks the painted DOM and
compares every visible text run against the background it is actually composited onto, ancestor stack
included, so a glass veil counts as the blend it paints (`app/tests/playwright/theme-parity.spec.ts:16-22`).
Its floors are `TEXT_FLOOR = 4.5`, `LARGE_TEXT_FLOOR = 3`, `BOUNDARY_FLOOR = 3`
(`app/tests/playwright/theme-parity.spec.ts:45-47`), and what those floors mean for the product is
`docs/ACCESSIBILITY.md`'s to say. The audit runs without axe-core: the wave rule was no new npm
package, and the audit needs only `getComputedStyle` (`app/tests/playwright/theme-parity.spec.ts:24-25`).

## 5. Surfaces, and one recipe for a floating one

The background roles are `--color-canvas`, `--color-surface`, `--color-surface-raised` and
`--color-surface-interactive` (`app/src/styles/globals.css:151-173`). The raised and interactive pair
replaced the `bg-white/[0.03–0.12]` veils that used to lift chips, rows and hovers, so one utility
carries the step (`app/src/styles/globals.css:170-173`). A floating surface has one primitive:
`glass-float rounded-2xl shadow-elevation-3`, and the hand-rolled second recipe that had grown beside
it is what `app/src/styles/globals.floatSurface.test.ts:1-8` refuses.

## 6. An accent may bend the brand roles and nothing else

The three accent preset blocks may bend exactly the four brand roles named in `docs/BRAND.md` §3. The
ground, the status tones, the selection steps and the terminal palette stay the base sheet's, and every
pair the file checks is computed from the shipped literals, so an accent changed without its measurement
fails there (`app/src/styles/globals.accents.test.ts:1-8`).

## 7. Status colours keep their own axes

`--color-signal-ok`, `--color-signal-warn` and `--color-signal-danger` are declared with the reason for
each step beside them: success stepped back to hold AA on ink, danger on its own axis at a measured
distance from the brand red, warning unchanged on the amber axis
(`app/src/styles/globals.css:174-180`). The separation from the brand is the sheet's own number, not a
re-measurement: it records the shipped danger at ΔE≈20 from the brand red, and says the planned darker
value lay only ΔE 8 away, which was corrected by measurement because the brand must not read as danger
(`app/src/styles/globals.css:176-179`). The red a retired mark carried left the product on 2026-10-19
(`scripts/mark_contract.py:52`).

## 8. A control's only edge is a boundary; a decorative hairline is not one

```
--border-control: var(--color-control);                     globals.css:297
--color-control: var(--color-hairline-strong);              globals.css:168
--color-hairline-strong: hsl(22.5 9% 46%);                  globals.css:167
--color-hairline: hsl(22.5 9.5% 16.5%);   /* #2E2926 */     globals.css:156
```

The rule is one sentence and three files hold it at three layers.

At the token layer, `app/src/styles/globals.boundaryContrast.test.ts:124` requires the control boundary
to clear 3:1 against every background role the sheet declares, recomputed from the values in the sheet
on every run, and `app/src/styles/globals.boundaryContrast.test.ts:154-160` refuses the boundary role
being pointed back at the decorative hairline. The measured defect the file names is that no UI boundary
reached 3:1 before this token existed: the 1-px hairline sits at 1.21–1.42:1 and the louder hover step
at 1.4–1.9:1, so six interactive elements carried an edge nobody with reduced contrast sensitivity can
see.

At the class-list layer, `app/src/pages/filterChipEdge.test.ts:30-56` refuses
`border border-transparent` — a 1px width that paints nothing, which made a row of pressable words read
as headings — and requires every unselected filter chip and view tab to carry `border border-control`.
The selected branch is checked too, because an edge only the unselected state carries moves the label by
2px on every tap.

At the painted layer, `app/tests/playwright/theme-parity.spec.ts:577-595` scores an edge only on
elements that carry a control (`isControl(el)`, width at least 1px, a border colour with alpha), and it
compares that edge with the parent's ground, because WCAG 1.4.11 compares an edge with what lies beyond
it: `border-ink bg-ink` is a filled button, not a boundary.

Measured on 2026-11-24 by `cd app && CI=true pnpm exec vitest run
src/styles/globals.boundaryContrast.test.ts` (vitest 4.1.12, node v22.23.5, Apple Silicon, exit 0), the
control edge clears the floor on each background role: 4.06:1 on `--color-canvas`, 3.79:1 on
`--color-surface`, 3.42:1 on `--color-surface-raised`, 3.03:1 on `--color-surface-interactive`. The test
prints that grid every run; it is an expression of today's tokens, not a recorded number.

The register's list pattern is the same rule seen from the component side: an inset grouped list on the
forest canvas, neutral graphite surfaces, a 44px row floor and 10-12px radii, where the card is the only
frame a row gets (`app/src/components/shell/SettingsRow.tsx:7-11`).

## 9. A focus outline, a stroke and a run state each have one source

The focus outline has a single source: an unlayered `*:focus-visible { outline: 2px solid … }` beat
every layered rule through the cascade model and is what `app/src/styles/globals.focus.test.ts:1-6`
removed. Icons carry one optical stroke, which is why the sheet pins the raster Lucide draws with
(`app/src/styles/globals.iconRaster.test.ts:1-5`). The four run states the workbench chrome moves
through share the durations the first-open scene already set, animate only compositor properties, and
land every state on the still under both the operating system's switch and the user's
(`app/src/styles/globals.runState.test.ts:1-9`).

## 10. One scale, a 4px grid, and a motion budget that has consumers

Every axis carries exactly one ordered step set declared once in `@theme` — type, radius, shadow,
z-index and tracking — and the duplicate layers that predate that rule are what
`app/src/styles/globals.scale.test.ts:1-6` refuses. Radii are five steps plus full on the 4px grid
(`--radius-sm` 4px through `--radius-2xl` 20px) with no dead `:root` duplicate
(`app/src/styles/globals.radius.test.ts:11-30`). The type roles are `--text-scale-title`,
`--text-scale-ui` and `--text-scale-data`, each derived from `--ui-font-size` so one knob moves the
sheet (`app/src/styles/globals.css:44-55`). The motion budget has consumers: seven tokens sat in
`:root` unread while 14 sites hardcoded `duration-200`, which is the state
`app/src/styles/globals.motion.test.ts:1-6` closed.

## 11. A name that resolves nowhere is a defect, not a style

Three static checks keep the sheet and its callers naming the same things. Every `var()` reference
resolves somewhere in `src/` — the defect that earned the rule was a component reading
`var(--background)`, a name no stylesheet defines, which rendered nothing and failed nothing
(`app/src/styles/globals.deadTokens.test.ts:1-6`). A custom property written from code must have a
reader (`app/src/styles/deadCssVars.test.ts:1-4`). And a utility class naming a token nobody
declared is refused, because `text-ui-xxs` and `text-ui-md` emitted no rule at all, inherited their
parent's size, and let the page look right (`app/src/styles/globals.utilityDrift.test.ts:1-5`).

## 12. A baseline moves in its own commit, with the count before and after

A gate that starts at zero on a tree that is not at zero is a gate nobody trusts, so a finding the tree
already carries is frozen once and every later run compares against the snapshot. Two committed
baselines show the shape, and a page may name only those.

`.design-tokens-baseline.json`, at the repository root, is the shape spelled out in a file: `version 1`,
`frozenAt 2026-10-14T19:54:17.769Z`, three axes (`radiusArbitrary` 3, `shadowArbitrary` 0,
`colorLiteral` 20) and `total 23`. It is read by `scripts/design_tokens_check.mjs:27`, where a missing
baseline makes the run a hint at exit 0 rather than a verdict, and held by
`tests/test_w10_design_tokens.py:18`, where every ratchet verdict is proved on a private copy under
`tmp_path` and never on the tracked file, and where one test recounts the three axes in Python against
the committed snapshot so the snapshot cannot drift from the code it freezes.

`app/tests/playwright/theme-parity.baseline.json` holds the sweep's counts per surface, ground, width
and metric; a surface that exceeds its entry, or appears without one, is red
(`app/tests/playwright/theme-parity.spec.ts:27-31`). The instrument is a ratchet, not a claim of zero.

A move is its own commit and names both numbers. `17ad447` dropped one entry from
`scripts/prose-tells-baseline.json` and its commit text carries "One key removed and the derived total
with it: 380 to 379", with the measured total beside it — the ratchet holds with room under it, which is
the difference between a floor and a ceiling. The family in the tree:
`.architecture-baseline.json`, `scripts/prose-tells-baseline.json`, `scripts/language-baseline.json`,
`scripts/coverage-floor-baseline.json`, `scripts/provenance-baseline.json`,
`scripts/changelog-baseline.json`, `scripts/docker-lint-baseline.json`,
`scripts/engine-language-baseline.json` and `tests/home-isolation-baseline.json`. When a whole wave
lands at once and cannot tell its own red from a pre-existing one, `scripts/gate_baseline.py` freezes
the verdicts first and attributes them after, at exit 0, 1 or 3.

A count in a comment here is worth exactly the command that printed it. The numbers on this page name
their file and their run; a number with no command beside it does not belong on this page, and a
decision nobody took does not belong in a document written for it.
