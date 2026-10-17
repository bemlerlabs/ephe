import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

// R36 audit-repair regressions (docs/DEEP_DIVE_AUDIT_2026-09-07.md).
// Each block locks in one verified deep-dive finding.

test.describe('DD-02 header fits the canvas', () => {
  for (const width of [1280, 1440]) {
    test(`right header controls are on-canvas at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 860 })
      await ensureOnboarded(page)
      await page.addInitScript(() => localStorage.setItem('i18nextLng', 'en'))
      await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
      for (const sel of ['[data-testid="side-panel-toggle"]']) {
        const el = page.locator(sel)
        await expect(el).toBeVisible()
        const box = await el.boundingBox()
        expect(box, `${sel} has a box`).toBeTruthy()
        expect(box!.x + box!.width, `${sel} inside right edge`).toBeLessThanOrEqual(width + 1)
        expect(box!.x).toBeGreaterThanOrEqual(0)
      }
      // The library moved into the named overflow; the menu still exposes it.
      await page.getByTestId('header-more').click()
      await expect(page.getByTestId('artifact-library-toggle')).toBeVisible()
      await page.keyboard.press('Escape')
      // Toggle inventory 2026-09-07: the retired header gear must not return, and
      // the single settings entry lives in the sidebar footer.
      await expect(page.locator('[data-testid="header-settings-btn"]')).toHaveCount(0)
      await expect(page.getByTestId('sidebar-settings-btn')).toBeVisible()
    })
  }
})

test.describe('DD-03 audit tab is terminal-free', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await page.addInitScript(() => localStorage.setItem('i18nextLng', 'en'))
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('activating Audit shows the feed without the terminal command input', async ({ page }) => {
    // Open via the single header toggle, pick tabs inside the panel's own tab
    // bar (the old header 5-cluster was retired by the 2026-09-07 toggle inventory).
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // Runden-G: multi-tab pane — additional pages open through the tab-bar "+" menu.
    await panel.getByTestId('panel-add-tab').click()
    await panel.getByTestId('panel-new-tab-item-terminal').click()
    // The terminal needs its WebSocket on /api/shell/term. Against the
    // configuration-wise backend-less dist-server it reads as disconnected —
    // then the claim is not verifiable, so Skip with reason instead of a wrong verdict.
    const commandInput = panel.getByPlaceholder('Type a command and press Enter (whitelisted)')
    test.skip((await commandInput.count()) === 0, 'braucht laufendes Backend (Terminal-WebSocket)')
    // Sanity: the terminal branch renders its command input...
    await expect(
      panel.getByPlaceholder('Type a command and press Enter (whitelisted)'),
    ).toBeVisible()
    // ...but the audit branch must not stack it on top of the audit feed.
    await panel.getByTestId('panel-add-tab').click()
    await panel.getByTestId('panel-new-tab-item-audit').click()
    await expect(panel.getByRole('button', { name: 'Refresh audit log' })).toBeVisible({
      timeout: 5000,
    })
    await expect(
      panel.getByPlaceholder('Type a command and press Enter (whitelisted)'),
    ).toBeHidden()
  })
})
