import { test, expect, type Page } from '@playwright/test'

/*
 * QA-E2E F1 (2026-11-11): on `#/settings/plugins` the first-run intro stayed in
 * the DOM after a trusted click on its skip control. The settings sheet walks its
 * ancestor chain and marks every sibling inert; the intro was a sibling of <App/>
 * in #root, so it was marked too and `elementFromPoint` at the skip point answered
 * the settings HEADER. The scene is portalled to <body> now and exempt from that
 * walk, and the skip sits below the 48 px header band.
 *
 * One loop over every route the shell offers, with the same real click a person
 * makes. A hit-test first, because a click that only lands because Playwright
 * forced it would not prove the surface is reachable.
 */

const ROUTES = [
  '/',
  '/chat',
  '/tools',
  '/discover',
  '/workspaces',
  '/artifacts',
  '/memory',
  '/settings/engine',
  '/settings/plugins',
] as const

const SETTINGS = {
  provider: {
    type: 'openai_compatible',
    model: 'fixture-model',
    endpoint: 'http://127.0.0.1:9/v1',
  },
  language: 'de',
  theme: 'dark',
  memory_enabled: true,
  deep: [],
}

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
    if (path === '/api/settings') return json(SETTINGS)
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
    if (path === '/api/health') {
      return json({
        status: 'ok',
        models: ['fixture-model'],
        active_model: 'fixture-model',
        active_provider: 'openai_compatible',
        engine_online: true,
        engine_state: 'ok',
        model_installed: true,
        ollama: false,
      })
    }
    return json({})
  })
}

// The product registers a service worker, and its fetch handling sits below the
// route layer — the stubs above would otherwise never answer.
test.use({ serviceWorkers: 'block' })

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.addInitScript(() => {
    localStorage.clear()
  })
})

test.describe('the first-run intro is reachable on every route (F1)', () => {
  for (const route of ROUTES) {
    test(`skip closes the intro on ${route}`, async ({ page }) => {
      await page.goto(`/#${route}`, { waitUntil: 'load' })
      if (route.startsWith('/settings/')) {
        await page.waitForSelector('[data-testid="settings-page"]', { timeout: 10000 })
      }
      const skip = page.getByTestId('intro-skip')
      await expect(skip).toBeVisible({ timeout: 10000 })

      // The hit test the QA report used: the centre of the control must belong to
      // the control, not to a header painted over it.
      const hit = await skip.evaluate((el) => {
        const rect = el.getBoundingClientRect()
        const node = document.elementFromPoint(
          rect.left + rect.width / 2,
          rect.top + rect.height / 2,
        )
        return node?.closest('[data-testid]')?.getAttribute('data-testid') ?? null
      })
      expect(hit).toBe('intro-skip')

      await skip.click()
      await expect(page.getByTestId('first-run-intro')).toHaveCount(0, { timeout: 5000 })
    })
  }
})
