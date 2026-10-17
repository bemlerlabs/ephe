/**
 * Session deep-check — the session store, the restore race, and the task menu.
 *
 * This spec runs against the LIVE product server (default http://127.0.0.1:8765,
 * override with EPHE_WALKTHROUGH_BASE) with the REAL engine. It mocks NOTHING.
 * The locale is pinned to English through addInitScript (a user setting, not a
 * backend mock — the server still answers for real).
 *
 * What it is built to answer, with screenshots and a machine-readable verdict per
 * attempt (observations.json):
 *
 *   1. Cold open in a clean browser context: WHICH task is active, and is the user
 *      told anything that this is restored history rather than a new task?
 *   2. The restore race: type and send IMMEDIATELY after load (no settle) three
 *      times in a row — did the sent message stay in the task it was sent from, or
 *      was the view displaced by a late `GET /api/sessions/restore`?
 *   3. Switch a task in the sidebar, then reload: does the chosen task come back,
 *      or does the newest one win?
 *   4. "New task" (header control and Command-N): does it really start empty, does
 *      the title update as the conversation grows, and does the restored-history
 *      behaviour stay away?
 *   5. The task menu: which actions exist for real (rename, delete, pin, export,
 *      ...), and is the 22x22 px trigger usable?
 *   6. What happens when the task store is empty, and when a task was deleted?
 *
 * Selector policy: data-testid / role / accessible name exactly as they exist in
 * app/src — never a CSS class, except for the one signal the Sidebar does not
 * expose as an attribute (the active row is marked only by the `bg-brand/10` class
 * on its select button). Every lookup is bounded, and a "not there" is recorded as
 * a finding instead of aborting the run.
 *
 * Data safety: the owner's sessions live server-side (~/.ephe/sessions/) and are
 * NOT touched. Every mutating action (rename, pin, export, delete) is performed
 * ONLY on a task this spec created itself through the product's own "New task"
 * control; the one delete is exercised on that self-created task only.
 */
import { test, expect, type Page, type Browser, type BrowserContext } from '@playwright/test'
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

/** The live product server (built app/dist). NOT the Vite dev server. */
const LIVE_BASE = process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765'
/** HashRouter: every surface is a hash route off one document. */
const CHAT_URL = `${LIVE_BASE}/#/chat`
const SETUP_URL = `${LIVE_BASE}/#/setup`

const OUT_DIR = walkthroughOutDir('session-deep')
mkdirSync(OUT_DIR, { recursive: true })
/** One file per recorded step: a step survives a Playwright worker restart. */
const STEPS_DIR = path.join(OUT_DIR, 'steps')

// ── the app's own default/derived title (chat/helpers.ts) ─────────────────────
const DEFAULT_TITLE = 'New task'
/** Mirror of deriveSessionTitle(): ~48 chars, cut at a word boundary. */
function deriveTitle(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= 48) return clean
  const cut = clean.slice(0, 48)
  const lastSpace = cut.lastIndexOf(' ')
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut).trimEnd() + '…'
}

// ── screenshots: NN-name.png full page, across the whole file ─────────────────
let shotIndex = 0
const takenShots: string[] = []
async function shot(page: Page, name: string): Promise<string> {
  shotIndex += 1
  const rel = `${String(shotIndex).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: path.join(OUT_DIR, rel), fullPage: true })
  takenShots.push(rel)
  console.log(`[session-deep] screenshot → ${rel}`)
  return rel
}

// ── evidence: console, page errors, failed requests, HTTP >= 400 ──────────────
interface Evidence {
  consoleErrors: string[]
  consoleWarnings: string[]
  pageErrors: string[]
  failedRequests: string[]
  badResponses: string[]
  restoreResponses: string[]
  streamResponses: string[]
}
const evidence: Evidence = {
  consoleErrors: [],
  consoleWarnings: [],
  pageErrors: [],
  failedRequests: [],
  badResponses: [],
  restoreResponses: [],
  streamResponses: [],
}
function watch(page: Page, tag: string): void {
  page.on('console', (m) => {
    const line = `[${tag}] ${m.type()}: ${m.text()}`
    if (m.type() === 'error') evidence.consoleErrors.push(line)
    else if (m.type() === 'warning') evidence.consoleWarnings.push(line)
  })
  page.on('pageerror', (e) => {
    evidence.pageErrors.push(`[${tag}] ${String((e as Error)?.stack ?? e)}`)
  })
  page.on('requestfailed', (r) => {
    evidence.failedRequests.push(
      `[${tag}] ${r.method()} ${r.url()} — ${r.failure()?.errorText ?? 'unknown'}`,
    )
  })
  page.on('response', (r) => {
    const u = r.url()
    if (u.includes('/api/sessions/restore')) {
      evidence.restoreResponses.push(`[${tag}] ${r.status()} GET restore @${Date.now()}`)
    }
    if (u.includes('/api/chat/stream')) {
      evidence.streamResponses.push(`[${tag}] ${r.status()} POST chat/stream`)
    }
    if (r.status() >= 400) {
      evidence.badResponses.push(`[${tag}] ${r.status()} ${r.request().method()} ${u}`)
    }
  })
}

// ── boot helpers ──────────────────────────────────────────────────────────────
async function pinLocale(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en')
  })
}

async function openApp(page: Page): Promise<void> {
  try {
    await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  } catch (e) {
    throw new Error(
      `Live server at ${LIVE_BASE} is not reachable (${String(e)}). ` +
        `Start the Ephe product server (app/dist) before running this spec — do NOT mock it.`,
    )
  }
  if (page.url().includes('/setup')) {
    throw new Error(
      `The app landed on ${SETUP_URL}: the engine is not configured, so no chat is reachable. ` +
        `Configure the engine first (see 00-blocked-setup.png).`,
    )
  }
}

/**
 * Hydration is finished when the message pane left the boot skeleton behind:
 * either the conversation scroll region or the welcome empty state is on screen.
 * (chat/index.tsx: `!hydrated` renders ChatSkeleton.)
 */
async function waitHydrated(page: Page, timeout = 45_000): Promise<boolean> {
  const start = Date.now()
  let sawSkeleton = false
  while (Date.now() - start < timeout) {
    const s = await page
      .evaluate(() => ({
        skeleton: !!document.querySelector('[data-testid="chat-skeleton"]'),
        region: !!document.querySelector('[data-testid="chat-scroll-region"]'),
        welcome: !!document.querySelector('[data-testid="ephe-mark-hero"]'),
      }))
      .catch(() => ({ skeleton: false, region: false, welcome: false }))
    if (s.skeleton) sawSkeleton = true
    if (s.region || s.welcome) return true
    if (sawSkeleton && !s.skeleton) return true
    await page.waitForTimeout(200)
  }
  return false
}

// ── DOM readers ───────────────────────────────────────────────────────────────
interface TaskRow {
  id: string | null
  title: string | null
  active: boolean
}
interface SessionState {
  activeId: string | null
  activeRowTitle: string | null
  headerTitle: string | null
  taskCount: number
  topTask: TaskRow | null
  rows: TaskRow[]
  bubbles: number
  userBubbles: number
  assistantBubbles: number
  bubbleTexts: string[]
  skeletonVisible: boolean
  welcomeVisible: boolean
  sidebarText: string
  bodyText: string
}

async function readSessionState(page: Page): Promise<SessionState> {
  return await page.evaluate(() => {
    const rows = Array.from(
      document.querySelectorAll('[data-testid^="session-row-"]'),
    ) as HTMLElement[]
    const list = rows.map((r) => {
      const selectBtn = r.querySelector('button')
      const titleEl = r.querySelector('[data-testid="session-title-text"]')
      return {
        id: r.getAttribute('data-session-id'),
        title: (titleEl?.textContent ?? '').trim() || null,
        // The active row is marked only by this class on its select button.
        active: !!selectBtn && /bg-brand\/10/.test(selectBtn.className),
      }
    })
    const active = list.find((x) => x.active) ?? null
    const bubbles = Array.from(
      document.querySelectorAll('[data-testid="message-bubble"]'),
    ) as HTMLElement[]
    const sidebar = document.querySelector('[data-testid="chat-sidebar"]')
    return {
      activeId: active?.id ?? null,
      activeRowTitle: active?.title ?? null,
      headerTitle:
        (document.querySelector('[data-testid="session-title"]')?.textContent ?? '').trim() || null,
      taskCount: list.length,
      topTask: list[0] ?? null,
      rows: list.slice(0, 12),
      bubbles: bubbles.length,
      userBubbles: document.querySelectorAll('[data-testid="message-bubble"][data-role="user"]')
        .length,
      assistantBubbles: document.querySelectorAll(
        '[data-testid="message-bubble"][data-role="assistant"]',
      ).length,
      bubbleTexts: bubbles.map((b) => (b.textContent ?? '').replace(/\s+/g, ' ').trim()),
      skeletonVisible: !!document.querySelector('[data-testid="chat-skeleton"]'),
      welcomeVisible: !!document.querySelector('[data-testid="ephe-mark-hero"]'),
      sidebarText: (sidebar?.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 600),
      bodyText: (document.body.innerText ?? '').replace(/\s+/g, ' ').slice(0, 4000),
    }
  })
}

/** Does any visible evidence tell the user this transcript is restored history? */
function disclosureScan(state: SessionState): {
  banners: string[]
  keywordHits: string[]
  verdict: string
} {
  const keywords = [
    'restored',
    'restore',
    'history',
    'previous session',
    'previous task',
    'loaded from',
    'from the server',
    'server mirror',
    'continu',
    'older',
  ]
  const hay = state.bodyText.toLowerCase()
  const keywordHits = keywords.filter((k) => hay.includes(k))
  return {
    banners: [],
    keywordHits,
    verdict:
      keywordHits.length === 0
        ? 'no user-facing notice that the open task is restored history'
        : `possible disclosure wording on screen: ${keywordHits.join(', ')}`,
  }
}

/** Wait until the active row changed away from `prevId` (a new task was created). */
async function waitForActiveIdChange(
  page: Page,
  prevId: string | null,
  timeout = 12_000,
): Promise<string | null> {
  const deadline = Date.now() + timeout
  let last: string | null = prevId
  while (Date.now() < deadline) {
    const st = await readSessionState(page)
    last = st.activeId
    if (last && last !== prevId) return last
    await page.waitForTimeout(150)
  }
  return last
}

/** Every task id currently listed in the sidebar (not just the visible first rows). */
async function listAllTaskIds(page: Page): Promise<string[]> {
  return await page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid^="session-row-"]'))
      .map((r) => r.getAttribute('data-session-id'))
      .filter((x): x is string => !!x),
  )
}

/**
 * Wait until the turn that carries `marker` has both started (the user bubble is
 * on screen) and finished (send button back, no streaming pulse, last assistant
 * bubble non-empty). Bounded; returns false instead of throwing.
 */
async function waitTurnEnd(page: Page, marker: string, timeout = 120_000): Promise<boolean> {
  await page
    .waitForFunction(
      (m) =>
        Array.from(
          document.querySelectorAll('[data-testid="message-bubble"][data-role="user"]'),
        ).some((b) => (b.textContent ?? '').includes(m)),
      marker,
      { timeout: 20_000 },
    )
    .catch(() => undefined)
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const done = await page
      .evaluate(() => {
        const send = document.querySelector('[data-testid="send-btn"]')
        const stop = document.querySelector('[data-testid="stop-btn"]')
        const assistants = Array.from(
          document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
        ) as HTMLElement[]
        const last = assistants[assistants.length - 1]
        return {
          sendVisible: !!send,
          stopVisible: !!stop,
          streaming: last ? !!last.querySelector('span.animate-pulse') : false,
          lastLen: (last?.textContent ?? '').trim().length,
        }
      })
      .catch(() => ({ sendVisible: false, stopVisible: false, streaming: true, lastLen: 0 }))
    if (done.sendVisible && !done.stopVisible && !done.streaming && done.lastLen > 0) return true
    await page.waitForTimeout(250)
  }
  return false
}

// ── shared run state (one worker: fullyParallel is false, tests run in order) ─
const observations: Record<string, unknown> = {
  spec: 'app/e2e/walkthrough/session-deep.spec.ts',
  purpose:
    'Deep-check of the session store: cold open, the restore race under immediate sending, session switching across reload, New task, the task menu, and the empty/deleted cases.',
  liveBase: LIVE_BASE,
  chatUrl: CHAT_URL,
  locale: 'en (pinned via addInitScript → localStorage.i18nextLng)',
  mocking: 'none — every request hits the live server and the live engine',
  dataSafety:
    'the owner sessions server-side were not deleted or renamed; every mutation below was applied to a task this spec created itself via New task',
  viewport: { width: 1440, height: 900 },
  startedAt: new Date().toISOString(),
}
const steps: Record<string, unknown> = {}
observations.steps = steps

/**
 * Records one step's evidence. Writing the report must never be able to abort a test:
 * a failure is logged with the step key and the test keeps going, so the run log names
 * the step whose evidence is missing instead of the whole file failing.
 *
 * The value must be plain data. Never pass an expression that awaits a locator:
 * locator auto-wait has no bound of its own, so such an await turns the whole test
 * into "Test timeout ... exceeded" without naming the element it waited for.
 */
function recordStep(key: string, value: unknown): void {
  try {
    steps[key] = value
    // Persist the step immediately, not only in afterAll: Playwright restarts the
    // worker after a timed-out test, and the fresh module state then holds no step
    // written before the restart unless it is already on disk.
    mkdirSync(STEPS_DIR, { recursive: true })
    writeFileSync(path.join(STEPS_DIR, `${key}.json`), JSON.stringify({ [key]: value }, null, 2))
  } catch (error) {
    console.log(`[session-deep] step ${key} could not be recorded: ${String(error)}`)
  }
}

test.describe('session deep-check (live engine, no mocks)', () => {
  test.describe.configure({ timeout: 300_000 })
  test.use({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })

  // ── 1 ─────────────────────────────────────────────────────────────────────
  test('1 — cold open in a clean context: which task is active, and is a restore disclosed?', async ({
    page,
  }) => {
    watch(page, 'cold-open')
    await pinLocale(page)
    await openApp(page)

    // The shell first; this is not a settle, only the sidebar mounting.
    await expect(page.getByTestId('chat-sidebar')).toBeVisible({ timeout: 20_000 })
    const firstPaint = await readSessionState(page)
    await shot(page, 'cold-open-first-paint')

    const hydrated = await waitHydrated(page)
    const afterHydration = await readSessionState(page)
    // Let any late restore land, then read the settled task.
    await page.waitForTimeout(2_500)
    const settled = await readSessionState(page)
    await shot(page, 'cold-open-settled')

    const disclosure = disclosureScan(settled)
    const activeIsTop = settled.activeId !== null && settled.activeId === settled.topTask?.id
    const activeIsRestoredHistory = settled.bubbles > 0 && settled.headerTitle !== DEFAULT_TITLE

    recordStep('1_cold_open', {
      question: 'Which task is active on a cold open, and is the user told it is restored history?',
      hydrated,
      firstPaint: {
        activeId: firstPaint.activeId,
        headerTitle: firstPaint.headerTitle,
        taskCount: firstPaint.taskCount,
        bubbles: firstPaint.bubbles,
        skeletonVisible: firstPaint.skeletonVisible,
      },
      afterHydration: {
        activeId: afterHydration.activeId,
        headerTitle: afterHydration.headerTitle,
        taskCount: afterHydration.taskCount,
        bubbles: afterHydration.bubbles,
      },
      settled: {
        activeId: settled.activeId,
        activeRowTitle: settled.activeRowTitle,
        headerTitle: settled.headerTitle,
        taskCount: settled.taskCount,
        topTask: settled.topTask,
        bubbles: settled.bubbles,
        userBubbles: settled.userBubbles,
        assistantBubbles: settled.assistantBubbles,
        welcomeVisible: settled.welcomeVisible,
        firstTaskRows: settled.rows,
      },
      activeTaskIsTheTopListEntry: activeIsTop,
      activeTaskIsRestoredHistory: activeIsRestoredHistory,
      disclosure,
      restoreRequestsSeen: evidence.restoreResponses.length,
    })
    console.log(
      `[session-deep] step1 activeId=${String(settled.activeId)} title=${JSON.stringify(
        settled.headerTitle,
      )} bubbles=${settled.bubbles} tasks=${settled.taskCount} disclosure=${disclosure.verdict}`,
    )
  })

  // ── 2 ─────────────────────────────────────────────────────────────────────
  test('2 — the restore race: type and send immediately after load, three times', async ({
    browser,
  }) => {
    const attempts: Record<string, unknown>[] = []
    for (let i = 0; i < 3; i += 1) {
      attempts.push(await runRaceAttempt(browser, i))
    }
    recordStep('2_restore_race', {
      question:
        'Sending the first message without waiting for the boot restore: does the message stay in the task it was sent from, or is the view displaced?',
      attempts,
      verdictSummary: attempts.map((a) => ({
        attempt: a.attempt,
        verdict: a.verdict,
        sentIntoRestoredHistory: a.sentIntoRestoredHistory,
        markerStillVisibleAtEnd: a.markerStillVisibleAtEnd,
        activeIdAtSend: a.activeIdAtSend,
        activeIdAtEnd: a.activeIdAtEnd,
      })),
    })
    console.log(
      `[session-deep] step2 verdicts: ${JSON.stringify(
        attempts.map((a) => `${String(a.attempt)}:${String(a.verdict)}`),
      )}`,
    )
  })

  // ── 3 ─────────────────────────────────────────────────────────────────────
  test('3 — switch a task in the sidebar, then reload: which one comes back?', async ({ page }) => {
    watch(page, 'switch-reload')
    await pinLocale(page)
    await openApp(page)
    const hydrated = await waitHydrated(page)
    const initial = await readSessionState(page)
    await shot(page, 'switch-reload-before')

    const other = initial.rows.find((r) => r.id && r.id !== initial.activeId)
    if (!other || !other.id) {
      recordStep('3_switch_reload', {
        question: 'Switch a task, then reload: does the chosen task come back?',
        hydrated,
        initialActiveId: initial.activeId,
        taskCount: initial.taskCount,
        finding:
          'fewer than two tasks were listed, so a switch could not be performed — the question is unanswered on this store',
      })
      console.log('[session-deep] step3 skipped: fewer than two tasks listed')
      return
    }

    // Click the row's title text: it sits inside the select button, so the click
    // selects the task without having to guess which button in the row is the label.
    await page.locator(`[data-session-id="${other.id}"] [data-testid="session-title-text"]`).click()
    await page.waitForTimeout(700)
    const afterSwitch = await readSessionState(page)
    await shot(page, 'switch-reload-after-switch')

    await page.reload({ waitUntil: 'domcontentloaded' })
    const hydratedAfterReload = await waitHydrated(page)
    await page.waitForTimeout(2_000)
    const afterReload = await readSessionState(page)
    await shot(page, 'switch-reload-after-reload')

    const verdict =
      afterReload.activeId === other.id
        ? 'chosen_task_came_back'
        : afterReload.activeId === initial.topTask?.id
          ? 'newest_wins'
          : 'neither_the_chosen_nor_the_newest_task'

    recordStep('3_switch_reload', {
      question:
        'Switch a task in the sidebar, then reload: does the chosen task come back, or does the newest one win?',
      hydrated,
      hydratedAfterReload,
      chosenTask: other,
      initialActiveId: initial.activeId,
      afterSwitch: { activeId: afterSwitch.activeId, headerTitle: afterSwitch.headerTitle },
      afterReload: {
        activeId: afterReload.activeId,
        activeRowTitle: afterReload.activeRowTitle,
        headerTitle: afterReload.headerTitle,
        bubbles: afterReload.bubbles,
        topTask: afterReload.topTask,
      },
      verdict,
    })
    console.log(
      `[session-deep] step3 chosen=${String(other.id)} → after reload active=${String(
        afterReload.activeId,
      )} (${verdict})`,
    )
  })

  // ── 4 ─────────────────────────────────────────────────────────────────────
  test('4 — New task (header control and Command-N): empty, title growth, no late restore', async ({
    page,
  }) => {
    watch(page, 'new-task')
    await pinLocale(page)
    await openApp(page)
    await waitHydrated(page)
    const before = await readSessionState(page)

    // The header control (the only New-task entry point besides the sidebar pill).
    await page.getByTestId('header-new-session').click()
    await page.waitForTimeout(500)
    const afterHeaderNew = await readSessionState(page)
    const lateRepopulated = await page
      .waitForFunction(
        () => document.querySelectorAll('[data-testid="message-bubble"]').length > 0,
        undefined,
        {
          timeout: 2_000,
        },
      )
      .then(() => true)
      .catch(() => false)
    const stillEmpty = await readSessionState(page)
    await shot(page, 'new-task-empty')

    // Command-N while the composer holds focus: the palette handler ignores the
    // key when the event target is an INPUT/TEXTAREA — recorded, not assumed.
    const afterCmdNInComposer = await readCmdN(page, 'composer-focused')
    // Command-N with focus off any input: the palette handler only acts when the
    // event target is not an INPUT/TEXTAREA/contenteditable.
    await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (el && typeof el.blur === 'function') el.blur()
      document.body.focus()
    })
    await page.waitForTimeout(200)
    const afterCmdNBlurred = await readCmdN(page, 'blurred')

    // Title growth: send the first message into the fresh task.
    const msg = 'SESSION-DEEP title growth check'
    const activeBeforeSend = await readSessionState(page)
    await page.getByTestId('chat-input').click()
    await page.getByTestId('chat-input').fill(msg)
    await page.getByTestId('send-btn').click()
    const turnEnded = await waitTurnEnd(page, 'SESSION-DEEP', 120_000)
    const afterTurn = await readSessionState(page)
    await shot(page, 'new-task-after-first-message')

    const titleBefore = activeBeforeSend.headerTitle
    const titleAfter = afterTurn.headerTitle
    const expectedTitle = deriveTitle(msg)

    recordStep('4_new_task', {
      question:
        'Does New task really start empty, does the title update as the conversation grows, and does the restored-history behaviour stay away?',
      before: {
        activeId: before.activeId,
        headerTitle: before.headerTitle,
        taskCount: before.taskCount,
      },
      afterHeaderNewTaskClick: {
        activeId: afterHeaderNew.activeId,
        headerTitle: afterHeaderNew.headerTitle,
        bubbles: afterHeaderNew.bubbles,
        userBubbles: afterHeaderNew.userBubbles,
        welcomeVisible: afterHeaderNew.welcomeVisible,
        composerInputValue: await page
          .getByTestId('chat-input')
          .inputValue()
          .catch(() => null),
      },
      emptyAfterNewTask: afterHeaderNew.bubbles === 0,
      lateRestoreRepopulatedTheNewTask: lateRepopulated,
      stillEmptyAfterSettle: {
        bubbles: stillEmpty.bubbles,
        headerTitle: stillEmpty.headerTitle,
        activeId: stillEmpty.activeId,
      },
      commandN: {
        whileComposerFocused: afterCmdNInComposer,
        afterBlur: afterCmdNBlurred,
      },
      titleGrowth: {
        message: msg,
        titleBefore,
        titleAfter,
        expectedDerivedTitle: expectedTitle,
        titleUpdatedToDerivedTitle: titleAfter === expectedTitle,
        turnEnded,
        bubblesAfterTurn: afterTurn.bubbles,
        userBubblesAfterTurn: afterTurn.userBubbles,
        assistantBubblesAfterTurn: afterTurn.assistantBubbles,
      },
    })
    console.log(
      `[session-deep] step4 empty=${String(afterHeaderNew.bubbles === 0)} title ${JSON.stringify(
        titleBefore,
      )} → ${JSON.stringify(titleAfter)} (expected ${JSON.stringify(expectedTitle)})`,
    )
  })

  // ── 5 ─────────────────────────────────────────────────────────────────────
  test('5 — the task menu: the real actions and the 22x22 px trigger', async ({ page }) => {
    watch(page, 'menu')
    await pinLocale(page)
    await openApp(page)
    await waitHydrated(page)
    const before = await readSessionState(page)
    const t5 = Date.now()
    const mark = (what: string) => console.log(`[session-deep] step5 +${Date.now() - t5}ms ${what}`)

    // Work on a task this spec owns, so nothing of the owner's is mutated.
    await page.getByTestId('header-new-session').click({ timeout: 15_000 })
    const ownId = await waitForActiveIdChange(page, before.activeId)
    mark(`new task row active=${String(ownId !== null)}`)
    if (!ownId) {
      recordStep('5_task_menu', {
        question: 'Which actions does the task menu offer, and is the 22x22 px trigger usable?',
        finding:
          'no active task row could be located after New task — the menu could not be opened',
      })
      return
    }

    const row = page.locator(`[data-session-id="${ownId}"]`)
    await row.hover()
    const menuBtn = page.getByTestId(`session-menu-${ownId}`)
    await expect(menuBtn).toBeVisible({ timeout: 10_000 })
    const box = await menuBtn.boundingBox()
    const measured = box ? { width: Math.round(box.width), height: Math.round(box.height) } : null
    const meetsWcag24 = !!measured && measured.width >= 24 && measured.height >= 24

    await menuBtn.click({ timeout: 10_000 })
    const menu = page.getByTestId('session-context-menu')
    await expect(menu).toBeVisible({ timeout: 10_000 })
    mark('context menu open')
    // Read both attributes here, once, while the trigger and the menu are provably on
    // screen. A locator read inside the report assembly further down would auto-wait
    // with no bound (default action timeout 0) and can only ever end as
    // "Test timeout of 300000ms exceeded", which names nothing.
    const triggerAriaLabel = await menuBtn
      .getAttribute('aria-label', { timeout: 5_000 })
      .catch(() => null)
    const menuRole = await menu.getAttribute('role', { timeout: 5_000 }).catch(() => null)
    const items = await menu.locator('[data-testid^="menu-"]').evaluateAll((els) =>
      els
        .filter((e) => !(e.getAttribute('data-testid') ?? '').startsWith('menu-sep-'))
        .map((e) => ({
          testid: e.getAttribute('data-testid'),
          text: (e.textContent ?? '').replace(/\s+/g, ' ').trim(),
          role: e.getAttribute('role'),
        })),
    )
    const separators = await menu.locator('[data-testid^="menu-sep-"]').count()
    await shot(page, 'task-menu-open')

    // ── rename (reversible, on our own task) ────────────────────────────────
    // Every interaction here is bounded: an action left on the default timeout can
    // only ever surface as "Test timeout of 300000ms exceeded", which names nothing.
    const renameClickOk = await menu
      .getByTestId('menu-rename')
      .click({ timeout: 10_000 })
      .then(() => true)
      .catch(() => false)
    mark(`rename clicked ok=${String(renameClickOk)}`)
    const renameInput = page.getByLabel('Rename task')
    const renameAppeared = await renameInput
      .waitFor({ state: 'visible', timeout: 6_000 })
      .then(() => true)
      .catch(() => false)
    const newTitle = 'SESSION-DEEP renamed task'
    if (renameAppeared) {
      await renameInput.fill(newTitle)
      await page.keyboard.press('Enter')
      await page.waitForTimeout(500)
    }
    const titleAfterRename =
      (await readSessionState(page)).rows.find((r) => r.id === ownId)?.title ?? null

    // ── pin (reversible, on our own task) ───────────────────────────────────
    await row.hover()
    const pinClickOk = await menuBtn
      .click({ timeout: 10_000 })
      .then(() => page.getByTestId('menu-pin').click({ timeout: 10_000 }))
      .then(() => true)
      .catch(() => false)
    mark(`pin clicked ok=${String(pinClickOk)}`)
    await page.waitForTimeout(600)
    const afterPin = await readSessionState(page)

    // ── export (downloads to the browser, writes nothing into the store) ────
    await row.hover()
    mark('export: opening the menu')
    let exportTriggerClickOk = true
    await menuBtn.click({ timeout: 10_000 }).catch(() => {
      exportTriggerClickOk = false
    })
    let exportFilename: string | null = null
    let exportError: string | null = null
    try {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 10_000 }),
        page.getByTestId('menu-export').click(),
      ])
      exportFilename = download.suggestedFilename()
    } catch (e) {
      exportError = String(e).slice(0, 240)
    }
    await page.waitForTimeout(400)
    mark(`export download=${JSON.stringify(exportFilename)} error=${JSON.stringify(exportError)}`)

    recordStep('5_task_menu', {
      question:
        'Which actions can a user really apply to a task, and is the 22x22 px trigger usable?',
      ownTaskId: ownId,
      trigger: {
        testid: `session-menu-${ownId}`,
        ariaLabel: triggerAriaLabel,
        measuredPx: measured,
        meetsWcag25x24PxMinimum: meetsWcag24,
        note: 'the trigger is opacity-0 until the row is hovered on a viewport >= 1024 px (max-lg:opacity-100 below that)',
      },
      menuRole,
      entryCount: items.length,
      separatorCount: separators,
      entries: items,
      exercised: {
        rename: {
          menuClickAccepted: renameClickOk,
          renameInputAppeared: renameAppeared,
          newTitle,
          titleAfterRename,
          titleChanged: titleAfterRename === newTitle,
        },
        pin: {
          menuClickAccepted: pinClickOk,
          taskRowsOrderAfterPin: afterPin.rows.map((r) => r.id),
          pinnedTaskIsNowTop: afterPin.topTask?.id === ownId,
        },
        export: {
          triggerClickAccepted: exportTriggerClickOk,
          downloadSuggestedFilename: exportFilename,
          error: exportError,
        },
      },
      notExercised: [
        'menu-copy-path / menu-copy-task-path / menu-copy-log-path / menu-copy-id (clipboard writes)',
        'menu-show-path (toast only)',
        'menu-goto-config (opens settings)',
        'menu-trajectory (opens the preview pane)',
        'menu-branch (forks the task)',
        'menu-report-issue (opens github.com in a new tab)',
        'menu-archive (hides the task; exercised on the self-created task in step 6 path only)',
      ],
    })
    console.log(
      `[session-deep] step5 entries=${items.length} separators=${separators} trigger=${JSON.stringify(
        measured,
      )} wcag24=${String(meetsWcag24)} export=${JSON.stringify(exportFilename)}`,
    )
    mark('step recorded')
  })

  // ── 6 ─────────────────────────────────────────────────────────────────────
  test('6 — empty store and a task deleted: does a deleted task stay deleted?', async ({
    page,
  }) => {
    watch(page, 'empty-deleted')
    await pinLocale(page)
    await openApp(page)
    // The window before the boot restore lands IS the empty-store view.
    await expect(page.getByTestId('chat-sidebar')).toBeVisible({ timeout: 20_000 })
    const preRestore = await readSessionState(page)
    await shot(page, 'empty-store-pre-restore')
    await waitHydrated(page)
    const afterRestore = await readSessionState(page)

    // ── (a) our own task, created, deleted through the product's own menu ────
    const before = await readSessionState(page)
    await page.getByTestId('header-new-session').click()
    const ownId = await waitForActiveIdChange(page, before.activeId)
    let deleteOutcome: Record<string, unknown> = { ownId, performed: false }
    if (ownId) {
      // One message makes the task durable in the server mirror (restore.ts drops
      // 0-message shells), so the reload is a real resurrection test.
      const msg = 'Session-deep: delete check'
      await page.getByTestId('chat-input').fill(msg)
      await page.getByTestId('send-btn').click()
      await waitTurnEnd(page, 'Session-deep: delete check', 120_000)
      const beforeDelete = await readSessionState(page)
      await shot(page, 'delete-before')

      const row = page.locator(`[data-session-id="${ownId}"]`)
      await row.hover()
      await page.getByTestId(`session-menu-${ownId}`).click()
      await page.getByTestId('menu-delete').click()
      const confirm = row.getByRole('button', { name: 'Yes', exact: true })
      const confirmVisible = await confirm
        .waitFor({ state: 'visible', timeout: 6_000 })
        .then(() => true)
        .catch(() => false)
      await shot(page, 'delete-confirm')
      if (confirmVisible) await confirm.click()
      await page.waitForTimeout(1_200)
      const afterDeleteIds = await listAllTaskIds(page)

      await page.reload({ waitUntil: 'domcontentloaded' })
      const hydratedAfterReload = await waitHydrated(page)
      await page.waitForTimeout(2_500)
      const afterReloadIds = await listAllTaskIds(page)
      await shot(page, 'delete-after-reload')

      const stillGone = !afterReloadIds.includes(ownId)
      deleteOutcome = {
        ownId,
        performed: true,
        messageSent: msg,
        bubblesBeforeDelete: beforeDelete.bubbles,
        confirmVisible,
        taskRowPresentAfterDelete: afterDeleteIds.includes(ownId),
        hydratedAfterReload,
        taskRowPresentAfterReload: afterReloadIds.includes(ownId),
        verdict: stillGone
          ? 'deleted_task_stays_deleted_after_reload'
          : 'deleted_task_came_back_after_reload',
      }
    }

    // ── (b) the empty-store path ─────────────────────────────────────────────
    recordStep('6_empty_and_deleted', {
      question:
        'What does the app show when the task store is empty, and does a task deleted through the menu stay deleted after a reload?',
      emptyStore: {
        note: 'the server mirror cannot be emptied from the client without deleting the owner sessions, and mocking is forbidden by this spec — so the reachable empty-store view is the window before the boot restore resolves',
        preRestore: {
          taskCount: preRestore.taskCount,
          skeletonVisible: preRestore.skeletonVisible,
          welcomeVisible: preRestore.welcomeVisible,
          sidebarText: preRestore.sidebarText,
          sidebarShowsNoTasksYet: /No tasks yet/i.test(preRestore.sidebarText),
        },
        afterRestore: {
          taskCount: afterRestore.taskCount,
          bubbles: afterRestore.bubbles,
          headerTitle: afterRestore.headerTitle,
        },
        emptyStateTextKey: 'sidebar.noSessions = "No tasks yet" (en.json)',
      },
      deletedTask: deleteOutcome,
      restoreRequestsSeen: evidence.restoreResponses.length,
    })
    console.log(`[session-deep] step6 deleteOutcome=${JSON.stringify(deleteOutcome)}`)
  })

  test.afterAll(() => {
    // Merge the step files of every worker that ran this file, so a restart cannot
    // erase the earlier steps from the report.
    try {
      for (const file of readdirSync(STEPS_DIR)) {
        if (!file.endsWith('.json')) continue
        const parsed = JSON.parse(readFileSync(path.join(STEPS_DIR, file), 'utf8')) as Record<
          string,
          unknown
        >
        for (const [key, value] of Object.entries(parsed)) {
          if (steps[key] === undefined) steps[key] = value
        }
      }
    } catch (error) {
      console.log(`[session-deep] merging the step files failed: ${String(error)}`)
    }
    observations.finishedAt = new Date().toISOString()
    observations.screenshots = takenShots
    observations.evidence = evidence
    writeFileSync(path.join(OUT_DIR, 'observations.json'), JSON.stringify(observations, null, 2))
    console.log(
      `[session-deep] console errors: ${evidence.consoleErrors.length}, page errors: ${evidence.pageErrors.length}, ` +
        `failed requests: ${evidence.failedRequests.length}, HTTP >= 400: ${evidence.badResponses.length}, ` +
        `restore responses: ${evidence.restoreResponses.length}`,
    )
    for (const line of evidence.consoleErrors) console.log(`[session-deep] console.error: ${line}`)
    for (const line of evidence.failedRequests) console.log(`[session-deep] requestfailed: ${line}`)
    for (const line of evidence.badResponses) console.log(`[session-deep] http>=400: ${line}`)
    for (const line of evidence.restoreResponses) console.log(`[session-deep] restore: ${line}`)
  })
})

/** Command-N from the current focus: records whether it created an empty task. */
async function readCmdN(page: Page, tag: string): Promise<Record<string, unknown>> {
  const before = await readSessionState(page)
  await page.keyboard.press('Meta+n')
  await page.waitForTimeout(600)
  const after = await readSessionState(page)
  return {
    tag,
    taskCountBefore: before.taskCount,
    taskCountAfter: after.taskCount,
    activeIdBefore: before.activeId,
    activeIdAfter: after.activeId,
    createdANewTask: after.taskCount > before.taskCount || after.activeId !== before.activeId,
    newTaskIsEmpty: after.bubbles === 0,
    newTaskTitle: after.headerTitle,
  }
}

/**
 * One cold race attempt in its own make-or-break browser context: a clean profile
 * (empty IndexedDB/localStorage) so the boot path really runs
 * initFromDb → GET /api/sessions/restore. The message is typed and sent as soon as
 * the composer exists — no settle, no wait for the restore.
 */
async function runRaceAttempt(browser: Browser, index: number): Promise<Record<string, unknown>> {
  const context: BrowserContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  const tag = `race-${index + 1}`
  watch(page, tag)

  const marker = `Race probe ${index + 1}`
  const text = `${marker}: reply "ack" only.`
  const result: Record<string, unknown> = {
    attempt: index + 1,
    marker,
    text,
    expectedDerivedTitle: deriveTitle(text),
  }

  try {
    await pinLocale(page)
    const t0 = Date.now()
    await openApp(page)
    await page.waitForSelector('[data-testid="chat-input"]', { timeout: 20_000 })
    result.msDomContentLoadedToComposerMs = Date.now() - t0

    const atSend = await readSessionState(page)
    result.atSend = {
      activeIdAtSend: atSend.activeId,
      headerTitle: atSend.headerTitle,
      taskCount: atSend.taskCount,
      bubbles: atSend.bubbles,
      skeletonVisible: atSend.skeletonVisible,
      welcomeVisible: atSend.welcomeVisible,
    }
    // Did the message go straight into restored history, or into a task the app
    // had to create on the spot?
    result.sentIntoRestoredHistory =
      atSend.activeId !== null &&
      atSend.headerTitle !== null &&
      atSend.headerTitle !== DEFAULT_TITLE

    const composer = page.getByTestId('chat-input')
    await composer.click()
    await composer.fill(text)
    const send = page.getByTestId('send-btn')
    await expect(send).toBeEnabled({ timeout: 10_000 })
    const tSend = Date.now()
    await send.click()
    result.msLoadToSendMs = tSend - t0

    const justAfter = await readSessionState(page)
    result.justAfterSend = {
      activeId: justAfter.activeId,
      headerTitle: justAfter.headerTitle,
      taskCount: justAfter.taskCount,
    }

    result.turnEndReached = await waitTurnEnd(page, marker, 120_000)

    // Sample for a late displacement: a restore that lands after the send would
    // swap the active task out from under the message.
    const samples: Record<string, unknown>[] = []
    for (let s = 0; s < 14; s += 1) {
      const st = await readSessionState(page)
      samples.push({
        msSinceSend: Date.now() - tSend,
        activeId: st.activeId,
        headerTitle: st.headerTitle,
        taskCount: st.taskCount,
        markerInTranscript: st.bubbleTexts.some((t) => t.includes(marker)),
      })
      await page.waitForTimeout(500)
    }
    result.samples = samples

    const final = await readSessionState(page)
    const sentTask = final.rows.find((r) => r.title === deriveTitle(text)) ?? null
    const markerInTranscriptAtEnd = final.bubbleTexts.some((t) => t.includes(marker))
    // Two anchors for "the task the message was sent from": the active task right
    // after the send, and (when the app created a fresh task) the sidebar row that
    // carries the auto-derived title.
    const activeIdAtSend = justAfter.activeId
    result.activeIdAtSend = activeIdAtSend
    result.activeIdAtEnd = final.activeId
    result.headerTitleAtEnd = final.headerTitle
    result.markerStillVisibleAtEnd = markerInTranscriptAtEnd
    result.sentTaskIdInSidebar = sentTask?.id ?? null
    result.sentTaskStillListed = sentTask !== null
    result.taskCountAtEnd = final.taskCount
    result.bubblesAtEnd = final.bubbles

    result.verdict = !result.turnEndReached
      ? 'turn_did_not_complete'
      : markerInTranscriptAtEnd &&
          (activeIdAtSend === final.activeId || sentTask?.id === final.activeId)
        ? 'stayed_in_the_task_it_was_sent_from'
        : markerInTranscriptAtEnd
          ? 'message_present_but_the_view_moved_to_another_task'
          : sentTask
            ? 'displaced_from_the_visible_task_the_message_survives_in_a_sidebar_task'
            : 'message_lost_no_task_carries_the_sent_text'

    if (index === 0) await shot(page, 'race-attempt-1-final')
    if (index === 1) await shot(page, 'race-attempt-2-final')
    if (index === 2) await shot(page, 'race-attempt-3-final')
  } catch (e) {
    result.error = String((e as Error)?.stack ?? e).slice(0, 800)
    result.verdict = 'attempt_failed'
    await shot(page, `race-attempt-${index + 1}-failed`).catch(() => undefined)
  } finally {
    await context.close()
  }
  return result
}
