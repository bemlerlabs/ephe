import { test, expect, type Browser, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import { readFile } from 'node:fs/promises'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * docs/AGENT_PANEL_CONDUCT_2026-10-11.md §2/§3 against the shipping bundle.
 *
 * Serves app/dist and answers POST /api/chat/stream with the event body each
 * scenario names, so the pane movement is the product's own code over a chosen
 * stream. The vitest family holds the same rules at component level; this file is
 * the one that can see a streamed turn, because it runs what actually ships.
 *
 * A pane move is a false→true transition of `open` on PANEL_STATE_EVENT. Counting
 * broadcasts instead would overstate it: the pane re-broadcasts on every tab and
 * width change while it stays open.
 */

const DIST_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../dist')
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../out/panel-conduct')
const CHAT_PANEL = '[data-testid="panel-chat"]'
const CHAT_INPUT = '[data-testid="chat-input"]'

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.map': 'application/json',
  '.webmanifest': 'application/manifest+json',
}

function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`
}

const HEAD = [
  { type: 'chunk', data: 'Working. ' },
  { type: 'chunk', data: 'Done.' },
]
const TAIL = [{ type: 'done' }]

/** The event body of one turn, keyed by the probe name typed into the composer. */
function bodyFor(text: string): unknown[] {
  if (text.startsWith('PROBE_MD'))
    return [
      ...HEAD,
      {
        type: 'file_result',
        file_type: 'markdown',
        path: '/tmp/ephe/notes.md',
        label: 'notes.md',
        id: 'a-md',
      },
      ...TAIL,
    ]
  if (text.startsWith('PROBE_PDF'))
    return [
      ...HEAD,
      // The shape a real create_pdf turn leaves behind (server/routes/chat.py
      // _emit_file_result_event): the tool's ARGS carry no path — the path arrives
      // in file_result, so the tool card has nothing to point at.
      {
        type: 'tool_call',
        name: 'create_pdf',
        args: { topic: 'conduct probe' },
        status: 'completed',
      },
      {
        type: 'file_result',
        file_type: 'pdf',
        path: '/tmp/ephe/report.pdf',
        label: 'PDF: report.pdf',
        id: 'a-pdf',
      },
      { type: 'activity', cmd: 'create_pdf → PDF saved', status: 'done' },
      ...TAIL,
    ]
  if (text.startsWith('PROBE_IMAGE'))
    return [
      ...HEAD,
      {
        type: 'file_result',
        file_type: 'image',
        path: '/tmp/ephe/chart.png',
        label: 'chart.png',
        id: 'a-png',
      },
      ...TAIL,
    ]
  return [...HEAD, ...TAIL]
}

function startFixture(): Promise<Server> {
  const server = createServer(async (req, res) => {
    const path = new URL(req.url ?? '/', 'http://127.0.0.1').pathname

    if (path === '/api/setup/status') {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(
        JSON.stringify({
          configured: true,
          skipped: false,
          provider: 'openai_compatible',
          model: 'fixture-model',
          url: null,
        }),
      )
      return
    }
    if (path === '/api/health') {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(
        JSON.stringify({
          status: 'ok',
          version: 'fixture',
          models: ['fixture-model'],
          active_model: 'fixture-model',
          active_provider: 'openai_compatible',
          engine_online: true,
          engine_state: 'ok',
          model_installed: true,
          detail: 'panel conduct fixture',
        }),
      )
      return
    }
    if (path === '/api/file') {
      // A real PDF so the opened frame is a file and not an error page.
      res.writeHead(200, { 'Content-Type': 'application/pdf' })
      res.end(Buffer.from('%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n'))
      return
    }
    if (path === '/api/chat/stream' && req.method === 'POST') {
      const raw = await new Promise<string>((done) => {
        let acc = ''
        req.on('data', (d) => (acc += d))
        req.on('end', () => done(acc))
      })
      let text = ''
      try {
        text = String(JSON.parse(raw).message ?? '')
      } catch {
        text = ''
      }
      res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8' })
      res.write(': ready\n\n')
      for (const event of bodyFor(text)) res.write(sse(event))
      res.end()
      return
    }
    if (path.startsWith('/api/')) {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
      res.end(req.method === 'GET' ? '{}' : '{"ok":true}')
      return
    }

    const relative = path === '/' ? 'index.html' : path.replace(/^\/+/, '')
    try {
      const body = await readFile(join(DIST_ROOT, relative))
      res.writeHead(200, { 'Content-Type': MIME[extname(relative)] ?? 'application/octet-stream' })
      res.end(body)
    } catch {
      res.writeHead(200, { 'Content-Type': MIME['.html'] })
      res.end(await readFile(join(DIST_ROOT, 'index.html')))
    }
  })
  return new Promise((listening) => server.listen(0, '127.0.0.1', () => listening(server)))
}

function installOpenRecorder() {
  const w = window as unknown as {
    __moves: number
    __open: boolean
    __afterClick: number
  }
  w.__moves = 0
  w.__open = false
  w.__afterClick = 0
  document.addEventListener(
    'click',
    () => {
      // Any press is a gesture — the rule is that the pane moves as a consequence
      // of one, wherever it lands. Sending a turn is a keypress, so a pane that
      // opens at send time stays counted, which is the case worth catching.
      w.__afterClick = performance.now()
    },
    true,
  )
  window.addEventListener('ephe:panel-state', (ev) => {
    const detail = (ev as CustomEvent).detail as { open: boolean }
    if (detail.open && !w.__open) {
      const since = performance.now() - w.__afterClick
      // A move inside 400 ms of a press is that press's own consequence.
      if (since > 400) w.__moves += 1
    }
    w.__open = detail.open
  })
}

const moves = (page: Page) =>
  page.evaluate(() => (window as unknown as { __moves: number }).__moves)

let origin = ''
let server: Server

test.describe.configure({ mode: 'serial' })

test.describe('panel conduct against the built bundle', () => {
  test.setTimeout(120_000)

  test.beforeAll(async () => {
    await readFile(join(DIST_ROOT, 'index.html'))
    server = await startFixture()
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('no fixture port')
    origin = `http://127.0.0.1:${address.port}`
    console.log(`conduct FIXTURE origin=${origin} dist=${DIST_ROOT}`)
  })

  test.afterAll(async () => {
    await new Promise<void>((done) => server.close(() => done()))
  })

  async function openChat(browser: Browser) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    const page = await context.newPage()
    page.on('pageerror', (e) => console.log(`conduct PAGEERROR ${String(e).slice(0, 160)}`))
    await page.addInitScript(installOpenRecorder)
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'de')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_PANEL, { timeout: 15_000 })
    await page.waitForTimeout(500)
    return { context, page }
  }

  async function send(page: Page, text: string) {
    await page.locator(CHAT_INPUT).fill(text)
    await page.keyboard.press('Enter')
    await page
      .waitForFunction(() => !document.querySelector('[data-testid="stop-btn"]'), null, {
        timeout: 30_000,
      })
      .catch(() => console.log('conduct TURN did not close in 30s'))
    await page.waitForTimeout(1200)
  }

  const bubble = (page: Page) =>
    page.locator('[data-testid="message-bubble"][data-role="assistant"]').last()

  test('an ordinary streamed turn moves the pane zero times', async ({ browser }) => {
    const { context, page } = await openChat(browser)
    await send(page, 'PROBE_PLAIN first message of a new task')
    expect(await moves(page)).toBe(0)
    await expect(page.locator('[role="tabpanel"]')).toHaveCount(0)
    console.log('conduct RESULT plain-first moves=0')
    await context.close()
  })

  test('a follow-up turn moves it zero times either', async ({ browser }) => {
    const { context, page } = await openChat(browser)
    await send(page, 'PROBE_PLAIN warm-up')
    await send(page, 'PROBE_PLAIN ordinary follow-up')
    expect(await moves(page)).toBe(0)
    console.log('conduct RESULT plain-second moves=0')
    await context.close()
  })

  test('a turn that produces a PDF leaves the pane put and hands the file over', async ({
    browser,
  }) => {
    const { context, page } = await openChat(browser)
    await send(page, 'PROBE_PLAIN warm-up')
    await send(page, 'PROBE_PDF build a report')
    expect(await moves(page)).toBe(0)
    await expect(page.locator('[role="tabpanel"]')).toHaveCount(0)

    const card = bubble(page).locator('[data-testid^="message-file-open-"]')
    await expect(card).toBeVisible()
    await expect(bubble(page).locator('[data-testid^="message-file-download-"]')).toBeVisible()
    await expect(bubble(page).locator('[data-testid^="message-file-adopt-"]')).toBeVisible()
    await page.screenshot({ path: join(OUT, 'after-pdf-turn.png') })

    await card.click()
    const panel = page.locator('[role="tabpanel"]')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await expect(panel.getByTestId('preview-url-input')).toHaveAttribute('title', /report\.pdf$/)
    // The click is the user's; the pane moved for it and for nothing else.
    expect(await moves(page)).toBe(0)
    await page.screenshot({ path: join(OUT, 'after-pdf-opened.png') })
    console.log('conduct RESULT pdf moves=0 card=open+download pane-on-click=1')
    await context.close()
  })

  test('an image turn behaves the same way', async ({ browser }) => {
    const { context, page } = await openChat(browser)
    await send(page, 'PROBE_PLAIN warm-up')
    await send(page, 'PROBE_IMAGE draw a chart')
    expect(await moves(page)).toBe(0)
    await expect(bubble(page).locator('[data-testid^="message-file-open-"]')).toBeVisible()
    console.log('conduct RESULT image moves=0 card=1')
    await context.close()
  })

  test('a markdown file is reachable too — the extension no longer decides', async ({
    browser,
  }) => {
    const { context, page } = await openChat(browser)
    await send(page, 'PROBE_PLAIN warm-up')
    await send(page, 'PROBE_MD write notes')
    expect(await moves(page)).toBe(0)
    await expect(bubble(page).locator('[data-testid^="message-file-open-"]')).toBeVisible()
    console.log('conduct RESULT md moves=0 card=1')
    await context.close()
  })

  test('the header toggle still opens and closes it, and Escape closes it', async ({ browser }) => {
    const { context, page } = await openChat(browser)
    const panel = page.locator('[role="tabpanel"]')
    await page.getByTestId('side-panel-toggle').click()
    await expect(panel).toBeVisible({ timeout: 5000 })
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden({ timeout: 5000 })
    await page.getByTestId('side-panel-toggle').click()
    await expect(panel).toBeVisible({ timeout: 5000 })
    await page.getByTestId('side-panel-toggle').click()
    await expect(panel).toBeHidden({ timeout: 5000 })
    expect(await moves(page)).toBe(0)
    console.log('conduct RESULT toggle+escape ok')
    await context.close()
  })
})
