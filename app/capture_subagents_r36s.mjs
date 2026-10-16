/**
 * R36-S visual gate: render the SubagentsTab with real subagent activities.
 * Seeds the dev store (window.__epheStore) with two SubAgent feed rows
 * (running + done) and shoots a 2x Dark-DE desktop screenshot.
 * Usage (from app/): node capture_subagents_r36s.mjs [output.png]
 */
import { chromium } from 'playwright-core'

const out = process.argv[2] || '/tmp/audit/r36s_subagents_1.png'

const SEED = () => {
  const store = window.__epheStore
  if (!store) return 'no-store'
  const now = Date.now()
  const mk = (id, label, status, detail) => ({ id, label, status, ...(detail ? { detail } : {}) })
  const session = {
    id: 'seed-r36s',
      id: 'seed-r36s',
      title: 'R36-S Subagent-Feed',
      messages: [
        {
          id: 'm1', role: 'user', content: 'Recherchiere die aktuellen Timeout-Standards für HTTP-Clients.',
          timestamp: now - 90_000,
        },
        {
          id: 'm2', role: 'assistant',
          content: 'Ich delegiere die Recherche an einen Subagenten und fasse die Ergebnisse zusammen.',
          timestamp: now - 80_000,
          activities: [
            mk('a1', 'spawn_agent', 'done', 'Web-Recherche: HTTP-Client-Timeouts'),
            mk('a2', 'SubAgent subagent-1 (researcher)', 'running', 'web_search: {"query": "HTTP client timeout best practices"}'),
            mk('a3', 'SubAgent subagent-2 (reviewer)', 'done', 'Report: 4 Quellen, p95 30s empfohlen.'),
          ],
          toolCalls: [],
        },
      ],
    createdAt: now - 120_000,
    updatedAt: now - 60_000,
  }
  store.setState({
    sessions: [session],
    activeSessionId: 'seed-r36s',
    currentSession: session,
  })
  return store.getState().activeSessionId
}

const browser = await chromium.launch()
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  colorScheme: 'dark',
})
await page.addInitScript(() => {
  localStorage.setItem('i18nextLng', 'de')
  localStorage.setItem('ephe_onboarded', '1')
})

await page.goto('http://localhost:5173/chat', { waitUntil: 'networkidle' })
await page.waitForSelector('[data-testid="status-bar"]', { timeout: 20_000 })
await page.waitForTimeout(1600)

const seeded = await page.evaluate(SEED)
if (seeded === 'no-store') throw new Error('window.__epheStore fehlt (dev build?)')
await page.waitForTimeout(600)
// Activate the Subagents tab: open the panel if needed; an empty panel state →
// tab cards, otherwise the add menu.
const toggle = page.locator('[data-testid="side-panel-toggle"]')
if (await toggle.count()) await toggle.first().click()
await page.waitForTimeout(700)
const card = page.locator('[data-testid="panel-tab-card-subagents"]')
const addItem = page.locator('[data-testid="panel-new-tab-item-subagents"]')
if (await card.count()) {
  await card.first().click()
} else {
  await page.locator('[data-testid="panel-add-tab"]').click()
  await addItem.click()
}
await page.waitForSelector('[data-testid="subagents-view"]', { timeout: 10_000 })
await page.waitForTimeout(900)

await page.screenshot({ path: out })
console.log('saved:', out)
await browser.close()
