import { test, expect, type Page, type Route } from '@playwright/test'

/**
 * S19: a turn that loses its terminal frame does not end the session.
 *
 * The 18:38 stream carried its content, then the connection dropped before
 * `done`; the composer stayed out of reach. Here the first stream ends without
 * a terminal frame on purpose, and the next message has to go out normally.
 */

test.use({ serviceWorkers: 'block' })

function sse(events: object[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}

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

let turns = 0

async function stub(route: Route) {
  const path = new URL(route.request().url()).pathname
  if (path === '/api/chat/stream') {
    turns += 1
    if (turns === 1) {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: sse([
          { type: 'turn', turn_id: 't-first' },
          { type: 'chunk', data: 'I looked at the page. ' },
          { type: 'tool_start', tool: 'browser_go', round: 1 },
        ]),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: sse([
        { type: 'turn', turn_id: 't-second' },
        { type: 'chunk', data: 'Second answer is here.' },
        { type: 'done' },
      ]),
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

test('S19: a stream without a terminal frame ends the turn and the next message goes out', async ({
  page,
}) => {
  turns = 0
  await openChat(page)

  await page.getByTestId('chat-input').fill('look at mimi tech ai')
  await page.getByTestId('send-btn').click()

  await expect(page.getByText('The turn ended before it was complete.')).toBeVisible({
    timeout: 15000,
  })
  // A lost terminal frame is not "no engine": no setup CTA on this bubble.
  await expect(page.getByTestId('error-setup-engine')).toHaveCount(0)
  // The partial answer stays.
  await expect(page.getByText('I looked at the page.')).toBeVisible()

  await page.getByTestId('chat-input').fill('try again')
  await page.getByTestId('send-btn').click()

  await expect(page.getByText('Second answer is here.')).toBeVisible({ timeout: 15000 })
  expect(turns).toBe(2)
})
