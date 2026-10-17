// W14 sight-check — fresh PNGs for the judge gate (2026-09-10).
// Backend 8765 + Vite 5173. DPR=2; seed after the IndexedDB hydration.
// Focus: P0-1 (dynamic window from the budget), P1-7 (tok/s + TTFT),
// P1-10 (engine badge that names the exact provider), context-popover breakdown.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5173/#/chat'
const OUT = 'docs/media/w14_2026-09-10'
mkdirSync(OUT, { recursive: true })

const SEED = () => {
  const now = Date.now()
  const msgs = [
    { id: 'u1', role: 'user', content: 'Erklaer mir die Architektur', timestamp: now - 3000 },
    {
      id: 'a1', role: 'assistant',
      content: 'Die Architektur ist dreischichtig: Sandbox, Approval-Gate, Injection-Guard.',
      timestamp: now - 2600, ttftMs: 820, streaming: true,
      thinking: { start: now - 2600, end: now - 1500, text: 'Ich lese zuerst das Manifest.' },
      blocks: [
        { kind: 'thinking', index: 0 },
        { kind: 'text', text: 'Die Architektur ist dreischichtig: Sandbox, Approval-Gate, Injection-Guard.' }
      ],
      activities: [{ id: 'ac1', label: 'read_file', status: 'done', detail: 'manifest.json' }]
    }
  ]
  const S = { id: 's1', title: 'Sichtcheck W14', createdAt: now, messageCount: 2, messages: msgs }
  window.__epheStore.setState(() => ({ sessions: [S], currentSession: S, activeSessionId: 's1' }))
}

const RECTS = () => {
  const out = {}
  for (const t of ['status-bar', 'statusbar-tok-chip', 'context-popover', 'composer-permission-badge']) {
    const el = document.querySelector(`[data-testid="${t}"]`)
    if (el) { const b = el.getBoundingClientRect(); out[t] = [b.x, b.y, b.width, b.height].map(Math.round) }
  }
  const texts = {}
  for (const t of ['status-bar', 'composer-permission-badge']) {
    const el = document.querySelector(`[data-testid="${t}"]`)
    if (el) texts[t] = el.textContent
  }
  const chips = Array.from(document.querySelectorAll('[data-testid="status-bar"] span')).map((e) => e.textContent).filter(Boolean)
  return { rects: out, texts, chips }
}

async function boot (pw, viewport) {
  const page = await pw.newPage({ viewport, deviceScaleFactor: 2, colorScheme: 'dark' })
  await page.addInitScript({ content: "() => { localStorage.setItem('i18nextLng', 'de'); localStorage.setItem('ephe_onboarded', '1') }" })
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="status-bar"]', { timeout: 15000 })
  await page.waitForTimeout(1200)
  return page
}

const browser = await chromium.launch()

// 1) Desktop: status bar with tok/s + TTFT + token count (window from the budget)
const page = await boot(browser, { width: 1280, height: 900 })
await page.evaluate(SEED)
await page.waitForTimeout(700)
console.log('desktop:', JSON.stringify(await page.evaluate(RECTS)))
await page.screenshot({ path: `${OUT}/w14_1_statuszeile_desktop.png` })

// 2) context popover (breakdown + window)
await page.evaluate(() => {
  const els = Array.from(document.querySelectorAll('button')).filter((e) => e.textContent?.includes('tok'))
  els[0]?.click()
})
await page.waitForTimeout(600)
await page.screenshot({ path: `${OUT}/w14_2_context_popover.png` })
await page.keyboard.press('Escape')
await page.close()

// 3) Mobile 390: leaner bar + composer badge carrying the provider name
const mob = await boot(browser, { width: 390, height: 844 })
await mob.evaluate(SEED)
await mob.waitForTimeout(700)
console.log('mobile:', JSON.stringify(await mob.evaluate(RECTS)))
await mob.screenshot({ path: `${OUT}/w14_3_mobile.png` })
await mob.close()

await browser.close()
console.log('OK 3 PNGs in', OUT)
