// R5 visual check — the night surfaces on the live index and the live route.
// No seed: shelf, detail, the way back to the task, the replay with its files,
// the scope question, the mobile view. Geometry and console errors included.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const OUT = '/tmp/r5-sicht'
mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8765'
const say = (label, value) => console.log(`${label}: ${value}`)

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
page.setDefaultTimeout(30_000)
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 140)))
page.on('pageerror', (e) => errors.push('pageerror: ' + String(e).slice(0, 140)))

// 1 — the shelf with real cards
await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const rowsAll = await page.locator('[data-testid^="artifact-row-"]').count()
say('cards in the shelf', rowsAll)

// 2 — find a card with an order (turn_id): through the index, not through guesses
const withTurn = await page
  .evaluate(async () => {
    const res = await fetch('/api/artifacts?limit=200')
    const body = await res.json()
    const hit = body.artifacts.find((a) => a.turn_id && a.session_id)
    return hit ? { id: hit.id, turn: hit.turn_id, session: hit.session_id, name: hit.name } : null
  })
  .catch(() => null)
say('card with turn and session', withTurn ? `${withTurn.name} · turn=${withTurn.turn?.slice(0, 8)}` : 'none')

if (withTurn) {
  await page.goto(`${BASE}/#/artifacts?turn=${encodeURIComponent(withTurn.turn)}`, {
    waitUntil: 'networkidle',
  })
  await page.waitForTimeout(1200)
  const scoped = await page.locator('[data-testid^="artifact-row-"]').count()
  say('cards in this order scope', `${scoped} of ${rowsAll}`)
  const chip = await page.locator('[data-testid="artifacts-scope"]').count()
  say('scope chip visible', chip > 0 ? await page.locator('[data-testid="artifacts-scope"]').innerText() : false)

  // 3 — detail: provenance, labels, the way back
  await page.locator(`[data-testid="artifact-row-${withTurn.id}"]`).first().click()
  await page.waitForTimeout(1200)
  say('provenance block', (await page.locator('[data-testid="artifact-provenance"]').count()) > 0)
  say('tag area', (await page.locator('[data-testid="artifact-tags"]').count()) > 0)
  const backBtn = page.locator('[data-testid="artifact-open-task"]')
  say('way-back button', (await backBtn.count()) > 0)

  // 4 — the click: chat with this session, replay open
  if ((await backBtn.count()) > 0) {
    await backBtn.first().click()
    await page.waitForTimeout(2500)
    const url = page.url()
    say('target URL', url.split('#')[1] ?? url)
    say('replay tab open', (await page.locator('[data-testid="trajectory-view"]').count()) > 0)
    const chips = await page.locator('[data-testid^="trajectory-turn-files-"]').count()
    say('turn headers with file count', chips)
    await page.screenshot({ path: `${OUT}/replay.png`, fullPage: false })
  }
}

// 5 — composer: the attachment gesture in the browser (PWA branch, no shell)
await page.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const fileInputs = await page.locator('input[type="file"]').count()
say('hidden file input for attachments', fileInputs)

// 6 — Mobile
const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
const mpage = await mobile.newPage()
mpage.setDefaultTimeout(30_000)
await mpage.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await mpage.waitForTimeout(1500)
await mpage.screenshot({ path: `${OUT}/mobile-artifacts.png` })
const overflow = await mpage.evaluate(() => {
  const de = document.documentElement
  return de.scrollWidth - de.clientWidth
})
say('mobile overflow in px', overflow)

say('console errors', errors.length)
for (const e of errors.slice(0, 6)) console.log('  · ' + e)
await browser.close()
