import { test, expect, type Page } from '@playwright/test'

/*
 * QA-E2E F7: at 320 px the tab bar answered "Einstellu…" and the access chip
 * answered "Voller Zu…". Below 340 px the label folds away and the icon plus
 * aria-label/title carry the name; 390 px keeps the words. Both widths must
 * stay free of horizontal overflow.
 */

test.use({ serviceWorkers: 'block', hasTouch: true })

async function stubApi(page: Page) {
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
          model: 'qwen3.8-flash-next',
          endpoint: 'http://127.0.0.1:9/v1',
        },
        language: 'en',
        theme: 'dark',
        memory_enabled: true,
        deep: [],
      })
    }
    if (path === '/api/plugins') {
      return json({
        version: 1,
        master_enabled: true,
        read_only: false,
        unproven: false,
        notices: [],
        public: [],
        personal: [],
        installed: [],
        orphans: [],
        contested: { tools: [], memory_providers: [] },
      })
    }
    if (path === '/api/market/installed') return json({ plugins: [] })
    if (path === '/api/model/providers') {
      return json({
        active: {
          model: 'qwen3.8-flash-next',
          provider: 'openai_compatible',
          offline_capable: false,
        },
        providers: [],
        local_models: [],
        local_model_options: [],
      })
    }
    if (path === '/api/health') {
      return json({
        status: 'ok',
        models: ['qwen3.8-flash-next'],
        active_model: 'qwen3.8-flash-next',
        active_provider: 'openai_compatible',
        engine_online: true,
        engine_state: 'ok',
        model_installed: true,
        ollama: false,
      })
    }
    return json({})
  })
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('ephe.intro.seen.v1', '1')
    localStorage.setItem('ephe_onboarded', '1')
  })
}

async function displayOf(page: Page, selector: string): Promise<string> {
  return page
    .getByTestId(selector)
    .locator('span')
    .first()
    .evaluate((el) => getComputedStyle(el).display)
}

for (const width of [320, 390]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 800 } })

    test('keeps the header words whole or folds them, never truncated', async ({ page }) => {
      await stubApi(page)
      await page.goto('/#/chat', { waitUntil: 'load' })
      await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 10000 })

      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2),
      ).toBe(false)

      const tabLabel = await displayOf(page, 'mobile-tab-settings')
      const accessLabel = await displayOf(page, 'composer-access-control')
      if (width <= 340) {
        expect(tabLabel).toBe('none')
        expect(accessLabel).toBe('none')
      } else {
        expect(tabLabel).not.toBe('none')
        expect(accessLabel).not.toBe('none')
      }

      await expect(page.getByTestId('mobile-tab-settings')).toHaveAttribute(
        'aria-label',
        'Settings',
      )
      await expect(page.getByTestId('model-chip')).toHaveAttribute('title', 'qwen3.8-flash-next', {
        timeout: 10000,
      })
    })
  })
}
