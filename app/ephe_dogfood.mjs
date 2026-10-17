// Ephe — user-simulation harness (Playwright, headless)
import { chromium } from 'playwright'
import { writeFileSync } from 'fs'

const BASE = 'http://localhost:5173/#/'
const OUT = '/tmp/audit'
const findings = []
const consoleErrors = []
const F = (sev, title, ev) => { findings.push({ sev, title, ev }); console.log(`[${sev}] ${title} :: ${ev}`) }

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', (e) => consoleErrors.push('PAGEERROR ' + e.message))

const goto = async () => { await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1500) }
const poll = async (fn, ms = 45000, step = 500) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await fn()) return true; await page.waitForTimeout(step) } return false }

try {
  await goto()

  // ── 1. Console errors on start ─
  if (consoleErrors.length) F('🔴', 'Console-Fehler beim Initial-Load', consoleErrors.slice(0, 3).join(' | '))

  // ── 2. Chat end-to-end over vLLM ─
  const ta = page.locator('textarea').first()
  await ta.click()
  await ta.fill('Antworte mit genau einem Wort: HalloTest')
  await ta.press('Enter')
  const gotReply = await poll(async () => {
    // the real DOM has no data-testid=markdown (only the test mocks do) → match the assistant content div
    const t = await page.locator('[class*="text-white/90"]').allInnerTexts().catch(() => '')
    return /HalloTest/.test(t)
  })
  await page.screenshot({ path: `${OUT}/01_chat.png`, fullPage: false })
  if (!gotReply) F('🔴', 'Chat-Antwort kam nicht durch (vLLM :8888)', 'kein HalloTest im Stream nach 45s')
  else console.log('[ok] Chat-Stream über vLLM')

  // ── 3. The /memory slash command ─
  await ta.click(); await ta.fill('/memory'); await ta.press('Enter')
  const memOk = await poll(async () => {
    const t = await page.locator('body').innerText().catch(() => '')
    return /Memory:.*Vektoren|Memory:.*vectors/i.test(t)
  }, 15000)
  await page.screenshot({ path: `${OUT}/02_memory.png` })
  if (!memOk) F('🟠', '/memory liefert keine System-Antwort', 'kein Memory-Text nach 15s')
  else console.log('[ok] /memory')

  // ── 4. Settings hub: the engine tab (active engine + editable URL) ─
  await page.locator('button[aria-label="Einstellungen"], button[aria-label="Settings"]').first().click().catch(async () => {
    await page.locator('[data-testid=settings-panel]').first().click({ timeout: 2000 }).catch(() => {})
  })
  await page.waitForTimeout(1200)
  const engText = await page.locator('body').innerText().catch(() => '')
  const hasEngineUrl = /8888|qwen3\.8-flash-next/i.test(engText)
  const urlInput = await page.locator('input[value*="8888"], input[value*="http"]').count()
  await page.screenshot({ path: `${OUT}/03_engine.png` })
  if (!hasEngineUrl) F('🟠', 'Engine-Tab zeigt keine aktive Engine/URL', 'kein 8888/qwen im Hub-Text')
  if (urlInput === 0) F('🟠', 'Keine editierbares API-URL-Input im Engine-Tab', 'input count=0')
  else console.log(`[ok] Engine-Tab: URL-Input vorhanden (${urlInput})`)

  // ── 5. Mobile tab: QR + tunnel progress ─
  await page.locator('text=/^.*Mobil.*$/i').first().click().catch(() => {})
  await page.waitForTimeout(800)
  const tunnelOrQr = await poll(async () => {
    const b = await page.locator('body').innerText().catch(() => '')
    return /Tunnel|QR|scannen|scan/i.test(b)
  }, 8000)
  await page.screenshot({ path: `${OUT}/04_mobile.png` })
  if (!tunnelOrQr) F('🟠', 'Mobile-Tab ohne QR/Tunnel-Hinweis', 'kein Text nach 8s')

  // ── 6. A11y: buttons without an accessible name ─
  const noName = await page.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' }
    return [...document.querySelectorAll('button')].filter((b) => vis(b) && !b.getAttribute('aria-label') && !b.getAttribute('title') && !b.textContent.trim()).map((b) => b.outerHTML.slice(0, 70))
  })
  if (noName.length) F('🟠', `${noName.length} Buttons ohne zugänglichen Namen`, noName.slice(0, 4).join(' | '))
  else console.log('[ok] A11y: alle Buttons benannt')

  // ── 7. Mobile viewport 390px ─
  await page.setViewportSize({ width: 390, height: 844 })
  await goto()
  await page.waitForTimeout(1200)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2)
  await page.screenshot({ path: `${OUT}/05_mobile390.png`, fullPage: false })
  if (overflow) F('🟠', 'Horizontaler Overflow im 390px-Viewport', 'scrollWidth > clientWidth')
  else console.log('[ok] Mobile 390px kein horizontaler Overflow')

} catch (e) {
  F('🔴', 'Harness-Exception', String(e).slice(0, 200))
} finally {
  writeFileSync(`${OUT}/findings.json`, JSON.stringify({ findings, consoleErrors }, null, 2))
  await browser.close()
  console.log(`\n=== DONE: ${findings.length} findings, ${consoleErrors.length} console-errors ===`)
}
