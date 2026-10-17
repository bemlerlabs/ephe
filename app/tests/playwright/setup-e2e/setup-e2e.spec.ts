import { test, expect } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

// ESM: `__dirname` is not available in a "type":"module" package.
const __dirname = path.dirname(fileURLToPath(import.meta.url))

/**
 * E2E against the REAL Ephe server — no mock, no stubs, real
 * Chromium, real DGX (SGLang/OpenAI-compatible).
 *
 * Tests the complete end-user first-run flow:
 *
 *   1. PWA loads → setup page (engine choice), because no engine.json exists
 *   2. User picks "OpenAI-compatible API" (DGX Spark via Tailnet)
 *   3. Endpoint input → probe → real model list from the DGX (/v1/models)
 *   4. Model choice → Save → engine.json gets persisted
 *   5. The app now shows the chat (configured=true)
 *   6. Chat message → REAL inference on the DGX → assistant reply
 *
 * Requirement: remote engine reachable — EPHE_EPHE_E2E_DGX_URL must point at
 * your own OpenAI-compatible endpoint (no hostname in the repo).
 * No Ollama, no gemma4 — the E2E uses the fast remote engine,
 * because Ollama would be too slow on the MacBook (user mandate 2026-08-21).
 */

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const E2E_CONFIG_DIR = path.join(REPO_ROOT, '.e2e-runtime', 'config')
const E2E_ENGINE_JSON = path.join(E2E_CONFIG_DIR, 'engine.json')

// W18: the endpoint comes from the env (no private hostname in the repo).
// Without EPHE_EPHE_E2E_DGX_URL the test aborts with a clear message (below).
const DGX_URL = (process.env.EPHE_EPHE_E2E_DGX_URL || '').replace(/\/$/, '')

// DGX inference (27B, SGLang): the first answer can take several seconds.
const CHAT_TIMEOUT = 90000

test.describe('Ephe first-run E2E (real server + real DGX, no mock)', () => {
  test.beforeAll(async () => {
    // Precondition: remote engine reachable — otherwise no meaningful E2E run.
    // (The server probe would report that too, but a clean
    // precondition error message beats a UI test that blows up.)
    if (!DGX_URL) {
      throw new Error(
        'EPHE_EPHE_E2E_DGX_URL is not set — this E2E needs your own ' +
          'OpenAI-compatible endpoint (there is no default in the repo).',
      )
    }
    // SSRF hardening (scanner finding): scheme allowlist + URL parse + no
    // redirects — the target stays owner-configured (env), but script-
    // controlled schemes/jumps are ruled out.
    const base = DGX_URL.replace(/\/v1$/, '')
    const modelsUrl = new URL(`${base}/v1/models`)
    if (modelsUrl.protocol !== 'http:' && modelsUrl.protocol !== 'https:') {
      throw new Error('EPHE_EPHE_E2E_DGX_URL must be http(s) — every other scheme is excluded.')
    }
    const res = await fetch(modelsUrl, { redirect: 'error' })
    if (!res.ok) {
      throw new Error(
        `DGX engine not reachable (${DGX_URL}): HTTP ${res.status}. ` +
          `Set EPHE_EPHE_E2E_DGX_URL or start the DGX Spark.`,
      )
    }
    const data = await res.json()
    const ids = (data.data || []).map((m: { id: string }) => m.id)
    if (ids.length === 0) {
      throw new Error(`DGX engine answers but lists no models: ${JSON.stringify(data)}`)
    }
    console.log(`[e2e] DGX reachable, models: ${ids.join(', ')}`)
  })

  test(
    'First run: setup page → DGX probe → model choice → chat with real inference',
    async ({ page }) => {
      const errors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(msg.text())
      })

      // ── 1. PWA loads → setup page (no engine.json → configured=false) ───
      await page.goto('/', { waitUntil: 'domcontentloaded' })
      const setupPage = page.locator('[data-testid="setup-page"]')
      await expect(setupPage).toBeVisible({ timeout: 15000 })
      await expect(setupPage.getByRole('heading', { name: /Engine/i })).toBeVisible()

      // ── 2. Provider: OpenAI-compatible API (DGX) ─────────
      await page.locator('[data-testid="setup-option-openai"]').click()
      // The endpoint input appears (only for remote engines)
      await expect(page.locator('[data-testid="setup-endpoint"]')).toBeVisible()

      // ── 3. Enter the endpoint + probe (real /api/model/providers/probe →
      //    backend → DGX /v1/models) ──
      await page.locator('[data-testid="setup-endpoint"]').fill(DGX_URL)
      await page.locator('[data-testid="setup-probe"]').click()

      const status = page.locator('[data-testid="setup-status"]')
      await expect(status).toBeVisible({ timeout: 15000 })
      // The state attribute, not the sentence next to it: `erreichbar` is `de.json`
      // copy (`setup.engineState.ok`), and an English UI would have failed this step
      // while the probe was working perfectly.
      await expect(status).toHaveAttribute('data-engine-state', 'ok', { timeout: 15000 })

      // The model select with the real DGX models
      const modelSelect = page.locator('[data-testid="setup-model"]')
      await expect(modelSelect).toBeVisible({ timeout: 10000 })
      const modelOptions = await modelSelect.locator('option').allTextContents()
      expect(modelOptions.length).toBeGreaterThan(0)
      console.log(`[e2e] DGX probe lists models: ${modelOptions.join(', ')}`)
      // Confirm the first (default) model
      await modelSelect.selectOption({ index: 0 })
      const selectedModel = await modelSelect.inputValue()

      // ── 4. Save → POST /api/settings (session override + engine.json) ────────
      await page.locator('[data-testid="setup-finish"]').click()

      // Check persistence: engine.json in the isolated E2E config dir
      await page.waitForTimeout(500) // persistence is synchronous server-side
      expect(fs.existsSync(E2E_ENGINE_JSON)).toBe(true)
      const persisted = JSON.parse(fs.readFileSync(E2E_ENGINE_JSON, 'utf-8'))
      expect(persisted.provider).toBe('openai_compatible')
      expect(persisted.model).toBe(selectedModel)
      expect(persisted.api_url).toBe(DGX_URL)
      console.log(`[e2e] engine.json persisted:`, JSON.stringify(persisted))

      // ── 5. After persist → app re-checks status → chat (no setup left) ───
      await page.goto('/#/chat', { waitUntil: 'domcontentloaded' })
      const chatPanel = page.locator('[data-testid="panel-chat"]')
      await expect(chatPanel).toBeVisible({ timeout: 20000 })

      // The setup page must NEVER become visible again (configured=true)
      await expect(page.locator('[data-testid="setup-page"]')).toHaveCount(0)

      // ── 6. REAL inference: chat message to the DGX ────
      // Located by test id, not by placeholder copy: the placeholder is translated
      // product text, and the old selector had already outlived that string, so
      // step 6 could not pass in any language. `data-testid="chat-input"` is the
      // composer's own contract (app/src/components/dashboard/ChatInput.tsx).
      const input = page.locator('[data-testid="chat-input"]')
      await expect(input).toBeVisible({ timeout: 10000 })
      await input.fill('Sag in einem Wort: Hallo')
      await input.press('Enter')

      // The user message renders immediately
      await expect(chatPanel.getByText('Sag in einem Wort: Hallo')).toBeVisible({ timeout: 10000 })

      // Assistant reply from the real DGX (SGLang, 27B) — generous timeout
      const assistantBubble = chatPanel.locator('.glass-reading.rounded-tl-sm')
      await expect(assistantBubble.first()).not.toHaveCount(0, { timeout: CHAT_TIMEOUT })
      const reply = (await assistantBubble.first().innerText()).trim()
      expect(reply.length).toBeGreaterThan(0)
      console.log(`[e2e] DGX answer: "${reply.slice(0, 120)}"`)

      // No UI errors (API-/WS-connection-refused is irrelevant in the E2E context,
      // since it is same-origin — what counts here is genuine UI error freedom)
      const uiErrors = errors.filter(
        (e) =>
          !e.includes('favicon') &&
          !e.includes('404') &&
          !e.includes('Failed to load resource') &&
          // WS handshake noise (by design): the PWA UI permanently tries a
          // WS connection to /ws/chat (an annex for streaming) — the server
          // deliberately has no WS endpoint right now, chat runs over REST /api/chat
          // (see the ChatLayout comment). The browser logs the failed
          // handshake as a console error and the WSClient (websocket.ts) also
          // logs '[WS] Error: Event' itself per reconnect attempt. Both
          // are expected UI architecture without a WS backend, not a UI bug.
          !e.includes('WebSocket') &&
          !e.includes('[WS]') &&
          !e.includes('ERR_'),
      )
      expect(uiErrors).toEqual([])
    },
    CHAT_TIMEOUT + 60000,
  )

  test('Reset: /api/setup/reset → the setup page comes back', async ({ page }) => {
    // Before: the chat is configured
    await page.goto('/#/chat', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('[data-testid="panel-chat"]')).toBeVisible({ timeout: 20000 })

    // Forget the engine choice (direct API call + UI parity)
    const res = await page.request.post('/api/setup/reset')
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.configured).toBe(false)
    expect(fs.existsSync(E2E_ENGINE_JSON)).toBe(false)

    // UI reload → the setup page is visible again (first-run flow testable)
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('[data-testid="setup-page"]')).toBeVisible({ timeout: 15000 })
  })
})
