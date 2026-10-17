// R5 verification pass against the running product — in real Chrome (the
// Playwright kernel we ship has no PDF viewer, so its blank screenshot would be
// a finding about the test setup, not about Ephe).
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'

const OUT = '/tmp/r5-pruef'
mkdirSync(OUT, { recursive: true })
const BASE = process.env.BASE || 'http://127.0.0.1:8790'
const say = (l, v) => console.log(`${l}: ${v}`)

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
await ctx.addInitScript(() => {
  localStorage.setItem('ephe_onboarded', '1')
  localStorage.setItem('i18nextLng', 'de')
})
const page = await ctx.newPage()
page.setDefaultTimeout(30_000)
const fehler = []
page.on('pageerror', (e) => fehler.push('pageerror: ' + String(e).slice(0, 120)))
const bild = async (name, clip) => {
  const png = await page.screenshot(clip ? { clip } : {})
  writeFileSync(`${OUT}/${name}.png`, png)
  say('image', `${name}.png (${Math.round(png.length / 1024)}KB)`)
}

await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2200)
await bild('01-regal')

const pdf = await page.evaluate(async () => {
  const r = await fetch('/api/artifacts?limit=200')
  const b = await r.json()
  return b.artifacts.find((a) => a.name?.toLowerCase().endsWith('.pdf'))?.id ?? null
})
if (pdf) {
  await page.locator(`[data-testid="artifact-row-${pdf}"]`).first().click()
  await page.waitForTimeout(3200)
  const rahmen = await page.locator('[data-testid="artifact-detail"] iframe').first().boundingBox()
  if (rahmen) await bild('02-pdf-im-blatt', rahmen)
  await bild('03-detail')
  say(
    'gesture row',
    (await page.locator('[data-testid="artifact-detail"]').innerText()).split('\n').slice(0, 8).join(' / '),
  )
}

await page.goto(`${BASE}/#/artifacts/ablage`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
say(
  'shelf text',
  (await page.locator('[data-testid="artifacts-shelf-empty"]').count())
    ? await page.locator('[data-testid="artifacts-shelf-empty"]').innerText()
    : 'list with cards',
)
await bild('04-ablage')

// English: the very same badges have to follow the language switch.
await ctx.addInitScript(() => localStorage.setItem('i18nextLng', 'en'))
const en = await ctx.newPage()
await en.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await en.waitForTimeout(2000)
if (pdf) {
  await en.locator(`[data-testid="artifact-row-${pdf}"]`).first().click()
  await en.waitForTimeout(2500)
  say(
    'EN badges',
    (await en.locator('[data-testid="artifact-detail"]').innerText()).split('\n').slice(0, 10).join(' / '),
  )
  await en.screenshot({ path: `${OUT}/05-detail-englisch.png` })
}

say('console errors', fehler.length ? fehler.slice(0, 5).join(' | ') : 0)
await browser.close()
