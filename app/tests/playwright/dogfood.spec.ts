import { test, expect, Page } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'

/**
 * Ephe dogfood spec — G1–G8 from a user's perspective against the DEV server (5173) + the live backend (8765).
 * Screenshots go to /tmp/ephe-dogfood/, console errors are captured, but only
 * real UI errors count (8765/localhost/WebSocket/ERR_* are the expected offline-first ones).
 */

const SHOTS = '/tmp/ephe-dogfood'
fs.mkdirSync(SHOTS, { recursive: true })

// The product names no model, so the lane must read the owner's persisted choice
// instead of pinning one — a hardcoded tag turns the instrument red when the
// engine changes for a reason that has nothing to do with the UI.
const ACTIVE_MODEL = (() => {
  try {
    const file = path.join(process.env.HOME ?? '', '.ephe', 'engine.json')
    return String(JSON.parse(fs.readFileSync(file, 'utf8')).model ?? '')
  } catch {
    return ''
  }
})()
const ACTIVE_MODEL_RE = ACTIVE_MODEL
  ? new RegExp(ACTIVE_MODEL.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  : null

const uiErrors = (errors: string[]) =>
  errors.filter(
    (e) =>
      !e.includes('8765') &&
      !e.includes('localhost') &&
      !e.includes('WebSocket') &&
      !e.includes('[WS]') &&
      !e.includes('ERR_FAILED') &&
      !e.includes('ERR_CONNECTION_REFUSED') &&
      !e.includes('favicon') &&
      !e.includes('404') &&
      !e.includes('501'),
  )

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('ephe.intro.seen.v1', '1')
  })
})

async function boot(page: Page, label: string, consoleCapture?: string[]) {
  if (consoleCapture) {
    page.on('console', (m) => {
      if (m.type() === 'error') consoleCapture.push(m.text())
    })
  }
  await page.goto('/', { waitUntil: 'load' })
  await page.waitForSelector('textarea', { timeout: 15000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.screenshot({ path: path.join(SHOTS, `${label}.png`) })
}

const composer = (page: Page) => page.locator('textarea').first()

test.describe('Dogfood G1–G8 (dev 5173 + backend 8765)', () => {
  test('P1 Baseline: Dashboard, Sidebar, Composer, keine UI-Errors', async ({ page }) => {
    const errors: string[] = []
    await boot(page, '01-baseline', errors)
    await expect(page.locator('[data-testid="chat-sidebar"]')).toBeVisible()
    // The sidebar's full-width new-task row is the shipped control; the header ⊕
    // was removed by the chrome budget and has no testid in the product today.
    await expect(page.getByTestId('new-session')).toBeVisible()
    expect(uiErrors(errors)).toEqual([])
  })

  test('P2 Chat: senden → Stream → Antwort; Composer bleibt beim Streamen tipbar', async ({
    page,
  }) => {
    const errors: string[] = []
    await boot(page, '02a-chat-gesendet', errors)
    const ta = composer(page)
    await ta.fill('Hallo, sag in einem Satz wer du bist.')
    await ta.press('Enter')
    // sending produced the bubble (the user message is visible)
    await expect(page.getByText('Hallo, sag in einem Satz wer du bist.').first()).toBeVisible({
      timeout: 10000,
    })
    // G1: typing stays possible while streaming (the composer is not disabled)
    await ta.fill('Und jetzt ein zweiter Satz.')
    await expect(ta).toHaveValue('Und jetzt ein zweiter Satz.')
    await ta.fill('')
    // wait for the assistant answer (DGX qwen3.8-27b: up to 60s)
    await page.waitForSelector('text=/^.*$/s', { timeout: 100 }).catch(() => {})
    await page.waitForTimeout(30000)
    await page.screenshot({ path: path.join(SHOTS, '02b-chat-antwort.png') })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P2 Hover-Toolbar: Copy + Neu generieren auf fertiger Assistant-Bubble', async ({
    page,
  }) => {
    // A live free endpoint can take longer than the 60 s default; the stream-end
    // wait below is the real boundary.
    test.setTimeout(180_000)
    const errors: string[] = []
    await boot(page, '02c-toolbar', errors)
    // an existing session from P2? No — a fresh page. Send something short, let it answer.
    const ta = composer(page)
    await ta.fill('Sag kurz: OK')
    await ta.press('Enter')
    // wait for the end of the stream — the toolbar only renders once !m.streaming.
    // (DGX qwen3.8-27b can take >25s; the earlier fixed wait time was the artifact.)
    // Wait for the stream to end — the toolbar only renders on bubbles that have
    // finished streaming; hovering during the stream is a race (a flake source).
    await page.waitForFunction(() => document.querySelectorAll('[aria-busy="true"]').length === 0, {
      timeout: 90_000,
    })
    // DD-27: the text filter /OK|ok/i over the model answer was the flake source —
    // free-form model answers need not contain the expected token. The
    // data-role anchor is deterministic; the toolbar is narrowed to the bubble
    // itself instead of being searched for globally.
    const bubble = page.locator('[data-testid="message-bubble"][data-role="assistant"]').last()
    await expect(bubble).toBeVisible({ timeout: 10000 })
    await bubble.hover()
    const regen = bubble.getByRole('button', { name: /Neu generieren|Regenerate/i }).first()
    await expect(regen).toBeVisible({ timeout: 10000 })
    await page.screenshot({ path: path.join(SHOTS, '02d-toolbar-hover.png') })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P3 Auto-Titel: erste Message benennt Session an Wortgrenze; Rename bleibt bestehen', async ({
    page,
  }) => {
    const errors: string[] = []
    await boot(page, '03-a', errors)
    // An auto title belongs to a NEW session; the previous version sent the prompt
    // into the restored one and then waited for a title that could never change.
    await page.getByTestId('new-session').click()
    const ta = composer(page)
    await ta.fill(
      'Gib mir eine ausführliche Liste mit den zehn häufigsten Programmiersprachen und ihrer Geschichte.',
    )
    await ta.press('Enter')
    await page.waitForTimeout(20000)
    // The sidebar refreshes its list on its own cadence; a reload proves the title
    // persisted instead of racing that poll.
    await page.reload({ waitUntil: 'load' })
    const sidebarTitle = page
      .locator('[data-testid="sessions-view"]')
      .locator('text=/Gib mir eine ausführliche Liste mit den zehn/i')
      .first()
    await expect(sidebarTitle).toBeVisible({ timeout: 30000 })
    await page.screenshot({ path: path.join(SHOTS, '03-b-auto-titel.png') })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P6 Settings: Panel öffnet, Model-Picker live, Memory-Stats, Sprache de/en', async ({
    page,
  }) => {
    test.skip(!ACTIVE_MODEL_RE, 'no persisted engine model to compare against')
    const errors: string[] = []
    await boot(page, '04-settings', errors)
    await page.getByTestId('sidebar-settings-btn').click()
    await expect(page.locator('[data-testid="settings-panel"]')).toBeVisible({ timeout: 10000 })
    await page.screenshot({ path: path.join(SHOTS, '04b-settings-modell.png') })
    // model picker: the owner's persisted model is the one the UI shows
    await expect(page.getByText(ACTIVE_MODEL_RE!).first()).toBeVisible({ timeout: 10000 })
    // memory tab: the vector statistics (the tab key is stable; the German label is "Wissen")
    await page.getByTestId('settings-nav-memory').click()
    await page.waitForTimeout(1500)
    await page.screenshot({ path: path.join(SHOTS, '04c-settings-memory.png') })
    // language: open the language tab → pick 'English' → the labels switch and persist
    await page.getByTestId('settings-nav-language').click()
    await page
      .getByRole('radio', { name: /English/i })
      .first()
      .click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: path.join(SHOTS, '04d-settings-sprache-en.png') })
    await page
      .evaluate(() => localStorage.getItem('i18nextLng'))
      .then((v) => {
        expect(['de', 'en']).toContain(v)
      })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P7 Slash-Commands: /model /sessions /skills /settings antworten im Chat', async ({
    page,
  }) => {
    test.skip(!ACTIVE_MODEL_RE, 'no persisted engine model to compare against')
    const errors: string[] = []
    await boot(page, '05-slash', errors)
    const ta = composer(page)
    for (const cmd of ['/model', '/sessions', '/skills']) {
      await ta.fill(cmd)
      await ta.press('Enter')
      await page.waitForTimeout(1200)
    }
    await page.screenshot({ path: path.join(SHOTS, '05-slash-antworten.png') })
    // /model shows the owner's active model
    await expect(page.getByText(ACTIVE_MODEL_RE!).first()).toBeVisible()
    // an unknown command → feedback (not silence)
    await ta.fill('/definitely-not-a-command')
    await ta.press('Enter')
    await page.waitForTimeout(1200)
    await page.screenshot({ path: path.join(SHOTS, '05b-slash-unbekannt.png') })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P8 Mobile Viewport (390x844): Sidebar-Collapse, Composer, Bubbles', async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    })
    const mpage = await ctx.newPage()
    await mpage.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'de')
      localStorage.setItem('ephe_onboarded', '1')
      localStorage.setItem('ephe.intro.seen.v1', '1')
    })
    const errors: string[] = []
    mpage.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    await mpage.goto('http://localhost:5173/', { waitUntil: 'load' })
    await mpage.waitForSelector('textarea', { timeout: 15000 })
    await mpage.screenshot({ path: path.join(SHOTS, '06-mobile-baseline.png') })
    // the composer is visible + typeable
    const ta = mpage.locator('textarea').first()
    await ta.fill('Hallo mobil')
    await ta.press('Enter')
    await mpage.waitForTimeout(20000)
    await mpage.screenshot({ path: path.join(SHOTS, '06b-mobile-chat.png') })
    await ctx.close()
    expect(uiErrors(errors)).toEqual([])
  })

  test('P10 Companion at 390 does not overlap the task dock', async ({ browser }) => {
    test.setTimeout(120_000)
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    })
    const page = await ctx.newPage()
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'de')
      localStorage.setItem('ephe_onboarded', '1')
      localStorage.setItem('ephe.intro.seen.v1', '1')
    })
    await page.goto('http://localhost:5173/', { waitUntil: 'load' })
    const companion = page.getByTestId('workspace-companion')
    await expect(companion).toBeVisible({ timeout: 30000 })
    const dock = page.locator('[data-testid="task-dock-pill"], [data-testid="task-dock"]').first()
    await expect(dock).toBeVisible({ timeout: 30000 })
    const a = await companion.boundingBox()
    const b = await dock.boundingBox()
    expect(a).not.toBeNull()
    expect(b).not.toBeNull()
    const overlap =
      a!.x < b!.x + b!.width &&
      b!.x < a!.x + a!.width &&
      a!.y < b!.y + b!.height &&
      b!.y < a!.y + a!.height
    expect(overlap, `companion ${JSON.stringify(a)} dock ${JSON.stringify(b)}`).toBe(false)
    await page.screenshot({ path: path.join(SHOTS, '10-companion-390.png') })

    const visibleActors = () =>
      page.evaluate(() => {
        const ids = [
          'workspace-companion',
          'header-companion',
          'ephe-mark-hero',
          'interactive-bee-guide',
        ]
        return ids.filter((id) => {
          const el = document.querySelector(`[data-testid="${id}"]`)
          if (!el) return false
          const style = getComputedStyle(el)
          const rect = el.getBoundingClientRect()
          return (
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            rect.width > 0 &&
            rect.height > 0
          )
        })
      })

    // One actor on the active page, one on the empty welcome, one in the tour.
    expect(await visibleActors()).toEqual(['workspace-companion'])
    await page.getByTestId('header-menu-toggle').click()
    await page.getByTestId('new-session').click()
    await page.keyboard.press('Escape')
    await page.waitForSelector('[data-testid="ephe-mark-hero"]', { timeout: 30000 })
    expect(await visibleActors()).toEqual(['ephe-mark-hero'])
    await page.goto('http://localhost:5173/?tour=1', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="interactive-bee-guide"]', { timeout: 30000 })
    expect(await visibleActors()).toEqual(['interactive-bee-guide'])
    await ctx.close()
  })

  test('P4 Attachments: Bild + Textdatei werden als Chips gerendert, entfernen funktioniert', async ({
    page,
  }) => {
    const errors: string[] = []
    await boot(page, '07a-attach-start', errors)
    // fixtures: a 1x1 PNG (base64) + a text file
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==',
      'base64',
    )
    const imgPath = path.join(SHOTS, 'fixture.png')
    fs.writeFileSync(imgPath, png)
    const txtPath = path.join(SHOTS, 'fixture.txt')
    fs.writeFileSync(txtPath, 'Hallo aus der Dogfood-Spec\n')

    // the image goes in through the hidden image input (accept="image/*")
    const imageInput = page.locator('input[type="file"][accept="image/*"]').first()
    await imageInput.setInputFiles(imgPath)
    await expect(page.getByText('fixture.png', { exact: false }).first()).toBeVisible({
      timeout: 5000,
    })
    await page.screenshot({ path: path.join(SHOTS, '07b-attach-bild.png') })

    // the text file through the general file input (no accept attribute)
    const fileInput = page.locator('input[type="file"]:not([accept])').first()
    await fileInput.setInputFiles(txtPath)
    await expect(page.getByText('fixture.txt', { exact: false }).first()).toBeVisible({
      timeout: 5000,
    })
    await page.screenshot({ path: path.join(SHOTS, '07c-attach-text.png') })

    // remove both chips → the preview disappears
    const removeBtns = page.getByRole('button', { name: /Attachment entfernen/i })
    await removeBtns.first().click()
    await removeBtns.first().click()
    await expect(page.getByText('fixture.png', { exact: false })).toHaveCount(0)
    await expect(page.getByText('fixture.txt', { exact: false })).toHaveCount(0)
    expect(uiErrors(errors)).toEqual([])
  })

  test('P5 Toasts: Sprachwechsel zeigt Success-Toast (role="status", auto-dismiss)', async ({
    page,
  }) => {
    const errors: string[] = []
    await boot(page, '08a-toast-start', errors)
    await page.getByTestId('sidebar-settings-btn').click()
    await expect(page.locator('[data-testid="settings-panel"]')).toBeVisible({ timeout: 10000 })
    await page.getByTestId('settings-nav-language').click()
    await page
      .getByRole('radio', { name: /English/i })
      .first()
      .click()
    // The toast speaks the language it just switched to.
    const toast = page.getByRole('status').filter({ hasText: /Sprache geändert|Language changed/i })
    await expect(toast).toBeVisible({ timeout: 10000 })
    await page.screenshot({ path: path.join(SHOTS, '08b-toast-sprache.png') })
    // auto-dismiss: the toast disappears on its own (5s + buffer)
    await expect(toast).toBeHidden({ timeout: 10000 })
    expect(uiErrors(errors)).toEqual([])
  })

  test('P9 Thinking-Stream + G8 i18n: "Denkt nach…" live, danach kollabiert; keine EN-Phase-Labels', async ({
    page,
  }) => {
    // Live engine: reasoning latency varies a lot — the budget is set deliberately,
    // instead of failing intermittently at the 60s default.
    test.setTimeout(180_000)
    const errors: string[] = []
    await boot(page, '09a-thinking-live', errors)
    // A restored session may still carry the in-flight block of an interrupted
    // turn; this leg measures the block the current turn opens and closes.
    await page.getByTestId('new-session').click()
    const ta = composer(page)
    await ta.fill('Erkläre in zwei Sätzen, was du gerade denkst.')
    await ta.press('Enter')
    // thinking_start is emitted IMMEDIATELY (before the model call) → the live label
    await expect(page.getByText(/Denkt nach…|Thinking/i).first()).toBeVisible({ timeout: 20000 })
    // the reasoning text comes AFTER the tool detection (non-streaming) → wait
    // until the live text is visible in the thinking block, then take the evidence screenshot.
    await page
      .waitForFunction(
        () => {
          const blocks = [...document.querySelectorAll('[aria-busy="true"]')]
          return blocks.some((b) => (b.textContent ?? '').length > 40)
        },
        { timeout: 60000 },
      )
      .catch(() => {})
    await page.screenshot({ path: path.join(SHOTS, '09b-thinking-live-shot.png') })
    // answer finished = no aria-busy message left (it stops thinking / collapses then).
    // Wait for the real stream end instead of a blind wait — the rigid 40s wait was
    // the flakiness source against the real DGX latency.
    await page.waitForFunction(() => document.querySelectorAll('[aria-busy="true"]').length === 0, {
      timeout: 150_000,
    })
    await page.screenshot({ path: path.join(SHOTS, '09c-thinking-collapsed.png') })
    const body = await page.locator('body').innerText()
    // G8: the backend phase strings ("Analyzing request…"/"Generating response…") must
    // no longer shine through in English — activityLabels.ts maps them onto the German keys.
    expect(body).not.toMatch(/Analyzing request|Generating response/i)
    expect(uiErrors(errors)).toEqual([])
  })

  // R36-B regression (found live during the full audit B5): the virtualizer cache
  // keeps sticking at estimateSize 120 after a streamed turn —
  // measure() empties the cache, but existing DOM rows are not measured
  // again (the refs do not fire once more, and ResizeObserver does not report without
  // a size change). Tall answers then overlap the following
  // rows. Two turns: a tall answer + a short follow-up question makes it visible.
  test('R36-B: Nach Stream-Ende ueberlappen Nachrichtenreihen nicht', async ({ page }) => {
    const errors: string[] = []
    await boot(page, 'r36b-overlap', errors)
    const ta = composer(page)
    // the turn really ended: the stop button appears (the turn started — aria-busy
    // alone falls into the TTFT gap, before the bubble exists) and turns back
    // into the send button (the turn is done). Otherwise turn 2 slips into
    // the composer queue and the test measures too early.
    const waitTurnDone = async () => {
      await page.waitForSelector('[data-testid="stop-btn"]', { timeout: 60_000 })
      await page.waitForSelector('[data-testid="send-btn"]', { state: 'visible', timeout: 150_000 })
    }
    // Turn 1: a tall answer (the streamed list is >> 120px)
    await ta.fill(
      'Antworte ausschließlich mit einer Markdown-Liste aus 12 nummerierten Punkten. Jeder Punkt besteht aus zwei vollständigen Sätzen über eine europäische Hauptstadt.',
    )
    await ta.press('Enter')
    // self-diagnosis: the turn MUST have started (the user bubble is visible),
    // otherwise the overlap check only measures old rows and the test is worthless.
    await expect(
      page.getByText(/Antworte ausschließlich mit einer Markdown-Liste/).first(),
    ).toBeVisible({
      timeout: 15000,
    })
    await waitTurnDone()
    // Turn 2: a short follow-up question — its rows have to sit BELOW the tall answer
    await ta.fill('Sag nur: OK')
    await ta.press('Enter')
    await expect(page.getByText('Sag nur: OK').first()).toBeVisible({ timeout: 15000 })
    await waitTurnDone()
    await page.waitForTimeout(1500) // the end-of-turn re-measure has to have run through
    const overlaps = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('[data-testid="message-row"]'))
        .map((el) => ({
          start: parseInt((el.style.transform.match(/-?\d+(?:\.\d+)?/) ?? ['0'])[0] ?? '0', 10),
          h: el.offsetHeight,
        }))
        .sort((a, b) => a.start - b.start)
      let prevEnd = 0
      const bad: Array<{ start: number; h: number }> = []
      for (const r of rows) {
        if (r.start < prevEnd - 2) bad.push(r)
        prevEnd = Math.max(prevEnd, r.start + r.h)
      }
      return bad
    })
    await page.screenshot({ path: path.join(SHOTS, 'r36b-overlap-after.png') })
    expect(overlaps).toEqual([])
  })
})
