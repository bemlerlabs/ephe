# Accessibility — the desktop target floor

The product holds WCAG 2.2 AA. For pointer input that means **2.5.8 Target Size
(Minimum): 24 × 24 CSS pixels**, with the criterion's spacing exception for anything
smaller. The 44 × 44 thumb rule (2.5.5, AAA) stays the requirement on a coarse
pointer, where the phone layouts and `docs/COMPOSER_MOBILE.md` hold it.

## Measured at 1280 × 800 (2026-11-12)

Chromium, built `app/dist`. Every visible control on `/`, `/chat` and `/settings`, with
the settings sheet open and with the composer popups open.

| Control | Size |
|---|---|
| Frame nav rail button | 40 × 40 |
| Settings nav row | 191 × 31 |
| Composer action buttons | 36 × 36 |
| Engine status pill | 180 × 24 |
| Composer thinking chip | 43 × 24 |
| Status-bar token breakdown | 78 × 27 |

The two 24 px rows were 19 px high before this measurement and are now pinned to
`min-h-6`. Nothing on the three routes is under 24 in either dimension, so the spacing
exception is not in use at this width.

## The 44 px recommendation on the desktop

The 44 × 44 figure is a recommendation for thumbs. Applying it to a mouse layout would
move the rail, the settings rows and the header the rest of the product is measured
against, without a criterion asking for it. The desktop keeps the 24 px floor, and the
thumb floor keeps its own breakpoints (`pointer: coarse`, `max-lg`). The rail at 40 px
and the settings rows at 31 px are the two places this shows; both stay clickable
comfortably and both are wider than the criterion's floor.

A control that is below 24 px in one dimension has to keep a 24 px circle clear of
every other target (2.5.8, spacing exception). The gate computes that circle, so a
future small control is held to the same rule instead of a hand-written gap.

## Where this is held

- `app/tests/playwright/a11y-desktop.spec.ts` — the nine-run axe matrix (three routes
  at 1280/390/320), the 24 px floor at 1280, the open phone drawer as a named dialog,
  the settings focus handback, the composer popup rectangles and the standing toast
  live region.
- `app/tests/playwright/a11y-b6.spec.ts` — the phone floors from the 2026-11-11 audit.
- `app/tests/playwright/theme-parity.spec.ts` — text and boundary contrast on the one
  shipped ground at 1280 and 390. `const GROUNDS = ['forest']`
  (`app/tests/playwright/theme-parity.spec.ts:724`) is the whole set since the paper ground
  was retired by owner decision 2026-10-19, and `tests/test_forest_only.py` refuses a second
  ground in the source rather than trusting this page.

The settings handback carries its measurement because it is the line here the code did not
keep until 2026-11-24. The rail's settings button
(`app/src/components/dashboard/Sidebar.tsx:1358`) is the invoker, and the sheet is mounted by
its own open (`app/src/pages/SettingsPage.tsx:14`), so the invoker is taken where focus is
set (`app/src/components/dashboard/settings/model/useSettingsState.ts:179-187`). The
`focusin` recorder that covers a surface mounted while closed stays beside it
(`app/src/components/dashboard/settings/index.tsx:154-161`), and the close-time handback is
the shared one: `handFocusBack` (`app/src/hooks/useFocusReturn.ts:58-74`), which reaches
`STABLE_FOCUS_TARGETS` (`app/src/hooks/useFocusReturn.ts:95-100`) when the invoker is gone.
Measured 2026-11-24:

```bash
cd app && pnpm run build && pnpm exec playwright test \
  -c tests/playwright/playwright.config.ts --workers=1 tests/playwright/a11y-desktop.spec.ts
```

13 passed on `@playwright/test` 1.64.0, chromium build 1248 (`Google Chrome for Testing
156.0.8078.4`), headless at `deviceScaleFactor: 1`, macOS on Apple Silicon. With no invoker
on screen — `/settings` opened directly — focus goes to one of the stable targets named
above. Both directions of that close, and the two conditions the handback checks on an
invoker, are pinned on the panel itself
(`app/src/components/dashboard/SettingsPanel.focusReturn.test.tsx`); the case on the shared
hook covers a surface built on it (`app/src/hooks/useFocusReturn.test.tsx:164-176`).

The audit that produced these numbers is the W2 read-only run; the 44 px note above is
its open item, recorded here as a decision rather than a styling debt.
