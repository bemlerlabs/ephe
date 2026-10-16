/**
 * R36 P1-UX visual gate: bubble quick actions + TimelineRail after the B-8 repaint.
 * Seeds three bubbles (user + assistant with tool activity) and measures the
 * hit boxes (min-h-6 ⇒ >=24px) of the demo's fixed buttons. Usage (from app/):
 * node capture_approval_ux_r36.mjs [output.png]
 */
import { chromium } from 'playwright-core'

const out = process.argv[2] || '/tmp/audit/r36_b8_desktop_1.png'

const SEED = () => {
  const store = window.__epheStore
  if (!store) return 'no-store'
  const now = Date.now()
  const session = {
    id: 'seed-r36b',
    title: 'R36 P1-UX Tap-Targets',
    messages: [
      {
        id: 'm1', role: 'user',
        content: 'Fasse die Top-3 Fehlerquellen fuer HTTP-Timeouts zusammen.',
        timestamp: now - 90_000,
      },
      {
        id: 'm2', role: 'assistant',
        content: '1. Nicht gesetzte Connect-Timeouts, 2. ignorierte Keepalive, 3. Retry-Stuerme ohne Backoff.',
        timestamp: now - 80_000,
        toolCalls: [
          { callId: 't1', name: 'web_search', args: { query: 'HTTP timeout best practices' }, status: 'done', result: '4 Quellen' },
        ],
      },
      { id: 'm3', role: 'user', content: 'Und fuer gRPC?', timestamp: now - 30_000 },
      {
        id: 'm4', role: 'assistant',
        content: 'gRPC nutzt HTTP/2 — hier greift der PING-Keepalive statt Read-Timeout.',
        timestamp: now - 20_000,
      },
    ],
    createdAt: now - 120_000,
    updatedAt: now - 60_000,
  }
  store.setState({
    sessions: [session],
    activeSessionId: 'seed-r36b',
    currentSession: session,
  })
  return store.getState().activeSessionId
}

const browser = await chromium.launch()
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: 'dark',
})
await page.addInitScript(() => {
  localStorage.setItem('i18nextLng', 'de')
  localStorage.setItem('ephe_onboarded', '1')
})
await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' })
await page.waitForSelector('[data-testid="status-bar"]', { timeout: 20_000 })
const seeded = await page.evaluate(SEED)
if (seeded === 'no-store') throw new Error('window.__epheStore fehlt (dev build?)')
await page.waitForTimeout(900)
await page.hover('[data-testid="message-bubble"]')
await page.waitForTimeout(350)

const metrics = await page.evaluate(() => {
  const probe = document.querySelector('[data-testid="message-regenerate"], [data-testid="message-branch"]')
  const rail = document.querySelector('[data-testid="timeline-rail"]')
  const dot = rail ? rail.querySelector('button') : null
  const px = (el) => (el ? [Math.round(el.getBoundingClientRect().width), Math.round(el.getBoundingClientRect().height)] : null)
  return { regenerate: px(probe), dot: px(dot) }
})
await page.screenshot({ path: out })
console.log('saved:', out, JSON.stringify(metrics))
await browser.close()
