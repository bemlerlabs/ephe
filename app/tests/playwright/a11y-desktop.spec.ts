import { createRequire } from 'node:module'
import { test, expect, type Page } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

/**
 * The desktop floor and the states the W2 audit measured open.
 *
 * `A11Y-REPORT.md` (2026-11-11) measured the three routes in their resting state:
 * nine axe runs, all viewports, no open drawer and no open popup. This file holds
 * the rest of that surface — the same nine runs as a gate, the 24 px pointer floor
 * at 1280 where a mouse, not a thumb, is the input, the phone drawer while it is
 * open (it carried `role="dialog"` on an `<aside>`, which ARIA in HTML refuses),
 * the settings sheet's focus handback, the composer popups' rectangles and the
 * standing toast live region.
 *
 * The 44 px recommendation stays a thumb rule. At 1280 the rail is 40 px and the
 * settings nav rows are 31 px; both pass WCAG 2.5.8 (24 px), and widening them
 * would move the desktop layout the rest of the product is measured against. The
 * floor asserted here is the one the criterion names.
 */

const require_ = createRequire(import.meta.url)
const AXE = require_.resolve('axe-core/axe.min.js')
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']

const ROUTES = [
  { path: '/', ready: '[data-testid="panel-chat"]' },
  { path: '/chat', ready: '[data-testid="panel-chat"]' },
  { path: '/settings', ready: '[data-testid="settings-page"]' },
]

const VIEWPORTS = [
  { name: 'desktop 1280', width: 1280, height: 800, hasTouch: false },
  { name: 'phone 390', width: 390, height: 844, hasTouch: true },
  { name: 'phone 320', width: 320, height: 568, hasTouch: true },
]

const TARGETS =
  'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="tab"], [role="menuitem"], [role="menuitemradio"], [role="switch"], [role="option"]'

async function axeViolations(page: Page): Promise<Array<Record<string, unknown>>> {
  await page.addScriptTag({ path: AXE })
  return page.evaluate(async (tags) => {
    const axe = (
      window as unknown as {
        axe: {
          run: (
            ctx: Document,
            opts: unknown,
          ) => Promise<{ violations: Array<{ id: string; nodes: unknown[] }> }>
        }
      }
    ).axe
    const result = await axe.run(document, {
      runOnly: { type: 'tag', values: tags },
      resultTypes: ['violations'],
    })
    return result.violations.map((v) => ({ id: v.id, nodes: v.nodes.length }))
  }, TAGS)
}

/**
 * WCAG 2.5.8 at the pointer: every visible control is at least 24 by 24, and an
 * undersized one would have to keep its 24 px circle clear of every other target.
 * The circles use the criterion's own construction, so the second list stays empty
 * for the right reason once the first one is.
 */
async function pointerFloor(page: Page): Promise<{
  under: Array<Record<string, unknown>>
  spacing: Array<Record<string, unknown>>
}> {
  return page.evaluate((selector) => {
    const box = (el: Element) => el.getBoundingClientRect()
    const visible: Array<{ id: string; x: number; y: number; w: number; h: number }> = []
    for (const el of Array.from(document.querySelectorAll(selector))) {
      const r = box(el)
      const css = getComputedStyle(el)
      if (r.width === 0 || r.height === 0 || css.visibility === 'hidden') continue
      if (el.closest('[inert]') || el.closest('[aria-hidden="true"]')) continue
      // The skip links are the sr-only 1 px pair above the content.
      if (r.width <= 2 && r.height <= 2) continue
      visible.push({
        id: el.getAttribute('data-testid') ?? el.tagName.toLowerCase(),
        x: r.x,
        y: r.y,
        w: r.width,
        h: r.height,
      })
    }
    const under = visible
      .filter((t) => t.w + 0.5 < 24 || t.h + 0.5 < 24)
      .map((t) => ({ ...t, w: Math.round(t.w), h: Math.round(t.h) }))
    const spacing: Array<Record<string, unknown>> = []
    for (const a of under) {
      const cx = a.x + a.w / 2
      const cy = a.y + a.h / 2
      for (const b of visible) {
        if (b === a) continue
        const dx = Math.max(b.x - cx, 0, cx - (b.x + b.w))
        const dy = Math.max(b.y - cy, 0, cy - (b.y + b.h))
        if (Math.hypot(dx, dy) < 12)
          spacing.push({ a: a.id, b: b.id, distance: Math.round(Math.hypot(dx, dy)) })
      }
    }
    return { under, spacing }
  }, TARGETS)
}

for (const viewport of VIEWPORTS) {
  test.describe(`the audit matrix at ${viewport.name}`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      hasTouch: viewport.hasTouch,
    })

    test('axe reports no violation on /, /chat and /settings', async ({ page }) => {
      test.setTimeout(90000)
      await ensureOnboarded(page)
      for (const route of ROUTES) {
        await gotoHash(page, route.path, route.ready)
        await page.waitForTimeout(600)
        expect(await axeViolations(page), `${route.path} at ${viewport.width}px`).toEqual([])
      }
    })
  })
}

test.describe('the 24 px floor with a mouse', () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: false })

  for (const route of ROUTES) {
    test(`no visible target is under 24 by 24 on ${route.path}`, async ({ page }) => {
      await ensureOnboarded(page)
      await gotoHash(page, route.path, route.ready)
      await page.waitForTimeout(500)
      const floors = await pointerFloor(page)
      expect(floors.under, `undersized targets on ${route.path}`).toEqual([])
      expect(floors.spacing, `undersized targets crowding a neighbour on ${route.path}`).toEqual([])
    })
  }
})

test.describe('the phone drawer while it is open', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

  test('is a named dialog that traps Tab and hands focus back on Escape', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('header-menu-toggle').click()

    const drawer = page.getByTestId('chat-sidebar')
    await expect(drawer).toHaveAttribute('role', 'dialog')
    await expect(drawer).toHaveAttribute('aria-modal', 'true')
    expect(await drawer.evaluate((el) => el.hasAttribute('inert'))).toBe(false)
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBe('sidebar-close')

    for (let i = 0; i < 30; i++) {
      await page.keyboard.press('Tab')
      expect(
        await page.evaluate(() =>
          Boolean(document.activeElement?.closest('[data-testid="chat-sidebar"]')),
        ),
        `Tab ${i + 1} stays in the dialog`,
      ).toBe(true)
    }

    await page.keyboard.press('Escape')
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBe('header-menu-toggle')
    await expect.poll(() => drawer.evaluate((el) => el.hasAttribute('inert'))).toBe(true)
  })

  test('axe reports no violation while the drawer is open', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('header-menu-toggle').click()
    await expect(page.getByTestId('chat-sidebar')).toHaveAttribute('role', 'dialog')
    expect(await axeViolations(page)).toEqual([])
  })
})

test.describe('the settings sheet', () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: false })

  test('takes focus, carries one area title and gives focus back to its invoker', async ({
    page,
  }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('sidebar-settings-btn').click()
    const sheet = page.getByTestId('settings-page')
    await expect(sheet).toBeVisible()
    await expect
      .poll(() =>
        page.evaluate(() =>
          Boolean(
            document
              .querySelector('[data-testid="settings-page"]')
              ?.contains(document.activeElement),
          ),
        ),
      )
      .toBe(true)
    await expect(page.locator('main#settings-content')).toHaveCount(1)

    const headings = await page.evaluate(() =>
      Array.from(
        document.querySelectorAll(
          '[data-testid="settings-page"] h1, [data-testid="settings-page"] h2',
        ),
      ).map((el) => (el.textContent ?? '').trim()),
    )
    expect(headings, 'one heading per name').toEqual([...new Set(headings)])

    // Escape belongs to the top disclosure first; the route survives that press.
    await page.getByTestId('settings-help').click()
    await expect(page.getByTestId('settings-help-hint')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('settings-help-hint')).toBeHidden()
    await expect(sheet).toBeVisible()
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBe('settings-help')

    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBe('sidebar-settings-btn')
  })
})

for (const width of [1280, 390, 320]) {
  test.describe(`the composer popups at ${width}px`, () => {
    test.use({ viewport: { width, height: 800 }, hasTouch: width < 700 })

    test('open inside the viewport', async ({ page }) => {
      await ensureOnboarded(page)
      await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
      const popups = [
        { trigger: 'composer-access-control', menu: 'composer-access-menu' },
        { trigger: 'composer-attach-plus', menu: 'composer-attach-menu' },
      ]
      for (const popup of popups) {
        await page.getByTestId(popup.trigger).click({ force: true })
        const box = await page.getByTestId(popup.menu).boundingBox()
        expect(box, `${popup.menu} has a box`).toBeTruthy()
        expect(box!.x, `${popup.menu} starts on canvas`).toBeGreaterThanOrEqual(0)
        expect(box!.y, `${popup.menu} starts below the top edge`).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width, `${popup.menu} ends on canvas`).toBeLessThanOrEqual(width + 1)
        expect(
          box!.y + box!.height,
          `${popup.menu} ends above the bottom edge`,
        ).toBeLessThanOrEqual(800 + 1)
        await page.keyboard.press('Escape')
        await expect(page.getByTestId(popup.menu)).toBeHidden()
      }
    })
  })
}

test.describe('toast announcements', () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: false })

  test('the live region stands before the first message and empties with the toast', async ({
    page,
  }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')

    // Both regions are mounted with the first paint, so the first message is a
    // change inside a region rather than an insertion of one.
    const live = page.getByTestId('toaster-live')
    const alert = page.getByTestId('toaster-live-alert')
    await expect(live).toHaveCount(1)
    await expect(alert).toHaveCount(1)
    await expect(page.getByTestId('toaster-region')).toHaveAttribute('aria-label', /.+/)

    // A cold open raises the history-restore toast; it is the deterministic message
    // of this bundle state (empty IndexedDB).
    const rail = page.getByTestId('toaster-rail')
    await expect(rail).toBeVisible({ timeout: 10000 })
    await expect(live).not.toHaveText('')

    await expect(rail).toBeHidden({ timeout: 12000 })
    await expect(live).toHaveText('')
  })
})
