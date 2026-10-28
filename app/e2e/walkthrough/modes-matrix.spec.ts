/**
 * modes-matrix.spec.ts — user walkthrough: "what does each composer mode really do?"
 *
 * PERSONA: a user who is told there are four modes («Ask», «Plan», «Edit auto»,
 * «Full access») and wants to know, per mode, what actually happens when a task
 * needs a tool and a task needs a write. The question this run answers with
 * evidence — per mode:
 *   - does a tool run at all,
 *   - does an approval dialog appear (and what does it say),
 *   - is a file really written to disk,
 *   - what does the assistant answer, what do the tool rows say,
 *   - and for `plan` (the mode this spec exists for): does it truly write
 *     nothing, does it PRESENT a plan before acting, is that plan rendered as a
 *     card a user can read and act on, and does accepting it actually run the
 *     work — or does nothing ever execute the plan.
 *
 * This spec runs against the LIVE stack — real backend, real engine
 * (openai_compatible / deepseek-v4-pro over the DeepSeek API). It does NOT mock
 * (`page.route` is never used), so it records what the surfaces really render
 * into `observations.json` next to the screenshots; it never softens a surprise
 * to make itself green.
 *
 * Preconditions:
 *   - the ephe backend is up on 127.0.0.1:8765 (serving the app — live URL
 *     http://127.0.0.1:8765/#/chat). Override the origin with
 *     EPHE_WALKTHROUGH_BASE (e.g. http://127.0.0.1:5174 for the Vite dev server,
 *     which proxies /api/* to 8765).
 *   - run with `--timeout 900000` (in addition to the describe-level configure
 *     below): a real engine turn with tool calls can run for minutes.
 *
 * "A turn is slow" and "a turn never ends" are two different findings, and this
 * spec must not confuse them. Every turn therefore records its own wall time
 * (`wallMs`) and the REASON its wait ended (`endReason`):
 *   settled      — no stop button, a fresh bubble, and its text byte-stable for
 *                  2 s: the turn really ended (recorded as slow if it was slow),
 *   engine_error — the same, plus a raw engine error in the transcript (a 400
 *                  from the provider ends the turn; waiting on it is wasted time),
 *   deadline     — SETTLE_MS passed without a settle: the turn hung. That is a
 *                  finding, and it fails the test (see the end of runMode).
 * Every poll is appended to `trace-<mode>.jsonl` in this directory, so a stall
 * is locatable on disk even if the test is killed mid-flight.
 *
 * The composer mode is a SESSION attribute shared by every client (server
 * mirror) — a sibling walkthrough shares this one server, so every test RESTORES
 * the mode to the default (`full-access`) when it ends.
 *
 * Selectors (all read from source, so they survive a copy refactor):
 *   mode selector   app/src/components/dashboard/chat/ComposerModeChip.tsx:41   data-testid="composer-mode-selector"
 *   mode menu list  app/src/components/dashboard/chat/ComposerModeMenu.tsx:124  data-testid="composer-mode-list"
 *   mode option     app/src/components/dashboard/chat/ComposerModeMenu.tsx:160  data-testid="composer-mode-<key>"  (key ∈ ask|plan|edit-auto|full-access, ComposerModeMenu.tsx:37-66)
 *   chat input      app/src/components/dashboard/ChatInput.tsx:433              data-testid="chat-input"
 *   send / stop     app/src/components/dashboard/chat/ComposerSendButton.tsx:77  data-testid="send-btn" | "stop-btn"
 *   assistant       app/src/components/dashboard/MessageBubble.tsx:118-119      data-testid="message-bubble" data-role="assistant"
 *   turn head       app/src/components/dashboard/bubble/turnHeadRow.tsx:36      data-testid="bubble-turn-head"
 *   tool rows       app/src/components/dashboard/bubble/toolStreamRows.tsx:47   data-testid="tool-stream-rows"
 *   tool row group  app/src/components/dashboard/bubble/toolStreamRows.tsx:84   data-testid="tool-stream-row-<family>"
 *   approval gate   app/src/components/dashboard/ToolApprovalPrompt.tsx:87-91   role="alertdialog" aria-label="Ephe wants to run a tool" (chat.approvalNeeded, locales/en.json:54)
 *   approve / deny  app/src/components/dashboard/ToolApprovalPrompt.tsx:123,147  data-testid "approval-once" ("Allow once") / "approval-deny" ("Deny")
 *   blast radius    app/src/components/dashboard/ToolApprovalPrompt.tsx:112      data-testid="approval-blast-radius"
 *   plan card       app/src/components/dashboard/PlanCard.tsx:52                data-testid="plan-card" (data-state draft|running|accepted)
 *   plan progress   app/src/components/dashboard/PlanCard.tsx:57                data-testid="plan-progress"
 *   plan item       app/src/components/dashboard/PlanCard.tsx:107               data-testid="plan-item-<i>" (data-status)
 *   plan accept     app/src/components/dashboard/PlanCard.tsx:131               data-testid="plan-accept"  → sends "Plan accepted — proceed." (locales/en.json:227)
 *   plan edit       app/src/components/dashboard/PlanCard.tsx:142               data-testid="plan-edit"
 *   (card renders only when the ANSWER text carries a `## Plan` / `- [ ]` block:
 *    app/src/components/dashboard/bubble/assistantExtras.tsx:53-57 → parsePlanCard,
 *    app/src/lib/planCardModel.ts:14-48. The `{"type":"plan"}` stream frame drives
 *    the status popover instead: server/routes/chat.py:821-839, streamActions.ts:167-173.)
 *   new task        app/src/components/dashboard/Sidebar.tsx:870                data-testid="new-session"
 *   files tab       app/src/components/dashboard/Sidebar.tsx:692                data-testid="sidebar-action-files"
 *   status popover  app/src/components/dashboard/AgentStatusButton.tsx:199,236  data-testid="agent-status-pill" → "agent-status-popover"
 *   plan semantics  docs/COMPOSER_MODES.md + server/routes/chat.py:445-472 (_mode_context),
 *                   server/routes/chat.py:1008-1022 (auto-approval is gated on the global
 *                   approval profile: mode_auto = profile != "strict"; autonomous=full-access,
 *                   app/src/components/dashboard/chat/model.ts:909)
 */
import { test, expect } from '@playwright/test'
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'
import { openTier } from './rail.ts'

// Siblings share one live server and one engine — a turn can run for minutes.
// The budget must outlast two SETTLE_MS turns plus the reads around them, so that a
// hung turn fails on its own recorded deadline and not on the runner's ceiling.
test.describe.configure({ timeout: 900_000 })

const BASE = process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765'
const OUT = walkthroughOutDir('modes-matrix')
const OBS = join(OUT, 'observations.json')

const CHAT_INPUT = '[data-testid="chat-input"]'
const STOP = '[data-testid="stop-btn"]'
const ASSISTANT = '[data-testid="message-bubble"][data-role="assistant"]'
const TOOL_ROWS = '[data-testid="tool-stream-rows"]'
const PLAN_CARD = '[data-testid="plan-card"]'
const PLAN_ITEM = '[data-testid^="plan-item-"]'
const PLAN_PROGRESS = '[data-testid="plan-progress"]'
const PLAN_ACCEPT = '[data-testid="plan-accept"]'
const PLAN_EDIT = '[data-testid="plan-edit"]'

// ── the settle budget (see the header): slow ≠ hung ──────────────────────────
const SETTLE_MS = 360_000 // per turn; a turn that settles at 200 s is recorded as slow
const POLL_MS = 500
const STABLE_POLLS = 4 // 2 s of byte-stable bubble text = the turn ended

// A raw provider error that reached the transcript. The 400 body is not in the
// exception text (server/routes/chat.py:601 `_error_msg` passes `str(exc)` on),
// so the marker is the httpx shape plus the MDN link it carries.
const RAW_ERROR_RE =
  /Client error '\d{3} [^']*' for url|developer\.mozilla\.org\/en-US\/docs\/Web\/HTTP\/Status/
// A plan block the user's language below the fixed heading (planCardModel.ts:13-38).
const PLAN_BLOCK_RE = /^\s*(?:#+\s*)?\*{0,2}\s*Plan\s*\*{0,2}\s*$|^\s*[-*+]\s*\[[ >xX!-]\]\s+/m

type TraceFn = (event: string, data?: Record<string, unknown>) => void

// The four, kept as a value so the type below is derived rather than restated.
const _MODES = ['ask', 'plan', 'edit-auto', 'full-access'] as const
type Mode = (typeof _MODES)[number]

// The short chip label a mode resolves to (ComposerModeMenu.modeShortLabel reads
// the head of chat.modeHint.<key>, locales/en.json:215-220).
const EXPECTED_CHIP: Record<Mode, string> = {
  ask: 'ask',
  plan: 'plan',
  'edit-auto': 'edit auto',
  'full-access': 'full access',
}
const DEFAULT_MODE: Mode = 'full-access'

// ── observations.json: one fact block per mode, merged across the four tests ──
type Obs = {
  generatedAt: string
  base: string
  note: string
  modes: Record<string, unknown>
  consoleErrors: string[]
  failedRequests: string[]
}
function loadObs(): Obs {
  try {
    return JSON.parse(readFileSync(OBS, 'utf8')) as Obs
  } catch {
    return {
      generatedAt: '',
      base: BASE,
      note:
        'Per composer mode: what a tool task and a write task really do. ' +
        'plan is the decisive mode — wroteFile=false is the claim, plan.acceptClicked / ' +
        'plan.postAcceptWroteFile answer whether accepting the plan ever runs the work.',
      modes: {},
      consoleErrors: [],
      failedRequests: [],
    }
  }
}
const dedupe = (xs: string[]) => Array.from(new Set(xs))
function saveObs(patch: {
  mode?: Mode
  modeFacts?: unknown
  consoleErrors?: string[]
  failedRequests?: string[]
}): void {
  mkdirSync(OUT, { recursive: true })
  const cur = loadObs()
  const next: Obs = {
    generatedAt: new Date().toISOString(),
    base: BASE,
    note: cur.note,
    modes: { ...cur.modes },
    consoleErrors: cur.consoleErrors,
    failedRequests: cur.failedRequests,
  }
  if (patch.mode && patch.modeFacts) next.modes[patch.mode] = patch.modeFacts
  if (patch.consoleErrors)
    next.consoleErrors = dedupe([...next.consoleErrors, ...patch.consoleErrors])
  if (patch.failedRequests)
    next.failedRequests = dedupe([...next.failedRequests, ...patch.failedRequests])
  writeFileSync(OBS, JSON.stringify(next, null, 2))
}

type TurnEndReason = 'settled' | 'engine_error' | 'deadline'

type TurnFact = {
  kind: 'tool' | 'write' | 'accept'
  task: string
  streamed: boolean
  freshBubble: boolean
  toolRowsSeen: boolean
  toolRowsText: string
  approvalSeen: boolean
  approvalText: string
  approvalApproved: boolean
  answer: string
  // Timing + why the wait ended — the difference between "slow" and "hung".
  startedAt: string
  endedAt: string
  wallMs: number
  endReason: TurnEndReason
  polls: number
  stopVisibleAtEnd: boolean
  textFrozenMs: number
  rawErrorSeen: boolean
  rawErrorText: string
  answerHasPlanBlock: boolean
}
type PlanFact = {
  cardSeen: boolean
  cardScope: 'bubble' | 'page' | null
  state: string | null
  progress: string
  itemCount: number
  items: string[]
  acceptVisible: boolean
  editVisible: boolean
  acceptClicked: boolean
  postAcceptFileStatus: number
  postAcceptWroteFile: boolean
  postAcceptAnswer: string
  postAcceptEndReason: TurnEndReason
  postAcceptWallMs: number
}

async function fileStatus(
  request: { get: (url: string) => Promise<{ status: () => number; body: () => Promise<Buffer> }> },
  name: string,
): Promise<{ status: number; bytes: number }> {
  const res = await request
    .get(`${BASE}/api/file?path=${encodeURIComponent(name)}`)
    .catch(() => null)
  if (!res) return { status: 0, bytes: 0 }
  const body = await res.body().catch(() => Buffer.from(''))
  return { status: res.status(), bytes: body.length }
}

/** Open the mode menu, record what it offers, click `mode`, return the chip text. */
async function pickMode(
  page: import('@playwright/test').Page,
  shot: (name: string) => Promise<void>,
  mode: Mode,
  trace?: TraceFn,
): Promise<{ chipText: string; menuText: string; optionFound: boolean }> {
  // Explicit timeouts everywhere: playwright.config.ts sets no `actionTimeout`, so an
  // action that never becomes actionable (an overlay over the chip, a detached node)
  // waits until the TEST timeout — that is how a finished run turns into a "timeout".
  trace?.('pick-mode-open', { mode })
  await page
    .getByTestId('composer-mode-selector')
    .click({ timeout: 10_000 })
    .catch(() => {})
  await page
    .getByTestId('composer-mode-list')
    .waitFor({ timeout: 8_000 })
    .catch(() => {})
  const menuText = (
    await page
      .getByTestId('composer-mode-list')
      .innerText()
      .catch(() => '')
  ).slice(0, 600)
  await shot('mode-menu')
  const opt = page.getByTestId(`composer-mode-${mode}`).first()
  const optionFound = (await opt.count()) > 0
  if (optionFound) await opt.click({ timeout: 10_000 }).catch(() => {})
  await page.waitForTimeout(500)
  const chipText = (
    await page
      .getByTestId('composer-mode-selector')
      .innerText({ timeout: 10_000 })
      .catch(() => '')
  ).trim()
  trace?.('pick-mode-done', { mode, chipText, optionFound })
  return { chipText, menuText, optionFound }
}

/**
 * Send `task`, then watch the turn to its end while answering any approval gate.
 * Records the arc, never a guess: streamed, tool rows, the approval dialog and
 * its answer, and the assistant answer text the user would read.
 */
async function runTurn(
  page: import('@playwright/test').Page,
  shot: (name: string) => Promise<void>,
  trace: TraceFn,
  kind: TurnFact['kind'],
  task: string,
): Promise<TurnFact> {
  const t0 = Date.now()
  const fact: TurnFact = {
    kind,
    task,
    streamed: false,
    freshBubble: false,
    toolRowsSeen: false,
    toolRowsText: '',
    approvalSeen: false,
    approvalText: '',
    approvalApproved: false,
    answer: '',
    startedAt: new Date(t0).toISOString(),
    endedAt: '',
    wallMs: 0,
    endReason: 'deadline',
    polls: 0,
    stopVisibleAtEnd: false,
    textFrozenMs: 0,
    rawErrorSeen: false,
    rawErrorText: '',
    answerHasPlanBlock: false,
  }
  const before = await page.locator(ASSISTANT).count()
  await page.locator(CHAT_INPUT).fill(task, { timeout: 20_000 })
  await shot(`${kind}-typed`)
  trace('turn-send', { kind, task, bubblesBefore: before })
  await page.keyboard.press('Enter')

  // Settle detection on the LAST bubble's raw text (`textContent`, so a collapsed
  // message still counts): no stop button + a fresh bubble whose text has not changed
  // for STABLE_POLLS polls means the turn ended. Anything else within SETTLE_MS is slow.
  const deadline = Date.now() + SETTLE_MS
  let lastSig = ''
  let stablePolls = 0
  let lastChangeAt = Date.now()
  let stopVisible = false
  while (Date.now() < deadline) {
    fact.polls++
    stopVisible = await page
      .locator(STOP)
      .isVisible()
      .catch(() => false)
    if (stopVisible) fact.streamed = true

    const dlg = page.getByRole('alertdialog')
    if ((await dlg.count()) > 0) {
      if (!fact.approvalSeen) {
        fact.approvalSeen = true
        fact.approvalText = (await dlg.innerText().catch(() => '')).slice(0, 600)
        await shot(`${kind}-approval`)
      }
      if (!fact.approvalApproved) {
        const approve = dlg.getByRole('button', { name: /^approve$/i }).first()
        if ((await approve.count()) > 0) {
          await approve.click({ timeout: 15_000 }).catch(() => {})
          fact.approvalApproved = true
          await page.waitForTimeout(400)
          await shot(`${kind}-approved`)
        }
      }
    }

    if (!fact.toolRowsSeen && (await page.locator(TOOL_ROWS).count()) > 0) {
      fact.toolRowsSeen = true
      fact.toolRowsText = (
        await page
          .locator(TOOL_ROWS)
          .first()
          .innerText()
          .catch(() => '')
      ).slice(0, 800)
      await shot(`${kind}-tool-rows`)
    }

    const bubbles = await page.locator(ASSISTANT).count()
    const text = await page
      .evaluate(() => {
        const all = document.querySelectorAll(
          '[data-testid="message-bubble"][data-role="assistant"]',
        )
        const last = all[all.length - 1] as HTMLElement | undefined
        return last ? last.textContent || '' : ''
      })
      .catch(() => '')
    if (!fact.rawErrorSeen && RAW_ERROR_RE.test(text)) {
      fact.rawErrorSeen = true
      fact.rawErrorText = text.slice(-900)
      await shot(`${kind}-raw-error`)
    }

    const sig = `${stopVisible}|${bubbles}|${text.length}|${text.slice(-240)}`
    if (sig !== lastSig) {
      lastSig = sig
      stablePolls = 0
      lastChangeAt = Date.now()
    } else {
      stablePolls++
    }
    const el = Date.now() - t0
    trace('poll', {
      el,
      stop: stopVisible,
      bubbles,
      stablePolls,
      rawError: fact.rawErrorSeen,
      tail: text.slice(-160),
    })

    if (!stopVisible && bubbles > before && stablePolls >= STABLE_POLLS) {
      fact.endReason = fact.rawErrorSeen ? 'engine_error' : 'settled'
      break
    }
    await page.waitForTimeout(POLL_MS)
  }
  fact.endedAt = new Date().toISOString()
  fact.wallMs = Date.now() - t0
  fact.stopVisibleAtEnd = stopVisible
  fact.textFrozenMs = Date.now() - lastChangeAt
  trace('turn-end', {
    kind,
    wallMs: fact.wallMs,
    endReason: fact.endReason,
    stopVisibleAtEnd: fact.stopVisibleAtEnd,
    textFrozenMs: fact.textFrozenMs,
    polls: fact.polls,
    rawError: fact.rawErrorSeen,
  })
  if (fact.endReason === 'deadline') await shot(`${kind}-never-settled`)
  await page.waitForTimeout(1500)

  const now = await page.locator(ASSISTANT).count()
  fact.freshBubble = now > before
  const bubble = page.locator(ASSISTANT).last()
  if (await bubble.count()) {
    const head = bubble.getByTestId('bubble-turn-head')
    if ((await head.getAttribute('aria-expanded').catch(() => null)) === 'false') {
      await head.click().catch(() => {})
      await page.waitForTimeout(400)
    }
    fact.answer = (await bubble.innerText().catch(() => '')).slice(0, 4000)
  }
  fact.answerHasPlanBlock = PLAN_BLOCK_RE.test(fact.answer)
  await shot(`${kind}-answer`)
  return fact
}

/** Raw provider errors visible in the transcript (textContent, so collapsing cannot hide one). */
async function rawErrorsInTranscript(
  page: import('@playwright/test').Page,
): Promise<{ count: number; samples: string[] }> {
  const texts = await page
    .evaluate(() =>
      Array.from(
        document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
        (b) => (b as HTMLElement).textContent || '',
      ),
    )
    .catch(() => [] as string[])
  const hits = texts.filter((t) => RAW_ERROR_RE.test(t))
  return { count: hits.length, samples: hits.map((t) => t.slice(-400)) }
}

/** Does the workspace Files panel list `name`? (null = the surface was not reachable) */
async function workspaceListsFile(
  page: import('@playwright/test').Page,
  name: string,
): Promise<boolean | null> {
  // #71: the Files row lives in the closed "Tools & Capabilities" tier.
  await openTier(page, 'tools')
  const btn = page.getByTestId('sidebar-action-files')
  if ((await btn.count()) === 0) return null
  await btn.click({ timeout: 10_000 }).catch(() => {})
  await page.waitForTimeout(1_800)
  const panel = page.getByRole('tabpanel').first()
  if ((await panel.count()) === 0) return null
  const txt = await panel.innerText({ timeout: 10_000 }).catch(() => '')
  return txt.includes(name)
}

async function runMode(
  page: import('@playwright/test').Page,
  request: import('@playwright/test').APIRequestContext,
  mode: Mode,
): Promise<void> {
  mkdirSync(OUT, { recursive: true })
  const consoleErrors: string[] = []
  const failedRequests: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 400))
  })
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${String(e.message).slice(0, 400)}`))
  page.on('requestfailed', (r) =>
    failedRequests.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText ?? 'failed'}`),
  )
  page.on('response', (r) => {
    if (r.status() >= 400) failedRequests.push(`${r.status()} ${r.request().method()} ${r.url()}`)
  })

  let n = 0
  const shot = async (name: string) => {
    const file = join(OUT, `${String(++n).padStart(2, '0')}-${mode}-${name}.png`)
    await page.screenshot({ path: file, fullPage: true }).catch(() => {})
  }

  // Durable trace: one line per poll, flushed to disk immediately, so a stall stays
  // locatable even if the runner kills the test mid-turn.
  const modeT0 = Date.now()
  const TRACE_FILE = join(OUT, `trace-${mode}.jsonl`)
  writeFileSync(TRACE_FILE, '')
  const trace: TraceFn = (event, data) => {
    try {
      appendFileSync(
        TRACE_FILE,
        `${JSON.stringify({ t: new Date().toISOString(), wall: Date.now() - modeT0, event, ...(data ?? {}) })}\n`,
      )
    } catch {
      /* a trace must never fail the run */
    }
  }
  trace('mode-start', { mode, base: BASE, settleMs: SETTLE_MS })

  const fileName = `mode-${mode}.txt`
  const toolTask = `Run this shell command and show the output: echo mode-${mode}`
  const writeTask = `Create a file named ${fileName} containing: hello`

  const facts: Record<string, unknown> = {
    mode,
    modeKey: mode,
    toolTask,
    writeTask,
    fileName,
    settleMs: SETTLE_MS,
    traceFile: `trace-${mode}.jsonl`,
    turns: [] as TurnFact[],
  }
  // A turn that never settled inside SETTLE_MS is a finding — it fails the test at the
  // very end, after every surface has been read and written to observations.json.
  let unsettledMsg: string | null = null

  try {
    // English locale, no first-run gate — same init as the sibling walkthroughs.
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })

    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_INPUT, { timeout: 30_000 })
    await page.waitForTimeout(1_200)
    await shot('chat-open')
    trace('chat-open')

    // Fresh task so the transcript starts empty for this mode.
    const ns = page.getByTestId('new-session')
    const nsVisible = await ns.isVisible().catch(() => false)
    if (nsVisible) {
      await ns.click().catch(() => {})
      await page.waitForTimeout(700)
    }
    trace('new-session', { visible: nsVisible })

    // ── 1. switch the composer to this mode ───────────────────────────────
    facts.chipBefore = (
      await page
        .getByTestId('composer-mode-selector')
        .innerText()
        .catch(() => '')
    ).trim()
    const picked = await pickMode(page, shot, mode)
    expect(picked.optionFound, `composer-mode-${mode} must exist in the mode menu`).toBe(true)
    facts.menuText = picked.menuText
    facts.chipAfter = picked.chipText
    facts.chipMatchesSelection = picked.chipText.toLowerCase().includes(EXPECTED_CHIP[mode])
    await shot('mode-selected')
    trace('mode-picked', { chip: picked.chipText, optionFound: picked.optionFound })

    // Baseline disk state — a previous sibling run could have left the file.
    const base = await fileStatus(request, fileName)
    facts.fileBaselineStatus = base.status
    trace('file-baseline', { status: base.status, bytes: base.bytes })

    // ── 2a. task that needs a TOOL ────────────────────────────────────────
    const t1 = await runTurn(page, shot, trace, 'tool', toolTask)
    ;(facts.turns as TurnFact[]).push(t1)
    await page.waitForTimeout(800)
    facts.toolTaskFileStatus = (await fileStatus(request, fileName)).status
    trace('after-tool-turn', { fileStatus: facts.toolTaskFileStatus as number })

    // ── 2b. task that needs a WRITE ───────────────────────────────────────
    const t2 = await runTurn(page, shot, trace, 'write', writeTask)
    ;(facts.turns as TurnFact[]).push(t2)
    await page.waitForTimeout(800)
    facts.writeAnswerHasPlanBlock = t2.answerHasPlanBlock
    trace('after-write-turn', {
      answerHasPlanBlock: t2.answerHasPlanBlock,
      endReason: t2.endReason,
    })

    // ── 3a. disk truth after both turns (the honest "is anything written") ─
    const after = await fileStatus(request, fileName)
    facts.fileAfterStatus = after.status
    facts.fileAfterBytes = after.bytes
    facts.wroteFile = after.status === 200
    trace('file-after', { status: after.status, bytes: after.bytes })

    // ── 3b. the workspace facts via the UI (Files panel) ──────────────────
    facts.workspaceListsFile = await workspaceListsFile(page, fileName)
    await shot('files-panel')
    trace('files-panel', { listsFile: facts.workspaceListsFile })

    // Raw provider errors anywhere in the transcript, for every mode — this is the
    // "did the 400 reach the chat" answer, independent of the mode's own turns.
    const rawErrors = await rawErrorsInTranscript(page)
    facts.rawErrorsAtFilesPanel = rawErrors
    if (rawErrors.count > 0) await shot('raw-error-transcript')
    trace('raw-error-scan', { count: rawErrors.count })

    // Back to the chat to read the rendered plan card from the transcript.
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_INPUT, { timeout: 20_000 })
    await page.waitForTimeout(1_200)
    trace('plan-read-start')

    // ── 3c. plan presentation (decisive for plan mode) ────────────────────
    const plan: PlanFact = {
      cardSeen: false,
      cardScope: null,
      state: null,
      progress: '',
      itemCount: 0,
      items: [],
      acceptVisible: false,
      editVisible: false,
      acceptClicked: false,
      postAcceptFileStatus: 0,
      postAcceptWroteFile: false,
      postAcceptAnswer: '',
      postAcceptEndReason: 'deadline',
      postAcceptWallMs: 0,
    }
    const bubbleScope = page.locator(ASSISTANT).last()
    let scope: import('@playwright/test').Locator = bubbleScope
    let count = await bubbleScope.locator(PLAN_CARD).count()
    let scopeName: 'bubble' | 'page' = 'bubble'
    if (count === 0) {
      scope = page.locator(PLAN_CARD)
      count = await scope.count()
      scopeName = 'page'
    }
    plan.cardSeen = count > 0
    if (plan.cardSeen) {
      plan.cardScope = scopeName
      const card = scope.locator(PLAN_CARD).first()
      plan.state = await card.getAttribute('data-state').catch(() => null)
      plan.progress = (
        await card
          .locator(PLAN_PROGRESS)
          .first()
          .innerText()
          .catch(() => '')
      ).trim()
      const items = card.locator(PLAN_ITEM)
      const ic = await items.count()
      plan.itemCount = ic
      for (let i = 0; i < ic; i++)
        plan.items.push(
          (
            await items
              .nth(i)
              .innerText()
              .catch(() => '')
          ).trim(),
        )
      plan.acceptVisible = (await card.locator(PLAN_ACCEPT).count()) > 0
      plan.editVisible = (await card.locator(PLAN_EDIT).count()) > 0
      await shot('plan-card')

      // The user's way to say "yes, do it": accept the plan and watch whether the
      // work then actually runs — the finding this spec exists for.
      if (plan.acceptVisible) {
        await card
          .locator(PLAN_ACCEPT)
          .first()
          .click({ timeout: 10_000 })
          .catch(() => {})
        plan.acceptClicked = true
        await page.waitForTimeout(600)
        await shot('plan-accepted-click')
        const t3 = await runTurn(page, shot, trace, 'accept', 'Plan accepted — proceed.')
        ;(facts.turns as TurnFact[]).push(t3)
        plan.postAcceptAnswer = t3.answer
        plan.postAcceptEndReason = t3.endReason
        plan.postAcceptWallMs = t3.wallMs
        await page.waitForTimeout(800)
        const post = await fileStatus(request, fileName)
        plan.postAcceptFileStatus = post.status
        plan.postAcceptWroteFile = post.status === 200 && post.bytes > 0
        await shot('post-accept')
        trace('plan-accept', {
          wroteFileAfterAccept: plan.postAcceptWroteFile,
          status: post.status,
        })
      }
    } else {
      // No card: the finding is the answer the user was left with instead. Recorded
      // verbatim in the write turn's `answer`, and the reason the wait ended.
      trace('plan-card-absent', { writeEndReason: t2.endReason, writeRawError: t2.rawErrorSeen })
    }
    facts.plan = plan
    trace('plan-read-done', {
      cardSeen: plan.cardSeen,
      itemCount: plan.itemCount,
      acceptVisible: plan.acceptVisible,
      state: plan.state,
    })

    // ── 3d. the status popover (the `{"type":"plan"}` frame's reader) ──────
    const pill = page.getByTestId('agent-status-pill')
    if ((await pill.count()) > 0) {
      await pill.click().catch(() => {})
      await page.waitForTimeout(600)
      const pop = page.getByTestId('agent-status-popover')
      facts.statusPopover =
        (await pop.count()) > 0 ? (await pop.innerText().catch(() => '')).slice(0, 1_000) : null
      await shot('status-popover')
    }

    facts.finalChip = (
      await page
        .getByTestId('composer-mode-selector')
        .innerText({ timeout: 10_000 })
        .catch(() => '')
    ).trim()

    // The whole transcript again, now including the accept turn — the raw provider
    // error of plan mode's accept lands here and nowhere earlier.
    facts.rawErrorsInTranscript = await rawErrorsInTranscript(page)
    facts.planAcceptTurnRawError = (facts.turns as TurnFact[])
      .filter((t) => t.endReason === 'engine_error')
      .map((t) => ({ kind: t.kind, wallMs: t.wallMs, rawErrorText: t.rawErrorText.slice(-420) }))
    trace('final-raw-error-scan', {
      count: (facts.rawErrorsInTranscript as { count: number }).count,
      turnsWithEngineError: (facts.planAcceptTurnRawError as unknown[]).length,
    })

    // ── 4. slow vs hung, settled here ─────────────────────────────────────
    const turns = facts.turns as TurnFact[]
    const stuck = turns.filter((t) => t.endReason === 'deadline')
    facts.turnWallMs = turns.map((t) => ({
      kind: t.kind,
      wallMs: t.wallMs,
      endReason: t.endReason,
    }))
    if (stuck.length > 0) {
      unsettledMsg =
        `${stuck.length} turn(s) never settled within ${SETTLE_MS / 1000}s — ` +
        stuck
          .map(
            (t) =>
              `${t.kind}: wallMs=${t.wallMs} stopStillVisible=${t.stopVisibleAtEnd} ` +
              `bubbleTextFrozenFor=${t.textFrozenMs}ms polls=${t.polls} rawError=${t.rawErrorSeen}`,
          )
          .join('; ') +
        ` (see trace-${mode}.jsonl)`
      trace('unsettled-turns', { stuck: stuck.map((t) => t.kind) })
    }
    trace('mode-body-done', { turns: turns.length, unsettled: stuck.length })
  } catch (e) {
    facts.error = String((e as Error)?.message ?? e)
    trace('mode-body-error', { error: facts.error as string })
    await page
      .screenshot({ path: join(OUT, `99-${mode}-failure.png`), fullPage: true })
      .catch(() => {})
  } finally {
    // RESTORE the composer mode to the default — siblings share this server.
    // The status popover can sit over the chip; Escape first, then race the whole
    // restore against a timer so a never-actionable click cannot eat the test budget.
    trace('restore-start')
    await page.keyboard.press('Escape').catch(() => {})
    await page.waitForTimeout(300)
    try {
      const restored = await Promise.race([
        pickMode(page, async () => {}, DEFAULT_MODE, trace),
        new Promise<null>((r) => setTimeout(() => r(null), 45_000)),
      ])
      if (restored) {
        facts.restoredChip = restored.chipText
        facts.restoredToDefault = restored.chipText
          .toLowerCase()
          .includes(EXPECTED_CHIP[DEFAULT_MODE])
      } else {
        facts.restoreTimedOut = true
        facts.restoredToDefault = false
      }
      trace('restored', { chip: (facts.restoredChip as string) ?? null, timedOut: !restored })
    } catch (e) {
      facts.restoredToDefault = false
      facts.restoreError = String((e as Error)?.message ?? e)
      trace('restore-failed', { error: facts.restoreError as string })
    }
    saveObs({ mode, modeFacts: facts, consoleErrors, failedRequests })
    trace('saved')
    console.log(`MODES-MATRIX ${mode} >>>\n${JSON.stringify(facts, null, 2)}\n<<<`)
  }

  // A turn that never settles is the finding this spec exists to separate from "slow":
  // every fact is already on disk, and the test still fails on it.
  if (unsettledMsg) throw new Error(unsettledMsg)
}

test(`composer mode ask: tool task, write task, plan — what really happens`, async ({
  page,
  request,
}) => {
  await runMode(page, request, 'ask')
})

test(`composer mode plan: does it write nothing and really present a plan?`, async ({
  page,
  request,
}) => {
  await runMode(page, request, 'plan')
})

test(`composer mode edit-auto: tool task, write task, plan — what really happens`, async ({
  page,
  request,
}) => {
  await runMode(page, request, 'edit-auto')
})

test(`composer mode full-access: tool task, write task, plan — what really happens`, async ({
  page,
  request,
}) => {
  await runMode(page, request, 'full-access')
})
