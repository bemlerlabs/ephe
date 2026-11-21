/**
 * deny-visible.spec.ts — wave 10 / w10-12: "a deny is visibly swallowed"
 * (docs/media/user-walkthrough-2026-10-12/FINDINGS.md, section "Confirmed — medium").
 *
 * The defect as measured: after the approval dialog is denied, the tool row in the
 * transcript still read "· Completed" — a refusal painted as a success. The cause was
 * one-sided: `app/src/lib/streamActions.ts` wrote `status: 'completed'` for EVERY
 * `tool_done` frame, and `app/src/lib/toolStreamModel.ts` only knew the word `failed`,
 * which no producer ever sent. The refusal's own reason already travelled on the frame
 * (`reason_code`, `core/tools/chat_gate.py`); only the outcome was lost.
 *
 * The fix under test:
 *   server   `server/routes/chat.py` `on_tool_done` sends an explicit
 *            `status: "completed" | "failed"` (failed = a coded result, i.e. `Denied`)
 *   frontend `streamActions.ts` maps `failed` onto the store's existing `denied`
 *            status, `toolStreamModel.ts` reads `denied` as a failure accent.
 *
 * This spec runs against the LIVE stack — the real backend on EPHE_WALKTHROUGH_BASE
 * (default http://127.0.0.1:8765) and the real engine. Nothing is mocked: no
 * `page.route`, no fixture standing in for the API. Every boolean is read off the live
 * DOM or off the live HTTP traffic; what cannot be proven is recorded in
 * `observations.json` next to the screenshots.
 *
 * The arc: switch the composer to `edit-auto` (the mode in which `run_shell` reaches
 * the gate), ask for one shell command, DENY the dialog, then read the transcript.
 *
 * Asserted (hard):
 *   - the deny really happened: a POST /api/sandbox/approve carried approved:false
 *   - the tool row's status word is NOT "Completed" after the turn settled
 *   - the tool row's status word IS "Failed" (the row vocabulary for a call that did not run)
 *   - the expanded card reads the localized refusal ("run_shell denied", chat.toolDenied)
 * Recorded (soft, only if the stream body could be read):
 *   - the raw `tool_done` frame carries status:"failed" and reason_code
 *
 * Selectors (all from source):
 *   chat input        app/src/components/dashboard/ChatInput.tsx           data-testid="chat-input"
 *   send / stop       .../dashboard/chat/ComposerSendButton.tsx            data-testid="send-btn" | "stop-btn"
 *   mode selector     .../dashboard/chat/ComposerModeChip.tsx              data-testid="composer-mode-selector"
 *   mode list/option  .../dashboard/chat/ComposerModeMenu.tsx              data-testid="composer-mode-list" |
 *                                                                         "composer-mode-edit-auto"
 *   new session       .../dashboard/Sidebar.tsx                            data-testid="new-session"
 *   tool stream row   .../dashboard/bubble/toolStreamRows.tsx              data-testid="tool-stream-row-<family>"
 *   row status word   .../dashboard/bubble/toolStreamRows.tsx              data-testid="tool-row-status"
 *   tool card         .../dashboard/ToolCallDisplay.tsx                    data-testid="tool-card"
 *   approval dialog   .../dashboard/ToolApprovalPrompt.tsx                 role="alertdialog"
 *
 * Running this spends a real engine turn. It is not part of the mocked suite.
 */

import { test, expect, type Locator, type Page, type Response } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'
import { walkthroughOutDir } from './walkthrough-out.ts'

const BASE = (process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765').replace(/\/$/, '')
const CHAT = `${BASE}/#/chat`
const STREAM_URL = '/api/chat/stream'

const OUT = walkthroughOutDir('deny-visible')
fs.mkdirSync(OUT, { recursive: true })
const OBS = path.join(OUT, 'observations.json')

// ---- testids, straight out of app/src ----------------------------------------------
const CHAT_INPUT = '[data-testid="chat-input"]'
const SEND = '[data-testid="send-btn"]'
const STOP = '[data-testid="stop-btn"]'
const MODE_SELECTOR = '[data-testid="composer-mode-selector"]'
const MODE_LIST = '[data-testid="composer-mode-list"]'
const MODE_EDIT_AUTO = '[data-testid="composer-mode-edit-auto"]'
const NEW_SESSION = '[data-testid="new-session"]'
const TOOL_ROW = 'div[data-testid^="tool-stream-row-"]'
const TOOL_ROW_STATUS = '[data-testid="tool-row-status"]'
// The row for the shell family specifically: the turn may legitimately call other
// tools (those rows may honestly read "Completed"), so the defect assertion is scoped
// to the row the denial belongs to.
const SHELL_ROW = '[data-testid="tool-stream-row-shell"]'
const SHELL_STATUS = `${SHELL_ROW} [data-testid="tool-row-status"]`
const SHELL_CARD = `${SHELL_ROW} [data-testid="tool-card"]`
const TOOL_CARD = '[data-testid="tool-card"]'

// ---- English strings the live app really prints (locales/en.json) -------------------
const STR_ROW_COMPLETED = 'Completed' // chat.rowCompleted -> tool-row-status
const STR_ROW_FAILED = 'Failed' // chat.rowFailed -> tool-row-status
const STR_DENIED_EN = 'run_shell denied' // chat.toolDenied, tool=run_shell

/** One harmless request that forces exactly one shell call. Read-only on disk. */
const SHELL_TASK =
  'Run exactly one shell command: `echo ephe-deny-visible-probe`. ' +
  'Call the run_shell tool directly — do not search for tools first. ' +
  'Then tell me the command output verbatim and nothing else.'

/** Mirrors app/src/lib/format.ts fmtMs (the duration chip the row renders). */
function fmtMsToken(ms: number | undefined): string {
  if (ms === undefined) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 10000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 1000).toFixed(1)}s`
}

interface ApproveRequest {
  at: string
  method: string
  url: string
  body: string | null
  approved: boolean | null
}
interface ToolDoneFrame {
  tool?: string
  status?: string
  reason_code?: string
  reason_params?: Record<string, unknown>
  duration_ms?: number
  result?: string
}
interface ObservFile {
  base?: string
  generatedAt?: string
  consoleErrors?: string[]
  pageErrors?: string[]
  requestFailures?: string[]
  sandboxApproveRequests?: ApproveRequest[]
  arc?: Record<string, unknown>
  shots?: string[]
}

const consoleErrors: string[] = []
const pageErrors: string[] = []
const requestFailures: string[] = []
const approveRequests: ApproveRequest[] = []
const shots: string[] = []
let shotIndex = 0

const dedupe = (a: string[]): string[] => Array.from(new Set(a))

function flushObservations(arc: Record<string, unknown>): void {
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
    arc: { ...(prev.arc ?? {}), ...arc },
    shots: dedupe([...(prev.shots ?? []), ...shots]),
  }
  fs.writeFileSync(OBS, JSON.stringify(merged, null, 2))
  console.log('DENY-VISIBLE OBSERVATIONS >>>\n' + JSON.stringify(merged, null, 2) + '\n<<<')
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
    if ((await page.locator(STOP).count()) === 0 && (await gateCount(page)) === 0) {
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
  if (!(await visible(page, NEW_SESSION))) return false
  await page
    .locator(NEW_SESSION)
    .click({ timeout: 10_000 })
    .catch(() => {})
  await page.waitForTimeout(800)
  return true
}

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

/** The status word of each tool stream row: "· Completed" / "· Failed" / … */
async function rowStatuses(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_ROW_STATUS)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

async function rowTexts(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_ROW)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

/** The colour class of the row's status word — the accent a user actually sees. */
async function rowStatusColors(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_ROW_STATUS)
    .evaluateAll((els) => els.map((e) => (e as HTMLElement).className))
}

async function toolCardTexts(page: Page): Promise<string[]> {
  return page
    .locator(TOOL_CARD)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLElement).innerText || '').replace(/\s+/g, ' ').trim()),
    )
}

async function assistantReply(page: Page): Promise<string> {
  return text(page.locator('[data-testid="message-bubble"][data-role="assistant"]').last())
}

/** Parse every `tool_done` frame out of a captured SSE body. */
function toolDoneFrames(sse: string): ToolDoneFrame[] {
  const out: ToolDoneFrame[] = []
  for (const line of sse.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed.startsWith('data:')) continue
    const payload = trimmed.slice('data:'.length).trim()
    if (!payload.includes('tool_done')) continue
    try {
      const parsed = JSON.parse(payload) as { type?: string } & ToolDoneFrame
      if (parsed.type === 'tool_done') out.push(parsed)
    } catch {
      /* partial or non-JSON data line — skip */
    }
  }
  return out
}

test.describe('w10-12 — a denied tool call is a visible refusal', () => {
  test('arc — deny the approval gate: the transcript row reads a refusal, not "Completed"', async ({
    page,
  }) => {
    test.setTimeout(420_000)

    // ---- wiring: observations + the raw SSE body of the turn ------------------------
    const captured: { stream: Response | null } = { stream: null }
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 400))
    })
    page.on('pageerror', (e) => pageErrors.push(String(e.message).slice(0, 400)))
    page.on('requestfailed', (r) =>
      requestFailures.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText ?? 'failed'}`),
    )
    page.on('response', (r) => {
      if (r.status() >= 400)
        requestFailures.push(`${r.status()} ${r.request().method()} ${r.url()}`)
      if (r.url().includes(STREAM_URL) && r.request().method() === 'POST') captured.stream = r
    })
    page.on('request', (req) => {
      if (!req.url().includes('/api/sandbox/approve')) return
      let approved: boolean | null = null
      try {
        approved = (JSON.parse(req.postData() ?? '{}') as { approved?: boolean }).approved ?? null
      } catch {
        /* body not JSON — leave null */
      }
      approveRequests.push({
        at: new Date().toISOString(),
        method: req.method(),
        url: req.url(),
        body: req.postData(),
        approved,
      })
    })

    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })
    await gotoChat(page)
    await freshSession(page)
    await page.waitForTimeout(800)
    await shoot(page, 'chat-open')

    // edit-auto is the mode in which run_shell still reaches the gate.
    const modePicked = await pickMode(page, MODE_EDIT_AUTO)
    const modeLabel = await text(page.locator(MODE_SELECTOR))
    await shoot(page, 'edit-auto-mode')

    await send(page, SHELL_TASK)
    await page
      .locator(STOP)
      .first()
      .waitFor({ state: 'visible', timeout: 60_000 })
      .catch(() => {})

    // ---- wait for the gate (bounded: the turn may end instead) ----------------------
    let gateAppeared = false
    let statusBeforeDeny: string[] = []
    const deadline = Date.now() + 240_000
    while (Date.now() < deadline) {
      if (await gateCount(page)) {
        gateAppeared = true
        break
      }
      if ((await page.locator(SEND).count()) > 0 && (await page.locator(STOP).count()) === 0) {
        await page.waitForTimeout(2500)
        if ((await gateCount(page)) === 0) break
      }
      await page.waitForTimeout(1000)
    }
    statusBeforeDeny = await rowStatuses(page)
    await shoot(page, 'gate-open')

    // ---- deny -----------------------------------------------------------------------
    let denyClicked = false
    try {
      await page
        .getByRole('button', { name: 'Deny', exact: true })
        .first()
        .click({ timeout: 10_000 })
      denyClicked = true
    } catch {
      denyClicked = false
    }
    await page.waitForTimeout(1200)
    const statusRightAfterDenyClick = await rowStatuses(page)

    const settledOk = await settled(page, 300_000)
    await shoot(page, 'after-deny-settled')

    // ---- read the transcript --------------------------------------------------------
    const statuses = await rowStatuses(page)
    const rows = await rowTexts(page)
    const colors = await rowStatusColors(page)
    const joinedRows = rows.join(' || ')
    const rowSaysCompleted = statuses.some((s) => s.includes(STR_ROW_COMPLETED))
    const rowSaysFailed = statuses.some((s) => s.includes(STR_ROW_FAILED))
    const rowRed = colors.some((c) => c.includes('status-danger'))

    // The row the denial belongs to, read on its own.
    const shellStatusWord = await text(page.locator(SHELL_STATUS))
    const shellStatusClass = await page
      .locator(SHELL_STATUS)
      .first()
      .evaluate((e) => (e as HTMLElement).className)
      .catch(() => '')

    // Expand the tool row so the per-call card (ToolCallDisplay) is in the DOM.
    let expanded = false
    try {
      await page
        .locator(SHELL_ROW)
        .first()
        .locator('button[aria-expanded]')
        .first()
        .click({ timeout: 8000 })
      await page.locator(SHELL_CARD).first().waitFor({ state: 'visible', timeout: 8000 })
      expanded = true
    } catch {
      expanded = false
    }
    const cards = await toolCardTexts(page)
    const shellCardText = await text(page.locator(SHELL_CARD))
    const cardSaysDenied =
      cards.some((c) => c.includes(STR_DENIED_EN)) || shellCardText.includes(STR_DENIED_EN)
    await shoot(page, 'row-expanded-card')

    const assistant = await assistantReply(page)
    const denyReq = approveRequests.find((r) => r.approved === false) ?? null

    // ---- the raw frame: what the server actually sent -------------------------------
    let sseText = ''
    const streamResponse = captured.stream
    if (streamResponse) {
      try {
        sseText = await Promise.race([
          streamResponse.text(),
          new Promise<string>((res) => setTimeout(() => res(''), 20_000)),
        ])
      } catch {
        sseText = ''
      }
    }
    const frames = toolDoneFrames(sseText)
    const failedFrames = frames.filter((f) => f.status === 'failed')
    const completedFrames = frames.filter((f) => f.status === 'completed')
    const shellFrame = frames.find((f) => f.tool === 'run_shell') ?? null
    // The refused call, identified in the transcript by its own duration chip: the row
    // the denial belongs to must read a refusal. This holds whether the model called
    // run_shell directly or reached it through the tool_call bridge.
    const refusedRows = failedFrames.map((f) => {
      const token = fmtMsToken(f.duration_ms)
      const row = token !== '' ? (rows.find((r) => r.includes(token)) ?? null) : null
      return {
        tool: f.tool ?? null,
        durationToken: token,
        row,
        rowReadsRefusal:
          row !== null && row.includes(STR_ROW_FAILED) && !row.includes(STR_ROW_COMPLETED),
      }
    })
    const completedRowCount = statuses.filter((s) => s.includes(STR_ROW_COMPLETED)).length
    fs.writeFileSync(path.join(OUT, 'tool_done-frames.json'), JSON.stringify(frames, null, 2))
    if (sseText) fs.writeFileSync(path.join(OUT, 'stream-raw.txt'), sseText)

    flushObservations({
      modePicked,
      modeLabel,
      gateAppeared,
      denyClicked,
      settled: settledOk,
      denyRequest: denyReq,
      toolRows: rows,
      toolRowStatuses: statuses,
      statusBeforeDeny,
      statusRightAfterDenyClick,
      shellRowStatus: shellStatusWord,
      shellRowStatusClass: shellStatusClass,
      shellRowSaysCompleted: shellStatusWord.includes(STR_ROW_COMPLETED),
      shellRowSaysFailed: shellStatusWord.includes(STR_ROW_FAILED),
      rowSaysCompleted,
      rowSaysFailed,
      rowRedAccent: rowRed,
      rowSaysDeniedWord: joinedRows.includes(STR_DENIED_EN),
      rowExpanded: expanded,
      shellCardText,
      toolCardTexts: cards,
      cardSaysDenied,
      sseCaptured: sseText.length > 0,
      toolDoneFrames: frames,
      failedFrames,
      completedFrames,
      shellToolDoneFrame: shellFrame,
      completedRowCount,
      refusedRows,
      assistantReplySnippet: assistant.slice(0, 400),
      note:
        'Deny posts approved:false. Before the fix the transcript row read "· Completed" after ' +
        'the turn settled (the tool_done frame overwrote the local denied status with ' +
        'completed). Now the server sends status:"failed" for a coded result and the row ' +
        'renders a refusal: red accent + "Failed", the expanded card reads "run_shell denied".',
    })

    // ---- assertions -----------------------------------------------------------------
    expect(gateAppeared, 'the approval gate appeared in edit-auto').toBe(true)
    expect(denyClicked, 'the Deny button was clickable').toBe(true)
    expect(denyReq?.approved, 'the deny really reached the server (approved:false)').toBe(false)
    expect(settledOk, 'the turn settled after the deny').toBe(true)
    // The defect: a refusal painted as a success. Scoped to the shell row — a turn may
    // honestly complete other calls, and those rows may keep saying "Completed".
    expect(
      shellStatusWord,
      `the shell row may not read "${STR_ROW_COMPLETED}" after a deny (saw ${JSON.stringify(statuses)})`,
    ).not.toContain(STR_ROW_COMPLETED)
    expect(
      shellStatusWord,
      `the shell row reads "${STR_ROW_FAILED}" (saw ${JSON.stringify(shellStatusWord)})`,
    ).toContain(STR_ROW_FAILED)
    expect(rowSaysFailed, `a row reads "${STR_ROW_FAILED}"`).toBe(true)
    expect(shellStatusClass, 'the shell row status carries the destructive accent').toContain(
      'status-danger',
    )
    expect(expanded, 'the tool row expanded into its per-call card').toBe(true)
    expect(cardSaysDenied, `the card reads "${STR_DENIED_EN}"; saw ${JSON.stringify(cards)}`).toBe(
      true,
    )

    // ---- the server-side half of the chain ------------------------------------------
    // A capture failure is a harness failure, not a product failure — but the chain is
    // only proven end to end when the frame is readable.
    expect.soft(sseText.length, 'the SSE body of the turn was captured').toBeGreaterThan(0)
    expect
      .soft(failedFrames.length, 'the refusal travelled as a tool_done frame with status:"failed"')
      .toBeGreaterThan(0)
    expect
      .soft(failedFrames[0]?.reason_code, 'the refused frame carries its reason code')
      .toBe('not_approved_by_user')
    // The row that belongs to the refused call must read a refusal — this is the row
    // that read "· Completed" before the fix (the refused frame overwrote the local
    // denial with "completed").
    expect
      .soft(refusedRows.length, 'the refused call was matched to a transcript row')
      .toBeGreaterThan(0)
    expect
      .soft(
        refusedRows.every((r) => r.rowReadsRefusal),
        `every refused call's row reads a refusal; saw ${JSON.stringify(refusedRows)}`,
      )
      .toBe(true)
    // A row may only say "Completed" when the server said so: the refused frame may not
    // inflate the Completed count.
    expect
      .soft(
        completedRowCount <= Math.max(completedFrames.length, 0) + (sseText ? 0 : 99),
        `rows reading "Completed" (${completedRowCount}) must not exceed completed frames (${completedFrames.length})`,
      )
      .toBe(true)
  })
})
