import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

test.describe('App Boot — Chat / Onboarding (the current React+Vite UI)', () => {
  test('root loads the chat dashboard without console errors', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    await ensureOnboarded(page)
    await page.goto('/', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 10000 })
    await page.waitForLoadState('networkidle')
    // The test runs without a local backend → WS-/fetch errors against
    // localhost:8765 are expected (an offline-first app with no backend). UI errors are everything else.
    const uiErrors = errors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('404') &&
        !e.includes('501') &&
        !e.includes('8765') &&
        !e.includes('localhost') &&
        !e.includes('WebSocket') &&
        !e.includes('[WS]') &&
        !e.includes('ERR_FAILED') &&
        !e.includes('ERR_CONNECTION_REFUSED'),
    )
    expect(uiErrors).toEqual([])
  })

  test('root route renders the chat workspace (no landing page any more)', async ({ page }) => {
    await ensureOnboarded(page)
    await page.goto('/', { waitUntil: 'load' })
    await expect(page.locator('[data-testid="chat-sidebar"]')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-testid="panel-chat"]')).toBeVisible()
  })

  test('chat route renders the workspace', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await expect(page.locator('[data-testid="panel-chat"]')).toBeVisible()
    await expect(page.locator('[data-testid="chat-sidebar"]')).toBeVisible()
  })

  test('chat input is present and editable', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', 'textarea')
    // By test id, not by placeholder copy: the composer's German placeholder this
    // line used to reach for no longer exists anywhere in app/src, so the step
    // could only ever pass against an old build.
    const input = page.locator('[data-testid="chat-input"]')
    await expect(input).toBeVisible()
    await input.fill('Hello Ephe')
    await expect(input).toHaveValue('Hello Ephe')
  })

  test('page title is set', async ({ page }) => {
    await ensureOnboarded(page)
    await page.goto('/', { waitUntil: 'load' })
    await expect(page).toHaveTitle(/Ephe/)
  })
})
