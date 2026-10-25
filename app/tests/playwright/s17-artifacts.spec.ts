import { test, expect, type Page, type Route } from '@playwright/test'

/**
 * S17: an artifact the turn produced is visible in the message that produced it.
 *
 * No engine and no backend: the stream is one SSE body, the PNG is one buffer.
 * The surface is the built bundle the static leg serves.
 */

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
)

async function openChat(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('ephe.intro.seen.v1', '1')
  })
  await page.route((url) => new URL(url).pathname.startsWith('/api/'), stub)
  await page.goto('/#/chat', { waitUntil: 'load' })
  await page.evaluate(async () => {
    if (!navigator.serviceWorker) return
    for (const registration of await navigator.serviceWorker.getRegistrations()) {
      await registration.unregister()
    }
  })
  await page.reload({ waitUntil: 'load' })
  await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 15000 })
}

function sse(events: object[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}

async function stub(route: Route) {
  const path = new URL(route.request().url()).pathname
  if (path === '/api/chat/stream') {
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: sse([
        { type: 'turn', turn_id: 't-s17' },
        {
          type: 'progress',
          turn_id: 't-s17',
          round: 2,
          round_cap: 4,
          tool: 'web_search',
          phase: 'tool_progress',
          elapsed_ms: 1000,
          query: 'spark price',
        },
        { type: 'chunk', data: 'The image is ready.' },
        {
          type: 'file_result',
          file_type: 'png',
          path: '/work/cat.png',
          label: 'Image: cat.png',
          id: 'art-png',
          turn_id: 't-s17',
        },
        { type: 'done' },
      ]),
    })
  }
  if (path === '/api/artifacts/art-png/file') {
    return route.fulfill({
      status: 200,
      contentType: 'image/png',
      headers: { 'Content-Disposition': 'inline; filename="cat.png"' },
      body: PNG,
    })
  }
  if (path === '/api/setup/status') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        skipped: false,
        provider: 'openai_compatible',
        model: 'stub-model',
        url: null,
      }),
    })
  }
  if (path === '/api/health') {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', version: 'stub', active_model: 'stub-model' }),
    })
  }
  return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
}

test('S17: a produced PNG renders inline and opens in the lightbox', async ({ page }) => {
  await openChat(page)
  await page.getByTestId('chat-input').fill('show me the image')
  await page.getByTestId('send-btn').click()

  const image = page.locator('[data-testid^="message-file-image-"]').first()
  await expect(image).toBeVisible({ timeout: 15000 })
  const src = await image.locator('img').getAttribute('src')
  expect(src).toContain('/api/artifacts/art-png/file')
  expect(src).not.toContain('/api/file?')

  await image.click()
  await expect(page.locator('[data-testid^="message-file-lightbox-"]')).toBeVisible()
})

test('S17: a missing image says so and offers a retry', async ({ page }) => {
  await openChat(page)
  await page.route('**/api/artifacts/art-png/file', (route) =>
    route.fulfill({ status: 500, contentType: 'text/plain', body: 'nope' }),
  )
  await page.getByTestId('chat-input').fill('show me the image')
  await page.getByTestId('send-btn').click()
  const fallback = page.locator('[data-testid^="message-file-unavailable-"]').first()
  await expect(fallback).toBeVisible({ timeout: 15000 })
  await expect(fallback).toContainText('Image not available')
})
