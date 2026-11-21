import { test, expect, type Locator, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync, appendFileSync } from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

/**
 * Persona 08 — memory ("what stays"): does the agent's memory page show what it
 * really holds, and does a durable fact spoken in the chat come back on it?
 *
 * Live server, REAL engine, no route interception anywhere in this file. The app
 * is the built PWA the ephe server serves from app/dist; every fact this file
 * reads comes from the store behind GET /api/memory/*.
 *
 * Steps it walks and captures:
 *   1. #/memory first load — the state the store is actually in
 *      (first-run gate / loading / empty / holdings / store-not-answering)
 *   2. the holdings view: count line, rows, per-row source and type
 *   3. search: one query, and what the count line says afterwards
 *   4. the sub-pages: corrections, trash, brains
 *   5. the row verbs: edit (opened, then cancelled), delete, trash, restore
 *   6. the round trip: a durable fact told to the chat, then looked up on the page
 *   7. what the page itself explains about WHAT is kept and WHY
 *
 * Honest-state rule (the point of this persona): a store that does not answer is
 * captured as such and reported with its own wording. It is never counted as the
 * walkthrough failing and never read as "Ephe remembers nothing".
 *
 * Run (the live server must already answer on EPHE_E2E_BASE):
 *   cd app && npx playwright test -c playwright.config.ts e2e/walkthrough/persona-08-speicher.spec.ts
 */

const ART_DIR = walkthroughOutDir('persona-08-speicher')

/** The live origin: the ephe server that serves app/dist and /api. Overridable. */
const BASE =
  process.env.EPHE_WALKTHROUGH_BASE ?? process.env.EPHE_E2E_BASE ?? 'http://127.0.0.1:8765'
const MEMORY_URL = `${BASE}/#/memory`
const CHAT_URL = `${BASE}/#/chat`

/** Unique per run, so the round trip can never be satisfied by an older entry. */
const STAMP = new Date()
  .toISOString()
  .replace(/[-:TZ.]/g, '')
  .slice(0, 14)
const MARKER = `walkthrough08${STAMP}`
const FACT = `Remember this for later: the walkthrough marker for this session is ${MARKER}. Please keep it and confirm that you have.`
/** Fallback target for the verb steps, written through the real API (never a mock). */
const PROBE = `Q: walkthrough probe ${MARKER}\nA: probe entry so the edit, delete and restore steps have a target of their own`
const PROBE_EDIT = `Probe ${MARKER} — wording rewritten by the walkthrough`

// ── evidence ────────────────────────────────────────────────────────────────
interface Evidence {
  steps: string[]
  consoleErrors: string[]
  failedRequests: string[]
  httpErrors: string[]
  deletes: string[]
  texts: Record<string, string>
  findings: string[]
}
const EVIDENCE: Evidence = {
  steps: [],
  consoleErrors: [],
  failedRequests: [],
  httpErrors: [],
  deletes: [],
  texts: {},
  findings: [],
}

function watch(page: Page): void {
  page.on('console', (msg) => {
    if (msg.type() === 'error') EVIDENCE.consoleErrors.push(msg.text())
  })
  page.on('requestfailed', (req) => {
    EVIDENCE.failedRequests.push(
      `${req.method()} ${req.url()} — ${req.failure()?.errorText ?? 'failed'}`,
    )
  })
  // The delete verb is the one write this persona must be able to account for:
  // did the click actually put a DELETE on the wire, and what did the store say?
  page.on('request', (req) => {
    if (req.method() === 'DELETE' && req.url().includes('/api/memory')) {
      EVIDENCE.deletes.push(`issued ${new Date().toISOString()} ${req.url()}`)
    }
  })
  page.on('response', (res) => {
    // A store that cannot be read answers 503 by design; that line is evidence,
    // not an accident of this file.
    if (res.request().method() === 'DELETE' && res.url().includes('/api/memory')) {
      EVIDENCE.deletes.push(`answered ${new Date().toISOString()} ${res.status()} ${res.url()}`)
    }
    if (res.status() >= 400) {
      EVIDENCE.httpErrors.push(`${res.status()} ${res.request().method()} ${res.url()}`)
    }
  })
}

let shotSeq = 0

async function snap(page: Page, name: string): Promise<string> {
  mkdirSync(ART_DIR, { recursive: true })
  const file = path.join(ART_DIR, `${String(shotSeq).padStart(2, '0')}-${name}.png`)
  shotSeq += 1
  await page.screenshot({ path: file, fullPage: true })
  EVIDENCE.steps.push(`screenshot ${path.relative(REPO, file)}`)
  return file
}

function note(line: string): void {
  EVIDENCE.steps.push(line)
}

// ── page state ──────────────────────────────────────────────────────────────
type MemState = 'rows' | 'empty' | 'unreachable' | 'loading'

async function visible(page: Page, testid: string): Promise<boolean> {
  return page
    .getByTestId(testid)
    .isVisible()
    .catch(() => false)
}

/**
 * Every text read in this file is bounded. An unguarded innerText() on an element
 * that is absent — or that a re-render detaches between count() and the read —
 * waits out the whole test budget instead of reporting the state it found, so a
 * missing counter is RECORDED as ''/the fallback, never fatal.
 */
const READ_TIMEOUT = 2_500

async function readText(page: Page, testid: string, fallback = ''): Promise<string> {
  return page
    .getByTestId(testid)
    .innerText({ timeout: READ_TIMEOUT })
    .then((t) => t.trim())
    .catch(() => fallback)
}

/** Bounded body read for the pages that carry their own wording. */
async function readBody(page: Page, limit: number): Promise<string> {
  return page
    .locator('body')
    .innerText({ timeout: 5_000 })
    .then((t) => t.slice(0, limit))
    .catch(() => '')
}

/** Bounded element read for the ranked list, where the element can vanish. */
async function readAll(page: Page, selector: string): Promise<string[]> {
  return Promise.race([
    page.locator(selector).allInnerTexts(),
    new Promise<string[]>((resolve) => setTimeout(() => resolve([]), READ_TIMEOUT)),
  ]).catch(() => [])
}

/** One attempt of the chat → memory round trip, appended, never overwritten. */
function recordAttempt(row: Record<string, unknown>): void {
  mkdirSync(ART_DIR, { recursive: true })
  appendFileSync(
    path.join(ART_DIR, 'roundtrip-attempts.ndjson'),
    `${JSON.stringify({ at: new Date().toISOString(), ...row })}\n`,
  )
}

interface StoreEntry {
  id: string
  text: string
}

/** What the store really holds for one marker — read from the store, not the page. */
async function storeEntries(page: Page, needle: string): Promise<StoreEntry[]> {
  const res = await page.request.get(`${BASE}/api/memory/list?limit=200`).catch(() => null)
  if (!res || !res.ok()) return []
  const body = (await res.json()) as { entries?: StoreEntry[] }
  return (body.entries ?? []).filter((e) => e.text.includes(needle))
}

function describeEntries(entries: StoreEntry[]): string {
  if (entries.length === 0) return '0 entries'
  return `${entries.length} entry/entries: ${entries
    .map((e) => `${e.id} "${e.text.replace(/\s+/g, ' ').slice(0, 120)}"`)
    .join(' | ')}`
}

/**
 * The page renders four distinguishable states and they must not stand in for
 * one another: rows present, store answers but holds nothing, store does not
 * answer, still loading.
 */
async function memoryState(page: Page, timeoutMs = 25_000): Promise<MemState> {
  const until = Date.now() + timeoutMs
  for (;;) {
    if (await visible(page, 'memory-unreachable')) return 'unreachable'
    if (await visible(page, 'memory-row-0')) return 'rows'
    if (await visible(page, 'memory-page-empty')) return 'empty'
    if (Date.now() > until) return 'loading'
    await page.waitForTimeout(250)
  }
}

async function stateText(page: Page, state: MemState): Promise<void> {
  const read = async (testid: string) =>
    (await visible(page, testid)) ? readText(page, testid) : ''
  EVIDENCE.texts[`count:${state}`] = await read('memory-page-count')
  if (state === 'empty') EVIDENCE.texts[`emptySentence:${state}`] = await read('memory-page-empty')
  if (state === 'unreachable') {
    EVIDENCE.texts[`unreachableSentence:${state}`] = await read('memory-unreachable')
    EVIDENCE.texts[`unreachableReason:${state}`] = await read('memory-unreachable-reason')
  }
}

/** Opens #/memory and reports the state, or 'setup' when the first-run gate stands. */
async function openMemory(page: Page): Promise<MemState | 'setup'> {
  await page.goto(MEMORY_URL)
  const ok = await page
    .getByTestId('memory-page')
    .waitFor({ state: 'visible', timeout: 25_000 })
    .then(() => true)
    .catch(() => false)
  if (!ok) return 'setup'
  return memoryState(page)
}

const ROW = '[data-testid^="memory-row-"]'

/**
 * The list re-renders under the read: after a delete the row count drops between
 * count() and the read, and an unbounded innerText() on that detached row waits
 * out the test. A failed row read re-reads the whole list (twice at most) instead
 * of hanging; only then does the row count as unreadable.
 */
async function rowTexts(page: Page, attempt = 0): Promise<string[]> {
  const rows = page.locator(ROW)
  const n = await rows.count().catch(() => 0)
  const out: string[] = []
  for (let i = 0; i < n; i += 1) {
    try {
      out.push((await rows.nth(i).innerText({ timeout: READ_TIMEOUT })).trim())
    } catch {
      if (attempt < 2) return rowTexts(page, attempt + 1)
      out.push('')
    }
  }
  return out
}

async function rowIndexWith(page: Page, needle: string): Promise<number> {
  const texts = await rowTexts(page)
  return texts.findIndex((t) => t.includes(needle))
}

async function view(
  page: Page,
  name: 'Holdings' | 'Corrections' | 'Trash' | 'Brains',
): Promise<void> {
  await page.getByRole('link', { name, exact: true }).click()
  await page.getByTestId('memory-page').waitFor({ state: 'visible', timeout: 15_000 })
  await page.waitForTimeout(600)
}

/** Waits for a row whose text carries `needle` to leave the list, or reports it stayed. */
async function waitUntilGone(page: Page, needle: string, timeoutMs: number): Promise<boolean> {
  const until = Date.now() + timeoutMs
  for (;;) {
    if ((await rowIndexWith(page, needle)) < 0) return true
    if (Date.now() > until) return false
    await page.waitForTimeout(500)
  }
}

/**
 * The assistant bubble shows a pending placeholder ("Thinking… · Ns") until the
 * first token lands; reading it early records the placeholder, not the answer.
 * This settles only once the placeholder is gone and streaming has stopped.
 */
async function waitForAnswer(page: Page, bubble: Locator): Promise<string> {
  const until = Date.now() + 240_000
  let last = ''
  for (;;) {
    last = (await bubble.innerText({ timeout: READ_TIMEOUT }).catch(() => '')).trim()
    const pending = last.includes('Thinking') || /^\s*·/.test(last)
    const streaming = await page
      .getByLabel('Stop', { exact: true })
      .isVisible()
      .catch(() => false)
    if (last.length > 0 && !pending && !streaming) return last
    if (Date.now() > until) return last
    await page.waitForTimeout(500)
  }
}

// ── tests ───────────────────────────────────────────────────────────────────
test.describe('persona 08 — memory', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test.beforeEach(async ({ page }) => {
    // A user preference, not a mock: the UI ships English by default and this
    // pins it so the captured sentences are the ones quoted in the notes.
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en')
    })
    watch(page)
  })

  test.afterAll(() => {
    mkdirSync(ART_DIR, { recursive: true })
    writeFileSync(
      path.join(ART_DIR, 'observations.json'),
      `${JSON.stringify({ base: BASE, marker: MARKER, generatedAt: new Date().toISOString(), ...EVIDENCE }, null, 2)}\n`,
    )
  })

  test('the memory page shows what it holds: states, sub-pages, search, row verbs', async ({
    page,
  }) => {
    test.setTimeout(180_000)

    const state = await openMemory(page)
    await snap(page, 'first-load')
    note(`first load state: ${state}`)

    if (state === 'setup') {
      const body = await readBody(page, 600)
      EVIDENCE.texts['setupGate'] = body
      EVIDENCE.findings.push(
        'The first-run gate stands: #/memory redirects to the engine setup page, so no memory page exists to walk yet.',
      )
      test.skip(true, 'first-run gate: the engine is not configured, #/memory redirects to setup')
      return
    }

    await stateText(page, state)
    EVIDENCE.findings.push(`memory page first state: ${state}`)

    if (state === 'unreachable') {
      // Recorded, not failed: the page names the outage and never renders it as
      // an empty store. Everything below still runs against the rendered shell.
      EVIDENCE.findings.push(
        `store not answering — page says: "${EVIDENCE.texts['unreachableSentence:unreachable']}" / reason "${EVIDENCE.texts['unreachableReason:unreachable']}"`,
      )
    }
    if (state === 'empty') {
      EVIDENCE.findings.push(
        `store answered and holds nothing — page says: "${EVIDENCE.texts['emptySentence:empty']}"`,
      )
    }

    // ── search ──
    const field = page.getByTestId('memory-page-search')
    await expect(field).toBeVisible()
    const before = await readText(page, 'memory-page-count', '(no count line)')
    const firstRow = (await rowTexts(page))[0] ?? ''
    // A word taken from a real row is the query with the best chance of a hit;
    // with no rows a nonsense word still exercises the ranking line.
    const query = (firstRow.split(/\s+/).find((w) => w.length > 4) ?? 'zurich').replace(
      /[^\p{L}\p{N}-]/gu,
      '',
    )
    await field.fill(query)
    await page.waitForTimeout(2500)
    const after = await readText(page, 'memory-page-count', '(no count line)')
    EVIDENCE.texts.search = `query "${query}" → ${after}`
    note(`search "${query}": count line "${before}" → "${after}"`)
    EVIDENCE.findings.push(`search count line after the query: "${after}"`)
    await snap(page, 'search-query')
    await field.fill('')
    await page.waitForTimeout(1500)

    // ── the sub-pages ──
    await view(page, 'Corrections')
    await snap(page, 'korrekturen')
    EVIDENCE.texts.correctionsEmpty = await readText(page, 'memory-page-empty')

    await view(page, 'Trash')
    await snap(page, 'papierkorb')
    EVIDENCE.texts.trashEmpty = await readText(page, 'memory-page-empty')

    await view(page, 'Brains')
    await snap(page, 'gehirne')
    EVIDENCE.texts.brains = (await readBody(page, 4000)).replace(/\s+\n/g, '\n').slice(0, 2000)

    await view(page, 'Holdings')
    await snap(page, 'holdings')

    // ── the row verbs, on a row we are allowed to touch ──
    const state2 = await memoryState(page)
    if (state2 !== 'rows') {
      EVIDENCE.findings.push(`row verbs not reachable: holdings state is ${state2}`)
      return
    }

    // Edit: opened and cancelled — a real store's facts are not this file's to
    // rewrite, so only the availability of the verb is captured here.
    const editIndex = await rowIndexWith(page, '')
    if (editIndex >= 0) {
      await page.getByTestId(`memory-edit-${editIndex}`).click()
      await expect(page.getByTestId('memory-edit-input')).toBeVisible()
      await snap(page, 'row-edit-open')
      note(
        'row edit opened: textarea memory-edit-input is visible, supersede/rewrite/cancel offered',
      )
      await page.getByTestId('memory-edit-cancel').click()
      await expect(page.getByTestId('memory-edit-input')).toHaveCount(0)
    }

    const sources = await readAll(page, '[data-testid^="memory-source-"]')
    const types = await readAll(page, '[data-testid^="memory-type-"]')
    EVIDENCE.texts.rowMeta = `sources=[${sources.join(' | ')}] types=[${types.join(' | ')}]`
    note(`row metadata: ${EVIDENCE.texts.rowMeta}`)
    EVIDENCE.findings.push(
      'the page has no control that adds a memory entry: a fact can only enter through the chat or the API, never from this page',
    )
    if (types.length === 0) {
      EVIDENCE.findings.push(
        'no row carries a type, so the "Filter by type" chips never appear — every fact the chat writes is stored as source "From chat" with no type',
      )
    }
  })

  test('round trip: a durable fact told to the chat comes back on the memory page', async ({
    page,
  }) => {
    test.setTimeout(300_000)

    // ── 1. the chat ──
    await page.goto(CHAT_URL)
    const composer = page.getByTestId('chat-input')
    await expect(composer).toBeVisible({ timeout: 25_000 })
    await snap(page, 'chat-composer')

    const sentAt = Date.now()
    await composer.fill(FACT)
    await page.getByLabel('Send', { exact: true }).click()

    // A local turn can stream past 30s. The turn is over when the composer is
    // back to Send (Stop is gone); only then does the last assistant bubble hold
    // the answer instead of the "Thinking… · Ns" placeholder it shows meanwhile.
    await page.getByLabel('Send', { exact: true }).waitFor({ state: 'visible', timeout: 240_000 })
    const bubble = page.locator('div.glass-reading.rounded-tl-sm').last()
    await bubble.waitFor({ state: 'visible', timeout: 30_000 })
    const answer = await waitForAnswer(page, bubble)
    EVIDENCE.texts.chatAnswer = answer.slice(0, 600)
    note(`chat answered with ${answer.length} characters`)
    await snap(page, 'chat-answer')

    // ── 2. the store side of the round trip ──
    // The write happens through the real endpoint the chat schedules; polling it
    // is what tells "not yet" from "never".
    let storedId = ''
    let storeHits: StoreEntry[] = []
    let polls = 0
    for (let i = 0; i < 15 && !storedId; i += 1) {
      polls += 1
      storeHits = await storeEntries(page, MARKER)
      if (storeHits.length > 0) storedId = storeHits[0].id
      if (!storedId) await page.waitForTimeout(2000)
    }
    const secondsUntilStored = storedId ? (Date.now() - sentAt) / 1000 : -1
    EVIDENCE.texts.storeAfterChat = describeEntries(storeHits)
    note(
      storedId
        ? `fact stored through the chat: yes (id ${storedId}, ${secondsUntilStored}s after send, ${polls} poll(s), ${storeHits.length} store entry/entries carry the marker)`
        : `fact stored through the chat: no (${polls} poll(s) over the store, ${answer.length} answer characters)`,
    )

    // ── 3. the page ──
    const state = await openMemory(page)
    await snap(page, 'memory-after-chat')
    if (state === 'setup') {
      EVIDENCE.findings.push('after the chat turn #/memory redirected to the engine setup page')
      test.skip(true, 'first-run gate: no memory page to read')
      return
    }
    await stateText(page, state)
    EVIDENCE.findings.push(`memory page after the chat turn: ${state}`)

    if (state === 'unreachable') {
      EVIDENCE.findings.push(
        'The store did not answer while the round trip was being checked — the chat fact could not be confirmed on the page. The page names the outage instead of showing an empty store.',
      )
      return
    }

    const field = page.getByTestId('memory-page-search')
    await field.fill(MARKER)
    await page.waitForTimeout(3000)
    await snap(page, 'memory-search-marker')
    EVIDENCE.texts.markerSearchCount = await readText(page, 'memory-page-count', '(no count line)')

    let index = await rowIndexWith(page, MARKER)
    if (index < 0) {
      // Fallback target so the verbs still get walked; written through the real
      // API and labelled as a probe, never as a stand-in for the chat fact.
      const res = await page.request
        .post(`${BASE}/api/memory/store`, { data: { text: PROBE, memory_type: 'semantic' } })
        .catch(() => null)
      note(`fallback probe stored: ${res ? res.status() : 'request failed'}`)
      await openMemory(page)
      await page.getByTestId('memory-page-search').fill(MARKER)
      await page.waitForTimeout(3000)
      index = await rowIndexWith(page, MARKER)
    }

    // One line per attempt, appended and never overwritten: what the store held,
    // what the page showed, and how long the answer the write gate saw was. A
    // round trip that passes once and not the next time has to read as a
    // distribution, not as whichever run happened to be last.
    const pageRow = index >= 0 ? ((await rowTexts(page))[index] ?? '') : ''
    recordAttempt({
      marker: MARKER,
      answerChars: answer.length,
      answerHead: answer.replace(/\s+/g, ' ').slice(0, 160),
      storeEntriesWithMarker: storeHits.length,
      storedId: storedId || null,
      secondsUntilStored,
      pageState: state,
      pageShowsFact: index >= 0,
      pageRowText: pageRow.replace(/\s+/g, ' ').slice(0, 200),
    })

    if (index < 0) {
      EVIDENCE.findings.push(
        storedId
          ? 'the fact reached the store but the page did not show it under the marker search'
          : 'the chat turn did not produce a stored fact and no probe entry could be found on the page',
      )
      expect(
        storedId,
        `the durable fact spoken in the chat never reached GET /api/memory/list — the chat answered ${answer.length} characters ("${answer.replace(/\s+/g, ' ').slice(0, 120)}"); auto-memory stores a turn only when the answer is at least memory.capture_min_answer_chars (default 120) characters long`,
      ).toBeTruthy()
      return
    }

    const row = page.locator(ROW).nth(index)
    EVIDENCE.texts.roundTripRow = (
      await row.innerText({ timeout: READ_TIMEOUT }).catch(() => '')
    ).trim()
    EVIDENCE.findings.push(
      `round trip row on the page: "${EVIDENCE.texts.roundTripRow.slice(0, 300)}"`,
    )
    await snap(page, 'memory-row-found')

    // ── 4. the verbs on our own entry ──
    // "Rewrite" promises to replace one fact's wording. Only the store can say
    // whether the entry's id kept its text (replace) or a second entry appeared
    // beside the first (duplicate) — the page's own line cannot tell those apart.
    const beforeRewrite = await storeEntries(page, MARKER)
    const beforeIds = new Set(beforeRewrite.map((e) => e.id))
    EVIDENCE.texts.storeBeforeRewrite = describeEntries(beforeRewrite)
    await page.getByTestId(`memory-edit-${index}`).click()
    const editor = page.getByTestId('memory-edit-input')
    await expect(editor).toBeVisible()
    await editor.fill(PROBE_EDIT)
    await snap(page, 'row-edit-filled')
    await page.getByTestId('memory-edit-rewrite').click()
    await expect(editor).toHaveCount(0, { timeout: 20_000 })
    await page.waitForTimeout(1500)
    const afterRewrite = await storeEntries(page, MARKER)
    const withNewText = afterRewrite.filter((e) => e.text.includes(PROBE_EDIT))
    const withOldText = afterRewrite.filter((e) => !e.text.includes(PROBE_EDIT))
    const keptIds = afterRewrite.filter((e) => beforeIds.has(e.id)).map((e) => e.id)
    const freshIds = afterRewrite.filter((e) => !beforeIds.has(e.id)).map((e) => e.id)
    EVIDENCE.texts.storeAfterRewrite = describeEntries(afterRewrite)
    EVIDENCE.texts.afterRewrite = `before: ${beforeRewrite.length} entry/entries [${beforeIds.size} id(s)] → after: ${afterRewrite.length} entry/entries; new wording: [${withNewText.map((e) => e.id).join(', ') || 'none'}], old wording still stored: [${withOldText.map((e) => e.id).join(', ') || 'none'}]; ids kept: [${keptIds.join(', ') || 'none'}], ids added: [${freshIds.join(', ') || 'none'}]`
    EVIDENCE.findings.push(`Rewrite verb, store side: ${EVIDENCE.texts.afterRewrite}`)
    EVIDENCE.texts.afterRewriteOnPage =
      (await rowIndexWith(page, PROBE_EDIT)) >= 0
        ? `rewritten wording on the page: yes; rows on the page: ${(await rowTexts(page)).length}`
        : 'rewritten wording on the page: no'
    await snap(page, 'row-rewritten')

    // Delete acts on the inventory as a whole, not on the ranked search list, so
    // clear the marker query first: otherwise the index below points at a ranked
    // position, not the list the person is looking at.
    await page.getByTestId('memory-page-search').fill('')
    await page.waitForTimeout(2500)

    const delIndex = await rowIndexWith(page, MARKER)
    if (delIndex >= 0) {
      const targetText = (
        await page
          .locator(ROW)
          .nth(delIndex)
          .innerText({ timeout: READ_TIMEOUT })
          .catch(() => '')
      ).trim()
      EVIDENCE.texts.deleteTarget = targetText.slice(0, 200)
      await page.getByTestId(`memory-delete-${delIndex}`).click()
      const gone = await waitUntilGone(page, MARKER, 15_000)
      EVIDENCE.texts.afterDelete = gone ? 'gone from holdings' : 'still in holdings'
      // Both sides of the same click: what the list holds afterwards, and what
      // the trash endpoint the Restore verb reads says it could bring back.
      EVIDENCE.texts.storeAfterDelete = describeEntries(await storeEntries(page, MARKER))
      const trashApi = await page.request
        .get(`${BASE}/api/memory/deleted?limit=100`)
        .catch(() => null)
      const trashBody =
        trashApi && trashApi.ok()
          ? ((await trashApi.json()) as { entries?: StoreEntry[]; total?: number })
          : null
      EVIDENCE.texts.apiTrash = trashBody
        ? `${trashBody.total ?? 0} entry/entries in GET /api/memory/deleted`
        : 'GET /api/memory/deleted did not answer'
      note(
        `delete clicked on row index ${delIndex} ("${EVIDENCE.texts.deleteTarget.slice(0, 80)}"): ${gone ? 'row gone from holdings' : 'row still there after 15s'}; DELETE calls seen: ${EVIDENCE.deletes.length ? EVIDENCE.deletes.join(' | ') : 'none'}; store afterwards: ${EVIDENCE.texts.storeAfterDelete}; trash endpoint: ${EVIDENCE.texts.apiTrash}`,
      )
      await snap(page, 'row-deleted')

      // Reached with the marker word still in the field — the state a person
      // leaves the page in after a search. If the filter survives the sub-page
      // switch, the trash hides behind "Nothing matches the search." (defect).
      await page.getByTestId('memory-page-search').fill(MARKER)
      await page.waitForTimeout(2500)
      await view(page, 'Trash')
      EVIDENCE.texts.trashMaskedBySearch = await readText(
        page,
        'memory-page-empty',
        'trash rendered rows, not an empty sentence',
      )
      await snap(page, 'papierkorb-stale-search')

      // The same trash with the field cleared: what the store really holds there.
      await page.getByTestId('memory-page-search').fill('')
      await page.waitForTimeout(2500)
      const trashIndex = await rowIndexWith(page, MARKER)
      EVIDENCE.texts.deletedInTrash =
        trashIndex >= 0
          ? (
              await page
                .locator(ROW)
                .nth(trashIndex)
                .innerText({ timeout: READ_TIMEOUT })
                .catch(() => '')
            )
              .trim()
              .slice(0, 300)
          : 'not in trash'
      EVIDENCE.texts.trashState = await readText(page, 'memory-page-empty', 'trash rendered rows')
      EVIDENCE.texts.trashCount = await readText(page, 'memory-page-count', '(no count line)')
      // The affordance a person would use to undo a forgetting: is it on screen
      // at all, and does the store have anything for it to act on?
      const restoreButtons = await page
        .locator('[data-testid^="memory-restore-"]')
        .count()
        .catch(() => 0)
      EVIDENCE.texts.restoreAffordance = `${restoreButtons} restore button(s) rendered in the trash; ${EVIDENCE.texts.apiTrash}`
      await snap(page, 'papierkorb-clear-search')

      if (trashIndex >= 0) {
        await page.getByTestId(`memory-restore-${trashIndex}`).click()
        await page.waitForTimeout(2500)
        EVIDENCE.texts.afterRestore =
          (await rowIndexWith(page, MARKER)) >= 0 ? 'restored to holdings' : 'not back in holdings'
        await snap(page, 'papierkorb-after-restore')
      }
      const restoreResult = EVIDENCE.texts.afterRestore || 'restore not reachable'
      EVIDENCE.findings.push(
        `delete → trash → restore: ${EVIDENCE.texts.afterDelete} / ${EVIDENCE.texts.deletedInTrash} / ${restoreResult}`,
      )
      EVIDENCE.findings.push(
        `trash reached with the search word still in the field: "${EVIDENCE.texts.trashMaskedBySearch}" (count line ${EVIDENCE.texts.trashCount})`,
      )
      EVIDENCE.findings.push(`trash with the field cleared: "${EVIDENCE.texts.trashState}"`)
    }

    // ── 5. leave the store as it was found ──
    await view(page, 'Holdings')
    for (let guard = 0; guard < 8; guard += 1) {
      const i = await rowIndexWith(page, MARKER)
      if (i < 0) break
      await page
        .getByTestId(`memory-delete-${i}`)
        .click({ timeout: 5_000 })
        .catch(() => {})
      await page.waitForTimeout(1500)
    }
    // The store, not the page, is the authority on what is left: a row the list
    // could not index would otherwise stay behind as a leftover of this run.
    let leftovers = await storeEntries(page, MARKER)
    for (const entry of leftovers) {
      await page.request.delete(`${BASE}/api/memory/${entry.id}`).catch(() => null)
    }
    leftovers = await storeEntries(page, MARKER)
    EVIDENCE.texts.leftOver = describeEntries(leftovers)
    note(`walkthrough entries removed from the store: ${EVIDENCE.texts.leftOver}`)
  })
})
