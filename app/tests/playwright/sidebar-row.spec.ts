import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'
import { collisionProbe } from './layoutProbe'

/**
 * A task row's trailing slot is the 11 px data step on every row, and it stays inside the row.
 *
 * Measured on the desktop build of 2026-11-01: the fresh-session label is a word rather than a
 * number, so it took none of the number's classes and rendered at the base step — wide enough
 * to reach over the ⋯ button beside it. The row keeps padding on its right for that button, and
 * a word that outgrows the slot paints over the control the row owns.
 */

const rowIds = (page: import('@playwright/test').Page) =>
  page
    .locator('[data-testid^="session-row-"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('data-testid')))

test.describe('the task row trailing slot', () => {
  for (const width of [1100, 1512]) {
    test.use({ viewport: { width, height: 900 } })

    test(`a fresh row keeps its label inside itself at ${width} px`, async ({ page }) => {
      await ensureOnboarded(page)
      await gotoHash(page, '/chat', '[data-testid="chat-input"]')

      const before = await rowIds(page)
      await page.getByTestId('new-session').click()
      await expect
        .poll(async () => (await rowIds(page)).length, 'the click creates a row')
        .toBeGreaterThan(before.length)
      const added = (await rowIds(page)).find((id) => !before.includes(id))!
      const row = page.locator(`[data-testid="${added}"]`)
      const age = row.locator('[data-testid^="session-age-"]')
      const label = age.locator('> *')
      await expect(label).toBeVisible()
      expect((await label.textContent())?.trim(), 'a fresh row names its cell').toBeTruthy()

      const rowBox = await row.boundingBox()
      const ageBox = await age.boundingBox()
      expect(rowBox, 'the row is measured').not.toBeNull()
      expect(ageBox, 'the trailing slot is measured').not.toBeNull()
      // The ⋯ button's box reaches 30 px into the row from its right edge; the text
      // column stops short of that, so no label is painted under the control.
      expect(ageBox!.x + ageBox!.width).toBeLessThanOrEqual(rowBox!.x + rowBox!.width - 30)

      const steps = await row.evaluate((el) => {
        const step = (node: Element) => getComputedStyle(node).fontSize
        const age = el.querySelector('[data-testid^="session-age-"]')!
        const meta = age.parentElement!
        return [step(meta.firstElementChild!), step(age.firstElementChild ?? age)]
      })
      expect(steps[1], "the label sits on the row's data step").toBe(steps[0])

      const probe = await page.evaluate(collisionProbe, `[data-testid="${added}"]`)
      expect(probe.missing, 'the row is in the document').toBe(false)
      expect(probe.hits, `the row's leaves overlap at ${width} px`).toEqual([])
    })
  }
})
