import { test, expect, type Locator, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

/**
 * Ephe PWA — user walkthrough, persona 9 "the workbench user".
 *
 * The person: someone who makes the agent produce work and wants to find it
 * again afterwards, without re-reading the chat.
 *
 * Questions this walkthrough answers with evidence:
 *  1. What does the workbench (app/src/pages/ArtifactsPage.tsx) show when it is
 *     empty — and when it is not?
 *  2. After a real task, can the user point at what the agent produced without
 *     reading the chat? (shelf row, search, kind grouping)
 *  3. Is the artifact's origin visible — which session, which turn, which tool?
 *     (detail meta + the provenance chain)
 *  4. What happens with an artifact type the preview cannot render?
 *
 * Measured 2026-10-12 (see notes.md): the workbench holds what the engine's
 * artifact tools produce — the chat stream registers a file when a tool result
 * starts with a `*_FILE:` marker. Anything a plain write_file writes (and any
 * type no artifact tool emits) never appears on the shelf, whatever the chat
 * claims about it. The walkthrough therefore asks for the two types an artifact
 * tool really makes: a spreadsheet (renderable as a table) and a pptx deck.
 *
 * Design rules of this spec:
 *  - NOTHING is mocked. No page.route / no synthetic SSE. The Vite dev server
 *    on 127.0.0.1:5174 proxies /api/* to the real engine on 127.0.0.1:8765.
 *    When that engine is unreachable or the app is still behind the setup gate,
 *    the walkthrough skips instead of inventing a result.
 *  - One ordered test: the walkthrough is stateful (empty state first, then the
 *    task, then the artifact). The Playwright config keeps fullyParallel off.
 *  - Locale is pinned to English in localStorage only (a user preference, not a
 *    network stub) so the label-based steps are stable. All element assertions
 *    go through data-testid where one exists.
 *  - Every step photographs the full page into the persona folder.
 *
 * Cross-referenced source (roles / test ids read from the app):
 *  - pages/ArtifactsPage.tsx: artifacts-page, artifacts-back, artifacts-stats,
 *    artifacts-nomatch, artifacts-clear-filters, artifacts-search-clear,
 *    artifacts-ablage-hint, artifacts-error, artifacts-retry,
 *    input aria-label/placeholder "Search all artifacts…".
 *    Nav links are hash hrefs: #/artifacts (Shelf), #/artifacts/ablage (Adopted).
 *  - components/dashboard/artifacts/shelf.tsx: artifacts-shelf-empty,
 *    shelf-group-<kind>, shelf-more-<kind>.
 *  - components/dashboard/artifacts/libraryRow.tsx: artifact-row-<id>,
 *    artifact-select-<id>, artifact-adopt-<id>, artifact-stamp-<id>,
 *    artifact-origin-<id>.
 *  - components/dashboard/artifacts/detail.tsx: artifact-detail, <dl> meta,
 *    artifact-detail-download/-adopt/-delete.
 *  - components/dashboard/artifacts/provenance.tsx: artifact-provenance,
 *    artifact-provenance-chain, artifact-provenance-node, artifact-open-task.
 *  - components/dashboard/artifacts/preview.tsx: artifact-preview-code,
 *    artifact-preview-retry; the "no content" card (NoPreview) carries no test
 *    id and is asserted by its English sentence.
 *  - components/dashboard/chat/ComposerSendButton.tsx: send-btn / stop-btn.
 */

const SHOT_DIR = walkthroughOutDir('persona-09-werkbank')
fs.mkdirSync(SHOT_DIR, { recursive: true })

// The config baseURL is the Vite dev server (5174, proxying /api/* to the engine).
// EPHE_WALKTHROUGH_BASE points the same spec at a base that serves the app itself
// (the live server on 8765), so the walkthrough can run without the dev server.
const OVERRIDE_BASE = process.env.EPHE_WALKTHROUGH_BASE
if (OVERRIDE_BASE) test.use({ baseURL: OVERRIDE_BASE })

// A unique token ties the produced file name and its content together, so a
// match on the page provably belongs to THIS walkthrough run.
const TOKEN = `wt09-${Date.now().toString(36)}`
// The workbench indexes what the engine's *artifact tools* produce — the chat
// stream registers a file when a tool result starts with a `*_FILE:` marker
// (server/routes/chat.py: _FILE_RESULT_PREFIXES). A plain write_file emits no
// marker and never reaches the shelf (measured: 2026-10-12, see notes.md). So
// both files are asked for as the types those tools produce:
//  - a spreadsheet (kind xlsx → the card renders a real table),
//  - an editable PowerPoint deck (kind pptx → no browser render, no text
//    extraction: the honest "shows no content for this type" card).
const NAME_SHEET = `walkthrough-artifact-${TOKEN}.xlsx`
const NAME_SLIDES = `walkthrough-artifact-${TOKEN}-slides.pptx`
const BODY_TEXT = `hello workbench ${TOKEN}`
const MSG_CREATE_SHEET =
  `Create an Excel spreadsheet with your spreadsheet tool. File name exactly: ${NAME_SHEET}. ` +
  `One sheet, one row: header "token", value "${BODY_TEXT}".`
const MSG_CREATE_SLIDES =
  `Create an editable PowerPoint file with your PowerPoint (pptx) tool. File name exactly: ${NAME_SLIDES}. ` +
  `Topic "workbench walkthrough ${TOKEN}", audience "one user", three slides, nothing else.`
const NO_MATCH_QUERY = `zzz-no-such-artifact-${TOKEN}-zzz`

// Both tasks in this walkthrough make the engine build a real file with an
// artifact tool, so a finished turn is a slow turn. These are ceilings, not
// deadlines: a turn that settles late is recorded as slow (wall-time attachments
// + [persona-09] console lines + a `slow` annotation), a turn that never settles
// still fails and is photographed. Overridable per environment.
const TURN_START_MS = Number(process.env.EPHE_TURN_START_MS ?? 120_000)
const TURN_SETTLE_MS = Number(process.env.EPHE_TURN_SETTLE_MS ?? 480_000)
const SLOW_TURN_MS = Number(process.env.EPHE_SLOW_TURN_MS ?? 60_000)

type Recorder = {
  consoleErrors: string[]
  pageErrors: string[]
  failedRequests: string[]
  errorResponses: string[]
}

/** Collect console errors, uncaught page errors, failed requests and 4xx/5xx. */
function watch(page: Page): Recorder {
  const rec: Recorder = {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    errorResponses: [],
  }
  page.on('console', (m) => {
    if (m.type() === 'error') rec.consoleErrors.push(m.text())
  })
  page.on('pageerror', (e) => rec.pageErrors.push(String(e.message ?? e)))
  page.on('requestfailed', (r) =>
    rec.failedRequests.push(`${r.method()} ${r.url()} — ${r.failure()?.errorText ?? ''}`),
  )
  page.on('response', (r) => {
    if (r.status() >= 400)
      rec.errorResponses.push(`${r.status()} ${r.request().method()} ${r.url()}`)
  })
  return rec
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOT_DIR, name), fullPage: true })
}

type TurnReport = { label: string; wallMs: number }

/**
 * Send one chat message and wait for the real streaming turn to finish.
 *
 * The settle signal is the composer's own state (stop-btn gone, send-btn back) —
 * the app's truth, not a guess. What changed is the window around it: an earlier
 * revision gave a turn that genuinely builds a file 180_000 ms and reported the
 * timeout as a product result. The engine decides how long a turn takes, so the
 * ceiling is generous (TURN_SETTLE_MS) and the measured wall time is what gets
 * reported. A turn that never settles is still a failure: it is photographed,
 * attached with its composer state and annotated as a defect.
 */
async function sendAndWaitForTurn(page: Page, text: string, label: string): Promise<TurnReport> {
  const input = page.getByTestId('chat-input')
  await expect(input).toBeVisible({ timeout: 30_000 })
  await input.fill(text)
  const sentAt = Date.now()
  await page.getByTestId('send-btn').click()

  // Stream started: the stop button appears, or an assistant bubble shows up.
  await expect
    .poll(
      async () => {
        const stop = await page
          .getByTestId('stop-btn')
          .isVisible()
          .catch(() => false)
        const bubbles = await page
          .locator('div.glass-reading')
          .count()
          .catch(() => 0)
        return stop || bubbles > 0
      },
      { timeout: TURN_START_MS, intervals: [400] },
    )
    .toBe(true)

  // Stream finished: the send button is back and the stop button is gone.
  let settled = false
  try {
    await expect
      .poll(
        async () => {
          const stop = await page
            .getByTestId('stop-btn')
            .isVisible()
            .catch(() => false)
          const send = await page
            .getByTestId('send-btn')
            .isVisible()
            .catch(() => false)
          return !stop && send
        },
        { timeout: TURN_SETTLE_MS, intervals: [500] },
      )
      .toBe(true)
    settled = true
  } finally {
    if (!settled) {
      const waited = Date.now() - sentAt
      const stop = await page
        .getByTestId('stop-btn')
        .isVisible()
        .catch(() => false)
      const send = await page
        .getByTestId('send-btn')
        .isVisible()
        .catch(() => false)
      const bubbles = await page
        .locator('div.glass-reading')
        .count()
        .catch(() => -1)
      const approval = await page
        .getByRole('alertdialog')
        .isVisible()
        .catch(() => false)
      const last = await page
        .locator('div.glass-reading')
        .last()
        .textContent()
        .catch(() => '(no assistant bubble)')
      await shot(page, `99-turn-never-settled-${label}.png`)
      await test.info().attach(`turn-never-settled-${label}`, {
        body: [
          `message: ${text}`,
          `waited: ${waited} ms of a ${TURN_SETTLE_MS} ms ceiling`,
          `stop-btn visible: ${stop} | send-btn visible: ${send}`,
          `approval dialog visible: ${approval}`,
          `assistant bubbles: ${bubbles}`,
          `last assistant bubble: ${(last ?? '').replace(/\s+/g, ' ').slice(0, 600)}`,
        ].join('\n'),
        contentType: 'text/plain',
      })
      test.info().annotations.push({
        type: 'defect',
        description: `the turn "${label}" never settled: after ${waited} ms the composer still showed stop-btn=${stop} / send-btn=${send} — the turn neither finished nor failed visibly.`,
      })
    }
  }

  const wallMs = Date.now() - sentAt

  console.log(`[persona-09] turn "${label}" settled after ${wallMs} ms`)
  await test.info().attach(`turn-${label}-wall-time`, {
    body: `${wallMs} ms (ceiling ${TURN_SETTLE_MS} ms)`,
    contentType: 'text/plain',
  })
  if (wallMs > SLOW_TURN_MS) {
    test.info().annotations.push({
      type: 'slow',
      description: `turn "${label}" needed ${wallMs} ms (${Math.round(wallMs / 1000)} s) — slow, but it finished.`,
    })
  }
  return { label, wallMs }
}

/** Fewest moving parts: hash into the shelf, then reload so the read is fresh. */
async function openShelfFresh(page: Page): Promise<void> {
  await page.goto('/#/artifacts')
  await expect(page.getByTestId('artifacts-page')).toBeVisible({ timeout: 30_000 })
  await page.reload()
  await expect(page.getByTestId('artifacts-page')).toBeVisible({ timeout: 30_000 })
}

/**
 * Search the workbench for a produced file and return its shelf row.
 * Retries because the engine indexes a freshly written file asynchronously.
 */
async function findRow(
  page: Page,
  query: string,
  name: string,
  attempts = 8,
): Promise<Locator | null> {
  for (let i = 0; i < attempts; i++) {
    await openShelfFresh(page)
    const search = page.getByPlaceholder(/Search all artifacts/i)
    await expect(search).toBeVisible({ timeout: 15_000 })
    await search.fill(query)
    const row = page.locator('[data-testid^="artifact-row-"]').filter({ hasText: name }).first()
    try {
      await row.waitFor({ state: 'visible', timeout: 10_000 })
      // The shelf keeps the previous list while a fresh read is in flight and
      // writes "Reading the workbench…" over it. Waiting that out and then
      // confirming the row is still there matters: a screenshot of the stale
      // list would claim a find the picture does not show (seen once while the
      // other walkthroughs ran against the same server).
      await page
        .getByText(/Reading the workbench/i)
        .waitFor({ state: 'hidden', timeout: 8_000 })
        .catch(() => {})
      await page.waitForTimeout(300)
      if (await row.isVisible().catch(() => false)) {
        await row.scrollIntoViewIfNeeded().catch(() => {})
        return row
      }
    } catch {
      /* not there yet — reload and look again */
    }
    await page.waitForTimeout(1_500)
  }
  return null
}

/**
 * Start a fresh task instead of the conversation the surface restored.
 *
 * The chat page restores the last stored session on load. That session can
 * carry a pending tool approval from somebody else's task, and the modal sits
 * over the composer — the walkthrough then cannot type (measured 2026-10-12).
 * A new task is also what this persona does at the start of a piece of work.
 * Returns true when a leftover approval had to be dismissed.
 */
async function startFreshTask(page: Page): Promise<boolean> {
  const button = page.getByTestId('new-session')
  try {
    await button.click({ timeout: 8_000 })
  } catch {
    // Sidebar collapsed or covered: the same action sits on ⌘N.
    await page.keyboard.press('Meta+n')
  }
  await page.waitForTimeout(700)

  const stale = page.getByRole('alertdialog')
  if (await stale.isVisible().catch(() => false)) {
    // Deny, never approve: the call belongs to a task this walkthrough did not
    // start. Recorded by the caller instead of being papered over.
    await stale
      .getByRole('button', { name: /deny|ablehnen/i })
      .first()
      .click({ timeout: 8_000 })
      .catch(() => {})
    return true
  }
  return false
}

/**
 * The artifact id a shelf row carries in its testid (`artifact-row-<id>`) —
 * the same id the API speaks.
 */
async function rowId(row: Locator): Promise<string> {
  const testId = (await row.getAttribute('data-testid')) ?? ''
  return testId.replace('artifact-row-', '')
}

test.describe('Walkthrough persona 9 — the workbench user', () => {
  test('empty workbench, a produced artifact, its origin, and an unrenderable type', async ({
    page,
  }) => {
    // Two real artifact turns, each with its own settle ceiling, plus the shelf
    // reads that follow: the engine decides how long one turn takes, so the test
    // budget is derived from those ceilings rather than from a deadline that
    // mismeasures a working slow turn.
    test.setTimeout(Number(process.env.EPHE_WALKTHROUGH_TIMEOUT_MS ?? 1_500_000))
    const rec = watch(page)

    // Pin the interface language for stable labels (user preference only).
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
    })

    // ── Prerequisite: the live engine must answer ────────────────────────
    const health = await page.request.get('/api/health').catch(() => null)
    test.skip(
      !health || !health.ok(),
      `Live engine on 127.0.0.1:8765 not reachable (health: ${health ? health.status() : 'no response'}) — walkthrough needs a real backend.`,
    )

    // ── Step 1: the workbench BEFORE anything is created ─────────────────
    await page.goto('/#/artifacts')
    await expect(page.getByTestId('artifacts-page')).toBeVisible({ timeout: 30_000 })
    test.skip(
      await page
        .getByTestId('setup-page')
        .isVisible()
        .catch(() => false),
      'Live engine is not configured (setup gate) — workbench not reachable.',
    )
    await shot(page, '01-shelf-initial.png')
    await test.info().attach('shelf-header', {
      body:
        (await page
          .getByTestId('artifacts-stats')
          .textContent()
          .catch(() => '(no stats line)')) ?? '',
      contentType: 'text/plain',
    })

    // If the workbench is genuinely empty, this IS the empty state — photograph it.
    const shelfEmpty = page.getByTestId('artifacts-shelf-empty')
    if (await shelfEmpty.isVisible().catch(() => false)) {
      await shot(page, '01b-shelf-empty.png')
      await test.info().attach('shelf-empty-text', {
        body: (await shelfEmpty.textContent()) ?? '',
        contentType: 'text/plain',
      })
    }

    // The Adopted archive is the empty state this persona can always reach
    // before producing anything.
    await page.locator('a[href="#/artifacts/ablage"]').click()
    await expect(page.getByTestId('artifacts-ablage-hint')).toBeVisible({ timeout: 15_000 })
    const ablageEmpty = page.getByTestId('artifacts-shelf-empty')
    await expect(ablageEmpty).toBeVisible({ timeout: 15_000 })
    await shot(page, '02-adopted-empty.png')
    await test.info().attach('adopted-empty-text', {
      body: (await ablageEmpty.textContent()) ?? '',
      contentType: 'text/plain',
    })

    // A filter that matches nothing — the third empty state.
    await page.locator('a[href="#/artifacts"]').click()
    await expect(page.getByTestId('artifacts-page')).toBeVisible({ timeout: 15_000 })
    const search = page.getByPlaceholder(/Search all artifacts/i)
    await search.fill(NO_MATCH_QUERY)
    const noMatch = page
      .getByTestId('artifacts-nomatch')
      .or(page.getByTestId('artifacts-shelf-empty'))
    await expect(noMatch).toBeVisible({ timeout: 20_000 })
    await shot(page, '03-search-no-match.png')
    await test.info().attach('no-match-text', {
      body: (await noMatch.first().textContent()) ?? '',
      contentType: 'text/plain',
    })

    // ── Step 2: produce real artifacts through the chat ──────────────────
    await page.goto('/#/chat')
    if (await startFreshTask(page)) {
      await test.info().annotations.push({
        type: 'defect',
        description:
          'the restored conversation still carried a pending tool approval from an earlier task; the modal covered the composer and had to be denied before this walkthrough could type.',
      })
    }

    // Only now: auto-approve a confirmation that belongs to THIS task. The
    // engine may ask before a file write; the walkthrough answers "Approve".
    // Registered after the fresh start so it can never approve a call that
    // belongs to somebody else's conversation.
    await page.addLocatorHandler(page.getByRole('alertdialog'), async () => {
      const approve = page.getByRole('button', { name: /^(approve|allow|genehmigen|zulassen)$/i })
      if (
        await approve
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        await approve
          .first()
          .click({ timeout: 8_000 })
          .catch(() => {})
      }
    })

    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 30_000 })
    const turnSheet = await sendAndWaitForTurn(page, MSG_CREATE_SHEET, 'sheet')
    await shot(page, '04-chat-sheet-after-turn.png')

    // A second file of a type the browser cannot render (pptx).
    const turnSlides = await sendAndWaitForTurn(page, MSG_CREATE_SLIDES, 'slides')
    await shot(page, '05-chat-slides-after-turn.png')
    await test.info().attach('turn-wall-times', {
      body: `${turnSheet.label}: ${turnSheet.wallMs} ms\n${turnSlides.label}: ${turnSlides.wallMs} ms`,
      contentType: 'text/plain',
    })

    // ── Step 3: find it on the workbench without reading the chat ────────
    const tSheet = Date.now()
    const sheetRow = await findRow(page, TOKEN, NAME_SHEET)
    const sheetWaitMs = Date.now() - tSheet
    await test.info().attach('find-wait-sheet', {
      body: `${sheetWaitMs} ms of polling until ${NAME_SHEET} was on the shelf (search query: ${TOKEN})`,
      contentType: 'text/plain',
    })

    const detail = page.getByTestId('artifact-detail')

    if (!sheetRow) {
      // THE finding if it happens: the agent produced a file and the user
      // cannot point at it. Photograph the shelf it is missing from and go on.
      await shot(page, '06-artifact-not-found-shelf.png')
      await test.info().annotations.push({
        type: 'defect',
        description: `produced spreadsheet ${NAME_SHEET} not findable on the workbench after ${sheetWaitMs} ms of polling (search "${TOKEN}") — the agent's output does not reach the shelf.`,
      })
    } else {
      await shot(page, '06-artifact-found-shelf.png')
      const group = page.locator('[data-testid^="shelf-group-"]').first()
      await expect.soft(group).toBeVisible({ timeout: 10_000 })
      await test.info().attach('shelf-group-heading', {
        body: (await group.textContent().catch(() => '(no group heading)')) ?? '',
        contentType: 'text/plain',
      })

      // Open the preview of the produced card.
      await sheetRow.locator('[data-testid^="artifact-select-"]').click()
      await expect(detail).toBeVisible({ timeout: 30_000 })
      await expect
        .soft(detail, `the produced file name ${NAME_SHEET} is not shown in its detail pane`)
        .toContainText(NAME_SHEET, { timeout: 30_000 })
      await expect
        .soft(detail, `the spreadsheet content "${BODY_TEXT}" is not rendered in the card`)
        .toContainText(BODY_TEXT, { timeout: 30_000 })
      await expect
        .soft(detail.locator('table'), 'the spreadsheet card renders no table')
        .toBeVisible({ timeout: 30_000 })
      // The bytes are in the DOM. The measured question is whether the user can
      // SEE them: in the picture the box holds the sheet-name caption and
      // nothing else. Measure the box chain instead of guessing, then try to
      // scroll the content into view.
      const cell: Locator = detail.getByText(BODY_TEXT).first()
      const cellFacts = await cell.evaluate((el) => {
        const chain: Record<string, unknown>[] = []
        let node: HTMLElement | null = el as HTMLElement
        while (node && node !== document.body) {
          const rect = node.getBoundingClientRect()
          chain.push({
            tag: node.tagName,
            testid: node.getAttribute('data-testid') ?? '',
            rect: [
              Math.round(rect.x),
              Math.round(rect.y),
              Math.round(rect.width),
              Math.round(rect.height),
            ],
            clientH: node.clientHeight,
            scrollH: node.scrollHeight,
            overflowY: getComputedStyle(node).overflowY,
          })
          node = node.parentElement
        }
        const own = el.getBoundingClientRect()
        return {
          chain,
          cellRect: [
            Math.round(own.x),
            Math.round(own.y),
            Math.round(own.width),
            Math.round(own.height),
          ],
          viewport: [window.innerWidth, window.innerHeight],
        }
      })
      await test.info().attach('sheet-cell-box', {
        body: JSON.stringify(cellFacts, null, 1),
        contentType: 'text/plain',
      })

      const scrolled = await cell.evaluate((el) => {
        let node: HTMLElement | null = el as HTMLElement
        while (node && node !== document.body) {
          if (node.scrollHeight > node.clientHeight + 2) {
            node.scrollTop = node.scrollHeight
            const rect = el.getBoundingClientRect()
            return {
              scroller: node.getAttribute('data-testid') || node.className.slice(0, 40),
              scrollTop: node.scrollTop,
              cellTop: Math.round(rect.top),
              visible: rect.width > 0 && rect.top >= 0 && rect.bottom <= window.innerHeight,
            }
          }
          node = node.parentElement
        }
        return { scroller: '(none found)', scrollTop: 0, cellTop: -1, visible: false }
      })
      await test.info().attach('sheet-cell-after-scroll', {
        body: JSON.stringify(scrolled),
        contentType: 'text/plain',
      })
      const preview = await page.request
        .get(`/api/artifacts/${await rowId(sheetRow)}/preview`)
        .catch(() => null)
      await test.info().attach('sheet-preview-payload', {
        body: preview
          ? `${preview.status()} ${(await preview.text()).slice(0, 600)}`
          : '(request failed)',
        contentType: 'text/plain',
      })
      if (!scrolled.visible) {
        await test.info().annotations.push({
          type: 'defect',
          description:
            `the produced spreadsheet card shows its content only in the DOM: "${BODY_TEXT}" (a real <td>) never enters the viewport, and scrolling the nearest scroll container ` +
            `(${scrolled.scroller}) does not bring it in — the preview box collapses to the sheet-name caption.`,
        })
      }
      await shot(page, '07-artifact-preview-sheet.png')

      // ── Step 4: the origin — which session, which turn, which tool ─────
      const provenance = page.getByTestId('artifact-provenance')
      await expect(provenance).toBeVisible({ timeout: 30_000 })
      const chain = page.getByTestId('artifact-provenance-chain')
      await expect
        .soft(chain, 'provenance chain not shown: the artifact origin is not visible')
        .toBeVisible({ timeout: 20_000 })
      await test.info().attach('provenance-text', {
        body: (await provenance.textContent().catch(() => '(no provenance block)')) ?? '',
        contentType: 'text/plain',
      })
      await test.info().attach('detail-meta', {
        body:
          (await detail
            .locator('dl')
            .textContent()
            .catch(() => '(no meta list)')) ?? '',
        contentType: 'text/plain',
      })
      const chainText = (await chain.textContent().catch(() => '')) ?? ''
      if (!/Task\s*[0-9a-f]{12}/i.test(chainText)) {
        await test.info().annotations.push({
          type: 'defect',
          description: `the provenance chain names no turn for ${NAME_SHEET} — the origin of the artifact is not visible.`,
        })
      }
      await shot(page, '08-artifact-provenance.png')
    }

    // ── Step 5: a type the preview cannot render ─────────────────────────
    const tSlides = Date.now()
    const slidesRow = await findRow(page, TOKEN, NAME_SLIDES)
    const slidesWaitMs = Date.now() - tSlides
    await test.info().attach('find-wait-slides', {
      body: `${slidesWaitMs} ms of polling until ${NAME_SLIDES} was on the shelf (search query: ${TOKEN})`,
      contentType: 'text/plain',
    })

    if (slidesRow) {
      await slidesRow.locator('[data-testid^="artifact-select-"]').click()
      await expect(detail).toBeVisible({ timeout: 30_000 })
      await expect.soft(detail).toContainText(NAME_SLIDES, { timeout: 20_000 })
      const card = await detail.textContent().catch(() => '(no detail text)')
      await test.info().attach('unrenderable-card-text', {
        body: card ?? '',
        contentType: 'text/plain',
      })
      await expect
        .soft(detail, `unrenderable type ${NAME_SLIDES} did not explain itself`)
        .toContainText(/shows no content/i, { timeout: 20_000 })
      const slidesPayload = await page.request
        .get(`/api/artifacts/${await rowId(slidesRow)}/preview`)
        .catch(() => null)
      await test.info().attach('unrenderable-preview-payload', {
        body: slidesPayload
          ? `${slidesPayload.status()} ${(await slidesPayload.text()).slice(0, 400)}`
          : '(request failed)',
        contentType: 'text/plain',
      })
      await shot(page, '09-artifact-unrenderable-slides.png')
    } else {
      await shot(page, '09-artifact-unrenderable-missing.png')
      await test.info().annotations.push({
        type: 'defect',
        description: `The engine never indexed ${NAME_SLIDES} after ${slidesWaitMs} ms — an unrenderable type could not be observed on the workbench.`,
      })
    }

    // ── Evidence: console + network ──────────────────────────────────────
    await test.info().attach('console-errors', {
      body: rec.consoleErrors.join('\n') || '(none)',
      contentType: 'text/plain',
    })
    await test.info().attach('page-errors', {
      body: rec.pageErrors.join('\n') || '(none)',
      contentType: 'text/plain',
    })
    await test.info().attach('failed-requests', {
      body: rec.failedRequests.join('\n') || '(none)',
      contentType: 'text/plain',
    })
    await test.info().attach('error-responses', {
      body: rec.errorResponses.join('\n') || '(none)',
      contentType: 'text/plain',
    })
  })
})
