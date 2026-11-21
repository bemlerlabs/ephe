import { test, expect } from '@playwright/test'

/*
 * QA-E2E F2: one installation, two windows. `/api/settings` carried
 * `language: "de"`, the PWA read it, and the Tauri origin (no detector cache)
 * booted English. The entry now applies the saved language before the first
 * render; this leg boots with an empty client store and only the server's
 * answer to go on.
 */

test.use({ serviceWorkers: 'block' })

test('the saved product language is the first paint, with no client choice', async ({ page }) => {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    if (path === '/api/setup/status') {
      return json({
        configured: true,
        skipped: false,
        provider: 'openai_compatible',
        model: 'fixture-model',
        url: null,
      })
    }
    if (path === '/api/settings') {
      return json({
        provider: {
          type: 'openai_compatible',
          model: 'fixture-model',
          endpoint: 'http://127.0.0.1:9/v1',
        },
        language: 'de',
        theme: 'dark',
        memory_enabled: true,
        deep: [],
      })
    }
    return json({})
  })
  await page.addInitScript(() => {
    localStorage.clear()
    // The scene and the setup gate are other subjects; this leg is the language.
    localStorage.setItem('ephe.intro.seen.v1', '1')
    localStorage.setItem('ephe_onboarded', '1')
  })

  await page.goto('/', { waitUntil: 'load' })
  const input = page.getByTestId('chat-input')
  await expect(input).toBeVisible({ timeout: 10000 })
  await expect(page.locator('html')).toHaveAttribute('lang', 'de')
  await expect(input).toHaveAttribute('placeholder', 'Womit kann ich dir helfen?')
})
