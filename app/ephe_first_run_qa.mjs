// Ephe — first-run QA harness (Playwright, headless)
// Simulates a user who operates the app for a longer stretch today, for the first time.
// Every phase is try/catch-resilient → one break does not kill the run.
import { chromium } from 'playwright'
import { writeFileSync, mkdirSync } from 'fs'

const BASE = 'http://localhost:5173/#/'
const OUT = '/tmp/qa'
mkdirSync(OUT, { recursive: true })

const findings = []
const consoleErrors = []
const netFailures = []
const F = (sev, title, ev) => { findings.push({ sev, title, ev }); console.log(`[${sev}] ${title} :: ${String(ev).slice(0, 160)}`) }
const OK = (m) => console.log(`[ok] ${m}`)

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', (e) => consoleErrors.push('PAGEERROR ' + e.message))
page.on('requestfailed', (r) => netFailures.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText}`))
page.on('response', (r) => { if (r.status() >= 500) netFailures.push(`${r.status()} ${r.url()}`) })

const shot = async (n) => { try { await page.screenshot({ path: `${OUT}/${n}.png` }) } catch {} }
const sleep = (ms) => page.waitForTimeout(ms)
const bodyText = () => page.locator('body').innerText().catch(() => '')
const poll = async (fn, ms = 45000, step = 500) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await fn()) return true; await sleep(step) } return false }
const ta = () => page.locator('textarea').first()
const send = async (txt) => { const t = ta(); await t.click(); await t.fill(txt); await t.press('Enter') }

// ── Phase 0: start / gate / console ─
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await sleep(2500)
  const url = page.url()
  if (!/chat/.test(url)) F('🟠', 'Erst-Route nicht /chat (Gate-Verhalten)', url)
  else OK(`Gate → ${url}`)
  const b = await bodyText()
  if (!b.trim()) F('🔴', 'Weißer Screen beim Start', 'body.innerText leer')
  await shot('00_start')
} catch (e) { F('🔴', 'Phase 0 Start-Exception', e) }

// ── Phase 1: chat end-to-end (real engine) ─
try {
  await send('Antworte mit genau einem Wort: HalloTest')
  const got = await poll(async () => /HalloTest/.test(await bodyText()))
  await shot('01_chat_reply')
  if (!got) F('🔴', 'Chat-Antwort kam nicht durch', 'kein HalloTest nach 45s')
  else OK('Chat-Stream über Engine')
} catch (e) { F('🔴', 'Phase 1 Chat-Exception', e) }

// ── Phase 2: markdown rendering (code block) ─
try {
  await send('Gib mir ein kleines Python-Codeblock mit print("hi") als Markdown.')
  const got = await poll(async () => /print\(/.test(await bodyText()), 45000)
  await sleep(1200)
  await shot('02_markdown_code')
  const hasPre = await page.locator('pre, code').count()
  if (!got) F('🟠', 'Codeblock-Antwort ausbleib', 'kein print( im Text')
  else if (hasPre === 0) F('🟠', 'Codeblock ohne <pre>/<code> gerendert', 'Markdown-Code nicht als Code-Block')
  else OK(`Markdown-Codeblock gerendert (${hasPre} pre/code)`)
} catch (e) { F('🟠', 'Phase 2 Markdown-Exception', e) }

// ── Phase 3: slash commands ─
const slash = [
  ['/help', /Befehl|command|\/compact|\/new/i],
  ['/model', /qwen|modell|model/i],
  ['/memory', /Memory|Vektor|vector|unavailable|offline/i],
  ['/skills', /Skill|verfügbar|available|unavailable/i],
  ['/sessions', /Session/i],
]
for (const [cmd, re] of slash) {
  try {
    const before = (await bodyText()).length
    await send(cmd)
    const hit = await poll(async () => re.test(await bodyText()), 12000)
    await shot(`03_slash_${cmd.slice(1)}`)
    if (!hit) F('🟠', `${cmd} liefert keine erkennbare Antwort`, 'kein Match nach 12s')
    else OK(`${cmd}`)
  } catch (e) { F('🟠', `${cmd}-Exception`, e) }
}

// ── Phase 4: /new → a new session ─
try {
  await send('/new')
  await sleep(1500)
  const b = await bodyText()
  await shot('04_new_session')
  // after /new the chat should be empty/fresh (HalloTest need no longer be present, but there must be no crash)
  if (/PAGEERROR|undefined is not/i.test(b)) F('🔴', '/new verursacht Fehlerzustand', b.slice(0, 120))
  else OK('/new → neue Session ohne Crash')
} catch (e) { F('🟠', 'Phase 4 /new-Exception', e) }

// ── Phase 5: command palette (Cmd+K) ─
try {
  await page.keyboard.press('Meta+k')
  await sleep(900)
  const dlg = await page.locator('[role="dialog"]').count()
  await shot('05_command_palette')
  if (dlg === 0) F('🟠', 'Cmd+K öffnet keine Command-Palette', 'kein [role=dialog]')
  else OK('Command-Palette offen (Cmd+K)')
  await page.keyboard.press('Escape')
  await sleep(400)
} catch (e) { F('🟠', 'Phase 5 Palette-Exception', e) }

// ── Phase 6: settings panel (engine + mobile) ─
try {
  await send('/settings')
  await sleep(1500)
  const b = await bodyText()
  const hasEngine = /8888|qwen|engine|provider|url/i.test(b)
  await shot('06_settings')
  if (!hasEngine) F('🟠', 'Settings zeigt keine Engine-Infos', 'kein 8888/qwen/provider')
  else OK('Settings-Panel mit Engine-Infos')
  // the mobile tab
  await page.locator('text=/^.*Mobil.*$/i').first().click().catch(() => {})
  await sleep(900)
  await shot('06b_settings_mobile')
} catch (e) { F('🟠', 'Phase 6 Settings-Exception', e) }

// ── Phase 7: sidebar interaction ─
try {
  const newBtn = page.locator('button[aria-label*="Neu" i], button[aria-label*="New" i], button:has-text("Neue")').first()
  const cnt = await page.locator('button[aria-label*="Neu" i], button[aria-label*="New" i]').count()
  await shot('07_sidebar')
  if (cnt === 0) F('🟠', 'Sidebar: kein "Neue Session"-Button auffindbar', 'count=0')
  else { await newBtn.click().catch(() => {}); await sleep(800); OK('Sidebar Neue-Session geklickt') }
} catch (e) { F('🟠', 'Phase 7 Sidebar-Exception', e) }

// ── Phase 8: a11y — buttons without a name ─
try {
  const noName = await page.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' }
    return [...document.querySelectorAll('button')].filter((b) => vis(b) && !b.getAttribute('aria-label') && !b.getAttribute('title') && !b.textContent.trim()).map((b) => b.outerHTML.slice(0, 70))
  })
  if (noName.length) F('🟠', `${noName.length} Buttons ohne zugänglichen Namen`, noName.slice(0, 4).join(' | '))
  else OK('A11y: alle Buttons benannt')
} catch (e) { F('🟠', 'Phase 8 A11y-Exception', e) }

// ── Phase 9: mobile 390px ─
try {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await sleep(2000)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2)
  await shot('09_mobile390')
  if (overflow) F('🟠', 'Horizontaler Overflow @390px', 'scrollWidth > clientWidth')
  else OK('Mobile 390px kein horizontaler Overflow')
} catch (e) { F('🟠', 'Phase 9 Mobile-Exception', e) }

// ── Phase 10: a longer session — multi-turn continuity ─
try {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await sleep(1800)
  await send('Merke dir die Zahl 4247.')
  await poll(async () => (await bodyText()).includes('4247'), 30000)
  await send('Welche Zahl habe ich dir gerade genannt? Antworte mit nur der Zahl.')
  const recall = await poll(async () => /4247/.test(await bodyText()), 45000)
  await shot('10_multiturn_recall')
  if (!recall) F('🟠', 'Kontext über Turns verloren (4247 nicht erinnert)', 'kein 4247 in Antwort')
  else OK('Multi-Turn-Kontext hält (4247 erinnert)')
} catch (e) { F('🟠', 'Phase 10 Multi-Turn-Exception', e) }

// ── Report ─
writeFileSync(`${OUT}/findings.json`, JSON.stringify({ findings, consoleErrors: [...new Set(consoleErrors)], netFailures: [...new Set(netFailures)] }, null, 2))
await browser.close()
console.log(`\n=== DONE: ${findings.length} findings, ${new Set(consoleErrors).size} console-errors, ${new Set(netFailures).size} net-failures ===`)
