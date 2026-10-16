// R5 inspection run, second part: chat, agent pane, settings, mobile.
// Real Chrome, the German surface, images of everything — find, do not assert.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'

const OUT = '/tmp/r5-pruef2'
mkdirSync(OUT, { recursive: true })
const BASE = process.env.BASE || 'http://127.0.0.1:8790'
const SITZ = 'ae1b2c46-6a68-4b82-9fab-d8df1d50cef5'
const say = (l, v) => console.log(`${l}: ${v}`)

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
await ctx.addInitScript(() => {
  try {
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('i18nextLng', 'de')
  } catch {
    /* a frame without an origin (the PDF viewer) has no localStorage */
  }
})
const page = await ctx.newPage()
page.setDefaultTimeout(20_000)
const fehler = []
page.on('pageerror', (e) => fehler.push('pageerror: ' + String(e).slice(0, 120)))
const bild = async (name) => {
  const png = await page.screenshot()
  writeFileSync(`${OUT}/${name}.png`, png)
  say('image', `${name}.png (${Math.round(png.length / 1024)}KB)`)
}

await page.goto(`${BASE}/#/chat?session=${SITZ}`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)
say('messages', await page.locator('[data-testid^="message-"]').count())
await bild('10-chat')

// The popup over the chat that the user complained about.
const schalter = page.locator('[data-testid="artifact-library-toggle"]')
say('rail toggle', (await schalter.count()) > 0)
if ((await schalter.count()) > 0) {
  await schalter.first().click()
  await page.waitForTimeout(1800)
  say('popup open', (await page.locator('[data-testid="artifact-modal"]').count()) > 0)
  await bild('11-artifact-popup')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(600)
}

// Agent pane: click through every pill.
const pane = page.locator('[data-testid="side-panel-toggle"]')
if ((await pane.count()) > 0) {
  await pane.first().click()
  await page.waitForTimeout(1200)
}
const pillen = await page.locator('[role="tab"]').allInnerTexts().catch(() => [])
say('tabs', pillen.join(' / ') || 'none')
for (const [i, pill] of pillen.entries()) {
  const el = page.locator('[role="tab"]').nth(i)
  await el.click().catch(() => {})
  await page.waitForTimeout(1200)
  const kurz = pill.replace(/\s+/g, '-').slice(0, 12)
  await bild(`12-tab-${i}-${kurz}`)
}

// Settings: no route, one button in the sidebar.
await page.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const offen = await page
  .getByRole('button', { name: /Einstellungen|Settings & Profile/i })
  .first()
  .click({ timeout: 5000 })
  .then(() => true)
  .catch(() => false)
say('settings opened', offen)
if (offen) {
  await page.waitForTimeout(1500)
  await bild('13-einstellungen')
  const bereiche = await page.locator('[data-testid^="settings-nav-"]').allInnerTexts().catch(() => [])
  say('areas', bereiche.join(' / ') || 'no nav test ids')
}

// Mobile
const mob = await ctx.newPage()
await mob.setViewportSize({ width: 390, height: 844 })
await mob.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle' })
await mob.waitForTimeout(2000)
await mob.screenshot({ path: `${OUT}/14-mobile-chat.png` })
say('image', '14-mobile-chat.png')
await mob.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await mob.waitForTimeout(1800)
await mob.screenshot({ path: `${OUT}/15-mobile-werkbank.png` })
say('image', '15-mobile-werkbank.png')

say('console errors', fehler.length ? fehler.slice(0, 6).join(' | ') : 0)
await browser.close()
