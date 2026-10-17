/**
 * plan-accept.spec.ts — the plan mode's exit, driven the way a user drives it.
 *
 * FINDINGS.md (docs/media/user-walkthrough-2026-10-12) records the blocker: Plan mode
 * drafts a real plan and writes nothing — its guard holds — and then Accept sends the
 * prose "Plan accepted — proceed." as an ordinary message while the composer stays in
 * `plan`, so the turn that is supposed to execute the plan still has no write tool and
 * the file the plan promised never appears.
 *
 * This is the acceptance test for the exit. With the composer in `plan` and a write task,
 * a plan card in state `draft` must appear; clicking `plan-accept` must then
 *   1. change the composer mode VISIBLY — the chip leaves "Plan" for the mode that can
 *      write (app/src/lib/planCardModel.ts::PLAN_EXECUTION_MODE),
 *   2. start the run by itself: no second typed message is needed, and the transcript
 *      carries a line that says the mode was left (never a silent prose hand-off), and
 *   3. put the promised file on disk, readable through GET /api/file, listed in the
 *      workspace Files panel, with a screenshot of its content.
 *
 * It runs against the LIVE stack — real backend, real engine, no `page.route` — so every
 * number below is read back from the product, not assumed.
 *
 * Preconditions:
 *   - ephe backend up on 127.0.0.1:8765 serving the app (EPHE_WALKTHROUGH_BASE overrides).
 *   - the app is served from the PWA build in app/dist, so a source change needs
 *     `npm run build` in app/ BEFORE this spec can see it. It reads the product, not the
 *     source.
 *   - run with `--timeout 900000`: a plan turn plus the run it triggers are two real
 *     engine turns.
 * Evidence (screenshots + observations.json + trace.jsonl) lands in the walkthrough
 * capture dir (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/plan-accept/.
 *
 * Selectors (read from source):
 *   mode selector  app/src/components/dashboard/chat/ComposerModeChip.tsx:41  data-testid="composer-mode-selector"
 *   mode option    app/src/components/dashboard/chat/ComposerModeMenu.tsx:160 data-testid="composer-mode-<key>"
 *   chat input     app/src/components/dashboard/ChatInput.tsx:433             data-testid="chat-input"
 *   send / stop    app/src/components/dashboard/chat/ComposerSendButton.tsx:77 data-testid="send-btn" | "stop-btn"
 *   assistant      app/src/components/dashboard/MessageBubble.tsx:118-119    data-testid="message-bubble" data-role="assistant"
 *   user           app/src/components/dashboard/MessageBubble.tsx:118-119    data-testid="message-bubble" data-role="user"
 *   tool rows      app/src/components/dashboard/bubble/toolStreamRows.tsx:47 data-testid="tool-stream-rows"
 *   plan card      app/src/components/dashboard/PlanCard.tsx:52              data-testid="plan-card" (data-state draft|running|accepted)
 *   plan accept    app/src/components/dashboard/PlanCard.tsx:131             data-testid="plan-accept"
 *   new task       app/src/components/dashboard/Sidebar.tsx:870              data-testid="new-session"
 *   files tab      app/src/components/dashboard/Sidebar.tsx:692              data-testid="sidebar-action-files"
 *   chip label     app/src/locales/en.json chat.modeHint.* — the head before the em dash
 *                  (app/src/components/dashboard/chat/ComposerModeMenu.tsx::modeShortLabel)
 */
import { test, expect } from '@playwright/test'
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'
import { openTier } from './rail.ts'

test.describe.configure({ timeout: 900_000 })

const BASE = process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765'
const OUT = walkthroughOutDir('plan-accept')
const OBS = join(OUT, 'observations.json')
const TRACE_FILE = join(OUT, 'trace.jsonl')

const CHAT_INPUT = '[data-testid="chat-input"]'
const STOP = '[data-testid="stop-btn"]'
const ASSISTANT = '[data-testid="message-bubble"][data-role="assistant"]'
const USER_BUBBLE = '[data-testid="message-bubble"][data-role="user"]'
const TOOL_ROWS = '[data-testid="tool-stream-rows"]'
const PLAN_CARD = '[data-testid="plan-card"]'
const PLAN_ITEM = '[data-testid^="plan-item-"]'
const PLAN_ACCEPT = '[data-testid="plan-accept"]'

const FILE_NAME = `plan-accept-${Date.now()}.txt`
const FILE_CONTENT = 'plan accept works'
// A user in Plan mode asks for the plan, not for the run — that is the mode's promise.
const WRITE_TASK = `Plan this first and do not run it yet: create a file named ${FILE_NAME} containing exactly: ${FILE_CONTENT}`
// The chip text a mode resolves to, lowercased (locales/en.json chat.modeHint.* heads).
const PLAN_CHIP = 'plan'
const EXECUTION_CHIP = 'edit auto'
/** The same mode as a value: PLAN_EXECUTION_MODE, the one the chip label is derived from. */
const EXECUTION_MODE = 'edit-auto'
const DEFAULT_MODE = 'full-access'
/** The same mode as the chip draws it: `full-access` renders as `Full access`. */
const DEFAULT_CHIP = 'full access'

const SETTLE_MS = 360_000
const POLL_MS = 500
const STABLE_POLLS = 4 // 2 s of byte-stable bubble text = the turn ended
/** How many times the plan turn may be sent before a missing card is a finding. */
const PLAN_ATTEMPTS = 3
const RAW_ERROR_RE =
  /Client error '\d{3} [^']*' for url|developer\.mozilla\.org\/en-US\/docs\/Web\/HTTP\/Status/

/**
 * The plan the Accept click is supposed to hand over, read from the request the product
 * itself builds — not from the bubble. The bubble renders markdown, so `## Plan` and
 * `- [ ]` are eaten by the renderer before `innerText` can see them; the wire text is the
 * only place the marker survives, and it is also the place the engine actually reads.
 */
type AcceptPost = { message: string; mode: string; autonomous: boolean }

/** Words only, both sides: the renderer drops backticks and list marks, so compare words. */
function normWords(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

/** A plan row's text is "<status glyph>\n<n>.<title>"; the title is the step itself. */
function planStepTitle(rowText: string): string {
  const last = rowText.split('\n').pop() ?? rowText
  return last.replace(/^\s*\d+[.)]\s*/, '').trim()
}

type EndReason = 'settled' | 'engine_error' | 'deadline'

type TurnFact = {
  kind: string
  task: string
  startedBy: 'typed' | 'plan-accept-click'
  streamed: boolean
  freshBubble: boolean
  toolRowsSeen: boolean
  toolRowsText: string
  approvalSeen: boolean
  approvalApproved: boolean
  answer: string
  wallMs: number
  endReason: EndReason
  polls: number
  stopVisibleAtEnd: boolean
  rawErrorSeen: boolean
  rawErrorText: string
}

type PlanFact = {
  cardSeen: boolean
  planTurnAttempts: { attempt: number; endReason: EndReason; wallMs: number; cardSeen: boolean }[]
  state: string | null
  progress: string
  itemCount: number
  items: string[]
  acceptVisible: boolean
  chipBeforeAccept: string
  acceptClicked: boolean
  cardStateAfterAccept: string | null
  chipAfterAccept: string
  transcriptLine: string
  transcriptLineCarriesPlanBlock: boolean
  transcriptStepsCarried: number
  transcriptStepCount: number
  acceptPostMode: string
  acceptPostCarriesPlanBlock: boolean
  acceptPostStepsCarried: number
  postAcceptFileStatus: number
  postAcceptFileText: string
  postAcceptWroteFile: boolean
  acceptTurn: TurnFact | null
}

let traceT0 = Date.now()
function trace(event: string, data?: Record<string, unknown>): void {
  try {
    appendFileSync(
      TRACE_FILE,
      `${JSON.stringify({ t: new Date().toISOString(), wall: Date.now() - traceT0, event, ...(data ?? {}) })}\n`,
    )
  } catch {
    /* a trace must never fail the run */
  }
}

function saveObs(facts: Record<string, unknown>): void {
  let merged: Record<string, unknown> = {}
  try {
    merged = JSON.parse(readFileSync(OBS, 'utf8')) as Record<string, unknown>
  } catch {
    merged = { note: 'The plan mode exit: Accept must leave Plan mode and run the plan.' }
  }
  merged.generatedAt = new Date().toISOString()
  merged.base = BASE
  merged.planAccept = facts
  writeFileSync(OBS, `${JSON.stringify(merged, null, 2)}\n`)
}

async function fileStatus(
  request: import('@playwright/test').APIRequestContext,
  name: string,
): Promise<{ status: number; text: string; bytes: number }> {
  const res = await request
    .get(`${BASE}/api/file?path=${encodeURIComponent(name)}`)
    .catch(() => null)
  if (!res) return { status: 0, text: '', bytes: 0 }
  const body = await res.body().catch(() => Buffer.from(''))
  return { status: res.status(), text: body.toString('utf8'), bytes: body.length }
}

/** Open the mode menu and click `mode`; return the chip text afterwards. */
async function pickMode(
  page: import('@playwright/test').Page,
  shot: (name: string) => Promise<void>,
  mode: string,
): Promise<string> {
  await page
    .getByTestId('composer-mode-selector')
    .click({ timeout: 10_000 })
    .catch(() => {})
  await page
    .getByTestId('composer-mode-list')
    .waitFor({ timeout: 8_000 })
    .catch(() => {})
  await shot(`mode-menu-${mode}`)
  await page
    .getByTestId(`composer-mode-${mode}`)
    .first()
    .click({ timeout: 10_000 })
    .catch(() => {})
  await page.waitForTimeout(500)
  return (
    await page
      .getByTestId('composer-mode-selector')
      .innerText()
      .catch(() => '')
  ).trim()
}

/**
 * Watch a turn to its end while answering any approval gate. `alreadySent` watches a turn
 * the product started by itself (the plan card's Accept) — nothing is typed.
 */
async function watchTurn(
  page: import('@playwright/test').Page,
  shot: (name: string) => Promise<void>,
  kind: string,
  opts: { task: string; before: number; alreadySent: boolean },
): Promise<TurnFact> {
  const t0 = Date.now()
  const fact: TurnFact = {
    kind,
    task: opts.task,
    startedBy: opts.alreadySent ? 'plan-accept-click' : 'typed',
    streamed: false,
    freshBubble: false,
    toolRowsSeen: false,
    toolRowsText: '',
    approvalSeen: false,
    approvalApproved: false,
    answer: '',
    wallMs: 0,
    endReason: 'deadline',
    polls: 0,
    stopVisibleAtEnd: false,
    rawErrorSeen: false,
    rawErrorText: '',
  }
  const before = opts.before
  if (!opts.alreadySent) {
    await page.locator(CHAT_INPUT).fill(opts.task, { timeout: 20_000 })
    await shot(`${kind}-typed`)
    trace('turn-send', { kind, task: opts.task, bubblesBefore: before })
    await page.keyboard.press('Enter')
  } else {
    trace('turn-card-start', { kind, bubblesBefore: before })
  }

  const deadline = Date.now() + SETTLE_MS
  let lastSig = ''
  let stablePolls = 0
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
        await shot(`${kind}-approval`)
      }
      if (!fact.approvalApproved) {
        const approve = dlg.getByRole('button', { name: /^approve$/i }).first()
        if ((await approve.count()) > 0) {
          await approve.click({ timeout: 15_000 }).catch(() => {})
          fact.approvalApproved = true
          await page.waitForTimeout(400)
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
    } else {
      stablePolls++
    }
    trace('poll', {
      kind,
      el: Date.now() - t0,
      stop: stopVisible,
      bubbles,
      stablePolls,
      tail: text.slice(-160),
    })

    if (!stopVisible && bubbles > before && stablePolls >= STABLE_POLLS) {
      fact.endReason = fact.rawErrorSeen ? 'engine_error' : 'settled'
      break
    }
    await page.waitForTimeout(POLL_MS)
  }
  fact.wallMs = Date.now() - t0
  fact.stopVisibleAtEnd = stopVisible
  trace('turn-end', {
    kind,
    wallMs: fact.wallMs,
    endReason: fact.endReason,
    rawError: fact.rawErrorSeen,
  })
  if (fact.endReason === 'deadline') await shot(`${kind}-never-settled`)
  await page.waitForTimeout(1_500)

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
  await shot(`${kind}-answer`)
  return fact
}

test('plan accept: the click leaves Plan mode and the plan produces its file', async ({
  page,
  request,
}) => {
  mkdirSync(OUT, { recursive: true })
  traceT0 = Date.now()
  writeFileSync(TRACE_FILE, '')
  trace('start', { base: BASE, fileName: FILE_NAME })

  let n = 0
  const shot = async (name: string) => {
    const file = join(OUT, `${String(++n).padStart(2, '0')}-${name}.png`)
    await page.screenshot({ path: file, fullPage: true }).catch(() => {})
  }

  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
  })

  const facts: Record<string, unknown> = { fileName: FILE_NAME, writeTask: WRITE_TASK }
  const plan: PlanFact = {
    cardSeen: false,
    planTurnAttempts: [],
    state: null,
    progress: '',
    itemCount: 0,
    items: [],
    acceptVisible: false,
    chipBeforeAccept: '',
    acceptClicked: false,
    cardStateAfterAccept: null,
    chipAfterAccept: '',
    transcriptLine: '',
    transcriptLineCarriesPlanBlock: false,
    transcriptStepsCarried: 0,
    transcriptStepCount: 0,
    acceptPostMode: '',
    acceptPostCarriesPlanBlock: false,
    acceptPostStepsCarried: 0,
    postAcceptFileStatus: 0,
    postAcceptFileText: '',
    postAcceptWroteFile: false,
    acceptTurn: null,
  }
  facts.plan = plan

  try {
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
    await page.locator(CHAT_INPUT).waitFor({ timeout: 30_000 })
    await page.waitForTimeout(1_200)
    await shot('chat-open')

    const ns = page.getByTestId('new-session')
    if (await ns.isVisible().catch(() => false)) {
      await ns.click().catch(() => {})
      await page.waitForTimeout(700)
    }

    // ── the composer in `plan` ───────────────────────────────────────────
    const chipPlan = await pickMode(page, shot, 'plan')
    facts.chipAfterPick = chipPlan
    expect(chipPlan.toLowerCase(), 'the composer must be in Plan mode for this arc').toContain(
      PLAN_CHIP,
    )
    await shot('mode-plan-selected')

    const baseline = await fileStatus(request, FILE_NAME)
    facts.fileBaselineStatus = baseline.status
    trace('file-baseline', { status: baseline.status })

    // ── 1. a write task in plan mode: a plan, no write ──────────────────
    // The plan turn is one real engine turn; a multi-call tool round kills it upstream
    // (a known, separately owned blocker), and then there is no card and no Accept to
    // test. Retry a bounded number of times and record EVERY attempt, so a plan that
    // never appears stays a finding instead of silently shrinking this spec's reach.
    const card = page.locator(PLAN_CARD).first()
    for (let attempt = 1; attempt <= PLAN_ATTEMPTS && !plan.cardSeen; attempt++) {
      const bubblesBeforePlan = await page.locator(ASSISTANT).count()
      const planTurn = await watchTurn(page, shot, `plan-task-${attempt}`, {
        task: attempt === 1 ? WRITE_TASK : `${WRITE_TASK} (attempt ${attempt})`,
        before: bubblesBeforePlan,
        alreadySent: false,
      })
      plan.planTurnAttempts.push({
        attempt,
        endReason: planTurn.endReason,
        wallMs: planTurn.wallMs,
        cardSeen: (await card.count()) > 0,
      })
      trace('plan-turn', {
        attempt,
        endReason: planTurn.endReason,
        wallMs: planTurn.wallMs,
        cardSeen: plan.planTurnAttempts[plan.planTurnAttempts.length - 1]?.cardSeen,
      })
      plan.cardSeen = (await card.count()) > 0
      if (!plan.cardSeen && attempt < PLAN_ATTEMPTS) await page.waitForTimeout(2_000)
    }

    expect(
      plan.cardSeen,
      `Plan mode must present a plan card (attempts: ${JSON.stringify(plan.planTurnAttempts)})`,
    ).toBe(true)
    plan.state = await card.getAttribute('data-state').catch(() => null)
    plan.progress = (
      await card
        .locator('[data-testid="plan-progress"]')
        .first()
        .innerText()
        .catch(() => '')
    ).trim()
    const items = card.locator(PLAN_ITEM)
    plan.itemCount = await items.count()
    for (let i = 0; i < plan.itemCount; i++) {
      plan.items.push(
        (
          await items
            .nth(i)
            .innerText()
            .catch(() => '')
        ).trim(),
      )
    }
    plan.acceptVisible = (await card.locator(PLAN_ACCEPT).count()) > 0
    plan.chipBeforeAccept = (
      await page
        .getByTestId('composer-mode-selector')
        .innerText()
        .catch(() => '')
    ).trim()
    await card.scrollIntoViewIfNeeded().catch(() => {})
    await shot('plan-card-draft')
    const stillNothing = await fileStatus(request, FILE_NAME)
    facts.fileStatusBeforeAccept = stillNothing.status
    expect(plan.acceptVisible, 'a draft plan must offer the Accept gate').toBe(true)

    // ── 2. Accept: the click itself must start the run ──────────────────
    // Capture the turn the product POSTs. This is passive observation, not interception:
    // the request goes to the real engine, and the body is what proves the hand-off.
    const captured: { accept?: AcceptPost } = {}
    const captureAcceptPost = (r: import('@playwright/test').Request) => {
      if (r.method() !== 'POST' || !r.url().includes('/api/chat/stream')) return
      try {
        const body = JSON.parse(r.postData() ?? '{}') as Partial<AcceptPost>
        const message = String(body.message ?? '')
        // The plan turn's own POST carries the write task; only the accept carries this lead.
        if (message.includes('left Plan mode')) {
          captured.accept = {
            message,
            mode: String(body.mode ?? ''),
            autonomous: Boolean(body.autonomous),
          }
        }
      } catch {
        /* a body we cannot read is not a body we may assert on */
      }
    }
    page.on('request', captureAcceptPost)

    const bubblesBeforeAccept = await page.locator(ASSISTANT).count()
    await card.locator(PLAN_ACCEPT).first().click({ timeout: 10_000 })
    plan.acceptClicked = true
    await page.waitForTimeout(350)
    plan.cardStateAfterAccept = await page
      .locator(`${PLAN_CARD}`)
      .first()
      .getAttribute('data-state')
      .catch(() => null)
    plan.chipAfterAccept = (
      await page
        .getByTestId('composer-mode-selector')
        .innerText()
        .catch(() => '')
    ).trim()
    await shot('plan-accepted')

    // The visible state change the user reads: the chip no longer says Plan.
    expect(
      plan.chipAfterAccept.toLowerCase(),
      'Accept must move the composer out of Plan mode into the mode that can write',
    ).toContain(EXECUTION_CHIP)

    const acceptTurn = await watchTurn(page, shot, 'accept-run', {
      task: '(started by the plan card\u2019s Accept click)',
      before: bubblesBeforeAccept,
      alreadySent: true,
    })
    plan.acceptTurn = acceptTurn
    trace('accept-turn', { endReason: acceptTurn.endReason, wallMs: acceptTurn.wallMs })

    page.off('request', captureAcceptPost)

    // ── 2b. what the click actually sent ────────────────────────────────
    // The wire text is the one place the `## Plan` marker survives: the bubble renders
    // markdown, so `innerText` shows the steps but never the syntax. Assert on the request
    // the product built, and keep the rendered line as corroboration.
    const accept = captured.accept
    expect(accept, 'the Accept click must POST a turn of its own').toBeTruthy()
    plan.acceptPostMode = accept?.mode ?? ''
    plan.acceptPostCarriesPlanBlock = (accept?.message ?? '').includes('## Plan')
    plan.acceptPostStepsCarried = plan.items.filter((row) => {
      const title = normWords(planStepTitle(row))
      return title.length > 0 && normWords(accept?.message ?? '').includes(title)
    }).length
    trace('accept-post', {
      mode: plan.acceptPostMode,
      carriesPlanBlock: plan.acceptPostCarriesPlanBlock,
      stepsCarried: plan.acceptPostStepsCarried,
      steps: plan.items.length,
      messageHead: (accept?.message ?? '').slice(0, 160),
    })

    expect(
      plan.acceptPostMode,
      'the posted turn must run in the mode that can write, not in Plan',
    ).toBe(EXECUTION_MODE)
    expect(
      plan.acceptPostCarriesPlanBlock,
      'the posted turn must carry the plan block — no silent prose hand-off',
    ).toBe(true)
    expect(
      plan.acceptPostStepsCarried,
      `the posted turn must carry every step the user confirmed (${JSON.stringify(plan.items)})`,
    ).toBe(plan.items.length)

    // Corroboration in the surface the user reads: the steps are on screen, under the
    // heading the renderer draws from `## Plan`.
    const line = page.locator(USER_BUBBLE).last()
    plan.transcriptLine = (await line.innerText().catch(() => '')).slice(0, 4_000)
    plan.transcriptStepCount = plan.items.length
    plan.transcriptStepsCarried = plan.items.filter((row) =>
      normWords(plan.transcriptLine).includes(normWords(planStepTitle(row))),
    ).length
    plan.transcriptLineCarriesPlanBlock =
      plan.transcriptStepsCarried === plan.items.length &&
      !plan.transcriptLine.includes('Plan accepted — proceed.')
    expect(
      plan.transcriptStepsCarried,
      'the accept line must show the plan it is executing — no silent prose hand-off',
    ).toBe(plan.items.length)
    expect(plan.transcriptLine).not.toBe('Plan accepted — proceed.')
    await shot('accept-transcript-line')

    // ── 3. the file the plan promised ───────────────────────────────────
    const post = await fileStatus(request, FILE_NAME)
    plan.postAcceptFileStatus = post.status
    plan.postAcceptFileText = post.text.slice(0, 400)
    plan.postAcceptWroteFile = post.status === 200 && post.text.includes(FILE_CONTENT)
    trace('post-accept-file', { status: post.status, text: post.text.slice(0, 120) })
    await shot('accept-answer')

    // The workspace surface the user reads.
    // #71: the Files row lives in the closed "Tools & Capabilities" tier.
    await openTier(page, 'tools')
    const filesBtn = page.getByTestId('sidebar-action-files')
    if ((await filesBtn.count()) > 0) {
      await filesBtn.click({ timeout: 10_000 }).catch(() => {})
      await page.waitForTimeout(1_800)
      const panel = page.getByRole('tabpanel').first()
      const txt = await panel.innerText({ timeout: 10_000 }).catch(() => '')
      facts.filesPanelListsFile = txt.includes(FILE_NAME)
      await shot('files-panel')
    }

    // The file's own content, straight from the server, as a screenshot.
    await page.goto(`${BASE}/api/file?path=${encodeURIComponent(FILE_NAME)}`, { waitUntil: 'load' })
    await page.waitForTimeout(600)
    await shot('file-on-disk')
    const diskBody = await page
      .locator('body')
      .innerText()
      .catch(() => '')
    facts.fileOnDiskScreenshotBody = diskBody.slice(0, 200)

    expect(
      plan.postAcceptFileStatus,
      `${FILE_NAME} must exist after the accept (was ${plan.postAcceptFileStatus} = ${baseline.status} before)`,
    ).toBe(200)
    expect(plan.postAcceptFileText).toContain(FILE_CONTENT)
    expect(acceptTurn.endReason).not.toBe('deadline')
    expect(plan.acceptTurn?.freshBubble, 'Accept must have started a real turn').toBe(true)
  } finally {
    // The composer mode is a session attribute on a shared server — put it back.
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' }).catch(() => {})
    await page
      .locator(CHAT_INPUT)
      .waitFor({ timeout: 20_000 })
      .catch(() => {})
    await page.waitForTimeout(1_000)
    const restored = await pickMode(page, async () => {}, DEFAULT_MODE).catch(() => '')
    facts.restoredChip = restored
    facts.restoredToDefault = restored.toLowerCase().includes(DEFAULT_CHIP)
    trace('restored', { chip: restored })
    saveObs(facts)
    console.log(`PLAN-ACCEPT >>>\n${JSON.stringify(facts, null, 2)}\n<<<`)
  }
})
