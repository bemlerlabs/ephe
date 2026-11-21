import { expect, test } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

/**
 * A2: the live counters carry `tabular-nums` (asserted in the component suites).
 * Whether that class actually sets figures is a question about the shipped
 * stylesheet, so it is asked of a probe element inside the built app — no data
 * dependency, nothing that can silently skip.
 */
test('the tabular-nums utility resolves in the built stylesheet', async ({ page }) => {
  await ensureOnboarded(page)
  await gotoHash(page, '/chat', '[data-testid="chat-input"]')

  const resolved = await page.evaluate(() => {
    const probe = document.createElement('span')
    probe.className = 'tabular-nums'
    probe.textContent = '0123456789'
    document.body.appendChild(probe)
    const value = getComputedStyle(probe).fontVariantNumeric
    probe.remove()
    return value
  })

  expect(resolved).toContain('tabular-nums')
})
