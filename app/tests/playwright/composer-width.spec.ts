import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'
import { collisionProbe } from './layoutProbe'

/**
 * R2-I: the chat's control rows expand downwards on a narrow column instead of
 * overlapping each other. The column is narrower than the window as soon as the
 * agent panel is open (measured: a 392 px header at a 1100 px window),
 * so no viewport breakpoint may drive the wrap-around row.
 *
 * Visibly overlapping is what still sits in the same pixels after taking the
 * clip rectangle of both parents — a scroll strip is allowed, a ⌘ button painted
 * over the model chip is not.
 */

const ROWS: [string, string][] = [
  ['header', 'main > div > header'],
  ['status', '[data-testid="status-bar"]'],
  ['composer', '[data-testid="composer-actions-row"]'],
]

test.describe('Steuerzeilen mit offenem Agent-Pane', () => {
  for (const width of [1100, 1280, 1440]) {
    test.use({ viewport: { width, height: 900 } })

    test(`nichts ueberlappt bei ${width} px`, async ({ page }) => {
      await ensureOnboarded(page)
      await gotoHash(page, '/chat', '[data-testid="chat-input"]')
      await page.getByTestId('side-panel-toggle').click()
      await expect(page.locator('[data-testid="panel-resize-handle"]')).toBeVisible()
      await page.waitForTimeout(400)

      for (const [name, sel] of ROWS) {
        const r = await page.evaluate(collisionProbe, sel)
        expect(r.missing, `${name}: Zeile fehlt im DOM`).toBe(false)
        expect(r.hits, `${name} bei ${width} px ueberlappt`).toEqual([])
      }
    })
  }

  test('die Steuerzeile hat eine Ausweich-Zeile', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="chat-input"]')
    const row = page.locator('[data-testid="composer-actions-row"]')
    await expect(row).toBeVisible()
    const cls = await row.getAttribute('class')
    expect(cls).toContain('flex-wrap')
    await page.setViewportSize({ width: 1100, height: 900 })
    await page.getByTestId('side-panel-toggle').click()
    await page.waitForTimeout(400)
    const h = await row.evaluate((el) => el.getBoundingClientRect().height)
    expect(h).toBeGreaterThan(48)
  })
})

test.describe('composer at 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the action row stays on one line and nothing overlaps', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="chat-input"]')
    const row = page.locator('[data-testid="composer-actions-row"]')
    await expect(row).toBeVisible()
    const cls = await row.getAttribute('class')
    expect(cls).toContain('max-sm:flex-nowrap')

    const box = await row.boundingBox()
    expect(box?.height ?? 0).toBeLessThan(60)

    const probe = await page.evaluate(collisionProbe, '[data-testid="composer-actions-row"]')
    expect(probe.missing).toBe(false)
    expect(probe.hits).toEqual([])
  })
})

test.describe('B1: one chrome row', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test('the header is 40 px and carries the run line and the engine state', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="chat-input"]')
    const header = page.locator('main > div > header')
    await expect(header).toBeVisible()
    const box = await header.boundingBox()
    expect(Math.round(box?.height ?? 0)).toBe(40)
    await expect(header.locator('[data-testid="agentic-bar"]')).toHaveCount(1)
    await expect(header.locator('[data-testid="workbench-state"]')).toHaveCount(1)
    await expect(header.locator('[data-testid="engine-status-pill"]')).toHaveCount(1)
  })
})
