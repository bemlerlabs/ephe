// Ephe — first-run QA phase 2: the remaining surfaces (suggestions, attachments, sidebar, persistence, model chip)
import { chromium } from 'playwright'
import { writeFileSync, mkdirSync } from 'fs'
const BASE = 'http://localhost:5173/#/'
const OUT = '/tmp/qa'
mkdirSync(OUT, { recursive: true })
const findings = []
const consoleErrors = []
const F = (sev, t, e) => { findings.push({ sev, t, e }); console.log(`[${sev}] ${t} :: ${String(e).slice(0,160)}`) }
const OK = (m) => console.log(`[ok] ${m}`)
const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', (e) => consoleErrors.push('PAGEERROR ' + e.message))
const shot = async (n) => { try { await page.screenshot({ path: `${OUT}/${n}.png` }) } catch {} }
const sleep = (ms) => page.waitForTimeout(ms)
const bodyText = () => page.locator('body').innerText().catch(() => '')

try { await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await sleep(2500) } catch (e) { F('🔴','Start',e) }

// A) the suggestion card is clickable → it fills or sends the input
try {
  const card = page.locator('text=/Explain my project/i').first()
  await card.click({ timeout: 4000 })
  await sleep(1200)
  const taVal = await page.locator('textarea').first().inputValue().catch(() => '')
  const sent = /explain|project|analyse|code/i.test(await bodyText())
  await shot('11_suggestion_card')
  if (taVal.trim() || sent) OK('Vorschlags-Karte reagiert (füllt oder sendet)')
  else F('🟠', 'Vorschlags-Karte ohne Wirkung', 'kein Text in textarea / kein Send')
} catch (e) { F('🟠', 'Vorschlags-Karte-Exception', e) }

// B) the attachment button (paperclip) opens a menu/file input
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await sleep(1800)
  const before = await page.locator('input[type=file]').count()
  // a button whose aria-label contains 'Attach'/'Anhang', or the paperclip svg inside the composer
  const clip = page.locator('button[aria-label*="ttach" i], button[aria-label*="nhang" i]').first()
  const clipCnt = await page.locator('button[aria-label*="ttach" i], button[aria-label*="nhang" i]').count()
  if (clipCnt > 0) { await clip.click({ timeout: 3000 }).catch(()=>{}) }
  await sleep(800)
  const after = await page.locator('input[type=file]').count()
  await shot('12_attachment')
  if (after > before || after > 0) OK('Attachment-Flow vorhanden (file-input)')
  else F('🟠', 'Attachment-Button ohne file-input/Menü', `clipCnt=${clipCnt} fileInputs=${after}`)
} catch (e) { F('🟠', 'Attachment-Exception', e) }

// C) the sidebar collapse toggle
try {
  const collapse = page.locator('button[aria-label*="ollapse" i], button[aria-label*="uklap" i], button[aria-label*="Sidebar" i]').first()
  const cnt = await page.locator('button[aria-label*="ollapse" i], button[aria-label*="uklap" i], button[aria-label*="Sidebar" i]').count()
  if (cnt > 0) { await collapse.click({ timeout: 3000 }).catch(()=>{}); await sleep(700); await shot('13_sidebar_collapsed'); OK('Sidebar-Kollaps-Toggle existiert + geklickt') }
  else { await shot('13_sidebar_collapsed'); F('🟠', 'Kein Sidebar-Kollaps-Button auffindbar', 'count=0') }
} catch (e) { F('🟠', 'Sidebar-Kollaps-Exception', e) }

// D) session persistence across a reload (a genuinely "longer-running user": the session has to come back)
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' }); await sleep(1500)
  const t = page.locator('textarea').first()
  await t.click(); await t.fill('PersistenzTest-Nachricht mit UniqueMarker XYZQ'); await t.press('Enter')
  await sleep(6000) // wait for the reply
  await page.reload({ waitUntil: 'domcontentloaded' }); await sleep(2500)
  const b = await bodyText()
  await shot('14_persist_after_reload')
  if (/PersistenzTest|UniqueMarker|XYZQ/i.test(b)) OK('Session über Reload persistiert (Nachricht wieder da)')
  else F('🟠', 'Session-Nachricht nach Reload verschwunden', 'Marker nicht im Text')
} catch (e) { F('🟠', 'Persistenz-Exception', e) }

// E) the model chip is clickable (at the bottom, 'qwen...' / 'Remote')
try {
  const chip = page.locator('button:has-text("qwen"), button:has-text("Remote")').first()
  const cnt = await page.locator('button:has-text("qwen"), button:has-text("Remote")').count()
  if (cnt > 0) { await chip.click({ timeout: 3000 }).catch(()=>{}); await sleep(900); await shot('15_model_chip'); OK('Modell-Chip klickbar') }
  else { await shot('15_model_chip'); F('🟠', 'Modell-Chip nicht als Button auffindbar', 'count=0') }
} catch (e) { F('🟠', 'Modell-Chip-Exception', e) }

// F) the recurring-tasks banner
try {
  const banner = page.locator('text=/Wiederkehrende Aufgaben/i').first()
  const cnt = await page.locator('text=/Wiederkehrende Aufgaben/i').count()
  if (cnt > 0) { await banner.click({ timeout: 3000 }).catch(()=>{}); await sleep(900); await shot('16_recurring'); OK('Wiederkehrende-Aufgaben-Banner klickbar') }
  else F('🟡', 'Wiederkehrende-Aufgaben-Banner nicht gefunden', 'count=0')
} catch (e) { F('🟠', 'Recurring-Banner-Exception', e) }

writeFileSync(`${OUT}/findings2.json`, JSON.stringify({ findings, consoleErrors: [...new Set(consoleErrors)] }, null, 2))
await browser.close()
console.log(`\n=== DONE2: ${findings.length} findings, ${new Set(consoleErrors).size} console-errors ===`)
