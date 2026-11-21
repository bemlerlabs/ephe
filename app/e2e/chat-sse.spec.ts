import { test, expect, type Page, type Route, type Request } from '@playwright/test'

/**
 * Ephe PWA — E2E: SSE chat round trip + tool approval (PWA-Chat-UX-Plan, E1)
 *
 * Design decision (deterministic, no live backend needed):
 * - ONE single catch-all route (a glob over every /api/* path) answers
 *   ALL API endpoints by dispatching on URL+method. (Playwright URL globs with
 *   single segments, e.g. for /api/health, are inconsistent — empirically shown,
 *   hence the catch-all.)
 * - "no ws://": a WebSocket observer. The SSE design opens NO WebSocket;
 *   a single connection event is a hard fail.
 * - "exactly 1 growing bubble": synthetic SSE with N chunks → exactly one
 *   assistant bubble whose text ends up containing the full content.
 * - Approval path: the SSE sends sandbox_confirm → alertdialog → Allow →
 *   the observed POST /api/sandbox/approve (token) → the call comes back 'approved'.
 */

const CHAT_URL = 'http://127.0.0.1:5174/#/chat'
const HEALTH_BODY = {
  status: 'ok',
  version: 'e2e',
  ollama: true,
  models: ['gemma4:e4b'],
  active_tier: 'local',
  active_model: 'gemma4:e4b',
  dgx_online: false,
  active_provider: 'ollama',
  offline_capable: true,
  requires_internet: false,
  model_installed: true,
}

/** Synthetic SSE: model_info → thinking_start → N×chunk → done */
function sseRoundtripBody(): string {
  const chunks = ['Hal', 'lo ', 'Welt', '!', ' Die ', 'Antwort ']
  const frames = [
    { type: 'model_info', model: 'gemma4:e4b', provider: 'ollama' },
    { type: 'thinking_start' },
    ...chunks.map((data) => ({ type: 'chunk', data })),
    { type: 'done' },
  ]
  return frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join('')
}

/** Synthetic SSE carrying a sandbox_confirm (the approval path) */
function sseApprovalBody(): string {
  const frames = [
    { type: 'model_info', model: 'gemma4:e4b', provider: 'ollama' },
    { type: 'thinking_start' },
    { type: 'chunk', data: 'Ich führe ein Tool aus: ' },
    {
      type: 'sandbox_confirm',
      token: 'tok_e2e_123',
      tool: 'run_shell',
      args: { cmd: 'echo e2e' },
    },
    { type: 'chunk', data: 'fertig.' },
    { type: 'done' },
  ]
  return frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join('')
}

/**
 * ONE catch-all route for every /api/* endpoint. `streamBody` is the body for
 * POST /api/chat/stream; `recordApprovals` collects the /api/sandbox/approve payloads.
 */
async function stubApi(
  page: Page,
  streamBody: string,
  recordApprovals?: Array<{ token: string; approved: boolean }>,
) {
  await page.route('**/api/**', async (route: Route) => {
    const req: Request = route.request()
    const url = req.url()
    const method = req.method()

    // POST /api/chat/stream → synthetic SSE
    if (url.endsWith('/api/chat/stream') && method === 'POST') {
      return void (await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: streamBody,
      }))
    }
    // POST /api/sandbox/approve → status + payload record
    if (url.endsWith('/api/sandbox/approve') && method === 'POST') {
      if (recordApprovals) {
        recordApprovals.push(req.postDataJSON() as { token: string; approved: boolean })
      }
      return void (await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      }))
    }
    // GET /api/health
    if (url.endsWith('/api/health')) {
      return void (await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(HEALTH_BODY),
      }))
    }
    // GET /api/setup/status → configured (so no setup page is rendered)
    if (url.includes('/api/setup/status')) {
      return void (await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ configured: true }),
      }))
    }
    // /api/schedule, /api/settings, anything else → an empty JSON object
    return void (await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  })
}

async function setupLocale(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
  })
}

test.describe('Ephe PWA — SSE-Chat', () => {
  test.beforeEach(async ({ page }) => {
    await setupLocale(page)
    // WebSocket observer: collects every ws connection (there must be 0)
    ;(page as unknown as { __ws?: string[] }).__ws = []
    page.on('websocket', (ws) => {
      const arr = (page as unknown as { __ws: string[] }).__ws
      arr.push(ws.url())
    })
    await page.goto(CHAT_URL)
    await expect(page.getByPlaceholder('Schreibe eine Nachricht...')).toBeVisible()
  })

  test('keine WebSocket-Verbindung + exakt 1 wachsende Assistant-Bubble', async ({ page }) => {
    await stubApi(page, sseRoundtripBody())

    await page.getByPlaceholder('Schreibe eine Nachricht...').fill('Hallo')
    await page.getByLabel('Senden').click()

    // the assistant bubble appears (glass-reading rounded-tl-sm = assistant bubble)
    const assistantBubble = page.locator('div.glass-reading.rounded-tl-sm')
    await expect(assistantBubble).toHaveCount(1)

    // the content grows out of the 7 chunks → the full text at the end
    await expect(assistantBubble).toContainText('Hallo Welt! Die Antwort ')

    // the bubble is NO LONGER streaming (a cursor + the copy action, not the pulse)
    await expect(assistantBubble.locator('span.animate-pulse')).toHaveCount(0)
    await expect(assistantBubble).toContainText('Inhalte kopieren')

    // the send button is back (streaming finished)
    await expect(page.getByLabel('Senden')).toBeVisible()

    // CORE ASSERTION: the app opens NO WebSocket to the old chat endpoint
    // /ws any more (the HMR channel is dev tooling and is filtered out by appWebSockets).
    const ws = (page as unknown as { __ws: string[] }).__ws
    const appWs = ws.filter((u) => {
      try {
        return new URL(u).pathname === '/ws' || u.includes('/ws?') || u.includes('/ws/')
      } catch {
        return true
      }
    })
    expect(appWs, `Chat-WebSocket: ${appWs.join(', ')}`).toHaveLength(0)
  })

  test('Tool-Approval: alertdialog + Zulassen löst POST /api/sandbox/approve aus', async ({
    page,
  }) => {
    const approvals: Array<{ token: string; approved: boolean }> = []
    await stubApi(page, sseApprovalBody(), approvals)

    await page.getByPlaceholder('Schreibe eine Nachricht...').fill('Shell ausführen')
    await page.getByLabel('Senden').click()

    // the approval dialog appears (role=alertdialog)
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('run_shell')

    // conservative a11y: focus lands on the reject button initially
    await expect(page.getByLabel('Ablehnen')).toBeFocused()

    // click Allow (the J2 label is 'Genehmigen')
    await page.getByLabel('Genehmigen').click()

    // POST /api/sandbox/approve with the exact token + approved=true
    await expect
      .poll(() => approvals.length, { message: 'Erwartete POST /api/sandbox/approve' })
      .toBe(1)
    expect(approvals[0]).toEqual({ token: 'tok_e2e_123', approved: true, remember: false })

    // the approval dialog disappears once it has been approved
    await expect(dialog).toHaveCount(0)

    const ws = (page as unknown as { __ws: string[] }).__ws
    const appWs = ws.filter((u) => {
      try {
        return new URL(u).pathname === '/ws' || u.includes('/ws?') || u.includes('/ws/')
      } catch {
        return true
      }
    })
    expect(appWs, `Chat-WebSocket: ${appWs.join(', ')}`).toHaveLength(0)
  })

  test('Tool-Approval: Ablehnen (Esc) meldet approved=false', async ({ page }) => {
    const approvals: Array<{ token: string; approved: boolean }> = []
    await stubApi(page, sseApprovalBody(), approvals)

    await page.getByPlaceholder('Schreibe eine Nachricht...').fill('Shell ausführen')
    await page.getByLabel('Senden').click()

    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible()

    // Esc = the escape hatch → deny (D1 a11y)
    await page.keyboard.press('Escape')

    await expect(dialog).toHaveCount(0)
    await expect
      .poll(() => approvals.length, { message: 'Erwartete POST /api/sandbox/approve' })
      .toBe(1)
    expect(approvals[0]).toEqual({ token: 'tok_e2e_123', approved: false, remember: false })
  })
})
