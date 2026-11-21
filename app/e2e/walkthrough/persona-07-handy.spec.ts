/**
 * Persona 07 — "Handy": a user on a phone, 390 x 844 (iPhone-class).
 *
 * Live walkthrough: a real server, a real engine, NO route interception. Every
 * step is captured as a full-page screenshot at 390 px into the walkthrough capture
 * dir (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/persona-07-handy/.
 *
 * What this measures, in the persona's own terms:
 *   01  the shell at 390 — is the chat reachable, does anything scroll sideways,
 *       and which chrome silently vanishes on a phone (desktop-only inventory)
 *   02  the sidebar: a drawer with a backdrop at this width, reachable targets,
 *       and both close paths (tap-away and the X)
 *   03  the composer: usable without horizontal scrolling, every primary control
 *       at or above the 44 px touch floor
 *   04  the status bar: it reflows (flex-wrap) instead of overflowing, and the
 *       mobile-only token chip replaces the desktop breakdown button
 *   05  the settings overlay: full-screen at 390, scrollable, reachable — and
 *       how its header/save controls measure against the 44 px floor
 *   06  a real round trip: the user bubble and the streamed answer stay inside
 *       390 px and the message column never scrolls sideways
 *
 * Every measurement (touch targets, overflow offenders, console errors) is
 * written to <out-dir>/measurements.json so notes.md can cite real numbers.
 *
 * Run (dev server + live backend on 127.0.0.1:8765 via the Vite proxy):
 *   cd app && npx playwright test -c playwright.config.ts e2e/walkthrough/persona-07-handy.spec.ts
 * Run (static dist on 127.0.0.1:9199):
 *   cd app && npx playwright test -c tests/playwright/playwright.config.ts \
 *     ../e2e/walkthrough/persona-07-handy.spec.ts --project=chromium
 */
import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

const OUT_DIR = walkthroughOutDir('persona-07-handy')

const VIEWPORT = { width: 390, height: 844 }
/** The persona rule: anything tappable smaller than this is a defect. */
const TOUCH_FLOOR = 44
/** WCAG 2.5.8 (AA) minimum target size — a hard loss below this. */

// Phone emulation, file-scoped: overrides the config's Desktop Chrome project.
test.use({
  viewport: VIEWPORT,
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  colorScheme: 'dark',
  // A click on an element that never becomes actionable must fail fast and
  // legibly instead of silently eating the whole 300s test budget (observed:
  // a run hung 300s inside an unbounded click with no screenshot written).
  actionTimeout: 15_000,
})

// ── evidence plumbing ────────────────────────────────────────────────────────

const measurements: Record<string, unknown> = {}

function record(key: string, value: unknown): void {
  measurements[key] = value
}

function flushMeasurements(): void {
  mkdirSync(OUT_DIR, { recursive: true })
  writeFileSync(
    path.join(OUT_DIR, 'measurements.json'),
    `${JSON.stringify(measurements, null, 2)}\n`,
    'utf8',
  )
}

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(OUT_DIR, { recursive: true })
  const file = path.join(OUT_DIR, name)
  // The shell is a fixed 390x844 app: the document never exceeds the viewport
  // (measured: documentElement.scrollHeight === 844 on every step), so a
  // viewport capture is pixel-identical to a full-page one — while avoiding the
  // full-page re-layout path, which stalls when several walkthrough browsers
  // run at once (observed as page.screenshot timeouts). `animations: 'disabled'`
  // freezes the streaming spinner / caret pulse so the frame is stable.
  const opts = { animations: 'disabled', caret: 'hide', timeout: 60_000 } as const
  try {
    await page.screenshot({ path: file, fullPage: false, ...opts })
  } catch {
    // One retry: capture starvation under concurrent load is transient.
    await page.screenshot({ path: file, fullPage: false, ...opts })
  }
}

/** Collects uncaught exceptions and console errors for the note's error section. */
function watchConsole(page: Page, sink: string[]): void {
  page.on('console', (m) => {
    if (m.type() === 'error') sink.push(`console.error: ${m.text()}`)
  })
  page.on('pageerror', (e) => sink.push(`pageerror: ${e.message}`))
}

function pageErrors(errors: string[]): string[] {
  return errors.filter((e) => e.startsWith('pageerror'))
}

// ── probes (all run in the page, so they see real layout) ────────────────────

type OverflowOffender = {
  tag: string
  testid: string | null
  label: string
  left: number
  right: number
  width: number
}
type OverflowProbe = {
  viewport: number
  docScrollWidth: number
  docClientWidth: number
  horizontalOverflowPx: number
  offenders: OverflowOffender[]
}

/**
 * Document-level horizontal overflow plus the elements that stick out past the
 * right edge. The mobile drawer parks off-canvas at x = -320 while closed, so
 * the sidebar subtree is excluded — that is a design state, not an overflow.
 */
async function probeOverflow(page: Page): Promise<OverflowProbe> {
  return page.evaluate(() => {
    const vw = window.innerWidth
    const de = document.documentElement
    const offenders: OverflowOffender[] = []
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      if (el.closest('[data-testid="chat-sidebar"]')) continue
      const r = el.getBoundingClientRect()
      if (r.width < 2 || r.height < 2) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue
      if (r.right > vw + 1 || r.left < -1) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          testid: el.getAttribute('data-testid'),
          label: (el.getAttribute('aria-label') ?? el.textContent ?? '')
            .trim()
            .replace(/\s+/g, ' ')
            .slice(0, 40),
          left: Math.round(r.left),
          right: Math.round(r.right),
          width: Math.round(r.width),
        })
        if (offenders.length >= 25) break
      }
    }
    return {
      viewport: vw,
      docScrollWidth: de.scrollWidth,
      docClientWidth: de.clientWidth,
      horizontalOverflowPx: de.scrollWidth - de.clientWidth,
      offenders,
    }
  })
}

type TouchTarget = {
  tag: string
  testid: string | null
  label: string
  width: number
  height: number
  minDim: number
  zone: 'drawer' | 'settings' | 'chat'
  belowFloor44: boolean
  belowWcagAA24: boolean
}

/** Every visible, enabled interactive element with its real box and zone. */
async function scanTouchTargets(page: Page): Promise<TouchTarget[]> {
  return page.evaluate(() => {
    const SELECTOR = [
      'button',
      'a[href]',
      'input:not([type="hidden"])',
      'textarea',
      'select',
      'summary',
      '[role="button"]',
      '[role="menuitem"]',
      '[role="menuitemradio"]',
      '[role="menuitemcheckbox"]',
      '[role="tab"]',
      '[role="switch"]',
      '[role="checkbox"]',
    ].join(', ')
    const out: TouchTarget[] = []
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(SELECTOR))) {
      const r = el.getBoundingClientRect()
      if (r.width < 1 || r.height < 1) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue
      if (r.right <= 0 || r.left >= window.innerWidth) continue // fully off-screen (closed drawer)
      if (el instanceof HTMLButtonElement && el.disabled) continue
      const width = Number(r.width.toFixed(1))
      const height = Number(r.height.toFixed(1))
      const minDim = Math.min(width, height)
      out.push({
        tag: el.tagName.toLowerCase(),
        testid: el.getAttribute('data-testid'),
        label: (el.getAttribute('aria-label') ?? el.getAttribute('title') ?? el.textContent ?? '')
          .trim()
          .replace(/\s+/g, ' ')
          .slice(0, 40),
        width,
        height,
        minDim,
        zone: el.closest('[data-testid="settings-page"]')
          ? 'settings'
          : el.closest('[data-testid="chat-sidebar"]')
            ? 'drawer'
            : 'chat',
        belowFloor44: minDim < 44,
        belowWcagAA24: minDim < 24,
      })
    }
    return out
  })
}

type Box = { x: number; y: number; width: number; height: number }

/** Playwright's boundingBox has no `right`; compute it and fail loudly if null. */
function rightEdge(box: Box | null): number {
  expect(box, 'element must be laid out for a box measurement').not.toBeNull()
  return box!.x + box!.width
}

/** Asserts one control against the 44 px floor (optionally in both dimensions). */
async function expectFloor(
  page: Page,
  testid: string,
  opts: { width?: boolean } = {},
): Promise<void> {
  const box = await page.getByTestId(testid).boundingBox()
  expect(box, `#${testid} must be laid out`).not.toBeNull()
  expect(box!.height, `${testid} height >= ${TOUCH_FLOOR}px`).toBeGreaterThanOrEqual(TOUCH_FLOOR)
  if (opts.width) {
    expect(box!.width, `${testid} width >= ${TOUCH_FLOOR}px`).toBeGreaterThanOrEqual(TOUCH_FLOOR)
  }
}

/** Chrome that only exists from md/lg/sm up — it must not appear at 390. */
const DESKTOP_ONLY = [
  'header-sidebar-toggle', // hidden md:inline-flex
  'header-new-session', // hidden md:inline-flex
  'session-nav-back', // hidden md:flex
  'session-nav-forward', // hidden md:flex
  'header-update', // inside a hidden md:flex island
  'header-theme', // inside the same island
  'header-help', // inside the same island
  'header-palette', // inside the same island
  'side-panel-toggle', // hidden md:inline-flex
  'artifact-library-toggle', // hidden md:inline-flex
  'toolbar-palette', // hidden md:inline-flex
  'toolbar-meta', // hidden md:flex
  'statusbar-breakdown-toggle', // hidden md:flex
]
/** Chrome that only exists below md — a phone must show it. */
const MOBILE_ONLY = ['header-menu-toggle', 'statusbar-tok-chip']

// ── navigation ───────────────────────────────────────────────────────────────

const CHAT_PATH = '/#/chat'

/** Forces the English shell before the app boots. The look has no stored mode to set. */
async function primeStorage(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('i18nextLng', 'en') // deterministic shell language
    } catch {
      /* storage can be blocked; the default look is used then */
    }
  })
}

/**
 * Opens the chat against the live server (no mocking) and waits for the shell.
 * When the backend is unconfigured the first-run gate redirects to /setup,
 * which the caller sees as a missing composer.
 */
async function openChat(page: Page): Promise<{ attempts: number; reachedEmpty: boolean }> {
  await primeStorage(page)
  await page.goto(CHAT_PATH, { waitUntil: 'domcontentloaded' })
  await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 30_000 })
  return startOwnSession(page)
}

/**
 * `/#/chat` restores `ephe.lastSession`, else the most recently updated session.
 * The product backend is SHARED with every other walkthrough running at the
 * same time, so that restore regularly lands on a session another run is
 * streaming into right now — a page that never stops animating (measured: it
 * hangs a fullPage capture, see `shot`) and whose bubbles are not this run's
 * (measured: test 06 matched a foreign prompt). Starting a "New task" makes the
 * evidence belong to this persona; under load the switch can lose the race, so
 * it is repeated until the message list is actually empty. Leaves the drawer shut.
 */
async function startOwnSession(page: Page): Promise<{ attempts: number; reachedEmpty: boolean }> {
  const backdrop = page.getByTestId('sidebar-backdrop')
  const drawer = page.getByTestId('chat-sidebar')
  const bubbles = page.locator('[data-testid="message-bubble"]')
  let attempts = 0
  for (; attempts < 4; attempts++) {
    await openDrawer(page)
    await page.getByTestId('new-session').click({ timeout: 15_000 })
    // Picking "New task" does NOT close the drawer at 390 (measured: the
    // backdrop is still mounted after the pick). A phone user taps away.
    await page.waitForTimeout(400)
    if (await backdrop.isVisible().catch(() => false)) {
      await backdrop.click({ position: { x: VIEWPORT.width - 12, y: 520 } })
    }
    await expect
      .poll(async () => (await drawer.boundingBox())?.x ?? 0, { timeout: 10_000 })
      .toBeLessThan(0)
    await expect(backdrop).toHaveCount(0, { timeout: 10_000 })
    // Give the create hook time to settle before trusting the empty list.
    await page.waitForTimeout(500)
    if ((await bubbles.count()) === 0) return { attempts: attempts + 1, reachedEmpty: true }
  }
  return { attempts, reachedEmpty: false }
}

/** Idempotent: opens the drawer only when it is not already open. */
async function openDrawer(page: Page): Promise<void> {
  const backdrop = page.getByTestId('sidebar-backdrop')
  if (!(await backdrop.isVisible().catch(() => false))) {
    await page.getByTestId('header-menu-toggle').click({ timeout: 15_000 })
    await expect(backdrop).toBeVisible({ timeout: 10_000 })
  }
}

test.describe('Persona 07 · Handy — 390 x 844 walkthrough', () => {
  test.afterEach(() => {
    flushMeasurements()
  })

  test('01 · shell at 390 — reachable, no sideways scroll, desktop chrome gone', async ({
    page,
  }) => {
    const errors: string[] = []
    watchConsole(page, errors)

    // Capture whatever the live environment renders BEFORE asserting, so a
    // first-run redirect still leaves evidence in the folder.
    await primeStorage(page)
    await page.goto(CHAT_PATH, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2_000)
    await shot(page, '01-chat-first-paint-390.png')

    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 30_000 })

    // Reachability: the drawer trigger is the phone's only way into the sidebar.
    await expect(page.getByTestId('header-menu-toggle')).toBeVisible()
    await expectFloor(page, 'header-menu-toggle', { width: true })

    // The phone shell carries the composer and the status row.
    await expect(page.getByTestId('composer-actions-row')).toBeVisible()
    await expect(page.getByTestId('status-bar')).toBeVisible()

    const visibleDesktopOnly: string[] = []
    const hiddenDesktopOnly: string[] = []
    for (const id of DESKTOP_ONLY) {
      const visible = await page
        .getByTestId(id)
        .isVisible()
        .catch(() => false)
      ;(visible ? visibleDesktopOnly : hiddenDesktopOnly).push(id)
    }
    const visibleMobileOnly: string[] = []
    for (const id of MOBILE_ONLY) {
      if (
        await page
          .getByTestId(id)
          .isVisible()
          .catch(() => false)
      )
        visibleMobileOnly.push(id)
    }

    const probe = await probeOverflow(page)
    const targets = await scanTouchTargets(page)
    const below44 = targets.filter((t) => t.belowFloor44)
    const below24 = targets.filter((t) => t.belowWcagAA24)

    record('01_shell', {
      probe,
      desktopOnlyVisible: visibleDesktopOnly,
      desktopOnlyHidden: hiddenDesktopOnly,
      mobileOnlyVisible: visibleMobileOnly,
      targetsScanned: targets.length,
      belowFloor44: below44.map((t) => ({
        testid: t.testid,
        label: t.label,
        w: t.width,
        h: t.height,
        zone: t.zone,
      })),
      belowWcagAA24: below24.map((t) => ({ testid: t.testid, label: t.label })),
    })
    record('01_consoleErrors', errors)
    test.info().annotations.push({
      type: 'touch-targets-below-44',
      description: JSON.stringify(
        below44.map((t) => `${t.zone}:${t.testid ?? t.label} ${t.width}x${t.height}`),
      ),
    })

    await shot(page, '02-chat-shell-390.png')

    expect(
      probe.horizontalOverflowPx,
      `document must not scroll horizontally at 390: ${JSON.stringify(probe)}`,
    ).toBeLessThanOrEqual(0)
    expect(visibleDesktopOnly, 'desktop-only chrome must be hidden at 390').toEqual([])
    expect(pageErrors(errors), 'no uncaught exceptions on load').toEqual([])
  })

  test('02 · sidebar is a drawer — reach it, tap targets, both close paths', async ({ page }) => {
    const errors: string[] = []
    watchConsole(page, errors)
    await openChat(page)

    const drawer = page.getByTestId('chat-sidebar')
    const backdrop = page.getByTestId('sidebar-backdrop')

    // Closed: parked off-canvas, no backdrop, no horizontal page scroll.
    await expect
      .poll(async () => (await drawer.boundingBox())?.x ?? -999, { timeout: 5_000 })
      .toBeLessThan(0)
    expect(await backdrop.isVisible().catch(() => false)).toBe(false)
    record('02_drawer_closed_x', (await drawer.boundingBox())?.x ?? null)

    // Open via the header trigger.
    await page.getByTestId('header-menu-toggle').click()
    await expect(backdrop).toBeVisible()
    await expect
      .poll(async () => (await drawer.boundingBox())?.x ?? -999)
      .toBeGreaterThanOrEqual(-1)

    const openBox = await drawer.boundingBox()
    expect(openBox).not.toBeNull()
    const drawerRight = openBox!.x + openBox!.width

    // The mobile drawer is a modal dialog and must fit the phone.
    await expect(drawer).toHaveAttribute('role', 'dialog')
    await expect(drawer).toHaveAttribute('aria-modal', 'true')
    expect(openBox!.width, 'drawer fits 390').toBeLessThanOrEqual(VIEWPORT.width)
    expect(openBox!.height, 'drawer is full height').toBeGreaterThanOrEqual(VIEWPORT.height - 1)

    await shot(page, '03-sidebar-drawer-open-390.png')

    // Primary drawer affordances are reachable and meet the floor.
    await expect(page.getByTestId('new-session')).toBeVisible()
    await expectFloor(page, 'new-session')
    await expectFloor(page, 'sidebar-settings-btn')
    const closeBtn = drawer.getByRole('button', { name: 'Close' }).first()
    await expect(closeBtn).toBeVisible()
    const closeBox = await closeBtn.boundingBox()
    expect(closeBox!.height, 'drawer close height >= 44').toBeGreaterThanOrEqual(TOUCH_FLOOR)
    expect(closeBox!.width, 'drawer close width >= 44').toBeGreaterThanOrEqual(TOUCH_FLOOR)

    const drawerSearch = drawer.locator('input').first()
    if (await drawerSearch.isVisible().catch(() => false)) {
      const sb = await drawerSearch.boundingBox()
      record('02_drawer_search_box', sb)
      expect(rightEdge(sb), 'search field inside the drawer').toBeLessThanOrEqual(drawerRight + 1)
    }

    const targets = await scanTouchTargets(page)
    const inDrawer = targets.filter((t) => t.zone === 'drawer')
    record('02_drawer_targets', inDrawer)
    record(
      '02_drawer_below44',
      inDrawer
        .filter((t) => t.belowFloor44)
        .map((t) => ({
          testid: t.testid,
          label: t.label,
          w: t.width,
          h: t.height,
        })),
    )
    record('02_consoleErrors', errors)

    // Close path 1 — tap away on the backdrop (right of the 288px drawer).
    await backdrop.click({ position: { x: VIEWPORT.width - 12, y: 520 } })
    await expect
      .poll(async () => (await drawer.boundingBox())?.x ?? 0, { timeout: 5_000 })
      .toBeLessThan(0)
    await expect(backdrop).toHaveCount(0)
    await shot(page, '04-sidebar-closed-390.png')

    // Close path 2 — reopen and use the X.
    await page.getByTestId('header-menu-toggle').click()
    await expect(backdrop).toBeVisible()
    await expect
      .poll(async () => (await drawer.boundingBox())?.x ?? -999)
      .toBeGreaterThanOrEqual(-1)
    await closeBtn.click()
    await expect(backdrop).toHaveCount(0)
    await expect.poll(async () => (await drawer.boundingBox())?.x ?? 0).toBeLessThan(0)

    expect(pageErrors(errors), 'no uncaught exceptions in the drawer flow').toEqual([])
  })

  test('03 · composer — usable at 390 without horizontal scrolling', async ({ page }) => {
    const errors: string[] = []
    watchConsole(page, errors)
    await openChat(page)

    const row = page.getByTestId('composer-actions-row')
    await expect(row).toBeVisible()
    const rowBox = await row.boundingBox()
    expect(rightEdge(rowBox), 'action row stays inside 390').toBeLessThanOrEqual(VIEWPORT.width + 1)

    // The primary controls: square icon buttons must be 44x44, the mode chip 44 tall.
    await expectFloor(page, 'composer-attach-plus', { width: true })
    await expectFloor(page, 'model-chip', { width: true })
    await expectFloor(page, 'send-btn', { width: true })
    await expectFloor(page, 'composer-mode-selector')

    // The text field is inside the viewport and is a comfortable tap target.
    const input = page.getByTestId('chat-input')
    const inputBox = await input.boundingBox()
    expect(rightEdge(inputBox), 'input stays inside 390').toBeLessThanOrEqual(VIEWPORT.width + 1)
    expect(inputBox!.height, 'input height >= 44').toBeGreaterThanOrEqual(TOUCH_FLOOR)

    await input.click()
    await input.fill('Phone persona: is this composer usable without horizontal scrolling?')
    await shot(page, '05-composer-390.png')

    const probe = await probeOverflow(page)
    const targets = await scanTouchTargets(page)
    record('03_composer', {
      rowBox,
      inputBox,
      probe,
      below44: targets
        .filter((t) => t.zone === 'chat' && t.belowFloor44)
        .map((t) => ({ testid: t.testid, label: t.label, w: t.width, h: t.height })),
    })
    record('03_consoleErrors', errors)

    expect(
      probe.horizontalOverflowPx,
      `composer must not force sideways scroll: ${JSON.stringify(probe.offenders)}`,
    ).toBeLessThanOrEqual(0)
    expect(pageErrors(errors)).toEqual([])
  })

  test('04 · status bar — reflows at 390, mobile token chip replaces the desktop one', async ({
    page,
  }) => {
    const errors: string[] = []
    watchConsole(page, errors)
    await openChat(page)

    const bar = page.getByTestId('status-bar')
    await expect(bar).toBeVisible()
    const box = await bar.boundingBox()
    expect(rightEdge(box), 'status bar stays inside 390').toBeLessThanOrEqual(VIEWPORT.width + 1)
    expect(box!.height, 'status bar wrapped to more than one line').toBeGreaterThan(0)

    await expect(page.getByTestId('statusbar-meter')).toBeVisible()
    await expect(page.getByTestId('statusbar-percent')).toBeVisible()
    // md:hidden — the phone's equivalent of the desktop breakdown button.
    await expect(page.getByTestId('statusbar-tok-chip')).toBeVisible()
    expect(
      await page
        .getByTestId('statusbar-breakdown-toggle')
        .isVisible()
        .catch(() => false),
      'the md:flex breakdown button is desktop-only',
    ).toBe(false)

    await shot(page, '06-status-bar-390.png')

    const probe = await probeOverflow(page)
    const targets = await scanTouchTargets(page)
    record('04_status_bar', {
      box,
      probe,
      statusBarTargets: targets.filter(
        (t) =>
          t.testid?.startsWith('statusbar') ||
          t.testid?.startsWith('composer-status') ||
          t.testid === 'statusbar-tok-chip',
      ),
    })
    record('04_consoleErrors', errors)

    expect(
      probe.horizontalOverflowPx,
      `status row must not force sideways scroll: ${JSON.stringify(probe.offenders)}`,
    ).toBeLessThanOrEqual(0)
    expect(pageErrors(errors)).toEqual([])
  })

  test('05 · settings overlay at 390 — full screen, scrollable, reachable', async ({ page }) => {
    const errors: string[] = []
    watchConsole(page, errors)
    await openChat(page)

    await openDrawer(page)
    await page.getByTestId('sidebar-settings-btn').click({ timeout: 15_000 })

    const overlay = page.getByTestId('settings-page')
    await expect(overlay).toBeVisible({ timeout: 15_000 })

    // Opening settings from the drawer closes the drawer (z-order guard, R16).
    expect(
      await page
        .getByTestId('sidebar-backdrop')
        .isVisible()
        .catch(() => false),
      'drawer closed while settings is open',
    ).toBe(false)

    const box = await overlay.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x, 'settings overlay starts at the left edge').toBeGreaterThanOrEqual(-1)
    expect(box!.width, 'settings overlay fits 390').toBeLessThanOrEqual(VIEWPORT.width)
    expect(box!.height, 'settings overlay is full height').toBeGreaterThanOrEqual(
      VIEWPORT.height - 1,
    )

    // The body mounts with a loading spinner while the register is fetched; wait
    // it out (bounded) so the evidence shows the real Engine section rather than
    // the loading state. If the register is slow the step still captures what is
    // there — the screenshot, never a guess, is the finding.
    await page
      .getByTestId('settings-engine-state')
      .waitFor({ state: 'visible', timeout: 20_000 })
      .catch(() => {})
    record(
      '05_settings_engine_content_loaded',
      await page
        .getByTestId('settings-engine-state')
        .isVisible()
        .catch(() => false),
    )

    await shot(page, '07-settings-overlay-390.png')

    // Header controls are reachable (Back is the phone's only way out).
    await expect(page.getByTestId('settings-back')).toBeVisible()
    await expect(page.getByTestId('settings-help')).toBeVisible()

    const panel = page.getByTestId('settings-panel')
    await expect(panel).toBeVisible()
    const panelBox = await panel.boundingBox()
    expect(rightEdge(panelBox), 'the settings content column stays inside 390').toBeLessThanOrEqual(
      VIEWPORT.width + 1,
    )

    // The nav is a horizontal snap strip below md — scroll it and re-shoot.
    const nav = page.getByTestId('settings-nav-group-model')
    if (await nav.isVisible().catch(() => false)) {
      await nav.evaluate((el) => el.scrollIntoView({ inline: 'start', block: 'nearest' }))
    }
    await shot(page, '08-settings-nav-390.png')

    const save = page.getByTestId('settings-save')
    if (await save.isVisible().catch(() => false)) {
      const sb = await save.boundingBox()
      record('05_settings_save_box', sb)
      expect(rightEdge(sb), 'save button inside 390').toBeLessThanOrEqual(VIEWPORT.width + 1)
    }

    const targets = await scanTouchTargets(page)
    const inSettings = targets.filter((t) => t.zone === 'settings')
    record('05_settings_targets', inSettings)
    record(
      '05_settings_below44',
      inSettings
        .filter((t) => t.belowFloor44)
        .map((t) => ({
          testid: t.testid,
          label: t.label,
          w: t.width,
          h: t.height,
        })),
    )
    record(
      '05_settings_below24',
      inSettings.filter((t) => t.belowWcagAA24).map((t) => t.testid),
    )
    const probe = await probeOverflow(page)
    record('05_settings_probe', probe)
    record('05_consoleErrors', errors)

    expect(
      probe.horizontalOverflowPx,
      `settings must not force sideways scroll: ${JSON.stringify(probe.offenders)}`,
    ).toBeLessThanOrEqual(0)

    // Back to the chat.
    await page.getByTestId('settings-back').click()
    await expect(overlay).toBeHidden()
    await expect(page.getByTestId('chat-input')).toBeVisible()
    await shot(page, '09-settings-closed-390.png')

    expect(pageErrors(errors), 'no uncaught exceptions in the settings flow').toEqual([])
  })

  test('06 · real round trip at 390 — user + streamed answer inside the viewport', async ({
    page,
  }) => {
    const errors: string[] = []
    watchConsole(page, errors)
    const started = await openChat(page)

    // The backend is shared with the other walkthroughs; the evidence must be
    // this run's. A foreign session from another live run would put its bubbles
    // in the DOM (measured: a persona-04 prompt was matched here before the guard).
    const bubbles = page.locator('[data-testid="message-bubble"]')
    const foreignAtStart = await bubbles.count()
    record('06_session_start', started)
    record('06_foreign_bubbles_at_start', foreignAtStart)
    expect(foreignAtStart, 'the round trip must run in this run’s own, empty session').toBe(0)

    const token = `phone-${Date.now().toString(36)}`
    const input = page.getByTestId('chat-input')
    await input.click()
    await input.fill(
      `Persona 07 on a phone: reply with one short sentence saying hello. (${token})`,
    )
    await shot(page, '10-composer-filled-390.png')

    const assistantBubbles = page.locator('[data-testid="message-bubble"][data-role="assistant"]')
    const assistantsBefore = await assistantBubbles.count()

    await page.getByTestId('send-btn').click()

    // The user bubble is client-side, but it matches on the per-run token rather
    // than DOM order, so a foreign bubble can never pass for this run's prompt.
    const userBubble = page
      .locator('[data-testid="message-bubble"][data-role="user"]')
      .filter({ hasText: token })
      .first()
    await expect(userBubble).toBeVisible({ timeout: 30_000 })
    await shot(page, '11-user-bubble-390.png')

    // The live engine streams the answer back (no mocking anywhere): exactly one
    // new assistant turn, then it goes idle.
    await expect(assistantBubbles).toHaveCount(assistantsBefore + 1, { timeout: 90_000 })
    const assistantBubble = assistantBubbles.last()
    await expect(assistantBubble).not.toBeEmpty({ timeout: 90_000 })
    await expect(page.getByTestId('stop-btn')).toHaveCount(0, { timeout: 90_000 })
    await shot(page, '12-assistant-bubble-390.png')

    // Both bubbles stay inside the 390 px column.
    for (const [name, loc] of [
      ['user', userBubble],
      ['assistant', assistantBubble],
    ] as const) {
      const b = await loc.boundingBox()
      expect(rightEdge(b), `${name} bubble must not cross the right edge`).toBeLessThanOrEqual(
        VIEWPORT.width + 1,
      )
      expect(b!.x, `${name} bubble must not cross the left edge`).toBeGreaterThanOrEqual(-1)
    }

    // The message column must not scroll sideways.
    const column = page.getByTestId('panel-chat').first()
    const col = await column.evaluate((el) => ({
      scrollW: el.scrollWidth,
      clientW: el.clientWidth,
    }))
    record('06_message_column_overflow', col.scrollW - col.clientW)

    const probe = await probeOverflow(page)
    record('06_probe', probe)
    record('06_consoleErrors', errors)

    expect(col.scrollW - col.clientW, 'the message column scrolls sideways').toBeLessThanOrEqual(1)
    expect(
      probe.horizontalOverflowPx,
      `chat with messages must not force sideways scroll: ${JSON.stringify(probe.offenders)}`,
    ).toBeLessThanOrEqual(0)
    expect(pageErrors(errors), 'no uncaught exceptions during the round trip').toEqual([])
  })
})
