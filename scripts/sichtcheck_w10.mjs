// W10 sight-check — fresh PNGs for the judge gate (2026-09-09).
// Backend 8765 + Vite 5173. DPR=2 so the 10px type stays readable; seed only
// after the IndexedDB hydration (a later restore would otherwise overwrite it).
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5173/#/chat'
const OUT = 'docs/media/w10_7026-09-09'
mkdirSync(OUT, { recursive: true })

const SEED = () => {
  const now = Date.now()
  const msgs = [
    { id: 'u1', role: 'user', content: 'Erklaer mir die Architektur', timestamp: now },
    { id: 'a1', role: 'assistant', content: 'Die Architektur ist dreischichtig.', timestamp: now,
      thinking: { start: now - 2400, end: now - 1200, text: 'Ich lese zuerst das Manifest.' },
      thinkingPhases: [
        { start: now - 2400, end: now - 1200, text: 'Ich lese zuerst das Manifest.' },
        { start: now - 1100, end: now - 300, text: 'Danach traegt die Diff-Zeile das Ergebnis.' }
      ],
      tool_calls: [
        { id: 't1', name: 'read_file', args: { path: 'manifest.json' }, result: '{...}', status: 'completed', duration_ms: 120 },
        { id: 't2', name: 'run_shell', args: { command: 'rg -n no_split core' }, result: 'core/chat.py:41', status: 'completed', duration_ms: 80 },
        { id: 't3', name: 'spawn_swarm', args: { count: 2, role: 'general-purpose', subtasks: ['P2-Layout + P4-Doku'] }, result: 'fertig', status: 'completed', duration_ms: 900 }
      ],
      blocks: [
        { kind: 'thinking', index: 0 },
        { kind: 'tool', callId: 't1' },
        { kind: 'tool', callId: 't2' },
        { kind: 'thinking', index: 1 },
        { kind: 'tool', callId: 't3' },
        { kind: 'text', text: 'Die Architektur ist dreischichtig.' }
      ],
      activities: [
        { id: 'ac1', label: 'Agent general-purpose', status: 'done', detail: 'P2-Layout + P4-Doku — 2.1 s' },
        { id: 'ac2', label: 'Agent researcher', status: 'running', detail: 'Sammelt Quellen zu Thema X' }
      ] }
  ]
  const S = { id: 's1', title: 'Sichtcheck', createdAt: now, messageCount: 2, messages: msgs }
  window.__epheStore.setState(() => ({
    sessions: [S], currentSession: S, activeSessionId: 's1',
  }))
}

const RECTS = () => {
  const out = {}
  for (const t of ['toolbar-row', 'toolbar-meta', 'status-bar', 'artifact-modal', 'artifact-close', 'tool-stream-rows', 'side-panel-toggle', 'toolbar-palette', 'statusbar-tok-chip', 'subagents-running-section']) {
    const el = document.querySelector(`[data-testid="${t}"]`)
    if (el) { const b = el.getBoundingClientRect(); out[t] = [b.x, b.y, b.width, b.height].map(Math.round) }
  }
  return out
}

const VERIFY = () => {
  const st = window.__epheStore.getState()
  const msg = st.currentSession?.messages?.find((x) => x.id === 'a1')
  return { sessions: st.sessions.length, blocks: msg?.blocks?.length ?? 0,
    phases: msg?.thinkingPhases?.length ?? 0, calls: msg?.tool_calls?.length ?? 0 }
}

async function boot (pw, opts) {
  const page = await pw.newPage({ viewport: { width: 1280, height: 900, deviceScaleFactor: 2 }, ...opts })
  await page.addInitScript({ content: "() => { localStorage.setItem('i18nextLng', 'de') }" })
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="status-bar"]', { timeout: 15000 })
  await page.waitForTimeout(1200) // let the IndexedDB restore finish
  return page
}

const browser = await chromium.launch()

// 1) Desktop: two-row header + beat interleaving in the stream
const page = await boot(browser);
(async () => { try { await page.evaluate(SEED) } catch (e) { console.log("seed err:", e.message) } })();
await page.waitForTimeout(600)
console.log('seed-verify:', JSON.stringify(await page.evaluate(VERIFY)))
console.log('desktop rects:', JSON.stringify(await page.evaluate(RECTS)))
await page.screenshot({ path: `${OUT}/w10_71_desktop_strom.png` })

// 2) artifact popup (portal) at nearly main-window size
await page.getByTestId('artifact-library-toggle').click({ force: true })
await page.waitForTimeout(700)
await page.screenshot({ path: `${OUT}/w10_72_artefakt_popup.png` })
await page.getByTestId('artifact-close').click({ force: true })
await page.waitForTimeout(400)
await page.screenshot({ path: `${OUT}/w10_73_nach_esc.png` })

// 3) subagents tab in the side panel
await page.getByTestId('side-panel-toggle').click({ force: true })
await page.waitForTimeout(400)
await page.evaluate(() => window.dispatchEvent(new CustomEvent('ephe:preview-open', { detail: { tab: 'subagents' } })))
await page.waitForTimeout(800)
await page.screenshot({ path: `${OUT}/w10_74_subagenten_tab.png` })

// 3b) context-window popover (the status bar's token chip, desktop island)
await page.evaluate(() => {
  void 0
  const els = Array.from(document.querySelectorAll('button')).filter((e) => e.textContent?.includes('tok'))
  els[0]?.click()
})
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/w10_76_context_popover.png` })
await page.keyboard.press('Escape')
await page.waitForTimeout(300)
const popCount = await page.locator('[data-testid="context-popover"]').count()
console.log('popover nach Esc:', popCount)
await page.close()

// 4) Mobile 390x844 — two rows + a slim pill bar
const mob = await boot(browser, { viewport: { width: 390, height: 844, deviceScaleFactor: 2 } });
(async () => { try { await mob.evaluate(SEED) } catch (e) { console.log("seed err:", e.message) } })();
await mob.waitForTimeout(600)
console.log('mobile rects:', JSON.stringify(await mob.evaluate(RECTS)))
await mob.screenshot({ path: `${OUT}/w10_75_mobile.png` })
await mob.close()

await browser.close()
console.log('OK 5 PNGs in', OUT)
