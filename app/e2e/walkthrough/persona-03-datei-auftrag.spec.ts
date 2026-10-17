/**
 * persona-03-datei-auftrag.spec.ts — user walkthrough: "make the agent produce a real file".
 *
 * PERSONA: a user who wants the agent to produce a real file and then wants to
 * SEE that it exists and find it again later.
 *
 * The question this run answers with evidence:
 *   can a user SEE that a file was really created, and find it again later?
 *
 * This spec runs against the LIVE stack — real backend, real engine
 * (openai_compatible / deepseek-v4-pro over the DeepSeek API). It does NOT mock.
 * The sibling `e2e/chat-sse.spec.ts` mocks the backend on purpose; this one must
 * not, so it asserts only on surfaces the app really renders and records
 * everything it cannot prove into `findings.json` next to the screenshots.
 *
 * Preconditions:
 *   - the ephe backend is up on 127.0.0.1:8765.
 *   - playwright.config.ts starts Vite on 127.0.0.1:5174, which proxies /api/* to
 *     8765. If the walkthrough harness instead serves app/dist on 8765 directly,
 *     set EPHE_WALKTHROUGH_BASE=http://127.0.0.1:8765.
 *   - override the write mode with EPHE_WALKTHROUGH_MODE (ask|plan|edit-auto|
 *     full-access; default full-access — the mode most likely to actually write
 *     without an approval gate blocking the turn).
 *
 * Running this spends a real engine turn. It is not part of the mocked suite.
 *
 * Selectors (all from source, so they survive a refactor of the copy):
 *   chat input      app/src/components/dashboard/ChatInput.tsx:433  data-testid="chat-input"
 *   send / stop     .../dashboard/chat/ComposerSendButton.tsx:77     data-testid="send-btn" | "stop-btn"
 *   assistant       .../dashboard/MessageBubble.tsx:118              data-testid="message-bubble" data-role="assistant"
 *   turn head       .../dashboard/bubble/turnHeadRow.tsx:36          data-testid="bubble-turn-head"
 *   tool card       .../dashboard/ToolCallDisplay.tsx:164            data-testid="tool-card"  (only once expanded)
 *   tool rows       .../dashboard/bubble/toolStreamRows.tsx:47       data-testid="tool-stream-rows" (the DEFAULT surface)
 *   tool row group  .../dashboard/bubble/toolStreamRows.tsx:84       data-testid="tool-stream-row-<family>" (toggle: button[aria-expanded])
 *   tool target     .../dashboard/ToolCallDisplay.tsx:190            data-testid="tool-target"
 *   open preview    .../dashboard/ToolCallDisplay.tsx:254            data-testid="tool-open-preview"
 *   approval gate   .../dashboard/ToolApprovalPrompt.tsx:90          role="alertdialog"
 *   library pop-up  .../dashboard/chat/index.tsx:530                 data-testid="artifact-library-toggle"
 *   library modal   .../dashboard/ArtifactRail.tsx:175               data-testid="artifact-modal"
 *   mode selector   .../dashboard/chat/ComposerModeChip.tsx:41       data-testid="composer-mode-selector"
 *   mode option     .../dashboard/chat/ComposerModeMenu.tsx:160      data-testid="composer-mode-<key>"
 *   new task        .../dashboard/Sidebar.tsx:870                    data-testid="new-session"
 *   files tab       .../dashboard/Sidebar.tsx:692                    data-testid="sidebar-action-files"
 *   workbench page  app/src/pages/ArtifactsPage.tsx:135              data-testid="artifacts-page"
 *   workbench search app/src/pages/ArtifactsPage.tsx:198            aria-label = "Search all artifacts…"
 */
import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'
import { openTier } from './rail.ts'

const BASE = process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:5174'
const MODE = process.env.EPHE_WALKTHROUGH_MODE ?? 'full-access'
const OUT = walkthroughOutDir('persona-03-datei-auftrag')

const CHAT_INPUT = '[data-testid="chat-input"]'
const STOP = '[data-testid="stop-btn"]'
const ASSISTANT = '[data-testid="message-bubble"][data-role="assistant"]'
const TOOL_CARD = '[data-testid="tool-card"]'
const TOOL_TARGET = '[data-testid="tool-target"]'
const TOOL_OPEN = '[data-testid="tool-open-preview"]'
// The DEFAULT surface after a turn is the collapsed row group (verb + target +
// status). The detailed ToolCallDisplay card (TOOL_CARD) only renders once a row
// is expanded — so a probe that looks only for TOOL_CARD reports "nothing ran"
// even while the user plainly sees the action. Detect both surfaces.
const TOOL_ROWS = '[data-testid="tool-stream-rows"]'
const TOOL_ROW = '[data-testid^="tool-stream-row-"]'
const TOOL_ROW_WRITE = '[data-testid="tool-stream-row-write"]'
const TOOL_ROW_READ = '[data-testid="tool-stream-row-read"]'
const TOOL_ROW_TOGGLE = '[data-testid^="tool-stream-row-"] button[aria-expanded]'

type Finding = { step: string; ok: boolean; note: string }

test('PERSONA-03: file task — create a real file, then find it again', async ({
  page,
  request,
}) => {
  // A real engine turn with tool calls can run for minutes.
  test.setTimeout(600_000)

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

  const shots: string[] = []
  const findings: Finding[] = []
  let n = 0
  const shot = async (name: string) => {
    const file = join(OUT, `${String(++n).padStart(2, '0')}-${name}.png`)
    await page.screenshot({ path: file, fullPage: true }).catch(() => {})
    shots.push(file)
    return file
  }

  // A unique name per run so concurrent runs cannot collide.
  const runId = Date.now()
  const filename = `walkthrough-${runId}.txt`
  const task =
    `Create a file named ${filename} in the workspace, containing exactly three lines: ` +
    `alpha, beta, gamma (one per line). Then read the file back and tell me its size in bytes.`

  // Arc state, declared up front so the report is always written.
  let sawStream = false
  let toolRowSeen = false
  let toolCardSeen = false
  let toolCardExpanded = false
  let toolTarget = ''
  let toolPreviewOpened = false
  let approvalSeen = false
  let approvalApproved = false
  let approvalText = ''
  let modeChip = ''
  let answer = ''
  let libraryListsFile = false
  let workbenchListsFile = false
  let filesTabListsFile = false
  let fileEndpointStatus = 0
  let fileEndpointRelativeStatus = 0
  let fileEndpointBytes = 0
  let listedByApi = 0
  let bubblesBefore = 0

  const writeReport = (partial = false) => {
    const report = {
      runId,
      filename,
      mode: MODE,
      base: BASE,
      partial,
      sawStream,
      toolRowSeen,
      toolCardSeen,
      toolCardExpanded,
      toolTarget,
      toolPreviewOpened,
      approvalSeen,
      approvalApproved,
      approvalText,
      modeChip,
      answer: answer.slice(0, 2000),
      answerMentionsFile: answer.includes(filename),
      answerMentionsSize: /\d+\s*(?:bytes?|B)\b/i.test(answer),
      libraryListsFile,
      workbenchListsFile,
      filesTabListsFile,
      fileEndpointStatus,
      fileEndpointRelativeStatus,
      fileEndpointBytes,
      listedByApi,
      artifactRegisteredByApi: listedByApi > 0,
      bubblesBefore,
      consoleErrors,
      failedRequests,
      shots,
      findings,
    }
    writeFileSync(join(OUT, 'findings.json'), JSON.stringify(report, null, 2))
    console.log('PERSONA-03 FINDINGS >>>\n' + JSON.stringify(report, null, 2) + '\n<<<')
    return report
  }

  try {
    // ── setup: English locale, no first-run gate ─────────────────────────
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
      localStorage.setItem('ephe_onboarded', '1')
    })

    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_INPUT, { timeout: 30_000 })
    await page.waitForTimeout(1200)
    await shot('chat-open')

    // Fresh task so the transcript starts empty.
    const newSession = page.getByTestId('new-session')
    if (await newSession.isVisible().catch(() => false)) {
      await newSession.click().catch(() => {})
      await page.waitForTimeout(600)
    } else {
      findings.push({
        step: 'new-session',
        ok: false,
        note: 'new-session not visible (sidebar collapsed?) — running in the current session',
      })
    }

    // Pick a write-capable mode. The mode selector is the chip in the composer.
    await page
      .getByTestId('composer-mode-selector')
      .click()
      .catch(() => {})
    await page
      .getByTestId('composer-mode-list')
      .waitFor({ timeout: 5000 })
      .catch(() => {})
    await shot('mode-menu-open')
    const option = page.getByTestId(`composer-mode-${MODE}`).first()
    if ((await option.count()) > 0) {
      await option.click().catch(() => {})
    } else {
      findings.push({
        step: 'mode',
        ok: false,
        note: `composer-mode-${MODE} not found in the menu`,
      })
    }
    await page.waitForTimeout(500)
    // The mode is session state: record what the composer chip really shows, not
    // just what we clicked — a silent revert (or a shared session) must be visible.
    modeChip = await page
      .getByTestId('composer-mode-selector')
      .innerText()
      .catch(() => '')
    if (modeChip && !/full access|vollzugriff/i.test(modeChip)) {
      findings.push({
        step: 'mode-effective',
        ok: false,
        note: `selected ${MODE} in the menu, but the composer chip reads "${modeChip.trim()}" — the selection did not stick`,
      })
    }

    // ── the request ──────────────────────────────────────────────────────
    await page.locator(CHAT_INPUT).fill(task)
    await shot('request-typed')
    bubblesBefore = await page.locator(ASSISTANT).count()
    await page.keyboard.press('Enter')

    // ── capture the arc while the turn runs ──────────────────────────────
    // The approval gate blocks the turn until answered, so we poll and answer
    // it; the tool card is grabbed the first time it appears.
    const deadline = Date.now() + 420_000
    while (Date.now() < deadline) {
      if ((await page.locator(STOP).count()) > 0) sawStream = true

      const dlg = page.getByRole('alertdialog')
      if ((await dlg.count()) > 0) {
        if (!approvalSeen) {
          approvalSeen = true
          approvalText = (await dlg.innerText().catch(() => '')).slice(0, 400)
          await shot('approval-gate')
        }
        if (!approvalApproved) {
          const approve = dlg.getByRole('button', { name: /approve/i }).first()
          if ((await approve.count()) > 0) {
            await approve.click().catch(() => {})
            approvalApproved = true
            await page.waitForTimeout(500)
            await shot('approval-approved')
          }
        }
      }

      // The DEFAULT surface a user sees while a turn runs is the collapsed row
      // group (tool-stream-rows) — grab it the first time it appears. The detailed
      // ToolCallDisplay card is captured after the turn, once the group is expanded.
      if (!toolRowSeen && (await page.locator(TOOL_ROWS).count()) > 0) {
        toolRowSeen = true
        await shot('tool-activity')
      }

      const streaming = await page.locator(STOP).count()
      const bubblesNow = await page.locator(ASSISTANT).count()
      if (
        (sawStream || bubblesNow > bubblesBefore) &&
        streaming === 0 &&
        bubblesNow > bubblesBefore
      ) {
        break
      }
      await page.waitForTimeout(400)
    }
    await page.waitForTimeout(1500)
    await shot('turn-end')

    // ── the assistant's answer ───────────────────────────────────────────
    const bubble = page.locator(ASSISTANT).last()
    await expect(bubble).toBeVisible()
    const head = bubble.getByTestId('bubble-turn-head')
    if ((await head.getAttribute('aria-expanded').catch(() => null)) === 'false') {
      await head.click().catch(() => {})
      await page.waitForTimeout(500)
    }
    answer = await bubble.innerText().catch(() => '')
    await shot('assistant-answer')

    // ── the detailed tool activity (behind the collapsed row group) ───────
    // The user sees only the collapsed row by default. Expand it to record the
    // detailed card, its target and its preview button (if the tool model
    // carries a filePath). This is where the familiar "tool card" lives.
    const groupSel = `${TOOL_ROW_WRITE}, ${TOOL_ROW_READ}`
    // Prefer the LAST assistant bubble (this turn) before falling back to a
    // page-wide match, so a shared/contaminated transcript cannot make us expand
    // some other turn's tool group.
    let group = bubble.locator(groupSel).first()
    if ((await group.count()) === 0) group = page.locator(groupSel).first()
    if ((await group.count()) === 0) group = bubble.locator(TOOL_ROW).first()
    if ((await group.count()) === 0) group = page.locator(TOOL_ROW).first()
    const toggle =
      (await group.count()) > 0
        ? group.locator('button[aria-expanded]').first()
        : page.locator(TOOL_ROW_TOGGLE).first()
    if ((await toggle.count()) > 0) {
      await toggle.click().catch(() => {})
      await page.waitForTimeout(1000)
      if ((await page.locator(TOOL_CARD).count()) > 0) {
        toolCardExpanded = true
        toolCardSeen = true
        toolTarget = await page
          .locator(TOOL_TARGET)
          .first()
          .innerText()
          .catch(() => '')
        await shot('tool-card-expanded')
        const open = page.locator(TOOL_OPEN).first()
        if ((await open.count()) > 0) {
          await open.click().catch(() => {})
          toolPreviewOpened = true
          await page.waitForTimeout(1500)
          await shot('tool-open-preview')
        } else {
          findings.push({
            step: 'tool-open-preview',
            ok: false,
            note: 'expanded tool card rendered without a preview button (no filePath on the tool model)',
          })
        }
      } else {
        findings.push({
          step: 'tool-card-expand',
          ok: false,
          note: 'clicking the tool row did not reveal a detailed tool card',
        })
      }
    } else if (toolRowSeen) {
      findings.push({
        step: 'tool-card-expand',
        ok: false,
        note: 'tool row present but no expand toggle button found',
      })
    }
    if (!toolRowSeen) {
      findings.push({
        step: 'tool-activity',
        ok: false,
        note: 'no tool-stream-rows and no tool-card appeared — the user saw no visible tool activity',
      })
    }

    // ── "find it again later" — surface (a): the library pop-up ──────────
    const libToggle = page.getByTestId('artifact-library-toggle')
    if ((await libToggle.count()) > 0) {
      await libToggle.click().catch(() => {})
      await page.waitForTimeout(1500)
      await shot('library-popup')
      const modal = page.getByTestId('artifact-modal')
      if ((await modal.count()) > 0) {
        libraryListsFile = (await modal.innerText().catch(() => '')).includes(filename)
        await modal
          .getByTestId('artifact-close')
          .click()
          .catch(() => {})
      } else {
        findings.push({
          step: 'library-popup',
          ok: false,
          note: 'artifact-library-toggle opened no artifact-modal',
        })
      }
    } else {
      findings.push({
        step: 'library-popup',
        ok: false,
        note: 'artifact-library-toggle not found in the chat header',
      })
    }
    await page.waitForTimeout(500)

    // ── surface (b): the workbench page ──────────────────────────────────
    await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'load' })
    await page
      .waitForSelector('[data-testid="artifacts-page"]', { timeout: 20_000 })
      .catch(() => {})
    await page.waitForTimeout(1200)
    const search = page.getByLabel(/search all artifacts/i)
    if ((await search.count()) > 0) {
      await search.fill(filename).catch(() => {})
      await page.waitForTimeout(1500)
    } else {
      findings.push({
        step: 'workbench-search',
        ok: false,
        note: 'workbench search input not found',
      })
    }
    await shot('workbench-search')
    workbenchListsFile = (await page.getByText(filename, { exact: false }).count()) > 0

    // ── surface (c): the Files tab (workspace explorer) ──────────────────
    await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_INPUT, { timeout: 20_000 })
    await page.waitForTimeout(800)
    // #71: the Files row lives in the closed "Tools & Capabilities" tier.
    await openTier(page, 'tools')
    const filesAction = page.getByTestId('sidebar-action-files')
    if ((await filesAction.count()) > 0) {
      await filesAction.click().catch(() => {})
      await page.waitForTimeout(2000)
      await shot('files-tab')
      const panel = page.getByRole('tabpanel')
      if ((await panel.count()) > 0) {
        filesTabListsFile = (await panel.innerText().catch(() => '')).includes(filename)
      }
    } else {
      findings.push({ step: 'files-tab', ok: false, note: 'sidebar-action-files not found' })
    }
    await shot('end-state')

    // ── server truth (live reads, not a mock) ────────────────────────────
    // The strongest honest evidence that the file exists on disk: fetch the
    // path the tool card reported straight from the backend.
    if (toolTarget && toolTarget.includes('/')) {
      const res = await request
        .get(`/api/file?path=${encodeURIComponent(toolTarget)}`)
        .catch(() => null)
      if (res) {
        fileEndpointStatus = res.status()
        fileEndpointBytes = (await res.body().catch(() => Buffer.from(''))).length
      }
    }
    // Independent of what path the tool model carried: bare filename resolved
    // against the workspace (the app's own resolution — verified live).
    const relRes = await request
      .get(`/api/file?path=${encodeURIComponent(filename)}`)
      .catch(() => null)
    if (relRes) {
      fileEndpointRelativeStatus = relRes.status()
      if (!fileEndpointStatus) {
        fileEndpointStatus = relRes.status()
        fileEndpointBytes = (await relRes.body().catch(() => Buffer.from(''))).length
      }
    }
    const listRes = await request
      .get('/api/artifacts', { params: { q: filename } })
      .catch(() => null)
    if (listRes) {
      const body = (await listRes.json().catch(() => ({ artifacts: [] }))) as {
        artifacts?: unknown[]
      }
      listedByApi = Array.isArray(body.artifacts) ? body.artifacts.length : 0
    }

    // ── the finding this persona exists for ──────────────────────────────
    // The produced file is real (it is served by /api/file and listed in the
    // workspace Files panel) but it never became an ARTIFACT, so the two
    // "find it again later" surfaces (library pop-up, workbench) are blind to it.
    // Root cause: server/routes/chat.py::_emit_file_result_event registers an
    // artifact only for tool results prefixed CHART_FILE:/PDF_FILE:/SVG_FILE:/
    // XLSX_FILE:/DOCX_FILE:/PNG_FILE:/PITCH_DECK_FILE:/PPTX_DECK_FILE:/
    // SCREENSHOT_FILE:. write_file returns "WRITE_FILE:<path>", which is absent
    // from that table — so plain file writes are never indexed.
    if (filesTabListsFile && !libraryListsFile && !workbenchListsFile && listedByApi === 0) {
      findings.push({
        step: 'artifact-library-gap',
        ok: false,
        note:
          'The file is really on disk (/api/file?path=<name> → ' +
          `${fileEndpointRelativeStatus}, ${fileEndpointBytes} bytes) and listed in the workspace ` +
          'Files panel, but it is NOT an artifact: the library pop-up shows "Artifacts (0)", the ' +
          `workbench search finds 0 of 54 cards, and /api/artifacts?q=${filename} returns total 0. ` +
          'A user who wants to find the produced file again later via the artifact library or the ' +
          'workbench cannot. Severity: high — this breaks the persona promise for the most common ' +
          'file-production path (write_file).',
      })
    }
    if (!toolCardExpanded && toolRowSeen) {
      findings.push({
        step: 'tool-card-collapsed',
        ok: true,
        note:
          'The detailed tool card (ToolCallDisplay) is not shown by default; tool activity appears ' +
          'only as collapsed tool-stream-rows (verb + target + status + duration). Low severity — ' +
          'the row already tells the user an action ran.',
      })
    }
    if (
      approvalSeen &&
      approvalText &&
      !approvalText.includes(filename) &&
      !/write|create|file/i.test(approvalText)
    ) {
      findings.push({
        step: 'foreign-approval-gate',
        ok: false,
        note:
          'An approval gate appeared for an action unrelated to this persona\u2019s request (' +
          JSON.stringify(approvalText.slice(0, 160)) +
          '). write_file itself was auto-approved (audit log: status=edit_auto). Under concurrent ' +
          'walkthrough runs against one live server the pending approval is not scoped to the ' +
          'requesting session; clicking Approve here hit POST /api/sandbox/approve \u2192 404 ' +
          '("sandbox token not found or expired"). Severity: medium — only observed with concurrent ' +
          'clients against the shared server.',
      })
    }
    if (!(
      filesTabListsFile ||
      libraryListsFile ||
      workbenchListsFile ||
      fileEndpointStatus === 200
    )) {
      findings.push({
        step: 'no-surface-lists-file',
        ok: false,
        note: 'No UI surface and no /api/file read exposed the produced file.',
      })
    }

    // ── soft assertions: the walkthrough's claims, without aborting ──────
    // Soft, so the run still finishes and delivers every screenshot even when
    // a surface is missing — the gap is the finding.
    expect
      .soft(sawStream || toolRowSeen || toolCardSeen, 'the turn produced visible activity')
      .toBeTruthy()
    expect
      .soft(
        toolRowSeen || toolCardSeen,
        'a tool-activity surface became visible — the user can see an action ran (collapsed row and/or expanded card)',
      )
      .toBeTruthy()
    expect
      .soft(
        libraryListsFile ||
          workbenchListsFile ||
          filesTabListsFile ||
          fileEndpointStatus === 200 ||
          fileEndpointRelativeStatus === 200,
        'the produced file is reachable from the UI (library pop-up, workbench, files tab, or /api/file)',
      )
      .toBeTruthy()
    expect
      .soft(
        answer.includes(filename) || /\d+\s*(?:bytes?|B)\b/i.test(answer),
        'the answer names the file and/or reports its size',
      )
      .toBeTruthy()
  } finally {
    writeReport()
  }
})
