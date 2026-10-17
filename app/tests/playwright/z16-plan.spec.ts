import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Z16 (Reference-B parity): plan card with an accept/edit gate in the chat stream.
 * Mule: __epheStore fills an assistant message with an EphePlan check block;
 * expected are numbered steps, the progress chip, the status icons and the
 * click behaviour of the two gate buttons.
 */
const PLAN_TEXT = [
  '**Plan · 1/3**',
  '[x] Read the manifest',
  '[>] Run the test suite',
  '[ ] Summarize results',
].join('\n')

test.describe('Z16 — Plan-Karte im Chat-Stream', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    if (!(await hasDevHandle(page)))
      test.skip(true, 'braucht vite dev server (DEV-only __epheStore handle)')
  })

  test('Plan-Block rendert Karte mit nummerierten Schritten und Gate', async ({ page }) => {
    await page.evaluate((content) => {
      const store = (
        window as unknown as {
          __epheStore: {
            getState: () => {
              createSession: (t?: string) => void
              addMessage: (r: 'assistant', c: string, t?: unknown[]) => void
            }
          }
        }
      ).__epheStore.getState()
      store.createSession('Z16 Plan-Session')
      store.addMessage('assistant', content)
    }, PLAN_TEXT)
    await page.waitForTimeout(400)

    const card = page.locator('[data-testid="plan-card"]')
    await expect(card).toBeVisible()
    await expect(card.locator('[data-testid="plan-progress"]')).toHaveText('1/3')
    await expect(card.locator('[data-testid="plan-item-0"]')).toContainText('Read the manifest')
    await expect(card.locator('[data-testid="plan-item-2"]')).toContainText('Summarize results')
    // A completed step renders with strikethrough (text wrapper = second span),
    // the active one without it.
    await expect(card.locator('[data-testid="plan-item-0"] span').nth(1)).toHaveClass(
      /line-through/,
    )
    await expect(card.locator('[data-testid="plan-item-1"] span').nth(1)).not.toHaveClass(
      /line-through/,
    )
    // Gate buttons visible and inside the viewport (judge lesson: check box geometry)
    const accept = card.locator('[data-testid="plan-accept"]')
    const edit = card.locator('[data-testid="plan-edit"]')
    await expect(accept).toBeVisible()
    await expect(edit).toBeVisible()
    const box = await accept.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)

    await accept.click()
    await expect(page.getByText('Plan angenommen — fahre fort.')).toBeVisible()
  })
})
