// R4 sight-check, part A — a real user creates a PDF in the chat.
// No seed, no mock: type into the composer, send, click the approval, expect the artifact.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const OUT = '/tmp/r4-sicht'
mkdirSync(OUT, { recursive: true })
const BASE_URL = 'http://127.0.0.1:8765'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
page.setDefaultTimeout(120_000)

await page.goto(`${BASE_URL}/#/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)
console.log('Titel:', await page.title())
console.log('sichtbare Buttons:', (await page.locator('button:visible').count()))
const composer = page.locator('#ephe-chat-input')
console.log('Composer vorhanden:', await composer.count() > 0)
await page.screenshot({ path: `${OUT}/a01-chat-_start.png` })

if (!(await composer.count())) {
  console.log('ABORT: no composer — page shows:', (await page.locator('body').innerText()).slice(0, 400))
  await browser.close()
  process.exit(2)
}

await composer.click()
await composer.fill(
  'Erstelle genau ein PDF mit dem Titel R4-Werkbank-Sichtcheck und zwei Absätzen über die Werkbank. Datei: r4-sichtcheck.pdf. Schreibe keinen Text davor.',
)
await page.keyboard.press('Enter')
console.log('gesendet…')

let approved = false
for (let i = 0; i < 120; i++) {
  await page.waitForTimeout(2000)
  const approve = page.getByRole('button', { name: /Zulassen|Approve|Erlauben/i })
  if ((await approve.count()) > 0 && !approved) {
    console.log('Freigabe erschienen — klicke Zulassen')
    await approve.first().click()
    approved = true
    await page.screenshot({ path: `${OUT}/a02-freigabe.png` })
  }
  const card = page.locator('[data-testid="artifact-modal"], a[href*="/api/artifacts/"], [data-file-result]')
  const fileRow = await page.getByText(/r4-sichtcheck\.pdf/i).count()
  if (fileRow > 0) {
    console.log(`artifact in the surface after ~${(i + 1) * 2}s (approved=${approved})`)
    break
  }
}

await page.waitForTimeout(3000)
await page.screenshot({ path: `${OUT}/a03-chat_ergebnis.png`, fullPage: false })
const body = await page.locator('body').innerText()
console.log('PDF mentioned in the reply:', /PDF/i.test(body))
console.log('last 300 characters:', body.slice(-300).replace(/\n{2,}/g, '\n'))

// The index knows it most precisely.
const stats = await (await fetch(`${BASE_URL}/api/artifacts/stats`)).json()
console.log('stats:', JSON.stringify(stats))
const list = await (await fetch(`${BASE_URL}/api/artifacts?limit=5`)).json()
for (const a of list.artifacts.slice(0, 3)) {
  console.log('  ', a.name, '| id:', a.id.slice(0, 8), '| in Werkbank:', a.path.includes('/.ephe/artifacts/'), '| expires_at:', a.expires_at, '| call:', a.call_id)
}
await browser.close()
