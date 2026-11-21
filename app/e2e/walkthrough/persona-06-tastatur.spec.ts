/**
 * Persona 06 — the keyboard-only user.
 *
 * Live, real-engine walkthrough. NO network interception, NO fixture mocking:
 * every assertion reads the running app (app/dist served by the local runtime)
 * and the real engine behind it. When the runtime is not reachable the spec
 * skips with an explicit reason instead of faking a result.
 *
 * Base URL: http://127.0.0.1:8765 (the served PWA). Override with
 * EPHE_E2E_BASE when the runtime listens elsewhere.
 *
 * What this persona captures (with screenshots + a focus transcript per step):
 *   (a) the skip target and the first Tab stops — sane order + a visible
 *       token-based focus ring on every stop;
 *   (b) Cmd/Ctrl+K — palette opens, focus is inside, ArrowDown/Enter select,
 *       Escape closes, and where focus lands AFTER closing (audit: it returns
 *       to the invoker);
 *   (c) the settings overlay — open/step/close by keyboard, background inert
 *       while open, focus handed back on close;
 *   (d) surfaces that claim role=dialog aria-modal — does Tab actually stay
 *       inside? (audit: CommandPalette, ArtifactRail and the mobile sidebar
 *       declare aria-modal without trapping Tab).
 *
 * Selector sources: app/src/lib/shortcuts.ts, app/src/hooks/useCommandPalette.ts,
 * app/src/hooks/paletteScoring.ts, app/src/components/ui/CommandPalette.tsx,
 * app/src/components/dashboard/chat/index.tsx, .../settings/index.tsx,
 * .../ArtifactRail.tsx, app/src/App.tsx.
 *
 * Evidence dir: the walkthrough capture dir (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/persona-06-tastatur/
 */
import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

// ── Target ──────────────────────────────────────────────────────────────────
// The product serves the built PWA from app/dist at 127.0.0.1:8765 (the local
// runtime, real engine). Overridable so the same spec can point at a dev server.
const BASE = process.env.EPHE_E2E_BASE ?? 'http://127.0.0.1:8765'
const CHAT_URL = `${BASE}/#/chat`

// ── Evidence paths ──────────────────────────────────────────────────────────
const SHOT_DIR = walkthroughOutDir('persona-06-tastatur')
const shotPath = (name: string): string => path.join(SHOT_DIR, `${name}.png`)

// ── Selectors (derived from source, kept language-independent) ───────────────
const SKIP_TO_INPUT = 'Skip to chat input' // i18n a11y.skipToInput (en)
const SKIP_TO_CONTENT = 'Skip to content' // i18n a11y.skipToContent (en)
const COMPOSER_ID = '#ephe-chat-input' // ChatInput.tsx / App.tsx skip target
const MAIN_CONTENT = '#main-content' // chat/index.tsx <main>
const SIDEBAR_SETTINGS = '[data-testid="sidebar-settings-btn"]' // Sidebar footer
const RAIL_TOGGLE = '[data-testid="artifact-library-toggle"]' // header, desktop only
const RAIL_MODAL = '[data-testid="artifact-modal"]' // ArtifactRail.tsx
const SETTINGS_PAGE = '[data-testid="settings-page"]' // settings/index.tsx
const SETTINGS_BACK = '[data-testid="settings-back"]' // first focusable in the dialog
const PALETTE_LISTBOX = '#cmd-palette-listbox' // CommandPalette.tsx
const PALETTE_COMBOBOX = 'input[role="combobox"]'

// ── Console capture ─────────────────────────────────────────────────────────
let consoleErrors: string[] = []

// ── Focus transcript helpers ────────────────────────────────────────────────
interface FocusInfo {
  tag: string | null
  id: string | null
  testid: string | null
  role: string | null
  ariaLabel: string | null
  text: string
  outlineStyle: string
  outlineWidth: string
  outlineColor: string
  outlineOffset: string
}

const FOCUS_SNAPSHOT = `(() => {
  const el = document.activeElement;
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {
    tag: el.tagName ? el.tagName.toLowerCase() : null,
    id: el.id || null,
    testid: el.getAttribute ? el.getAttribute('data-testid') : null,
    role: el.getAttribute ? el.getAttribute('role') : null,
    ariaLabel: el.getAttribute ? el.getAttribute('aria-label') : null,
    text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 60),
    outlineStyle: cs.outlineStyle,
    outlineWidth: cs.outlineWidth,
    outlineColor: cs.outlineColor,
    outlineOffset: cs.outlineOffset,
  };
})()`

async function focusInfo(page: Page): Promise<FocusInfo | null> {
  return (await page.evaluate(FOCUS_SNAPSHOT)) as FocusInfo | null
}

/** A stop counts as ringed when an author outline is painted (the program's
 *  *:focus-visible rule → 2px solid var(--color-ring)). */
function hasVisibleRing(i: FocusInfo | null): boolean {
  if (!i) return false
  if (i.outlineStyle === 'none' || i.outlineStyle === '') return false
  if (parseFloat(i.outlineWidth || '0') < 1) return false
  return !/rgba?\(\s*0,\s*0,\s*0,\s*0\)|transparent/i.test(i.outlineColor)
}

function describe(i: FocusInfo | null): string {
  if (!i) return '(no active element)'
  const bits = [
    i.tag,
    i.id ? `#${i.id}` : '',
    i.testid ? `[${i.testid}]` : '',
    i.ariaLabel ? `(${i.ariaLabel})` : '',
  ]
  return `${bits.filter(Boolean).join(' ')} "${i.text}" — outline ${i.outlineStyle} ${i.outlineWidth} ${i.outlineColor}`
}

async function capture(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: shotPath(name), fullPage: true }).catch(() => undefined)
}

async function captureRing(page: Page, name: string): Promise<void> {
  await page
    .locator(':focus')
    .screenshot({ path: shotPath(name) })
    .catch(() => undefined)
}

// ── Navigation ──────────────────────────────────────────────────────────────
/** Loads the served PWA in English (deterministic labels), no mocking. */
async function gotoApp(page: Page): Promise<boolean> {
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('i18nextLng', 'en')
    } catch {
      /* private mode — the app's own default applies */
    }
  })
  const res = await page
    .goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 20_000 })
    .catch(() => null)
  if (res === null) return false
  // The App shell (the two skip links) commits immediately, but the dashboard
  // — sidebar, composer, tabbable toolbar — is lazily mounted afterwards. A Tab
  // sweep issued straight after domcontentloaded would therefore only ever see
  // the two skip links and then re-wrap to the document, which is a test race,
  // not a product finding. Wait for the interactive shell before reading focus.
  await page
    .locator(SIDEBAR_SETTINGS)
    .first()
    .waitFor({ state: 'attached', timeout: 20_000 })
    .catch(() => undefined)
  return true
}

/** The chat shell (header + sidebar) only exists on the configured route. */
async function chatShellReady(page: Page): Promise<boolean> {
  return (await page.locator(SIDEBAR_SETTINGS).count()) > 0
}

/** Opens the palette via the keyboard. Accepts Ctrl+K or Cmd+K (the handler
 *  toggles on either) so the same spec works on macOS and Linux CI. */
async function openPalette(page: Page, palette: ReturnType<Page['locator']>): Promise<boolean> {
  if (await palette.isVisible().catch(() => false)) return true
  await page.keyboard.press('Control+k')
  if (
    await palette
      .waitFor({ state: 'visible', timeout: 1200 })
      .then(() => true)
      .catch(() => false)
  )
    return true
  await page.keyboard.press('Meta+k')
  return palette
    .waitFor({ state: 'visible', timeout: 1500 })
    .then(() => true)
    .catch(() => false)
}

/** Walks focus with Tab and reports every stop that left `container`. */
async function sweepTab(
  page: Page,
  container: ReturnType<Page['locator']>,
  steps: number,
): Promise<Array<{ step: number; info: FocusInfo | null }>> {
  const escapes: Array<{ step: number; info: FocusInfo | null }> = []
  for (let i = 0; i < steps; i++) {
    await page.keyboard.press('Tab')
    const inside = await container
      .evaluate((el) =>
        Boolean(el && document.activeElement && el.contains(document.activeElement)),
      )
      .catch(() => false)
    if (!inside) escapes.push({ step: i + 1, info: await focusInfo(page) })
  }
  return escapes
}

/** Every Tab-stop reachable inside a container (`tabIndex >= 0`). A sweep must
 *  be at least this long: a shorter sweep never reaches the far boundary and
 *  reports a false "focus stayed inside", which is how the palette's real
 *  escape (Tab #37) was missed before. */
async function focusableCount(page: Page, container: ReturnType<Page['locator']>): Promise<number> {
  return container
    .evaluate((el) =>
      el
        ? Array.from(
            el.querySelectorAll<HTMLElement>('a[href],button,input,select,textarea,[tabindex]'),
          ).filter((n) => n.tabIndex >= 0).length
        : 0,
    )
    .catch(() => 0)
}

test.beforeAll(() => {
  fs.mkdirSync(SHOT_DIR, { recursive: true })
})

test.beforeEach(async ({ page }) => {
  consoleErrors = []
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`))
})

// eslint-disable-next-line no-empty-pattern -- Playwright requires the fixture argument destructured
test.afterEach(async ({}, testInfo) => {
  if (consoleErrors.length) {
    await testInfo
      .attach('console-errors', { body: consoleErrors.join('\n'), contentType: 'text/plain' })
      .catch(() => undefined)
    console.log(
      `[persona-06] console errors (${consoleErrors.length}):\n${consoleErrors.join('\n')}`,
    )
  }
})

// ════════════════════════════════════════════════════════════════════════════
// (a) Skip target + first Tab stops + focus ring
// ════════════════════════════════════════════════════════════════════════════
test('(a) skip links are the first Tab stops, in order, each with the token focus ring', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(
    !reachable,
    `Served app not reachable at ${BASE} — start the runtime or set EPHE_E2E_BASE`,
  )

  const skipInput = page.getByRole('link', { name: SKIP_TO_INPUT })
  const skipContent = page.getByRole('link', { name: SKIP_TO_CONTENT })
  await expect(skipInput).toBeAttached({ timeout: 20_000 })
  await expect(skipContent).toBeAttached({ timeout: 20_000 })
  await capture(page, '01-initial-load')

  // The ring is a design token, not a hardcoded colour.
  const ringToken = String(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-ring').trim(),
    ),
  )
  expect
    .soft(
      ringToken.length,
      '--color-ring token must be defined (the program has exactly one focus ring)',
    )
    .toBeGreaterThan(0)
  await testInfo.attach('focus-ring-token', {
    body: `--color-ring = ${ringToken}`,
    contentType: 'text/plain',
  })

  const stops: FocusInfo[] = []
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    const info = await focusInfo(page)
    if (info) stops.push(info)
    expect
      .soft(
        hasVisibleRing(info),
        `Tab stop ${i + 1} shows no visible focus ring → ${describe(info)}`,
      )
      .toBeTruthy()
    if (i === 0) {
      await capture(page, '02-focus-01-skip-to-input')
      await captureRing(page, '02b-ring-skip-to-input')
    }
    if (i === 1) {
      await capture(page, '03-focus-02-skip-to-content')
      await captureRing(page, '03b-ring-skip-to-content')
    }
  }
  await capture(page, '04-focus-sequence')

  await testInfo.attach('tab-order', {
    body: stops.map((s, i) => `${i + 1}. ${describe(s)}`).join('\n'),
    contentType: 'text/plain',
  })

  // Order sanity: the two skip links come first (keyboard-only users get a way
  // past the ~30 header/sidebar stops before anything else grabs focus).
  expect
    .soft(stops[0]?.text ?? '', 'first Tab stop must be the skip-to-input link')
    .toContain(SKIP_TO_INPUT)
  expect
    .soft(stops[1]?.text ?? '', 'second Tab stop must be the skip-to-content link')
    .toContain(SKIP_TO_CONTENT)

  // The skip link must actually be revealed (sr-only → focus:not-sr-only).
  const box = await skipInput.boundingBox()
  expect
    .soft(box?.width ?? 0, 'focused skip link must be visibly laid out (not sr-only/clipped)')
    .toBeGreaterThan(0)

  // One Enter from the skip link lands the caret in the primary action.
  await skipInput.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator(COMPOSER_ID)).toBeFocused()
  await capture(page, '05-skip-target-composer-focused')
})

// ════════════════════════════════════════════════════════════════════════════
// (b) Command palette — keyboard round trip
// ════════════════════════════════════════════════════════════════════════════
test('(b) Ctrl/Cmd+K: palette opens with focus inside, ArrowDown/Enter select, Escape closes and returns focus to the invoker', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(!reachable, `Served app not reachable at ${BASE}`)
  test.skip(
    !(await chatShellReady(page)),
    'Chat shell absent (app is on /setup) — the palette needs the configured chat route',
  )

  const palette = page
    .locator('[role="dialog"][aria-modal="true"]')
    .filter({ has: page.locator(PALETTE_LISTBOX) })
  const combobox = page.locator(PALETTE_COMBOBOX)

  // Deterministic invoker: the skip link puts the caret in the composer.
  const skipInput = page.getByRole('link', { name: SKIP_TO_INPUT })
  await skipInput.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator(COMPOSER_ID)).toBeFocused()

  const opened = await openPalette(page, palette)
  expect(opened, 'Ctrl/Cmd+K must open the palette').toBe(true)
  await expect(palette).toBeVisible()
  await expect(combobox).toBeFocused()
  await capture(page, '06-palette-open')

  // The palette has selectable options and marks the first one.
  const options = palette.locator('#cmd-palette-listbox [role="option"]')
  const optionCount = await options.count()
  expect(optionCount, 'palette must expose at least one option').toBeGreaterThan(1)

  const act0 = await combobox.getAttribute('aria-activedescendant')
  expect.soft(act0, 'first option must be marked (cmd-opt-0)').toBe('cmd-opt-0')

  await page.keyboard.press('ArrowDown')
  const act1 = await combobox.getAttribute('aria-activedescendant')
  expect.soft(act1, `ArrowDown must move the marker (was ${act0})`).not.toBe(act0)
  expect
    .soft(
      await palette.locator(`#${act1}[aria-selected="true"]`).count(),
      'the moved-to row must be aria-selected',
    )
    .toBe(1)
  await capture(page, '07-palette-arrowdown')

  await page.keyboard.press('ArrowUp')
  expect
    .soft(await combobox.getAttribute('aria-activedescendant'), 'ArrowUp must move the marker back')
    .toBe(act0)

  // Escape closes and focus returns to the invoker (the audit's claim).
  await page.keyboard.press('Escape')
  await expect(palette).toBeHidden()
  const afterEscape = await focusInfo(page)
  await testInfo.attach('focus-after-palette-escape', {
    body: describe(afterEscape),
    contentType: 'text/plain',
  })
  expect
    .soft(afterEscape?.id, 'Escape must hand focus back to the palette invoker (the composer)')
    .toBe('ephe-chat-input')
  await capture(page, '08-palette-closed-focus-returned')

  // Enter selects: reopening and committing must close the palette.
  const reopened = await openPalette(page, palette)
  expect(reopened, 'palette must reopen').toBe(true)
  await expect(combobox).toBeFocused()
  const activeBeforeEnter = await combobox.getAttribute('aria-activedescendant')
  const activeLabel = activeBeforeEnter
    ? await palette
        .locator(`#${activeBeforeEnter}`)
        .innerText()
        .catch(() => '')
    : ''
  await page.keyboard.press('Enter')
  await expect(palette).toBeHidden()
  await testInfo.attach('enter-selection', {
    body: `Enter committed ${activeBeforeEnter} ${activeLabel.replace(/\s+/g, ' ').trim()}`,
    contentType: 'text/plain',
  })
  await capture(page, '08b-palette-after-enter')
})

// ════════════════════════════════════════════════════════════════════════════
// (c) Settings overlay — keyboard open / tab-trap / inert background / handback
// ════════════════════════════════════════════════════════════════════════════
test('(c) settings overlay: opens by keyboard, focus stays inside, background is inert, Escape closes and hands focus back', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(!reachable, `Served app not reachable at ${BASE}`)
  test.skip(
    !(await chatShellReady(page)),
    'Chat shell absent (app is on /setup) — settings needs the configured chat route',
  )

  const dialog = page.locator(SETTINGS_PAGE)
  const sidebarSettings = page.locator(SIDEBAR_SETTINGS)

  // The shell's only settings entry is the sidebar footer button.
  if (!(await sidebarSettings.isVisible().catch(() => false))) {
    const expand = page.locator('[data-testid="sidebar-expand-toggle"]')
    if (await expand.isVisible().catch(() => false)) {
      await expand.focus()
      await page.keyboard.press('Enter')
    }
  }
  await expect(sidebarSettings).toBeVisible()
  await sidebarSettings.focus()
  await page.keyboard.press('Enter')

  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAttribute('role', 'dialog')
  await expect(dialog).toHaveAttribute('aria-modal', 'true')

  // Initial focus is inside the dialog (first focusable = the back button).
  await expect(page.locator(SETTINGS_BACK)).toBeFocused()
  await testInfo.attach('settings-initial-focus', {
    body: describe(await focusInfo(page)),
    contentType: 'text/plain',
  })

  // The background must be inert while the dialog is open.
  await expect(page.locator(MAIN_CONTENT)).toHaveAttribute('inert', '')
  await expect(page.locator(MAIN_CONTENT)).toHaveAttribute('aria-hidden', 'true')
  await expect(page.locator('[data-testid="chat-sidebar"]')).toHaveAttribute('inert', '')
  await capture(page, '09-settings-open-background-inert')

  // Tab must stay inside.
  const focusables = await focusableCount(page, dialog)
  const escapes = await sweepTab(page, dialog, focusables + 4)
  await capture(page, '10-settings-tab-trap')
  await testInfo.attach('settings-tab-escapes', {
    body:
      `settings focusable stops = ${focusables}; swept ${focusables + 4}\n` +
      (escapes.length
        ? escapes.map((e) => `step ${e.step}: ${describe(e.info)}`).join('\n')
        : 'none — focus stayed inside'),
    contentType: 'text/plain',
  })
  expect.soft(escapes, 'Tab must not leave the settings dialog').toEqual([])

  // Escape closes and focus is handed back to the invoker.
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  const afterClose = await focusInfo(page)
  await testInfo.attach('focus-after-settings-close', {
    body: describe(afterClose),
    contentType: 'text/plain',
  })
  expect
    .soft(
      afterClose?.testid,
      'closing settings must return focus to its invoker (sidebar settings button)',
    )
    .toBe('sidebar-settings-btn')
  await capture(page, '11-settings-closed-focus-returned')
})

// ════════════════════════════════════════════════════════════════════════════
// (d1) CommandPalette claims role=dialog aria-modal — does Tab stay inside?
// ════════════════════════════════════════════════════════════════════════════
test('(d1) CommandPalette declares aria-modal but does not trap Tab (known defect — soft evidence)', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(!reachable, `Served app not reachable at ${BASE}`)
  test.skip(!(await chatShellReady(page)), 'Chat shell absent (app is on /setup)')

  const palette = page
    .locator('[role="dialog"][aria-modal="true"]')
    .filter({ has: page.locator(PALETTE_LISTBOX) })
  expect(await openPalette(page, palette), 'palette must open').toBe(true)
  await expect(page.locator(PALETTE_COMBOBOX)).toBeFocused()

  const optionCount = await palette.locator('#cmd-palette-listbox [role="option"]').count()
  const focusables = await focusableCount(page, palette)
  // Sweep past the last focusable stop: the palette has ~37 stops, so a
  // capped sweep of 25 never reached the boundary and gave a false all-clear.
  const escapes = await sweepTab(page, palette, focusables + 4)
  if (escapes.length) await capture(page, '12-palette-tab-escaped')
  await testInfo.attach('palette-tab-escapes', {
    body:
      `palette focusable stops = ${focusables} (${optionCount} option rows)\n` +
      (escapes.length
        ? escapes.map((e) => `Tab #${e.step} escaped to → ${describe(e.info)}`).join('\n')
        : 'none — focus stayed inside'),
    contentType: 'text/plain',
  })
  // The requirement: an aria-modal surface keeps Tab inside. A failure here is
  // the measured defect, not a broken test.
  expect
    .soft(
      escapes.length,
      `aria-modal palette must trap Tab; focus escaped ${escapes.length}x → ${escapes.map((e) => describe(e.info)).join(' | ')}`,
    )
    .toBe(0)
})

// ════════════════════════════════════════════════════════════════════════════
// (d2) ArtifactRail claims role=dialog aria-modal — does Tab stay inside?
// ════════════════════════════════════════════════════════════════════════════
test('(d2) ArtifactRail declares aria-modal but does not trap Tab (known defect — soft evidence)', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(!reachable, `Served app not reachable at ${BASE}`)
  test.skip(!(await chatShellReady(page)), 'Chat shell absent (app is on /setup)')

  const toggle = page.locator(RAIL_TOGGLE)
  test.skip(
    !(await toggle.isVisible().catch(() => false)),
    'ArtifactRail toggle not visible at this viewport (desktop-only control)',
  )

  const modal = page.locator(RAIL_MODAL)
  await toggle.focus()
  await page.keyboard.press('Enter')
  await expect(modal).toBeVisible()
  await expect(modal).toHaveAttribute('role', 'dialog')
  await expect(modal).toHaveAttribute('aria-modal', 'true')
  await capture(page, '13-rail-open')

  // Contrast with settings: the rail does NOT inert the page behind it.
  const backgroundInert = await page.locator(MAIN_CONTENT).getAttribute('inert')
  await testInfo.attach('rail-background-inert', {
    body: `#main-content inert = ${JSON.stringify(backgroundInert)} (settings sets "" here; the rail does not)`,
    contentType: 'text/plain',
  })

  const focusables = await focusableCount(page, modal)
  const escapes = await sweepTab(page, modal, focusables + 4)
  if (escapes.length) await capture(page, '14-rail-tab-escaped')
  await testInfo.attach('rail-tab-escapes', {
    body:
      `rail focusable stops = ${focusables}; swept ${focusables + 4}\n` +
      (escapes.length
        ? escapes.map((e) => `Tab #${e.step} escaped to → ${describe(e.info)}`).join('\n')
        : 'none — focus stayed inside'),
    contentType: 'text/plain',
  })
  expect
    .soft(
      escapes.length,
      `aria-modal rail must trap Tab; focus escaped ${escapes.length}x → ${escapes.map((e) => describe(e.info)).join(' | ')}`,
    )
    .toBe(0)

  // Escape still closes it (that part works).
  await page.keyboard.press('Escape')
  await expect(modal).toBeHidden()
  await capture(page, '15-rail-closed')
})

// ════════════════════════════════════════════════════════════════════════════
// (extra) Focus handback when settings is opened FROM the palette
// ════════════════════════════════════════════════════════════════════════════
test('(extra) settings opened from the palette: where does focus land after closing?', async ({
  page,
}, testInfo) => {
  const reachable = await gotoApp(page)
  test.skip(!reachable, `Served app not reachable at ${BASE}`)
  test.skip(!(await chatShellReady(page)), 'Chat shell absent (app is on /setup)')

  const palette = page
    .locator('[role="dialog"][aria-modal="true"]')
    .filter({ has: page.locator(PALETTE_LISTBOX) })
  const combobox = page.locator(PALETTE_COMBOBOX)
  expect(await openPalette(page, palette), 'palette must open').toBe(true)
  await expect(combobox).toBeFocused()

  // Narrow to the settings command and commit it (English labels only needed
  // for the agent's own reporting — the commit is language-independent).
  await combobox.fill('settings')
  await page.waitForTimeout(250)
  const firstOption = palette.locator('#cmd-palette-listbox [role="option"]').first()
  const firstLabel = (await firstOption.innerText().catch(() => '')).replace(/\s+/g, ' ').trim()
  await page.keyboard.press('Enter')

  const dialog = page.locator(SETTINGS_PAGE)
  await expect(dialog).toBeVisible()
  await capture(page, '16-settings-opened-from-palette')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  const after = await focusInfo(page)
  const connected = await page
    .evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      return Boolean(el && el.isConnected && el !== document.body)
    })
    .catch(() => false)
  await testInfo.attach('focus-after-palette-opened-settings', {
    body: `committed "${firstLabel}" (${firstOption ? 'via palette' : ''})\nfocus after close → ${describe(after)}\nlands on a real element: ${connected}`,
    contentType: 'text/plain',
  })
  // The settings invoker here is the palette's combobox, which unmounts when the
  // palette closes — so the handback target is gone. Requirement: focus must
  // still land somewhere usable (not <body>).
  expect
    .soft(
      connected,
      `after closing settings, focus >must< land on a connected element (not <body>) → ${describe(after)}`,
    )
    .toBe(true)
  await capture(page, '17-settings-from-palette-closed')
})
