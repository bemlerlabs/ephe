// I3 visual check — the settings area on screen, against the real backend.
// Pattern from scripts/sichtcheck_w14c.mjs, but without a dev store: the page runs
// against the production-identical server (dist + FastAPI), because that is
// exactly the shipped state.
//
// Start:  EPHE_URL=http://127.0.0.1:8965 node scripts/sichtcheck_i3.mjs
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const BASE = process.env.EPHE_URL || 'http://127.0.0.1:8965'
const OUT = process.env.OUT_DIR || 'docs/media/i3_2026-10-03'
const ONLY = (process.env.TABS || '').split(',').filter(Boolean)
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
await ctx.addInitScript(() => {
  localStorage.setItem('i18nextLng', 'de')
  localStorage.setItem('ephe_onboarded', '1')
})
const page = await ctx.newPage()
const problems = []
page.on('console', (m) => m.type() === 'error' && problems.push(m.text().slice(0, 140)))
page.on('pageerror', (e) => problems.push('pageerror ' + String(e).slice(0, 140)))

await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
await page.waitForTimeout(1800)
await page.screenshot({ path: `${OUT}/00-chat.png` })

const gear = page.getByTestId('sidebar-settings-btn')
console.log('Open button found:', (await gear.count()) > 0)
if (await gear.count()) {
  try {
    await gear.first().click({ timeout: 6000 })
  } catch (err) {
    // The sidebar animates (framer-motion) — a click then often has to hold until
    // the motion stops. Force-click plus an evidence screenshot, not an abort.
    console.log('normal click stuck:', String(err).split('\n')[0].slice(0, 90))
    await page.screenshot({ path: `${OUT}/90-vor-klick.png` })
    await gear.first().click({ force: true, timeout: 6000 })
  }
}
await page.waitForSelector('[data-testid="settings-page"]', { timeout: 10000 })
await page.waitForTimeout(1500)
await page.screenshot({ path: `${OUT}/01-settings-engine.png` })

const tabs = await page.$$eval('[data-testid^="settings-nav-"]', (els) =>
  els.map((e) => e.getAttribute('data-testid').replace('settings-nav-', '')),
)
for (const tab of ONLY.length ? ONLY : tabs) {
  const btn = page.getByTestId(`settings-nav-${tab}`)
  if (!(await btn.count())) {
    console.log(`no nav tab: ${tab}`)
    continue
  }
  await btn.first().click()
  await page.waitForTimeout(800)
  const panel = await page.$('[data-testid="settings-panel"]')
  if (panel) await panel.screenshot({ path: `${OUT}/panel-${tab}.png` })
  await page.screenshot({ path: `${OUT}/page-${tab}.png` })
}

// The nav search: one word that appears in only a single description.
const search = page.getByTestId('settings-search')
if (await search.count()) {
  await search.first().fill('schrift')
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${OUT}/15-navsuche-schrift.png` })
  const hit = page.getByTestId('settings-search-field-appearance-Schriftgröße (%)')
  console.log('search hit:', (await hit.count()) > 0)
  if (await hit.count()) {
    await hit.first().click()
    await page.waitForTimeout(800)
    await page.screenshot({ path: `${OUT}/16-navsuche-sprung.png` })
  }
  await search.first().fill('')
  await page.waitForTimeout(300)
}

const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 })
await mctx.addInitScript(() => {
  localStorage.setItem('i18nextLng', 'de')
  localStorage.setItem('ephe_onboarded', '1')
})
const mpage = await mctx.newPage()
await mpage.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
await mpage.waitForTimeout(1500)
await mpage.screenshot({ path: `${OUT}/20-mobile-chat.png` })
const mgear = mpage.getByTestId('sidebar-settings-btn')
// I6-8: "visible" per Playwright is not enough — a sidebar that lies outside the
// canvas still has a bounding box and counts as visible. The check reported its own
// limitation ("settings NOT reachable", the wording the mobile branch prints) because it
// never opened the burger menu. The decision goes by the box.
const box = await mgear.first().boundingBox()
if (!box || box.x < 0) {
  const burger = mpage.locator('button[aria-label*="Men"]').first()
  if (await burger.count()) {
    await burger.click()
    await mpage.waitForTimeout(900)
    await mpage.screenshot({ path: `${OUT}/21-mobile-drawer.png` })
  }
}
  try {
    await mgear.first().click({ timeout: 6000 })
    await mpage.waitForTimeout(1500)
    await mpage.screenshot({ path: `${OUT}/21-mobile-settings.png` })
    const navs = await mpage.getByTestId(/^settings-nav-/).count()
    console.log(`mobile: settings reachable (${navs} nav entries)`)
  } catch {
    console.log('mobile: settings NOT reachable — finding')
    await mpage.screenshot({ path: `${OUT}/21-mobile-kein-zugang.png` })
  }

console.log('Tabs:', tabs.join(', '))
console.log('console errors:', problems.length ? problems.slice(0, 6).join(' | ') : 'none')
await browser.close()
