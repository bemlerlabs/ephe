/**
 * Persona 01 — the first-time user ("just installed Ephe, nothing is familiar").
 *
 * This spec runs against the LIVE product server at http://127.0.0.1:8765 (the built
 * app/dist, served by the Ephe product server) with the REAL engine
 * (openai_compatible / deepseek-v4-pro). It is deliberately different from
 * e2e/chat-sse.spec.ts: that spec intercepts the backend and pins German; this one
 * mocks NOTHING and uses the app's own English default (no stored i18nextLng →
 * fallbackLng 'en').
 *
 * It behaves like a real newcomer: open the app, look at what the first screen shows,
 * read the rail, open every main destination he would plausibly click, and try one
 * message. Every meaningful step is photographed full-page into the walkthrough
 * capture dir (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/persona-01-erstnutzer/.
 *
 * As it runs it appends an observed-facts block (per-step observations + every console
 * error, page error and failed network request) into that directory's notes.md, between
 * the RUNTIME markers. Re-running replaces only that block; the hand-written framing in
 * notes.md is preserved.
 *
 * Selector policy: `data-testid` / role / text exactly as they exist in app/src — never a
 * CSS class. Each lookup carries a fallback shape so a single renamed attribute does not
 * sink the walkthrough. Every wait is bounded and every "not there" is recorded as a
 * finding rather than deleted, so the walkthrough always completes and always reports
 * what it saw.
 */

import { test, expect, type Locator, type Page } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'
import { walkthroughOutDir } from './walkthrough-out.ts'
import { openTier } from './rail.ts'

/** The live product server (built app/dist). NOT the Vite dev server from playwright.config.ts. */
const BASE = 'http://127.0.0.1:8765'
/** HashRouter: every surface is a hash route off one document. */
const home = () => `${BASE}/#/`
const route = (hash: string) => `${BASE}/#/${hash.replace(/^\//, '')}`

const OUT_DIR = walkthroughOutDir('persona-01-erstnutzer')
const NOTES = path.join(OUT_DIR, 'notes.md')
const RUNTIME_BEGIN = '<!-- RUNTIME:persona-01 BEGIN -->'
const RUNTIME_END = '<!-- RUNTIME:persona-01 END -->'

type Severity = 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'

// ---- per-run bookkeeping (single worker: tests in one file run in order) ------------
let shotIndex = 0
let stepTitle = ''
let stepLines: string[] = []
const perStep = new Map<string, string[]>()
const consoleEvents: { type: string; text: string }[] = []
const pageErrors: string[] = []
const requestFailures: string[] = []

function record(text: string, severity: Severity = 'INFO'): void {
  stepLines.push(severity === 'INFO' ? `- ${text}` : `- **[${severity}]** ${text}`)
  console.log(`[persona-01] ${severity} ${text}`)
}

async function shoot(page: Page, name: string): Promise<string> {
  shotIndex += 1
  const file = path.join(OUT_DIR, `${String(shotIndex).padStart(2, '0')}-${name}.png`)
  // Let entrance animations settle so the image is crisp, not a mid-fade frame.
  await page.waitForTimeout(450)
  await page.screenshot({ path: file, fullPage: true })
  record(`Screenshot ${path.basename(file)}`)
  return file
}

/** First locator that matches, across fallback shapes (testid / role / text). */
function anyOf(page: Page, ...selectors: string[]): Locator {
  return selectors.map((s) => page.locator(s)).reduce((acc, next) => acc.or(next))
}

/**
 * innerText with a BOUNDED wait. A locator that never appears must not stall the step:
 * Playwright's default for text reads is the whole test timeout, which is what used to
 * spin step 1 to a 120 s timeout when the welcome state was not on screen.
 */
async function innerText(loc: Locator): Promise<string> {
  try {
    return (await loc.first().innerText({ timeout: 2_500 })).replace(/\s+/g, ' ').trim()
  } catch {
    return ''
  }
}

async function isVisible(loc: Locator): Promise<boolean> {
  try {
    return await loc.first().isVisible()
  } catch {
    return false
  }
}

/** Bounded wait for the first visible match among selectors; true if one appeared. */
async function waitVisible(page: Page, selectors: string[], timeout = 20_000): Promise<boolean> {
  try {
    await anyOf(page, ...selectors)
      .first()
      .waitFor({ state: 'visible', timeout })
    return true
  } catch {
    return false
  }
}

/** Every data-testid currently on the page — evidence for what actually rendered. */
async function testIds(page: Page): Promise<string[]> {
  return page
    .evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid]')).map(
        (e) => e.getAttribute('data-testid') || '',
      ),
    )
    .catch(() => [] as string[])
}

/** Short settle after the shell is up (sidebar visible). Does NOT wait for chat hydration. */
async function settle(page: Page): Promise<void> {
  await page.waitForTimeout(500)
}

/**
 * Wait for the chat pane to finish hydrating — either a rendered conversation
 * (chat-scroll-region) or the welcome empty state. Until then the pane shows the
 * app's loading skeleton, which is its true first paint.
 */
async function hydrate(page: Page): Promise<void> {
  await page
    .waitForSelector('[data-testid="chat-scroll-region"], [data-testid="ephe-mark-hero"]', {
      timeout: 30_000,
    })
    .catch(() => undefined)
  await page.waitForTimeout(500)
}

/** Navigate to a hash route and wait for the shell; a clear error if the server is down. */
async function open(page: Page, hash = ''): Promise<void> {
  const url = hash ? route(hash) : home()
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  } catch {
    throw new Error(
      `Live server at ${BASE} is not reachable. Build and start the product server ` +
        `(serving app/dist at ${BASE}) before running this walkthrough; do not mock it.`,
    )
  }
  await expect(page.getByTestId('chat-sidebar')).toBeVisible({ timeout: 30_000 })
  await settle(page)
}

/**
 * Press "New task" and wait for the welcome empty state. The app opens the most recent
 * stored session, so this is the only way a newcomer reaches the first-run surface.
 * Returns true when the welcome mark appeared.
 */
async function newTask(page: Page): Promise<boolean> {
  for (let attempt = 0; attempt < 2; attempt++) {
    await page
      .getByTestId('new-session')
      .click()
      .catch(() => undefined)
    try {
      await page.waitForSelector('[data-testid="ephe-mark-hero"]', { timeout: 8_000 })
      await page.waitForTimeout(500)
      return true
    } catch {
      /* retry once */
    }
  }
  return await isVisible(page.getByTestId('ephe-mark-hero'))
}

// ------------------------------------------------------------------------------------

test.describe('persona-01 first-time user', () => {
  test.use({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })

  test.beforeAll(() => {
    fs.mkdirSync(OUT_DIR, { recursive: true })
  })

  test.beforeEach(async ({ page }) => {
    stepTitle = test.info().title
    stepLines = []
    perStep.set(stepTitle, stepLines)

    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        consoleEvents.push({ type: msg.type(), text: msg.text() })
      }
    })
    page.on('pageerror', (err) => pageErrors.push(err.message))
    page.on('requestfailed', (req) => {
      requestFailures.push(
        `${req.method()} ${req.url()} — ${req.failure()?.errorText ?? 'unknown'}`,
      )
    })
  })

  // STEP 1 ------------------------------------------------------------------------
  test('step 1 — first impression: what does the very first screen show?', async ({ page }) => {
    // The newcomer opens the app. He has never seen this UI.
    await open(page)

    // The very first paint (before the chat hydrates) is the app's loading skeleton.
    // Record it, then wait for the real chat state so the screenshot shows content.
    const stillSkeleton = !(await waitVisible(
      page,
      ['[data-testid="chat-scroll-region"]', '[data-testid="ephe-mark-hero"]'],
      400,
    ))
    record(
      stillSkeleton
        ? 'First paint after load: the chat pane shows the loading skeleton (placeholder bars) — no conversation, no welcome state yet.'
        : 'First paint after load: the chat was already hydrated (no skeleton observed).',
      stillSkeleton ? 'LOW' : 'INFO',
    )
    await hydrate(page)

    const bubblesOnOpen = await page.locator('[data-testid="message-bubble"]').count()
    const brand = page.getByTestId('hero-brand')
    const brandOnOpen = await isVisible(brand)
    if (brandOnOpen) {
      record(`Hero claims the product name: "${await innerText(brand)}"`)
    } else if (bubblesOnOpen > 0) {
      record(
        `No welcome screen after load: the app restored a previous conversation ` +
          `(${bubblesOnOpen} message bubbles) instead of showing a first screen.`,
        'MEDIUM',
      )
    } else {
      record('No hero-brand element on the first screen.', 'MEDIUM')
    }

    const composer = page.getByTestId('chat-input')
    const composerOnOpen = await isVisible(composer)
    record(
      composerOnOpen
        ? 'The composer (chat-input) is present on the first screen.'
        : 'The composer is NOT on the first screen.',
      composerOnOpen ? 'INFO' : 'HIGH',
    )

    await shoot(page, 'first-screen')

    // A newcomer whose store already holds sessions still has to press "New task" to
    // see the first-run surface. Record what that reveals.
    const welcomeShown = await newTask(page)
    record(
      welcomeShown
        ? 'The welcome empty state appears only after pressing "New task" — not on open.'
        : 'Pressing "New task" did not reveal a welcome empty state.',
      welcomeShown ? 'MEDIUM' : 'HIGH',
    )

    // What — if anything — tells him the system is ready to use?
    const status = page.getByTestId('model-status-toast')
    if (await isVisible(status)) {
      record(`Readiness indicator present (model-status-toast): "${await innerText(status)}"`)
    } else {
      record(
        'No readiness indicator on the first screen — nothing says whether Ephe can answer.',
        'HIGH',
      )
    }

    // The brief says the setup gate will NOT appear (engine already configured). Report
    // what actually happens rather than asserting it.
    const setupCta = page.getByTestId('welcome-engine-setup')
    if (await isVisible(setupCta)) {
      record(
        `First-run setup CTA is showing ("${await innerText(setupCta)}") — the engine was expected to be configured.`,
        'HIGH',
      )
    } else if (page.url().includes('/setup')) {
      record('The app redirected to /setup — the engine was expected to be configured.', 'HIGH')
    } else {
      record('No setup gate: no engine-setup CTA (engine reported reachable).')
    }

    const greeting = page.getByTestId('hero-greeting')
    record(`Greeting line: "${(await innerText(greeting)) || '(empty)'}"`)
  })

  // STEP 2 ------------------------------------------------------------------------
  test('step 2 — the rail: what does the sidebar offer a newcomer?', async ({ page }) => {
    // He looks for the main areas. Where does he start?
    await open(page)

    // A newcomer on a fresh install: if the rail is collapsed to icons, expand it so the
    // labels he would actually read are on screen.
    const collapsed = await page.getByTestId('chat-sidebar').getAttribute('data-collapsed')
    if (collapsed !== null) {
      const expand = page.getByTestId('sidebar-expand-toggle')
      if (await isVisible(expand)) {
        await expand.click()
        record('Rail opened collapsed (icon-only); expanded it to read the labels.', 'LOW')
      }
    }

    // #71: on first run the rail shows the two primary rows and the two tier
    // heads; the eleven rows behind the heads appear once a tier is opened.
    const firstRun = page.getByTestId('sidebar-actions').getByRole('button')
    const firstLabels = (await firstRun.allInnerTexts())
      .map((s) => s.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    record(
      `Rail on first run (${firstLabels.length}): ${firstLabels.join(' | ') || '(none rendered)'}`,
    )

    await openTier(page, 'tools')
    await openTier(page, 'more')
    const navButtons = page.getByTestId('sidebar-actions').getByRole('button')
    const labels = (await navButtons.allInnerTexts())
      .map((s) => s.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    record(
      `Rail with both tiers open (${labels.length}): ${labels.join(' | ') || '(none rendered)'}`,
    )

    const newTaskBtn = page.getByTestId('new-session')
    record(
      (await isVisible(newTaskBtn))
        ? `Primary action present: "${await innerText(newTaskBtn)}"`
        : 'No "New task" button in the rail.',
    )

    await shoot(page, 'sidebar-navigation')

    expect(labels.length).toBeGreaterThan(0)
  })

  // STEP 3 ------------------------------------------------------------------------
  test('step 3 — the empty chat: what tells him what to do next?', async ({ page }) => {
    // He stares at the chat. Does it explain the product? On this store the app opens a
    // restored conversation, so he first presses "New task" to get an empty one.
    await open(page)
    const welcome = await newTask(page)
    record(
      welcome
        ? 'Reached the empty chat via "New task".'
        : 'The empty chat could not be reached ("New task" did not clear the session).',
      welcome ? 'INFO' : 'HIGH',
    )

    const sub = page.locator('[data-testid="hero-brand"] + p').first()
    const subText = await innerText(sub)
    if (subText) record(`Empty-state pitch under the hero: "${subText}"`)
    else record('No pitch line under the hero in the empty state.', 'LOW')

    const cards = page.locator('[data-testid^="welcome-card-"]')
    const cardCount = await cards.count()
    if (cardCount > 0) {
      const titles = (await cards.allInnerTexts()).map((s) => s.replace(/\s+/g, ' ').trim())
      record(`Suggestion cards (${cardCount}): ${titles.join(' | ')}`)
    } else {
      record('The empty chat offers no suggestion cards / starting points.', 'MEDIUM')
    }

    await shoot(page, 'welcome-empty-state')

    // He clicks the first suggestion. It must not fire an engine call — it fills the
    // composer draft so he can edit before sending. Record whether it does.
    if (cardCount > 0) {
      await cards.first().click()
      const composer = page.getByTestId('chat-input')
      let filled = false
      try {
        await expect(composer).toHaveValue(/\S/, { timeout: 10_000 })
        filled = true
      } catch {
        filled = false
      }
      record(
        filled
          ? `Clicking the first card filled the composer: "${await composer.inputValue()}"`
          : 'Clicking a suggestion card did NOT fill the composer (expected: it fills the draft, no engine call).',
        filled ? 'INFO' : 'MEDIUM',
      )
      await shoot(page, 'composer-after-card-click')
    }
  })

  // STEP 4 ------------------------------------------------------------------------
  test('step 4 — Knowledge: the first-run empty state of #/memory', async ({ page }) => {
    await open(page)
    await openTier(page, 'more')
    await page.getByTestId('sidebar-action-knowledge').click()
    const ok = await waitVisible(page, ['[data-testid="memory-page"]'])
    record(
      ok
        ? 'The knowledge page (memory-page) opened from the rail row "Knowledge".'
        : 'Clicking "Knowledge" did not open the knowledge page.',
      ok ? 'INFO' : 'HIGH',
    )
    if (!ok) record(`Page testids present: ${(await testIds(page)).slice(0, 40).join(', ')}`)

    const empty = page.getByTestId('memory-page-empty')
    const emptyVisible = await isVisible(empty)
    record(
      emptyVisible
        ? `Knowledge empty state reads: "${await innerText(empty)}"`
        : 'Knowledge shows no first-run empty state — the store already holds entries (not a fresh store).',
      emptyVisible ? 'INFO' : 'LOW',
    )

    await shoot(page, 'knowledge-page')
  })

  // STEP 5 ------------------------------------------------------------------------
  test('step 5 — Workbench: the first-run empty state of #/artifacts', async ({ page }) => {
    await open(page)
    await openTier(page, 'more')
    await page.getByTestId('sidebar-action-artifacts').click()
    const ok = await waitVisible(page, ['[data-testid="artifacts-page"]'])
    record(
      ok
        ? 'The workbench page (artifacts-page) opened from the rail row "Workbench".'
        : 'Clicking "Workbench" did not open the artifacts page.',
      ok ? 'INFO' : 'HIGH',
    )
    if (!ok) record(`Page testids present: ${(await testIds(page)).slice(0, 40).join(', ')}`)

    const hint = page.getByTestId('artifacts-ablage-hint')
    const hintVisible = await isVisible(hint)
    record(
      hintVisible
        ? `Workbench hint reads: "${await innerText(hint)}"`
        : 'Workbench shows no explanatory hint / empty state (the spool already holds artifacts).',
      hintVisible ? 'INFO' : 'LOW',
    )

    await shoot(page, 'workbench-page')
  })

  // STEP 6 ------------------------------------------------------------------------
  test('step 6 — Tools: what opens from #/tools', async ({ page }) => {
    await open(page)
    await openTier(page, 'tools')
    await page.getByTestId('sidebar-action-tools').click()
    const ok = await waitVisible(page, [
      '[data-testid="tools-vision"]',
      '[data-testid="tools-bundle"]',
    ])
    record(
      ok
        ? 'The tools page opened from the rail row "Tools".'
        : 'Clicking "Tools" opened no tools surface.',
      ok ? 'INFO' : 'HIGH',
    )
    if (!ok) record(`Page testids present: ${(await testIds(page)).join(', ')}`)

    const vision = page.getByTestId('tools-vision')
    const bundle = page.getByTestId('tools-bundle')
    record(`Tools surfaced: vision=${await isVisible(vision)}, bundle=${await isVisible(bundle)}`)

    await shoot(page, 'tools-page')
  })

  // STEP 7 ------------------------------------------------------------------------
  test('step 7 — Helpers: the side panel a newcomer opens from the rail', async ({ page }) => {
    await open(page)
    await openTier(page, 'tools')
    await page.getByTestId('sidebar-action-helpers').click()

    const panel = await waitVisible(page, [
      '[data-testid="subagents-view"]',
      '[data-testid="panel-empty-state"]',
      '[data-testid="panel-tab-card-subagents"]',
      '[data-testid="panel-add-tab"]',
    ])
    record(
      panel
        ? 'The helpers side panel opened from the rail row "Helpers".'
        : 'Clicking "Helpers" opened no side panel.',
      panel ? 'INFO' : 'HIGH',
    )
    if (!panel) record(`Page testids present: ${(await testIds(page)).join(', ')}`)

    const empty = page.getByTestId('subagents-empty')
    if (await isVisible(empty)) record(`Helpers empty state reads: "${await innerText(empty)}"`)
    else
      record(
        'No "no runs yet" empty state in the helpers view (the panel opened onto the tab list / card grid instead).',
        'LOW',
      )

    await shoot(page, 'helpers-panel')
  })

  // STEP 8 ------------------------------------------------------------------------
  test('step 8 — Settings: is the engine configured and named?', async ({ page }) => {
    await open(page)
    await page.getByTestId('sidebar-settings-btn').click()
    const ok = await waitVisible(page, ['[data-testid="settings-panel"]'])
    record(
      ok ? 'Settings opened from the rail.' : 'Settings did not open from the rail.',
      ok ? 'INFO' : 'HIGH',
    )

    // Engine is the first nav group; select it explicitly so the shot is deterministic.
    const engineNav = page.getByTestId('settings-nav-engine')
    if (await isVisible(engineNav)) {
      await engineNav.click()
      record('Selected the "Engine" section in the settings nav.')
    } else {
      record('No engine entry in the settings nav.', 'MEDIUM')
    }

    // The engine section's content mounts a beat after the panel opens (lazy mount), so
    // wait for it rather than sampling instantly — an instant check falsely reports "no
    // engine state" while the element is still 26 ms from appearing.
    const stateReady = await waitVisible(page, ['[data-testid="settings-engine-state"]'], 15_000)
    const state = page.getByTestId('settings-engine-state')
    if (stateReady) {
      const attr = await state.getAttribute('data-engine-state')
      record(
        `Settings names the engine state: "${await innerText(state)}" (data-engine-state=${attr}).`,
      )
    } else {
      record('Settings does not surface an engine state on the engine tab.', 'MEDIUM')
    }

    const activeEngine = page.getByTestId('settings-active-engine')
    if (await isVisible(activeEngine)) {
      record(`Active engine named in Settings: "${await innerText(activeEngine)}"`)
    }

    await shoot(page, 'settings-hub')
  })

  // STEP 9 ------------------------------------------------------------------------
  test('step 9 — first message: does it actually answer?', async ({ page }) => {
    // The moment of truth for a newcomer: he types one thing and sends it.
    await open(page)

    // If the language is not English the walkthrough's premise is wrong; record it.
    const lang = await page.evaluate(() => document.documentElement.lang)
    record(`Document language at runtime: "${lang}"`)

    // A first message belongs in a fresh task, not appended to a restored conversation.
    const fresh = await newTask(page)
    record(
      fresh
        ? 'Sending into a fresh, empty task.'
        : 'Could not clear the session; sending into the restored conversation.',
      fresh ? 'INFO' : 'MEDIUM',
    )

    const composer = page.getByTestId('chat-input')
    await composer.click()
    await composer.fill('Hello — what can you do on this machine?')
    await shoot(page, 'composer-draft')

    const send = anyOf(page, '[data-testid="send-btn"]', '[data-testid="stop-btn"]')
    await send.first().click()

    // The user's own message is deterministic — this is the only hard assertion here.
    const userBubble = page.locator('[data-testid="message-bubble"][data-role="user"]')
    await expect(userBubble.first()).toBeVisible({ timeout: 30_000 })
    record('The sent message appears as a user bubble.')

    // The reply is live-engine dependent: observe, do not assert.
    const assistantBubble = page.locator('[data-testid="message-bubble"][data-role="assistant"]')
    const streaming = page.getByTestId('stop-btn')
    let verdict = 'no assistant output within 90s'
    try {
      await Promise.race([
        assistantBubble.first().waitFor({ state: 'visible', timeout: 90_000 }),
        streaming.waitFor({ state: 'visible', timeout: 90_000 }),
      ])
      await expect(streaming)
        .toBeHidden({ timeout: 120_000 })
        .catch(() => undefined)
      verdict =
        (await assistantBubble.count()) > 0
          ? 'assistant produced a reply'
          : 'streaming ran but no bubble captured'
    } catch {
      // keep the default verdict
    }
    const count = await assistantBubble.count()
    record(
      `First-message outcome: ${verdict} (assistant bubbles=${count}).`,
      count > 0 ? 'INFO' : 'HIGH',
    )

    await shoot(page, 'after-first-send')
  })

  // ---- write the runtime observations into notes.md -----------------------------
  test.afterAll(() => {
    const lines: string[] = []
    lines.push(RUNTIME_BEGIN)
    lines.push('')
    lines.push(`## Runtime observations (generated ${new Date().toISOString()} by the spec)`)
    lines.push('')
    lines.push(`- Target: \`${BASE}\` (live product server, real engine, no mocking)`)
    for (const [title, body] of perStep) {
      lines.push('')
      lines.push(`### ${title}`)
      lines.push(body.length ? body.join('\n') : '- (no observations recorded)')
    }

    lines.push('')
    lines.push(`## Console errors / warnings (${consoleEvents.length})`)
    lines.push(
      consoleEvents.length
        ? consoleEvents.map((e) => `- [${e.type}] ${e.text}`).join('\n')
        : '- none',
    )
    lines.push('')
    lines.push(`## Page errors (${pageErrors.length})`)
    lines.push(pageErrors.length ? pageErrors.map((e) => `- ${e}`).join('\n') : '- none')
    lines.push('')
    lines.push(`## Failed network requests (${requestFailures.length})`)
    lines.push(requestFailures.length ? requestFailures.map((e) => `- ${e}`).join('\n') : '- none')
    lines.push('')
    lines.push(RUNTIME_END)
    lines.push('')

    const block = lines.join('\n')
    let existing = ''
    try {
      existing = fs.readFileSync(NOTES, 'utf8')
    } catch {
      existing = '# Persona 01 — first-time user walkthrough\n'
    }
    const begin = existing.indexOf(RUNTIME_BEGIN)
    const end = existing.indexOf(RUNTIME_END)
    const head = begin >= 0 ? existing.slice(0, begin).trimEnd() : existing.trimEnd()
    const tail = end >= 0 ? existing.slice(end + RUNTIME_END.length).replace(/^\s*\n/, '') : ''
    fs.writeFileSync(NOTES, `${head}\n\n${block}${tail ? `\n${tail}` : ''}`)
    console.log(`[persona-01] wrote runtime notes to ${NOTES}`)
  })
})
