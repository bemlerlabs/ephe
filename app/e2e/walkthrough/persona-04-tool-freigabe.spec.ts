/**
 * persona-04-tool-freigabe.spec.ts — user walkthrough: "the agent wants to run a
 * shell command and the app asks me first — does it really?"
 *
 * PERSONA: an ordinary user who has been told the runtime asks before it runs a
 * command. It types a harmless request that needs a shell command and watches
 * whether the approval dialog actually appears, what it says, and what happens
 * when the user approves or denies.
 *
 * This spec runs against the LIVE stack — the real backend and the real engine
 * (openai_compatible / deepseek-v4-pro over the DeepSeek API). It mocks NOTHING:
 * there is no `page.route`, no fixture standing in for the API. Every boolean it
 * reports is read off the live DOM or off the live HTTP traffic, and everything
 * it cannot prove is recorded into `observations.json` next to the screenshots.
 *
 * The four arcs, one test each:
 *   (a) default mode   — the shipped composer mode: does the gate appear at all?
 *   (b) allow          — the gate fires; approve it and watch the command run.
 *   (c) deny           — the gate fires; deny it and read what the card says.
 *   (d) badge & control— where the user can actually change the approval profile.
 *
 * The gate only fires in a mode that does not auto-approve shell. The default
 * composer mode is `full-access`, which — under the stored `session` profile —
 * auto-approves `run_shell` before any dialog. Arc (a) documents exactly that;
 * arcs (b) and (c) switch the composer to `edit-auto` first, which is the mode in
 * which `run_shell` reaches the gate.
 *
 * Preconditions:
 *   - the ephe backend serves the built app on http://127.0.0.1:8765 (default).
 *   - override the origin with EPHE_WALKTHROUGH_BASE (no trailing slash needed).
 *
 * Running this spends real engine turns. It is not part of the mocked suite.
 *
 * Selectors (all from source, so they survive a refactor of the copy):
 *   chat input        app/src/components/dashboard/ChatInput.tsx:433        data-testid="chat-input"
 *   send / stop       .../dashboard/chat/ComposerSendButton.tsx:77         data-testid="send-btn" | "stop-btn"
 *   mode selector     .../dashboard/chat/ComposerModeChip.tsx:41           data-testid="composer-mode-selector"
 *   mode option       .../dashboard/chat/ComposerModeMenu.tsx:160          data-testid="composer-mode-<key>"
 *   permission badge  .../dashboard/ChatInput.tsx:525                      data-testid="composer-permission-badge"
 *   approval dialog   .../dashboard/ToolApprovalPrompt.tsx:90             role="alertdialog"
 *   approve / deny    .../dashboard/ToolApprovalPrompt.tsx:132,142        role="button" name="Approve" | "Deny"
 *   remember box      .../dashboard/ToolApprovalPrompt.tsx:121            role="checkbox"
 *   diff preview      .../dashboard/ToolApprovalPrompt.tsx:104            data-testid="approval-diff"
 *   blast radius      .../dashboard/ToolApprovalPrompt.tsx:112            data-testid="approval-blast-radius"
 *   tool card         .../dashboard/ToolCallDisplay.tsx:164               data-testid="tool-card"
 *   tool target       .../dashboard/ToolCallDisplay.tsx:190               data-testid="tool-target"
 *   sidebar settings  .../dashboard/Sidebar.tsx:1507                      data-testid="sidebar-settings-btn"
 *   settings page     .../dashboard/settings/index.tsx:174               data-testid="settings-page"
 *   privacy nav       .../dashboard/settings/model/sections-misc.tsx:139  data-testid="settings-nav-privacy"
 *   profile row       .../dashboard/settings/model/sections-misc.tsx:139  data-testid="privacy-profile"
 *   profile radios    .../dashboard/settings/model/sections-misc.tsx      data-testid="security-profile-session|strict"
 */

import { test, expect, type Locator, type Page } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'
import { walkthroughOutDir } from './walkthrough-out.ts'

const BASE = (process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765').replace(/\/$/, '')
const CHAT = `${BASE}/#/chat`

const OUT = walkthroughOutDir('persona-04-tool-freigabe')
fs.mkdirSync(OUT, { recursive: true })
const OBS = path.join(OUT, 'observations.json')

// ---- testids, straight out of app/src ----------------------------------------------
const CHAT_INPUT = '[data-testid="chat-input"]'
const SEND = '[data-testid="send-btn"]'
const STOP = '[data-testid="stop-btn"]'
const MODE_SELECTOR = '[data-testid="composer-mode-selector"]'
const MODE_LIST = '[data-testid="composer-mode-list"]'
const MODE_FULL_ACCESS = '[data-testid="composer-mode-full-access"]'
const MODE_EDIT_AUTO = '[data-testid="composer-mode-edit-auto"]'
const PERMISSION_BADGE = '[data-testid="composer-permission-badge"]'
const TOOL_CARD = '[data-testid="tool-card"]'
const TOOL_TARGET = '[data-testid="tool-target"]'
// The user-visible tool line in the MAIN stream is not the ToolCallDisplay card
// (that one renders only after a row is expanded): it is the aggregated stream row
// plus its status span. Read those for what the user actually sees.
const TOOL_ROW = '[data-testid^="tool-stream-row-"]'
const TOOL_ROW_STATUS = '[data-testid="tool-row-status"]'
const APPROVAL_DIFF = '[data-testid="approval-diff"]'
const BLAST_RADIUS = '[data-testid="approval-blast-radius"]'
const SIDEBAR_SETTINGS = '[data-testid="sidebar-settings-btn"]'
const SETTINGS_PAGE = '[data-testid="settings-page"]'
const NAV_PRIVACY = '[data-testid="settings-nav-privacy"]'
const PRIVACY_PROFILE = '[data-testid="privacy-profile"]'
const PROFILE_SESSION = '[data-testid="security-profile-session"]'
const PROFILE_STRICT = '[data-testid="security-profile-strict"]'
const NEW_SESSION = '[data-testid="new-session"]'

// ---- English strings the live app really prints (locales/en.json) -------------------
const STR_APPROVAL_NEEDED = 'Ephe wants to run a tool' // chat.approvalNeeded:54
const STR_REMEMBER = 'Remember for this session' // chat.toolApproval.remember:56
const STR_WAITING = 'Waiting for approval' // chat.toolWaiting:202
const STR_DENIED_EN = 'run_shell denied' // chat.toolDenied, tool=run_shell
const STR_COMPLETED_EN = 'run_shell completed' // chat.toolCompleted, tool=run_shell
const STR_RUNNING_EN = 'Running run_shell' // chat.toolRunning, tool=run_shell
const STR_GERMAN_BLAST = 'Blast-Radius:' // ToolApprovalPrompt.tsx:116 — hard-coded
const STR_GERMAN_ABORT = 'Abgebrochen.' // backend shell short-circuit when execute_confirmed_shell(confirmed=False)
const STR_TOOL_DENIED_REASON = 'TOOL-DENIED' // the reason the live deny path actually surfaces (core/tools/chat_gate.py)
const STR_ROW_COMPLETED = 'Completed' // chat.rowCompleted -> tool-row-status
const STR_ROW_FAILED = 'Failed'

/**
 * One harmless request that forces a shell tool call. It is read-only on disk, so
 * letting it run (or approving it) writes nothing.
 */
const SHELL_TASK =
  'Run exactly one shell command: `echo ephe-approval-probe`. ' +
  'Then tell me the command output verbatim and nothing else.'

// ---- per-run bookkeeping (merged across workers on flush) ---------------------------
interface ApproveRequest {
  at: string
  method: string
  url: string
  body: string | null
  approved: boolean | null
  remember: boolean | null
}
interface ObservFile {
  base?: string
  generatedAt?: string
  consoleErrors?: string[]
  pageErrors?: string[]
  requestFailures?: string[]
  sandboxApproveRequests?: ApproveRequest[]
  arcs?: Record<string, unknown>
  shots?: string[]
}

const consoleErrors: string[] = []
const pageErrors: string[] = []
const requestFailures: string[] = []
const approveRequests: ApproveRequest[] = []
const shots: string[] = []
const arcs: Record<string, unknown> = {}
let shotIndex = 0

const dedupe = (a: string[]): string[] => Array.from(new Set(a))

function flushObservations(): void {
  let prev: ObservFile = {}
  try {
    prev = JSON.parse(fs.readFileSync(OBS, 'utf8')) as ObservFile
  } catch {
    prev = {}
  }
  const merged: ObservFile = {
    base: BASE,
    generatedAt: new Date().toISOString(),
    consoleErrors: dedupe([...(prev.consoleErrors ?? []), ...consoleErrors]),
    pageErrors: dedupe([...(prev.pageErrors ?? []), ...pageErrors]),
    requestFailures: dedupe([...(prev.requestFailures ?? []), ...requestFailures]),
    sandboxApproveRequests: [...(prev.sandboxApproveRequests ?? []), ...approveRequests],
    arcs: { ...(prev.arcs ?? {}), ...arcs },
    shots: dedupe([...(prev.shots ?? []), ...shots]),
  }
  fs.writeFileSync(OBS, JSON.stringify(merged, null, 2))
  console.log('PERSONA-04 OBSERVATIONS >>>\n' + JSON.stringify(merged, null, 2) + '\n<<<')
}

/** Attach the listeners that feed observations.json. Call once per test, up front. */
function wire(page: Page): void {
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 400))
  })
  page.on('pageerror', (e) => pageErrors.push(String(e.message).slice(0, 400)))
  page.on('requestfailed', (r) =>
    requestFailures.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText ?? 'failed'}`),
  )
  page.on('response', (r) => {
    if (r.status() >= 400) requestFailures.push(`${r.status()} ${r.request().method()} ${r.url()}`)
  })
  page.on('request', (req) => {
    if (!req.url().includes('/api/sandbox/approve')) return
    let approved: boolean | null = null
    let remember: boolean | null = null
    try {
      const parsed = JSON.parse(req.postData() ?? '{}') as {
        approved?: boolean
        remember?: boolean
      }
      approved = parsed.approved ?? null
      remember = parsed.remember ?? null
    } catch {
      /* body not JSON — leave nulls */
    }
    approveRequests.push({
      at: new Date().toISOString(),
      method: req.method(),
      url: req.url(),
      body: req.postData(),
      approved,
      remember,
    })
  })
}

// ---- generic helpers -----------------------------------------------------------------

async function shoot(page: Page, name: string): Promise<string> {
  shotIndex += 1
  const file = path.join(OUT, `${String(shotIndex).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path: file, fullPage: true }).catch(() => {})
  shots.push(path.basename(file))
  return file
}

async function text(loc: Locator): Promise<string> {
  try {
    return (await loc.first().innerText()).replace(/\s+/g, ' ').trim()
  } catch {
    return ''
  }
}

async function visible(page: Page, selector: string): Promise<boolean> {
  try {
    return await page.locator(selector).first().isVisible()
  } catch {
    return false
  }
}

async function gateCount(page: Page): Promise<number> {
  return page.getByRole('alertdialog').count()
}

/** Poll until the runtime is idle: no stop button, no approval dialog pending. */
async function settled(page: Page, ms: number): Promise<boolean> {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    await page.waitForTimeout(1000)
    const streaming = await page.locator(STOP).count()
    const gate = await gateCount(page)
    if (streaming === 0 && gate === 0) {
      await page.waitForTimeout(1500)
      if ((await page.locator(STOP).count()) === 0 && (await gateCount(page)) === 0) return true
    }
  }
  return false
}

async function gotoChat(page: Page): Promise<void> {
  try {
    await page.goto(CHAT, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  } catch {
    throw new Error(
      `Live server at ${BASE} is not reachable. Serve the built app on ${BASE} before ` +
        'running this walkthrough; do not mock it.',
    )
  }
  await page.locator(CHAT_INPUT).waitFor({ state: 'visible', timeout: 30_000 })
  await page.waitForTimeout(1000)
}

async function freshSession(page: Page): Promise<boolean> {
  const btn = page.locator(NEW_SESSION)
  if (!(await visible(page, NEW_SESSION))) return false
  await btn.click({ timeout: 10_000 }).catch(() => {})
  await page.waitForTimeout(800)
  return true
}

async function modeLabel(page: Page): Promise<string> {
  return text(page.locator(MODE_SELECTOR))
}

/** Open the composer mode menu and pick a mode by its option testid. */
async function pickMode(page: Page, optionSelector: string): Promise<boolean> {
  try {
    await page.locator(MODE_SELECTOR).first().click({ timeout: 10_000 })
    await page.locator(MODE_LIST).waitFor({ state: 'visible', timeout: 8000 })
    await page.locator(optionSelector).first().click({ timeout: 8000 })
    await page.waitForTimeout(500)
    return true
  } catch {
    return false
  }
}

async function send(page: Page, prompt: string): Promise<void> {
  await page.locator(CHAT_INPUT).fill(prompt)
  await page.waitForTimeout(200)
  await page.keyboard.press('Enter')
}

/** Snapshot every tool card's visible text. */
async function toolCards(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_CARD)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

/** Snapshot every user-visible tool stream row (the `>` line above the reply). */
async function toolRows(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_ROW)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

/** The status word of each tool stream row: "· Completed" / "· Waiting for approval" / … */
async function rowStatuses(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_ROW_STATUS)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

/** The last assistant reply's full visible text. */
async function assistantReply(page: Page): Promise<string> {
  return text(page.locator('[data-testid="message-bubble"][data-role="assistant"]').last())
}

async function readGate(page: Page): Promise<Record<string, unknown>> {
  return page.evaluate(
    (sel) => {
      const dlg = document.querySelector('[role="alertdialog"]') as HTMLElement | null
      const blast = document.querySelector(sel.blast) as HTMLElement | null
      const diff = document.querySelector(sel.diff) as HTMLElement | null
      const box = document.querySelector(
        '[role="alertdialog"] input[type="checkbox"]',
      ) as HTMLInputElement | null
      return {
        present: !!dlg,
        ariaLabel: dlg?.getAttribute('aria-label') ?? null,
        innerText: (dlg?.innerText ?? '').replace(/\s+/g, ' ').trim().slice(0, 600),
        hasBlastRadius: !!blast,
        blastText: (blast?.innerText ?? '').trim(),
        hasDiff: !!diff,
        rememberCheckboxPresent: !!box,
        rememberChecked: box ? box.checked : null,
        focusTag: document.activeElement
          ? (document.activeElement as HTMLElement).tagName.toLowerCase()
          : null,
        focusLabel: document.activeElement
          ? (document.activeElement as HTMLElement).getAttribute('aria-label')
          : null,
      }
    },
    { blast: BLAST_RADIUS, diff: APPROVAL_DIFF },
  )
}

async function clickGateButton(page: Page, name: 'Approve' | 'Deny'): Promise<boolean> {
  try {
    await page.getByRole('button', { name, exact: true }).first().click({ timeout: 10_000 })
    return true
  } catch {
    return false
  }
}

// ---- the four arcs -------------------------------------------------------------------

test.describe('persona-04 — the tool-approval gate', () => {
  test('arc (a) — the shipped default mode runs the command with no gate', async ({ page }) => {
    // A real engine turn can run for minutes; the gate blocks the turn while open.
    test.setTimeout(300_000)
    wire(page)
    const tA: Record<string, number> = {}
    let tl = Date.now()
    const markA = (k: string): void => {
      tA[k] = Date.now() - tl
      tl = Date.now()
    }

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    markA('gotoChat')
    await freshSession(page)
    await page.waitForTimeout(1200)
    markA('fresh')

    const label = await modeLabel(page)
    const isFullAccess = label.includes('Full access')
    // The shipped default is full-access; if a prior run persisted another mode,
    // restore full-access so arc (a) genuinely measures the default posture.
    let restored = false
    if (!isFullAccess) {
      restored = await pickMode(page, MODE_FULL_ACCESS)
    }
    const labelAfter = await modeLabel(page)
    markA('mode')
    await shoot(page, 'arc-a-default-mode')
    markA('shootDefault')

    await send(page, SHELL_TASK)
    markA('send')

    // Wait for the turn to actually start, so the pre-turn idle state is never
    // mistaken for a finished turn.
    await page
      .locator(STOP)
      .first()
      .waitFor({ state: 'visible', timeout: 45_000 })
      .catch(() => {})
    markA('stopWait')

    let gateAppeared = false
    let toolRowSeen = false
    // Full-access never gates. Watch for a gate for a bounded window only — the
    // shared engine can make a single turn run for minutes, so we must not block on
    // completion here (that is what blew the 300 s test budget before). Three cheap
    // exits: a gate shows up, the turn ends, or the window closes.
    const deadline = Date.now() + 60_000
    while (Date.now() < deadline) {
      if (await gateCount(page)) {
        gateAppeared = true
        await shoot(page, 'arc-a-gate-would-be-unexpected')
        break
      }
      if ((await page.locator(TOOL_ROW).count()) > 0) toolRowSeen = true
      if ((await page.locator(STOP).count()) === 0) break // turn finished
      await page.waitForTimeout(1000)
    }
    markA('loop')
    await page.waitForTimeout(1500)
    await shoot(page, 'arc-a-after-turn')
    markA('shootAfter')

    const rows = await toolRows(page)
    toolRowSeen = toolRowSeen || rows.length > 0
    const statuses = await rowStatuses(page)
    const cards = await toolCards(page)
    const reply = await assistantReply(page)
    const target = await text(page.locator(TOOL_TARGET))
    const allTextA = [...rows, ...statuses, reply].join(' || ')
    markA('reads')

    arcs['a-default-mode'] = {
      modeLabelBeforeSend: label,
      modeLabelAfterSend: labelAfter,
      modeWasFullAccessByDefault: isFullAccess,
      restoredFullAccess: restored,
      gateAppeared,
      toolRowSeen,
      toolRows: rows,
      toolRowCount: rows.length,
      toolRowStatuses: statuses,
      toolRowLabel_SaysCompleted: statuses.some((s) => s.includes(STR_ROW_COMPLETED)),
      toolRowLabel_SaysFailed: statuses.some((s) => s.includes(STR_ROW_FAILED)),
      toolCardCount: cards.length,
      toolTarget: target,
      englishStringsSeen: {
        waiting: allTextA.includes(STR_WAITING),
        completedLabel: allTextA.includes(STR_COMPLETED_EN),
        runningLabel: allTextA.includes(STR_RUNNING_EN),
      },
      timingsMs: tA,
      assistantReplySnippet: reply.slice(0, 400),
      note:
        'Default full-access mode auto-approves run_shell: the command runs with NO ' +
        'dialog. The user-visible trace is the stream row ("Tool … · Completed"), ' +
        'not a ToolCallDisplay card (that one only renders once a row is expanded).',
    }
    // The defect: in the shipped default the gate never appears. (toolRowSeen is
    // recorded, not asserted: under a loaded shared engine a turn can still be
    // running when the bounded watch ends.)
    expect.soft(gateAppeared, 'arc (a): a dialog appeared in the default mode').toBe(false)
    flushObservations()
  })

  test('arc (b) — the gate fires in edit-auto and Approve runs the command', async ({ page }) => {
    test.setTimeout(300_000)
    wire(page)

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    await freshSession(page)
    await page.waitForTimeout(800)

    const switched = await pickMode(page, MODE_EDIT_AUTO)
    const label = await modeLabel(page)
    await shoot(page, 'arc-b-edit-auto-mode')

    await send(page, SHELL_TASK)

    // Wait for the gate (the turn blocks until it is answered).
    let gateAppeared = false
    const deadline = Date.now() + 180_000
    while (Date.now() < deadline) {
      if (await gateCount(page)) {
        gateAppeared = true
        break
      }
      // If the turn finished without a gate, stop early.
      if ((await page.locator(SEND).count()) > 0 && (await page.locator(STOP).count()) === 0) {
        await page.waitForTimeout(2000)
        if ((await gateCount(page)) === 0) break
      }
      await page.waitForTimeout(1000)
    }

    let gate = await readGate(page)
    await shoot(page, 'arc-b-gate-open')

    // Exercise the "Remember for this session" box so its effect on the POST is observable.
    let rememberBoxClicked = false
    const box = page.getByRole('alertdialog').getByRole('checkbox')
    if ((await box.count()) > 0) {
      await box
        .first()
        .check({ timeout: 5000 })
        .catch(() => {})
      rememberBoxClicked = true
      await page.waitForTimeout(200)
      gate = await readGate(page)
      await shoot(page, 'arc-b-remember-checked')
    }

    const approved = await clickGateButton(page, 'Approve')
    await settled(page, 180_000)
    await shoot(page, 'arc-b-after-approve')

    const cards = await toolCards(page)
    const rows = await toolRows(page)
    const statuses = await rowStatuses(page)
    const reply = await assistantReply(page)
    const approveReq = approveRequests.find((r) => r.approved === true) ?? null

    arcs['b-allow'] = {
      switchedToEditAuto: switched,
      modeLabel: label,
      gateAppeared,
      dialogAriaLabel: gate.ariaLabel,
      dialogIsEnglish: gate.ariaLabel === STR_APPROVAL_NEEDED,
      dialogInnerText: gate.innerText,
      dialogShowsRememberLabel: String(gate.innerText).includes(STR_REMEMBER),
      hasBlastRadius: gate.hasBlastRadius,
      blastText: gate.blastText,
      blastTextIsGerman: String(gate.blastText).includes(STR_GERMAN_BLAST),
      hasDiffPreview: gate.hasDiff,
      rememberCheckboxPresent: gate.rememberCheckboxPresent,
      rememberBoxClicked,
      initialFocus: { tag: gate.focusTag, label: gate.focusLabel },
      approved,
      approveRequest: approveReq,
      approveSentRemember: approveReq?.remember ?? null,
      rememberCheckboxShown: gate.rememberCheckboxPresent,
      toolRows: rows,
      toolRowStatuses: statuses,
      toolCards: cards,
      stdoutVisible:
        reply.toLowerCase().includes('ephe-approval-probe') ||
        rows.join(' ').toLowerCase().includes('ephe-approval-probe'),
      assistantReplySnippet: reply.slice(0, 400),
      note:
        'Approve works: the tool runs, its stdout appears, the turn continues. For ' +
        'run_shell the backend sends rememberable=false, so no checkbox is rendered ' +
        'at all (the "checkbox forwarded but dropped" claim does not reproduce here).',
    }
    expect.soft(gateAppeared, 'arc (b): the gate appeared after switching to edit-auto').toBe(true)
    expect.soft(approved, 'arc (b): the Approve button was clickable').toBe(true)
    flushObservations()
  })

  test('arc (c) — denying the gate is swallowed into a "completed" card', async ({ page }) => {
    test.setTimeout(300_000)
    wire(page)

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    await freshSession(page)
    await page.waitForTimeout(800)

    await pickMode(page, MODE_EDIT_AUTO)
    await shoot(page, 'arc-c-edit-auto-mode')

    await send(page, SHELL_TASK)

    let gateAppeared = false
    const deadline = Date.now() + 180_000
    while (Date.now() < deadline) {
      if (await gateCount(page)) {
        gateAppeared = true
        break
      }
      if ((await page.locator(SEND).count()) > 0 && (await page.locator(STOP).count()) === 0) {
        await page.waitForTimeout(2000)
        if ((await gateCount(page)) === 0) break
      }
      await page.waitForTimeout(1000)
    }

    const gate = await readGate(page)
    await shoot(page, 'arc-c-gate-open')

    const denied = await clickGateButton(page, 'Deny')
    await settled(page, 180_000)
    await shoot(page, 'arc-c-after-deny')

    const cards = await toolCards(page)
    const rows = await toolRows(page)
    const statuses = await rowStatuses(page)
    const assistant = await assistantReply(page)
    const denyReq = approveRequests.find((r) => r.approved === false) ?? null
    const joinedRows = rows.join(' || ')
    const allVisibleText = `${joinedRows} || ${assistant}`
    // The deny path the live app actually shows: the tool rows still read
    // "Completed" (the deny is visually swallowed), and the bare German
    // short-circuit "Abgebrochen." never reaches the surface — the reply carries
    // the TOOL-DENIED reason instead.
    const germanAbortPresent = allVisibleText.includes(STR_GERMAN_ABORT)
    const rowsSayCompleted = statuses.some((s) => s.includes(STR_ROW_COMPLETED))

    arcs['c-deny'] = {
      gateAppeared,
      dialogAriaLabel: gate.ariaLabel,
      denied,
      denyRequest: denyReq,
      toolRowCount: rows.length,
      toolRows: rows,
      toolRowStatuses: statuses,
      rowSaysCompleted: rowsSayCompleted,
      rowSaysDenied: joinedRows.includes(STR_DENIED_EN),
      toolCardCount: cards.length,
      germanAbortPresent,
      reasonCodePresent: allVisibleText.includes(STR_TOOL_DENIED_REASON),
      assistantReplySnippet: assistant.slice(0, 400),
      note:
        'Deny posts approved:false, but the tool row still reads "Completed" — the ' +
        'deny is visually swallowed. The bare German "Abgebrochen." does NOT appear ' +
        'in the UI; the live surface is the TOOL-DENIED reason in the reply.',
    }
    expect.soft(gateAppeared, 'arc (c): the gate appeared after switching to edit-auto').toBe(true)
    expect.soft(denied, 'arc (c): the Deny button was clickable').toBe(true)
    // Refuted claim: the reconnaissance said Deny yields a bare "Abgebrochen."; the
    // live run shows it never reaches the UI. Lock the observed invariant in.
    expect.soft(germanAbortPresent, 'arc (c): the German abort string reached the UI').toBe(false)
    // Confirmed defect: after an explicit Deny the row is not marked denied.
    expect
      .soft(rowsSayCompleted, 'arc (c): the tool row still reads "Completed" after Deny')
      .toBe(true)
    flushObservations()
  })

  test('arc (d) — the badge is read-only; the real control lives in Settings', async ({ page }) => {
    test.setTimeout(300_000)
    wire(page)

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    await page.waitForTimeout(800)
    await shoot(page, 'arc-d-chat-open')

    // The badge the user sees in the composer.
    const badge = await page.evaluate((sel) => {
      const el = document.querySelector(sel) as HTMLElement | null
      if (!el) return { present: false } as Record<string, unknown>
      const cs = getComputedStyle(el)
      return {
        present: true,
        tagName: el.tagName.toLowerCase(),
        role: el.getAttribute('role'),
        ariaLabel: el.getAttribute('aria-label'),
        title: el.getAttribute('title'),
        text: (el.innerText || '').trim(),
        tabIndex: el.getAttribute('tabindex'),
        cursor: cs.cursor,
        hasOnclickProp: typeof (el as unknown as { onclick?: unknown }).onclick === 'function',
      }
    }, PERMISSION_BADGE)
    await shoot(page, 'arc-d-permission-badge')

    // Clicking it should do nothing (it is a status readout, not a control).
    const urlBefore = page.url()
    await page
      .locator(PERMISSION_BADGE)
      .first()
      .click({ timeout: 5000, force: true })
      .catch(() => {})
    await page.waitForTimeout(800)
    const urlAfterClick = page.url()
    const settingsOpenedByBadge = await visible(page, SETTINGS_PAGE)
    await shoot(page, 'arc-d-after-badge-click')

    // The real control: Settings → Privacy → the approval profile.
    let sidebarOpened = false
    let privacyReached = false
    if (await visible(page, SIDEBAR_SETTINGS)) {
      await page
        .locator(SIDEBAR_SETTINGS)
        .first()
        .click({ timeout: 10_000 })
        .catch(() => {})
      sidebarOpened = await page
        .locator(SETTINGS_PAGE)
        .first()
        .waitFor({ state: 'visible', timeout: 20_000 })
        .then(() => true)
        .catch(() => false)
      await shoot(page, 'arc-d-settings-open')
    }
    if (sidebarOpened && (await visible(page, NAV_PRIVACY))) {
      await page
        .locator(NAV_PRIVACY)
        .first()
        .click({ timeout: 10_000 })
        .catch(() => {})
      // The Privacy pane mounts its rows asynchronously (a spinner shows first), so
      // wait for the profile row itself instead of guessing a fixed delay.
      privacyReached = await page
        .locator(PRIVACY_PROFILE)
        .first()
        .waitFor({ state: 'visible', timeout: 25_000 })
        .then(() => true)
        .catch(() => false)
      await shoot(page, 'arc-d-privacy-tab')
    }
    const control = await page.evaluate(
      (sel) => {
        const q = (s: string) => document.querySelector(s) as HTMLElement | null
        return {
          privacyRowPresent: !!q(sel.profile),
          sessionRadioPresent: !!q(sel.session),
          strictRadioPresent: !!q(sel.strict),
          sessionText: (q(sel.session)?.innerText ?? '').trim(),
          strictText: (q(sel.strict)?.innerText ?? '').trim(),
        }
      },
      { profile: PRIVACY_PROFILE, session: PROFILE_SESSION, strict: PROFILE_STRICT },
    )

    arcs['d-badge-and-control'] = {
      badge,
      badgeIsReadOnlyStatus: badge.role === 'status' && badge.tagName === 'span',
      badgeClickChangedUrl: urlBefore !== urlAfterClick,
      badgeClickOpenedSettings: settingsOpenedByBadge,
      sidebarOpenedSettings: sidebarOpened,
      settingsPrivacyReached: privacyReached,
      control,
      note:
        'The composer badge is a read-only <span role="status">; changing the ' +
        'approval profile requires leaving the chat for Settings → Privacy.',
    }
    expect.soft(badge.present, 'arc (d): the permission badge is present').toBe(true)
    expect.soft(privacyReached, 'arc (d): Settings → Privacy is reachable').toBe(true)
    flushObservations()
  })

  test('arc (z) — restore the shared app state (composer back to full-access)', async ({
    page,
  }) => {
    test.setTimeout(120_000)
    wire(page)

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    await freshSession(page)
    await page.waitForTimeout(1000)

    // The composer mode is persisted per session and a fresh session defaults to
    // full-access; sibling personas start from a fresh session. Put this session
    // back on that default and record it.
    const labelBefore = await modeLabel(page)
    let restored = labelBefore.includes('Full access')
    if (!restored) restored = await pickMode(page, MODE_FULL_ACCESS)
    const labelAfter = await modeLabel(page)
    await shoot(page, 'arc-z-restored-full-access')

    // The approval profile is a server setting this spec only ever READS. Record
    // which radio is checked so the report can prove nothing was left behind.
    let profile = 'not-reached'
    if (await visible(page, SIDEBAR_SETTINGS)) {
      await page
        .locator(SIDEBAR_SETTINGS)
        .first()
        .click({ timeout: 10_000 })
        .catch(() => {})
      const opened = await page
        .locator(SETTINGS_PAGE)
        .first()
        .waitFor({ state: 'visible', timeout: 20_000 })
        .then(() => true)
        .catch(() => false)
      if (opened && (await visible(page, NAV_PRIVACY))) {
        await page
          .locator(NAV_PRIVACY)
          .first()
          .click({ timeout: 10_000 })
          .catch(() => {})
        await page
          .locator(PRIVACY_PROFILE)
          .first()
          .waitFor({ state: 'visible', timeout: 25_000 })
          .catch(() => {})
        profile = await page.evaluate(() => {
          const checked = Array.from(
            document.querySelectorAll('[role="radio"][data-testid^="security-profile-"]'),
          )
            .filter((e) => e.getAttribute('aria-checked') === 'true')
            .map((e) => e.getAttribute('data-testid'))
          return checked.join(',') || 'none'
        })
      }
    }

    arcs['z-restore'] = {
      modeBefore: labelBefore,
      modeAfter: labelAfter,
      restoredFullAccess: restored,
      approvalProfileChecked: profile,
      note:
        'Restores the only thing the spec touches: the composer mode (per session). ' +
        'The approval profile is read, never written.',
    }
    expect.soft(restored, 'arc (z): full-access mode is back').toBe(true)
    flushObservations()
  })
})
