// The Sichtbar wave's final proof: the HELPER from the real live run (spawn_agent  // language-gate: ignore ("Sichtbar" is that wave's name, and the run's output dir named after it)
// on the DGX Spark) is opened inside the app — chat, rows, report, way back.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync, readdirSync } from 'node:fs'

const OUT = '/tmp/sichtbar'
mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8795'
const CFG = '/tmp/sichtbar-cfg'
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png` })
const AGENT = process.argv[2] ?? 'subagent-1'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
page.setDefaultTimeout(180_000)
await page.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle' })
await page.waitForTimeout(3500)
console.log('Window title:', await page.title())
console.log('Sessions from the mirror:', await page.locator('[data-testid^="session-row-"]').count())

// #71: the rail's lower tiers start closed, so open the one holding "Helpers" first.
await page.locator('[data-testid="sidebar-tier-tools-toggle"]').click()
await page.waitForTimeout(300)
await page.locator('[data-testid="sidebar-action-helpers"]').click()
await page.waitForTimeout(1500)
await shot(page, `e01-helfer-flaeche`)

const link = page.locator(`[data-testid="subagent-open-chat-${AGENT}"]`)
console.log('Link present:', (await link.count()) > 0)
if ((await link.count()) === 0) {
  await browser.close()
  process.exit(2)
}
await link.first().click()
await page.waitForTimeout(2000)
console.log('Chat title:', (await page.locator('[data-testid="session-title"]').innerText()).slice(0, 46))
console.log('branch-back chip:', await page.locator('[data-testid="header-branch-from"]').count())
console.log('helper marks in the sidebar:', await page.locator('[data-testid^="session-helper-mark-"]').count())
const bubbles = await page.locator('[data-testid^="message-bubble-"]').count()
console.log('bubbles in the helper chat:', bubbles)
await shot(page, 'e02-helfer-chat')

const chip = page.locator('[data-testid="header-branch-from"]')
if ((await chip.count()) > 0) {
  await chip.first().click()
  await page.waitForTimeout(1500)
  console.log('back in:', (await page.locator('[data-testid="session-title"]').innerText()).slice(0, 46))
  await shot(page, 'e03-rueckweg-zur-aufgabe')
}
console.log(
  'Helper files in the mirror:',
  readdirSync(`${CFG}/sessions`).filter((f) => f.includes('pwa-helper-')).length,
)
await browser.close()
