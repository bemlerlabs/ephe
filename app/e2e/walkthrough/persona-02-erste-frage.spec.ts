import { test, expect, type Page, type Response } from '@playwright/test'
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { walkthroughOutDir } from './walkthrough-out.ts'

/**
 * User walkthrough, persona 02 — "the first real question".
 *
 * A real person opens Ephe, asks ONE simple question, then follows up. Nothing
 * is mocked: every request goes to the live product server
 * (http://127.0.0.1:8765, which serves app/dist) and through to the real engine
 * (active provider `openai_compatible`, model `deepseek-v4-pro`) — a network
 * round trip that costs a fraction of a cent per turn.
 *
 * This is an OBSERVING walkthrough, not a benchmark. The two wall times it
 * records are a loaded-box observation (author's machine, other work running)
 * and are named as such everywhere they appear.
 *
 * Artifacts this file writes, below its walkthrough capture dir (walkthrough-out.ts;
 * the dated set is docs/media/user-walkthrough-2026-10-12/persona-02-erste-frage/):
 *   NN-*.png
 *   .../timing.json       — per turn: first-token ms + wall ms (loaded-box)
 *   .../observations.json — composer/status-bar/scroll/readability reads,
 *                           visible-streaming samples, console + network evidence
 *
 * Conventional selectors were taken from the source, not guessed:
 *   app/src/components/dashboard/ChatInput.tsx          chat-input, send-btn/stop-btn
 *   app/src/components/dashboard/MessageBubble.tsx      message-bubble + data-role
 *   app/src/components/dashboard/chat/index.tsx         panel-chat, chat-scroll-region
 *   app/src/components/dashboard/StatusBar.tsx          status-bar + its chips
 *   app/src/components/dashboard/bubble/assistantBubble.tsx  .prose, streaming cursor
 *   app/src/components/dashboard/bubble/turnHeadRow.tsx bubble-turn-head
 */

// ── target ──────────────────────────────────────────────────────────────────
// Absolute URL on purpose: the repo's playwright.config.ts points baseURL at the
// Vite dev server (5174). This spec talks to the product server directly.
const LIVE_BASE = process.env.EPHE_LIVE_BASE ?? 'http://127.0.0.1:8765'
const CHAT_URL = `${LIVE_BASE}/#/chat`

// ── persona script ──────────────────────────────────────────────────────────
const QUESTION_1 = 'What is 17 times 23? Answer with the number only.'
const EXPECTED_1 = '391'
const QUESTION_2 = 'Now double that last result. Answer with the number only.'
const EXPECTED_2 = '782'

/**
 * The spec must work whether Playwright runs it from the repo root or from app/.
 * Pick the candidate base that actually contains the app/e2e folder.
 */
function repoRoot(): string {
  const candidates: string[] = []
  try {
    // __dirname exists in Playwright's TS transform (CJS). Guarded: ESM-safe.
    candidates.push(path.resolve(__dirname, '..', '..', '..'))
  } catch {
    /* ESM without __dirname — fall through to cwd candidates */
  }
  candidates.push(
    process.cwd(),
    path.resolve(process.cwd(), '..'),
    path.resolve(process.cwd(), '..', '..'),
  )
  for (const base of candidates) {
    if (existsSync(path.join(base, 'app', 'e2e'))) return base
  }
  return process.cwd()
}

const OUT_DIR = walkthroughOutDir('persona-02-erste-frage')
mkdirSync(OUT_DIR, { recursive: true })

const takenShots: string[] = []

/** Full-page screenshot into the persona directory. Never throws on focus loss. */
async function shot(page: Page, name: string) {
  const file = path.join(OUT_DIR, `${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  takenShots.push(path.relative(repoRoot(), file))
  console.log(`[persona-02] screenshot → ${takenShots[takenShots.length - 1]}`)
}

// ── instrumentation ─────────────────────────────────────────────────────────
interface Evidence {
  consoleErrors: string[]
  consoleWarnings: string[]
  consoleInfos: string[]
  pageErrors: string[]
  failedRequests: string[]
  badResponses: string[]
  streamResponses: string[]
  websockets: string[]
}

function attachEvidence(page: Page): Evidence {
  const ev: Evidence = {
    consoleErrors: [],
    consoleWarnings: [],
    consoleInfos: [],
    pageErrors: [],
    failedRequests: [],
    badResponses: [],
    streamResponses: [],
    websockets: [],
  }
  page.on('console', (msg) => {
    const line = `${msg.type()}: ${msg.text()}`
    if (msg.type() === 'error') ev.consoleErrors.push(line)
    else if (msg.type() === 'warning') ev.consoleWarnings.push(line)
    else ev.consoleInfos.push(line)
  })
  page.on('pageerror', (err) => {
    ev.pageErrors.push(String((err as Error)?.stack ?? err))
  })
  page.on('requestfailed', (req) => {
    ev.failedRequests.push(
      `${req.method()} ${req.url()} — ${req.failure()?.errorText ?? 'unknown failure'}`,
    )
  })
  page.on('response', (res) => {
    const url = res.url()
    const method = res.request().method()
    if (url.includes('/api/chat/stream')) {
      ev.streamResponses.push(`${res.status()} ${method} ${url}`)
    }
    if (res.status() >= 400) ev.badResponses.push(`${res.status()} ${method} ${url}`)
  })
  page.on('websocket', (ws) => ev.websockets.push(ws.url()))
  return ev
}

// ── in-page readers (no assertions, pure observation) ───────────────────────
interface AnswerRead {
  bubbles: number
  text: string
  textLength: number
  usedProse: boolean
  streamingCursor: boolean
  streamingClass: boolean
}

/** Reads the LAST assistant bubble: text, streaming cursor, completed styling. */
async function readAnswer(page: Page): Promise<AnswerRead> {
  return await page.evaluate(() => {
    const bubbles = Array.from(
      document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
    ) as HTMLElement[]
    const last = bubbles[bubbles.length - 1]
    if (!last) {
      return {
        bubbles: 0,
        text: '',
        textLength: 0,
        usedProse: false,
        streamingCursor: false,
        streamingClass: false,
      }
    }
    const prose = last.querySelector('.prose') as HTMLElement | null
    const text = (prose?.textContent ?? last.textContent ?? '').trim()
    return {
      bubbles: bubbles.length,
      text,
      textLength: text.length,
      usedProse: !!prose,
      streamingCursor: !!last.querySelector('span.animate-pulse'),
      // MessageBubble adds `frost-subtle` only once m.streaming is false.
      streamingClass: !last.querySelector('.frost-subtle'),
    }
  })
}

async function readComposer(page: Page) {
  return await page.evaluate(() => {
    const ta = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement | null
    const ring = document.querySelector('[data-testid="composer-context-ring"]')
    const thinking = document.querySelector('[data-testid="composer-thinking-chip"]')
    const statusDot = document.querySelector('[data-testid="composer-status-dot"]')
    const queueBadge = document.querySelector('[data-testid="composer-queue-badge"]')
    return {
      present: !!ta,
      placeholder: ta?.getAttribute('placeholder') ?? null,
      value: ta?.value ?? null,
      readOnly: ta ? ta.hasAttribute('readonly') : null,
      disabled: ta ? ta.disabled : null,
      contextRingVisible: !!ring,
      thinkingChip: (thinking?.textContent ?? '').trim() || null,
      statusDot: statusDot?.getAttribute('aria-label') ?? null,
      queueBadge: (queueBadge?.textContent ?? '').trim() || null,
      sendBtnVisible: !!document.querySelector('[data-testid="send-btn"]'),
      stopBtnVisible: !!document.querySelector('[data-testid="stop-btn"]'),
    }
  })
}

async function readStatusBar(page: Page) {
  return await page.evaluate(() => {
    const pick = (id: string) => {
      const el = document.querySelector(`[data-testid="${id}"]`)
      return el ? (el.textContent ?? '').trim() || null : null
    }
    const meter = document.querySelector('[data-testid="statusbar-meter"]')
    const bar = document.querySelector('[data-testid="status-bar"]') as HTMLElement | null
    return {
      statusBarVisible: !!bar,
      rowText: (bar?.textContent ?? '').replace(/\s+/g, ' ').trim() || null,
      activity: pick('ki-activity'),
      tokensBreakdownToggle: pick('statusbar-breakdown-toggle'),
      tokensChipMobile: pick('statusbar-tok-chip'),
      contextPercent: pick('statusbar-percent'),
      meterTitle: meter?.getAttribute('title') ?? null,
      tokensPerSecond: pick('statusbar-tok-per-sec'),
      cost: pick('statusbar-cost'),
      noPricing: pick('statusbar-no-pricing'),
      cacheShare: pick('statusbar-cache'),
      tokenizer: pick('statusbar-tokenizer-chip'),
    }
  })
}

async function readScroll(page: Page) {
  return await page.evaluate(() => {
    const el = document.querySelector('[data-testid="panel-chat"]') as HTMLElement | null
    if (!el) return null
    const distanceFromBottom = Math.round(el.scrollHeight - el.clientHeight - el.scrollTop)
    const scrollBtn = Array.from(document.querySelectorAll('button')).find((b) => {
      const label = b.getAttribute('aria-label') ?? ''
      return /scroll to bottom|nach unten/i.test(label) // language-gate: ignore (matches the product's own German label beside the English one)
    })
    const rows = document.querySelectorAll('[data-testid="message-row"]').length
    return {
      scrollTop: Math.round(el.scrollTop),
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
      distanceFromBottom,
      pinnedToBottom: distanceFromBottom < 8,
      scrollToBottomButtonVisible: !!scrollBtn,
      renderedMessageRows: rows,
    }
  })
}

/** Assistant bubble readability: font metrics + contrast when measurable. */
async function readReadability(page: Page) {
  return await page.evaluate(() => {
    const bubbles = Array.from(
      document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
    ) as HTMLElement[]
    const last = bubbles[bubbles.length - 1]
    if (!last) return null
    const el = (last.querySelector('.prose') as HTMLElement | null) ?? last
    const cs = getComputedStyle(el)
    const rect = el.getBoundingClientRect()

    const parse = (c: string) => {
      const m = c.match(/rgba?\(([^)]+)\)/)
      if (!m) return null
      const parts = m[1]!.split(',').map((x) => parseFloat(x.trim()))
      return { r: parts[0]!, g: parts[1]!, b: parts[2]!, a: parts.length > 3 ? parts[3]! : 1 }
    }
    const lum = (c: { r: number; g: number; b: number }) => {
      const f = (v: number) => {
        const s = v / 255
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
      }
      return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b)
    }
    const fg = parse(cs.color)
    // Walk up for the first (near-)opaque background.
    let bg: { r: number; g: number; b: number; a: number } | null = null
    let node: HTMLElement | null = el
    while (node) {
      const c = parse(getComputedStyle(node).backgroundColor)
      if (c && c.a >= 0.95) {
        bg = c
        break
      }
      node = node.parentElement
    }
    let contrast: number | null = null
    if (fg && bg) {
      const l1 = lum(fg)
      const l2 = lum(bg)
      const hi = Math.max(l1, l2)
      const lo = Math.min(l1, l2)
      contrast = Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100
    }
    return {
      fontSize: cs.fontSize,
      lineHeight: cs.lineHeight,
      color: cs.color,
      bubbleClassOpaque: !!bg,
      backgroundOpaque: bg
        ? `rgb(${bg.r}, ${bg.g}, ${bg.b})`
        : 'translucent (glass-reading) — contrast not measurable',
      contrastRatio: contrast,
      widthPx: Math.round(rect.width),
      heightPx: Math.round(rect.height),
      textClipped: el.scrollHeight - el.clientHeight > 2,
      textLength: (el.textContent ?? '').trim().length,
    }
  })
}

async function readHeader(page: Page) {
  return await page.evaluate(() => {
    const title = document.querySelector('[data-testid="session-title"]')
    const heads = Array.from(document.querySelectorAll('[data-testid="bubble-turn-head"]')).map(
      (h) => (h.textContent ?? '').replace(/\s+/g, ' ').trim(),
    )
    return {
      sessionTitle: (title?.textContent ?? '').trim() || null,
      turnHeads: heads,
      bubblesTotal: document.querySelectorAll('[data-testid="message-bubble"]').length,
      userBubbles: document.querySelectorAll('[data-testid="message-bubble"][data-role="user"]')
        .length,
      assistantBubbles: document.querySelectorAll(
        '[data-testid="message-bubble"][data-role="assistant"]',
      ).length,
      copyActionVisible: Array.from(document.querySelectorAll('button')).some((b) =>
        /copy message/i.test(b.getAttribute('aria-label') ?? ''),
      ),
      timestamps: Array.from(document.querySelectorAll('[data-testid="message-timestamp"]'))
        .map((t) => (t.textContent ?? '').trim())
        .filter(Boolean),
    }
  })
}

/**
 * The visible-streaming evidence: length of the assistant text sampled on a
 * short cadence until the turn stops streaming. A monotonically growing series
 * is what "the answer streams visibly" looks like from the outside.
 */
async function sampleVisibleStreaming(page: Page, maxMs = 6000, stepMs = 120) {
  const started = Date.now()
  const series: number[] = []
  let streamingCursorSeen = false
  let broke = false
  while (Date.now() - started < maxMs) {
    const read = await readAnswer(page)
    series.push(read.textLength)
    streamingCursorSeen = streamingCursorSeen || read.streamingCursor
    if (!read.streamingCursor) {
      broke = true
      break
    }
    await page.waitForTimeout(stepMs)
  }
  const distinct = Array.from(new Set(series))
  return {
    textLengthSeries: series,
    distinctLengths: distinct.length,
    grewOverTime: distinct.length > 1,
    streamingCursorSeen,
    stoppedStreamingAtMs: broke ? Date.now() - started : null,
  }
}

// ── flow helpers ────────────────────────────────────────────────────────────
/** Waits until the turn finished: send button back, streaming cursor gone. */
async function waitForTurnEnd(page: Page, timeoutMs: number) {
  await expect(page.getByTestId('send-btn')).toBeVisible({ timeout: timeoutMs })
  await expect(
    page
      .locator('[data-testid="message-bubble"][data-role="assistant"]')
      .last()
      .locator('span.animate-pulse'),
  ).toHaveCount(0, { timeout: 15_000 })
}

// ── notes.md runtime block ──────────────────────────────────────────────────
// The hand-written framing in notes.md stays; this block, fenced by markers, is
// replaced on every run with what the run actually observed — including the two
// wall times, so the latency numbers live in the notes and cannot drift from the
// measurement that produced them.
const NOTES_FILE = path.join(OUT_DIR, 'notes.md')
const RT_BEGIN = '<!-- RUNTIME:persona-02 BEGIN -->'
const RT_END = '<!-- RUNTIME:persona-02 END -->'

function list(items: string[], label: string, limit = 40): string[] {
  if (items.length === 0) return [`- ${label}: none`]
  const head = items.slice(0, limit).map((x) => `- ${x}`)
  if (items.length > limit) head.push(`- (+${items.length - limit} more in observations.json)`)
  return head
}

function renderRuntime(
  observations: Record<string, unknown>,
  timing: Record<string, unknown>,
  ev: Evidence,
  shots: string[],
): string {
  const t = timing as {
    firstTokenTurn1Ms?: number
    wallTurn1Ms?: number
    firstTokenTurn2Ms?: number
    wallTurn2Ms?: number
    turn1?: { answerText?: string }
    turn2?: { answerText?: string }
  }
  const o = observations as Record<string, Record<string, unknown> | undefined>
  const ms = (v: number | undefined) => (typeof v === 'number' ? `${v} ms` : 'not measured')

  const lines: string[] = [RT_BEGIN, '']
  lines.push('## Observed at run time')
  lines.push('')
  lines.push(`Run: ${String(observations.startedAt)} → ${String(observations.finishedAt)}.`)
  lines.push('')
  lines.push('### The two turns — loaded-box observation, not a benchmark')
  lines.push('')
  lines.push('| Turn | Question | First token | Turn wall time | Answer the UI showed |')
  lines.push('| --- | --- | --- | --- | --- |')
  lines.push(
    `| 1 | ${QUESTION_1} | ${ms(t.firstTokenTurn1Ms)} | ${ms(t.wallTurn1Ms)} | ${String(t.turn1?.answerText ?? 'not captured')} |`,
  )
  lines.push(
    `| 2 | ${QUESTION_2} | ${ms(t.firstTokenTurn2Ms)} | ${ms(t.wallTurn2Ms)} | ${String(t.turn2?.answerText ?? 'not captured')} |`,
  )
  lines.push('')
  lines.push(
    'Both figures are wall-clock measurements on a loaded box (author machine, other work running) over the network to a hosted engine. They are not a benchmark and must not be quoted as one.',
  )
  lines.push('')
  lines.push('### The task the app opened on — and the reset to a new task')
  lines.push('')
  lines.push(`- restored prior task at open: ${JSON.stringify(o.step01_restoredConversation)}`)
  lines.push(`- after the "New task" control: ${JSON.stringify(o.step01b_newTask?.header)}`)
  lines.push('')
  lines.push('### Defects observed (severity)')
  lines.push('')
  lines.push(
    '- P2 — the chat restores the most recent task from the server mirror on open ' +
      '(initFromDb → restoreFromServer, GET /api/sessions/restore). A person who expects a ' +
      'blank composer instead lands in old history. Not a crash; a first-run/first-impression ' +
      'sharp edge. The walkthrough works around it with the header "New task" control.',
  )
  lines.push(
    `- P3 — the status bar shows no cost figure next to the token count: ` +
      `${JSON.stringify(
        (o.step05_answerComplete?.statusBar as { noPricing?: unknown } | undefined)?.noPricing,
      )} ` +
      `(statusbar-cost = ${JSON.stringify(
        (o.step05_answerComplete?.statusBar as { cost?: unknown } | undefined)?.cost,
      )}). ` +
      'The cost read was therefore ABSENT after turn 1 — not zero, and not a placeholder figure.',
  )
  lines.push('')
  lines.push('### What the composer showed')
  lines.push('')
  lines.push(`- while idle: ${JSON.stringify(o.step01_opened?.composer)}`)
  lines.push(`- while the first answer ran: ${JSON.stringify(o.turn1_firstToken?.read)}`)
  lines.push(
    `- the queue behaviour seen from the composer: ${JSON.stringify(o.step06_followUpTyped?.composer)}`,
  )
  lines.push('')
  lines.push('### What the status bar reported')
  lines.push('')
  lines.push(`- before anything was sent: ${JSON.stringify(o.step01_opened?.statusBar)}`)
  lines.push(`- after turn 1: ${JSON.stringify(o.step05_answerComplete?.statusBar)}`)
  lines.push(`- after turn 2: ${JSON.stringify(o.step07_conversationDone?.statusBar)}`)
  lines.push('')
  lines.push('### Did the answer stream visibly?')
  lines.push('')
  lines.push(`- turn 1: ${JSON.stringify(o.turn1_visibleStreaming)}`)
  lines.push(`- turn 2: ${JSON.stringify(o.turn2_visibleStreaming)}`)
  lines.push('')
  lines.push('### Scroll behaviour')
  lines.push('')
  lines.push(`- when opened: ${JSON.stringify(o.step01_opened?.scroll)}`)
  lines.push(`- after turn 1: ${JSON.stringify(o.step05_answerComplete?.scroll)}`)
  lines.push(`- after turn 2: ${JSON.stringify(o.step07_conversationDone?.scroll)}`)
  lines.push('')
  lines.push('### Readability of the assistant bubble')
  lines.push('')
  lines.push(`- after turn 1: ${JSON.stringify(o.step05_answerComplete?.readability)}`)
  lines.push('')
  lines.push('### The conversation as the UI held it')
  lines.push('')
  lines.push(`- after turn 1: ${JSON.stringify(o.step05_answerComplete?.header)}`)
  lines.push(`- after turn 2: ${JSON.stringify(o.step07_conversationDone?.header)}`)
  lines.push(
    `- session title changed by the follow-up: ${String(observations.sessionTitleChanged)}`,
  )
  lines.push('')
  lines.push('### Console and network evidence')
  lines.push('')
  lines.push(...list(ev.consoleErrors, 'console errors'))
  lines.push(...list(ev.consoleWarnings, 'console warnings'))
  lines.push(...list(ev.pageErrors, 'uncaught page errors'))
  lines.push(...list(ev.failedRequests, 'failed requests'))
  lines.push(...list(ev.badResponses, 'HTTP >= 400'))
  lines.push(...list(ev.streamResponses, 'POST /api/chat/stream responses', 10))
  lines.push(
    `- websocket connections: ${ev.websockets.length === 0 ? 'none' : ev.websockets.join(', ')}`,
  )
  lines.push('')
  lines.push('### Screenshots written by this run')
  lines.push('')
  lines.push(...(shots.length === 0 ? ['- none'] : shots.map((s) => `- \`${s}\``)))
  lines.push('')
  lines.push(
    'Machine-readable copies of everything above: `observations.json` and `timing.json` in this directory.',
  )
  lines.push('')
  lines.push(RT_END)
  return lines.join('\n')
}

function writeRuntimeBlock(block: string) {
  let md = ''
  try {
    md = readFileSync(NOTES_FILE, 'utf8')
  } catch {
    md = '# Persona 02\n'
  }
  const begin = md.indexOf(RT_BEGIN)
  const end = md.indexOf(RT_END)
  const next =
    begin >= 0 && end > begin
      ? md.slice(0, begin) + block + md.slice(end + RT_END.length)
      : `${md.trimEnd()}\n\n${block}\n`
  writeFileSync(NOTES_FILE, next)
}

// ── the walkthrough ─────────────────────────────────────────────────────────
test.describe('user walkthrough — persona 02, first real question (live engine)', () => {
  test.setTimeout(300_000) // two live turns over the network

  test('simple question, then a follow-up in the same conversation', async ({ page }) => {
    const ev = attachEvidence(page)
    const observations: Record<string, unknown> = {
      spec: 'app/e2e/walkthrough/persona-02-erste-frage.spec.ts',
      persona: 'simple, real question — first message ever sent by this user',
      liveBase: LIVE_BASE,
      chatUrl: CHAT_URL,
      viewport: { width: 1440, height: 900 },
      startedAt: new Date().toISOString(),
      statusOfThisFile:
        'observations.json is machine-written by the run; notes.md carries the human reading',
    }
    const timing: Record<string, unknown> = {
      note: 'Loaded-box observation on the author machine (other work running), two network turns against the live engine. NOT a benchmark.',
    }

    try {
      // ── step 01: open the chat, English UI pinned (locale choice is a user
      //    setting, not a backend mock — the server answers for real)
      await page.addInitScript(() => {
        localStorage.setItem('i18nextLng', 'en')
      })
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded' })

      // App.tsx routes "/" and "/chat" through GateRoute: an unconfigured engine
      // lands on #/setup instead of the chat. That is a finding, not a hiccup.
      try {
        await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 30_000 })
      } catch {
        const blockedRel = '00-blocked-no-composer.png'
        await page.screenshot({ path: path.join(OUT_DIR, blockedRel), fullPage: true })
        takenShots.push(blockedRel)
        observations.step01_blocked = {
          url: page.url(),
          bodyText: (await page.evaluate(() => document.body.innerText)).slice(0, 2000),
        }
        throw new Error(
          `no chat composer at ${page.url()} — a setup/first-run gate is in the way (see 00-blocked-no-composer.png)`,
        )
      }
      // A first-run dialog can steal focus; Escape closes overlays and is a no-op
      // otherwise. Recorded, not assumed.
      await page.keyboard.press('Escape')
      await page.waitForTimeout(400)

      const firstPaintHeader = await readHeader(page)
      observations.step01_opened = {
        composer: await readComposer(page),
        statusBar: await readStatusBar(page),
        header: firstPaintHeader,
        scroll: await readScroll(page),
      }
      await shot(page, '01-chat-opened')

      // ── step 01a: the boot-time restore is ASYNC and can land well after the
      //    first paint — even after the user has already begun to interact. On
      //    boot the store runs initFromDb → restoreFromServer
      //    (GET /api/sessions/restore); the request is in flight while an empty
      //    task is already on screen. Wait until the restore calls have gone
      //    quiet, otherwise a late restore hijacks the active session mid-run
      //    (observed on a prior run: an empty "Ephe" task at first paint,
      //    replaced by old history only after the first message was sent).
      {
        let lastRestoreAt = 0
        let restoreCount = 0
        const onRestore = (r: Response) => {
          if (r.url().includes('/api/sessions/restore')) {
            lastRestoreAt = Date.now()
            restoreCount += 1
          }
        }
        page.on('response', onRestore)
        const waitStart = Date.now()
        try {
          while (Date.now() - waitStart < 20_000) {
            if (lastRestoreAt !== 0 && Date.now() - lastRestoreAt > 1500) break
            if (lastRestoreAt === 0 && Date.now() - waitStart > 6000) break
            await page.waitForTimeout(200)
          }
        } finally {
          page.off('response', onRestore)
        }
        observations.step01_restoreWait = {
          note: 'waited until GET /api/sessions/restore had gone quiet before reading the screen',
          restoreResponsesSeen: restoreCount,
          waitedMs: Date.now() - waitStart,
        }
      }

      // The task the app settled on after the restore — recorded, not assumed.
      const restored = await readHeader(page)
      observations.step01_restoredConversation = {
        note: 'the task the app settled on after the boot restore',
        sessionTitle: restored.sessionTitle,
        bubblesTotal: restored.bubblesTotal,
        userBubbles: restored.userBubbles,
        assistantBubbles: restored.assistantBubbles,
        racedFirstPaint:
          restored.bubblesTotal !== firstPaintHeader.bubblesTotal ||
          restored.sessionTitle !== firstPaintHeader.sessionTitle,
      }

      // A real user starts a NEW task (header "New task" control; ⌘N does the
      // same) — the only way a "first message ever" exists in a product that
      // keeps history. The reset is verified and retried: a late second restore
      // can repopulate the transcript, so "empty" is checked to STAY empty
      // before anything is typed.
      const newTaskBtn = page.getByTestId('header-new-session')
      await expect(newTaskBtn).toBeVisible({ timeout: 10_000 })
      const bubbles = page.locator('[data-testid="message-bubble"]')
      let resetVerified = false
      for (let attempt = 0; attempt < 3 && !resetVerified; attempt += 1) {
        await newTaskBtn.click()
        await expect(bubbles).toHaveCount(0, { timeout: 10_000 })
        await expect(page.getByTestId('chat-input')).toHaveValue('', { timeout: 10_000 })
        await page.waitForTimeout(900)
        resetVerified = (await bubbles.count()) === 0
      }
      expect(resetVerified, 'the new task stayed empty').toBe(true)

      observations.step01b_newTask = {
        composer: await readComposer(page),
        statusBar: await readStatusBar(page),
        header: await readHeader(page),
        scroll: await readScroll(page),
      }
      await shot(page, '02-new-task-empty')

      // ── step 02: type the question
      const composerBefore = page.getByTestId('chat-input')
      await composerBefore.click()
      await composerBefore.fill(QUESTION_1)
      const sendBtn = page.getByTestId('send-btn')
      await expect(sendBtn).toBeEnabled({ timeout: 10_000 })
      observations.step02_typed = {
        question: QUESTION_1,
        composer: await readComposer(page),
        sendButtonEnabled: await sendBtn.isEnabled(),
      }
      await shot(page, '03-question-typed')

      // ── step 03: send, and clock the first token (loaded-box observation)
      const turn1Start = Date.now()
      await sendBtn.click()

      let stopButtonSeenAtMs: number | null = null
      try {
        await expect(page.getByTestId('stop-btn')).toBeVisible({ timeout: 20_000 })
        stopButtonSeenAtMs = Date.now() - turn1Start
      } catch {
        stopButtonSeenAtMs = null // recorded, not swallowed
      }

      await page.waitForFunction(
        () => {
          const bubbles = Array.from(
            document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
          ) as HTMLElement[]
          const last = bubbles[bubbles.length - 1]
          return !!last && (last.textContent ?? '').trim().length > 0
        },
        undefined,
        { timeout: 120_000 },
      )
      const firstTokenMs = Date.now() - turn1Start
      const firstTokenRead = await readAnswer(page)
      // Mirrored immediately: a later failure must not cost the measurement.
      timing.firstTokenTurn1Ms = firstTokenMs

      observations.turn1_firstToken = {
        firstTokenMsLoadedBoxObservation: firstTokenMs,
        stopButtonSeenAtMs,
        read: firstTokenRead,
      }
      await shot(page, '04-answer-first-chunk')

      // ── step 04: is the answer streaming visibly? sample the text length.
      observations.turn1_visibleStreaming = await sampleVisibleStreaming(page)
      await shot(page, '05-answer-streaming')

      // ── step 05: the answer is done — wait for the turn to end.
      await waitForTurnEnd(page, 120_000)
      const turn1WallMs = Date.now() - turn1Start
      timing.wallTurn1Ms = turn1WallMs

      const finalAnswer = await readAnswer(page)
      timing.turn1 = {
        question: QUESTION_1,
        expected: EXPECTED_1,
        firstTokenMsLoadedBoxObservation: firstTokenMs,
        stopButtonSeenAtMs,
        turnWallMsLoadedBoxObservation: turn1WallMs,
        answerText: finalAnswer.text,
        answerLength: finalAnswer.textLength,
      }

      observations.step05_answerComplete = {
        answer: finalAnswer.text,
        composer: await readComposer(page),
        statusBar: await readStatusBar(page),
        header: await readHeader(page),
        scroll: await readScroll(page),
        readability: await readReadability(page),
      }
      await shot(page, '06-answer-complete')

      // ── assertions for turn 1: the experience actually worked
      expect(finalAnswer.text, 'the answer must contain the product 17×23 = 391').toContain(
        EXPECTED_1,
      )
      expect(finalAnswer.streamingCursor).toBe(false)
      expect(
        observations.turn1_visibleStreaming &&
          (observations.turn1_visibleStreaming as { streamingCursorSeen: boolean })
            .streamingCursorSeen,
        'no streaming cursor was ever observed — the turn did not visibly stream',
      ).toBe(true)
      const afterTurn1Header = await readHeader(page)
      expect(afterTurn1Header.userBubbles, 'exactly one user bubble after one message').toBe(1)
      expect(
        afterTurn1Header.assistantBubbles,
        'exactly one assistant bubble after one message',
      ).toBe(1)
      expect(afterTurn1Header.copyActionVisible, 'a finished bubble offers its copy action').toBe(
        true,
      )

      // ── step 06: the follow-up — does the conversation continue in context?
      const statusBeforeFollowUp = await readStatusBar(page)
      const followUpComposer = page.getByTestId('chat-input')
      await followUpComposer.click()
      await followUpComposer.fill(QUESTION_2)
      observations.step06_followUpTyped = {
        question: QUESTION_2,
        statusBarBefore: statusBeforeFollowUp,
        composer: await readComposer(page),
      }
      await shot(page, '07-follow-up-typed')

      // The clock starts on the click, exactly like turn 1 — never around a screenshot.
      const turn2Start = Date.now()
      await page.getByTestId('send-btn').click()
      let stop2SeenAtMs: number | null = null
      try {
        await expect(page.getByTestId('stop-btn')).toBeVisible({ timeout: 20_000 })
        stop2SeenAtMs = Date.now() - turn2Start
      } catch {
        stop2SeenAtMs = null
      }

      await page.waitForFunction(
        () => {
          const bubbles = Array.from(
            document.querySelectorAll('[data-testid="message-bubble"][data-role="assistant"]'),
          ) as HTMLElement[]
          if (bubbles.length < 2) return false
          const last = bubbles[bubbles.length - 1]
          return (last?.textContent ?? '').trim().length > 0
        },
        undefined,
        { timeout: 120_000 },
      )
      const secondFirstTokenMs = Date.now() - turn2Start
      timing.firstTokenTurn2Ms = secondFirstTokenMs
      observations.turn2_firstToken = {
        firstTokenMsLoadedBoxObservation: secondFirstTokenMs,
        stopButtonSeenAtMs: stop2SeenAtMs,
        read: await readAnswer(page),
      }
      await shot(page, '08-follow-up-streaming')

      observations.turn2_visibleStreaming = await sampleVisibleStreaming(page)

      await waitForTurnEnd(page, 120_000)
      const turn2WallMs = Date.now() - turn2Start
      timing.wallTurn2Ms = turn2WallMs
      const secondAnswer = await readAnswer(page)

      timing.turn2 = {
        question: QUESTION_2,
        expected: EXPECTED_2,
        firstTokenMsLoadedBoxObservation: secondFirstTokenMs,
        stopButtonSeenAtMs: stop2SeenAtMs,
        turnWallMsLoadedBoxObservation: turn2WallMs,
        answerText: secondAnswer.text,
        answerLength: secondAnswer.textLength,
      }

      observations.step07_conversationDone = {
        header: await readHeader(page),
        statusBar: await readStatusBar(page),
        scroll: await readScroll(page),
        readability: await readReadability(page),
        composer: await readComposer(page),
      }
      await shot(page, '09-conversation-complete')

      // ── assertions for turn 2: context continued, no bubble duplication
      expect(secondAnswer.text, 'the follow-up answer must contain 391×2 = 782').toContain(
        EXPECTED_2,
      )
      const afterTurn2Header = await readHeader(page)
      expect(afterTurn2Header.userBubbles, 'two user bubbles after two messages').toBe(2)
      expect(afterTurn2Header.assistantBubbles, 'two assistant bubbles after two messages').toBe(2)
      observations.sessionTitleAfterFirstMessage = afterTurn1Header.sessionTitle
      observations.sessionTitleAfterFollowUp = afterTurn2Header.sessionTitle
      observations.sessionTitleChanged =
        afterTurn1Header.sessionTitle !== afterTurn2Header.sessionTitle

      expect(ev.pageErrors, `uncaught page errors: ${ev.pageErrors.join(' | ')}`).toHaveLength(0)
    } finally {
      // ── always leave the evidence behind, even when an assertion failed
      observations.finishedAt = new Date().toISOString()
      observations.screenshots = takenShots
      observations.evidence = ev
      writeFileSync(path.join(OUT_DIR, 'observations.json'), JSON.stringify(observations, null, 2))
      writeFileSync(path.join(OUT_DIR, 'timing.json'), JSON.stringify(timing, null, 2))
      // The measured facts, including the two wall times, land in notes.md itself.
      writeRuntimeBlock(renderRuntime(observations, timing, ev, takenShots))

      console.log(`\n[persona-02] WALKTHROUGH_TIMING ${JSON.stringify(timing)}`)
      console.log(
        `[persona-02] console errors: ${ev.consoleErrors.length}, page errors: ${ev.pageErrors.length}, ` +
          `failed requests: ${ev.failedRequests.length}, HTTP >=400: ${ev.badResponses.length}, ` +
          `websockets: ${ev.websockets.length}`,
      )
      for (const line of ev.consoleErrors) console.log(`[persona-02] console.error: ${line}`)
      for (const line of ev.failedRequests) console.log(`[persona-02] requestfailed: ${line}`)
      for (const line of ev.badResponses) console.log(`[persona-02] http>=400: ${line}`)
      for (const line of ev.streamResponses) console.log(`[persona-02] chat/stream: ${line}`)

      await test.info().attach('observations.json', {
        body: JSON.stringify(observations, null, 2),
        contentType: 'application/json',
      })
      await test.info().attach('timing.json', {
        body: JSON.stringify(timing, null, 2),
        contentType: 'application/json',
      })
      test.info().annotations.push({
        type: 'timing',
        description: `loaded-box observation: turn1 first token ${String(timing.firstTokenTurn1Ms)} ms / wall ${String(timing.wallTurn1Ms)} ms; turn2 first token ${String(timing.firstTokenTurn2Ms)} ms / wall ${String(timing.wallTurn2Ms)} ms`,
      })
    }
  })
})
