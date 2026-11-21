import { test, expect } from '@playwright/test'
import { resolve, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../out/panel-conduct')
const CHAT_PANEL = '[data-testid="panel-chat"]'
const CHAT_INPUT = '[data-testid="chat-input"]'
const BASE = 'http://localhost:5173'

function installOpenRecorder() {
  const w = window as unknown as {
    __opens: { open: boolean; tab: string | null; ts: number; afterClick: number }[]
    __lastClick: number
  }
  w.__opens = []
  w.__lastClick = 0
  document.addEventListener(
    'click',
    (e) => {
      const target = e.target as HTMLElement | null
      if (target?.closest?.('[data-testid="side-panel-toggle"],[role="tabpanel"]')) {
        w.__lastClick = performance.now()
      }
    },
    true,
  )
  window.addEventListener('ephe:panel-state', (ev) => {
    const detail = (ev as CustomEvent).detail as { open: boolean; tab: string | null }
    w.__opens.push({
      open: detail.open,
      tab: detail.tab ?? null,
      ts: performance.now(),
      afterClick: performance.now() - w.__lastClick,
    })
  })
}

test.describe.configure({ mode: 'serial' })

// The live leg costs a real turn on the persisted engine and leaves a real PDF under
// ~/.ephe/artifacts. Same discipline as r5-perceived-latency's lane flag: without it the
// file collects but does not run, so `probe.config.ts` stays a free, deterministic run.
const LIVE = process.env.EPHE_CONDUCT_LIVE === '1'

test('live run: one real PDF turn in a fresh full-access task', async ({ page }) => {
  test.skip(!LIVE, 'set EPHE_CONDUCT_LIVE=1 to spend a real engine turn')
  test.setTimeout(420_000)
  page.on('pageerror', (e) => console.log(`live PAGEERROR ${String(e).slice(0, 160)}`))
  await page.addInitScript(installOpenRecorder)
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
  })
  await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
  await page.waitForSelector(CHAT_PANEL, { timeout: 20_000 })
  await page.waitForTimeout(1200)

  await page.getByTestId('new-session').click()
  await page.waitForTimeout(800)

  await page.getByTestId('composer-mode-selector').click()
  await page.getByTestId('composer-mode-list').waitFor({ timeout: 4000 })
  await page
    .getByRole('menuitem', { name: /Voller Zugriff|Full access|Autonom/i })
    .first()
    .click()
  await page.waitForTimeout(400)

  const start = await page.evaluate(
    () => (window as unknown as { __opens: unknown[] }).__opens.length,
  )
  await page
    .locator(CHAT_INPUT)
    .fill(
      'Create a one-page PDF file named panel-conduct-probe.pdf with the title "Panel Conduct Probe" and three short paragraphs about attention conduct. Use the pdf tool, not markdown.',
    )
  await page.keyboard.press('Enter')

  // The new-task rule (if it fires) opens the pane right at send; the streaming
  // flag is the only honest end-of-turn marker.
  await page.waitForTimeout(2500)
  const opensAtSend = await page.evaluate(
    (s: number) =>
      (
        window as unknown as {
          __opens: { open: boolean; tab: string | null; afterClick: number }[]
        }
      ).__opens.slice(s),
    start,
  )
  console.log(
    `live AT-SEND autoOpens=${opensAtSend.filter((r) => r.open && r.afterClick > 400).length} tabs=${opensAtSend.map((r) => r.tab).join(',')}`,
  )

  await page
    .waitForFunction(() => !document.querySelector('[data-testid="stop-btn"]'), null, {
      timeout: 300_000,
    })
    .catch(() => console.log('live TURN still streaming after 300s'))
  await page.waitForTimeout(2500)

  const bubble = page.locator('[data-testid="message-bubble"][data-role="assistant"]').last()
  const head = bubble.getByTestId('bubble-turn-head')
  if ((await head.getAttribute('aria-expanded').catch(() => null)) === 'false') {
    await head.click()
    await page.waitForTimeout(600)
  }
  const text = await bubble.innerText().catch(() => '')
  console.log(`live BUBBLE-TEXT >>>\n${text.slice(0, 2000)}\n<<<`)
  const clickable = await bubble
    .locator('button, a')
    .evaluateAll((els) =>
      els.map(
        (e) =>
          `${e.tagName}:${(e.getAttribute('data-testid') ?? e.getAttribute('aria-label') ?? e.textContent ?? '').trim().slice(0, 60)}`,
      ),
    )
  console.log(`live BUBBLE-CLICKABLE ${JSON.stringify(clickable)}`)
  console.log(`live PDF-PATHS ${JSON.stringify((text.match(/[^\s`]*\.pdf/gi) ?? []).slice(0, 6))}`)
  const rows = await page.evaluate(
    (s: number) =>
      (
        window as unknown as {
          __opens: { open: boolean; tab: string | null; afterClick: number }[]
        }
      ).__opens.slice(s),
    start,
  )
  console.log(
    `live RESULT events=${rows.length} openTrue=${rows.filter((r) => r.open).length} ` +
      `autoOpens=${rows.filter((r) => r.open && r.afterClick > 400).length} tabs=${rows.map((r) => r.tab).join(',')} ` +
      `panelMounted=${await page.locator('[role="tabpanel"]').count()}`,
  )
  await page.screenshot({ path: join(OUT, 'live-pdf-turn-end.png') })
  await expect(bubble).toBeVisible()
})
