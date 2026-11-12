import { test, expect, type Page } from '@playwright/test'

/*
 * The docked placement, in the built bundle: a `dock-panel` bundle fills the shell's
 * named region on a wide window and folds into a bottom sheet behind a toggle on a
 * phone. The stubs answer the routes the settings row and the mount use; the frame's
 * document is a minimal page, because what is under test is the shell chrome and the
 * sandbox the region enforces, not a plugin's rendering.
 */

const PLUGIN = {
  name: 'docklet',
  id: 'docklet',
  description: 'A docked counter',
  enabled: true,
  tags: [],
  example_prompts: [],
  surface: {
    type: 'dock-panel',
    entry: 'ui/index.html',
    title: 'Docklet',
    width: 360,
    height: 320,
    placement: 'dock',
  },
}

async function stubApi(page: Page) {
  await page.route('**/api/**', (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
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
        public: [PLUGIN],
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
    if (path === '/api/plugins/surface-hosts') return json({ surfaces: {} })
    if (path.endsWith('/surface-token')) {
      return json({ plugin: PLUGIN.id, surface: 'n0nce', expires_in: 300 })
    }
    if (path.includes('/surface-host')) return json({ surface: {} })
    if (path.startsWith('/api/plugins/ui/docklet/')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<!doctype html><html><body style="margin:0;background:#15120f;color:#f2ece6">docklet</body></html>',
      })
    }
    return json({})
  })
}

test.use({ serviceWorkers: 'block' })

test.beforeEach(async ({ page }) => {
  await stubApi(page)
  await page.addInitScript(() => {
    localStorage.clear()
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('ephe.intro.seen.v1', '1')
    localStorage.setItem('ephe.register.open', '1')
  })
})

async function openDock(page: Page) {
  await page.goto('/#/settings/plugins', { waitUntil: 'load' })
  await page.waitForSelector('[data-testid="settings-page"]', { timeout: 10000 })
  const row = page.getByTestId('plugin-surface-docklet')
  await expect(row).toBeVisible({ timeout: 10000 })
  await row.click()
  const dock = page.getByTestId('dock-host')
  await expect(dock).toBeVisible({ timeout: 10000 })
  // The row lives in the settings sheet, which covers the workbench (and its own
  // close control sits over the dock's chrome). Leave the sheet the way a person
  // does; the hash route changes in place, so the docked panel stays mounted.
  await page.evaluate(() => {
    window.location.hash = '#/chat'
  })
  await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 10000 })
  await expect(dock).toBeVisible({ timeout: 10000 })
  return dock
}

test.describe('the docked plugin region', () => {
  test('a dock-panel fills the shell region in a sandboxed frame', async ({ page }) => {
    const dock = await openDock(page)
    const box = await dock.boundingBox()
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(320)
    expect(box?.width ?? 0).toBeLessThanOrEqual(400)
    const frame = page.getByTestId('dock-frame')
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-popups')
    await expect(frame).not.toHaveAttribute('sandbox', /allow-same-origin/)
    await expect(frame).toHaveAttribute('title', 'Docklet')
    await expect(frame).toHaveAttribute('src', /\/api\/plugins\/ui\/docklet\/n0nce\//)
    const region = await dock.getAttribute('role')
    expect(region).toBe('complementary')
  })

  test('the close control takes the region away', async ({ page }) => {
    await openDock(page)
    await page.getByTestId('dock-close').click()
    await expect(page.getByTestId('dock-host')).toHaveCount(0)
  })

  test('a phone folds the dock into a bottom sheet behind a toggle', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const dock = await openDock(page)
    const open = await dock.boundingBox()
    expect(open?.y ?? 0).toBeGreaterThan(300)
    await page.getByTestId('dock-collapse').click()
    await expect(page.getByTestId('dock-host')).toBeHidden()
    const toggle = page.getByTestId('dock-toggle')
    await expect(toggle).toBeVisible()
    await toggle.click()
    await expect(page.getByTestId('dock-host')).toBeVisible()
  })
})
