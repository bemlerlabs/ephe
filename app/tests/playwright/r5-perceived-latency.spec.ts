import { expect, test, type Page } from '@playwright/test'
import {
  startAppFixture,
  type AppFixture,
  type FixtureKind,
  type FixtureRequest,
} from './appFixture'
import { readFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// UI 4x programme, wave 3 (docs/UI_4X_PROGRAM_2026-10-11.md §3.3): perceived latency on the
// UI side. The deliverable is the SPLIT first, because :146 defers the fourfold claim until
// that number exists: "the honest 4x is on our own share, and today we cannot state our
// share at all". Then four figures: TTFT, first painted token after send, gesture-to-paint
// for the composer, and the cold first-run path. Single falling value: p95 of the
// client-side share of the wait.
//
// The engine leg is a fixture, not the product port. Port 8765 belongs to the visual-baseline
// lane, so this file starts its own server on an OS-assigned free port, serves the current
// app/dist unchanged, and answers POST /api/chat/stream with an SSE body whose first content
// chunk arrives a known ENGINE_MS after the request. That is what turns the split into a
// statement: the upstream leg is a constant we set, so whatever else the wait contains is
// ours. No claim about the real engine's rate comes out of this file; the live TTFT budget
// stays in docs/LATENCY_BUDGETS.md and tests/test_r25_latency_budgets.py. The same fixture
// is why the first-run lane can run tonight: §3.3 asks that it not run while the cohort owns
// ~/.ephe, and this server touches no config dir — it serves the bundle and answers JSON.
//
// Legs of one wait, each anchored on one clock:
//   wire      fetch() to the first byte the app reads (request flight, fixture accept, the
//             app's own reader construction) — it falls inside the upstream window below
//   engine    the fixture's measured gap from its first write to the first content chunk, on
//             the server clock: the upstream leg, and the only part the surface cannot own
//   render    the chunk read to the next frame timestamp after the answer text appeared — the
//             rAF batcher (components/dashboard/chat/model.ts:890), React, layout
//   ours      painted-after-send minus engine: what the user waits on top of the upstream leg.
//             This is the falling value §3.3 names (p95 of the client-side share).
// wire and render are not additive to ours: the page idles while the fixture waits, so the
// wire leg costs nothing beyond the engine window, while render is waited for. `skew` reports
// that overlap instead of hiding it.
//
// What this instrument cannot see, stated where it matters: the render leg ends at the next
// frame *timestamp*, and the rAF clock of this lane is a BeginFrame clock (wave 2 measured
// it: host load moved the idle mean by 0.01 ms), so render is bounded by one synthetic frame
// here. A real display pipeline would add compositor and GPU time this file cannot price.
//
// Gates are the repo's own cited bars, docs/UI_4X_PROGRAM_2026-10-11.md:134 — Nielsen 0.1 s
// and 1 s, INP p75 200 ms. No threshold is invented here, and every figure is logged before
// it is judged.
//
// The serial segment is configuration rather than habit: this file runs under
// tests/playwright/latency.config.ts (workers: 1, fullyParallel: false, no webServer), because
// playwright.config.ts belongs to the visual-baseline lane and a timing figure taken next to
// another lane's screenshots is not comparable to anything. Quote the host load beside any
// number; a wall-clock ceiling measured while another worker is busy measures the machine, the
// defect tests/test_wall_clock_budgets.py describes for the Python side of this class.

const DIST_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../dist')
const ENGINE_MS = Number(process.env.EPHE_LATENCY_ENGINE_MS ?? 400)
const TURNS = Number(process.env.EPHE_LATENCY_TURNS ?? 21)
const GESTURES = Number(process.env.EPHE_LATENCY_GESTURES ?? 21)
const FIRST_RUN_SAMPLES = Number(process.env.EPHE_LATENCY_FIRST_RUN_SAMPLES ?? 5)
const FIRST_LOAD_SAMPLES = Number(process.env.EPHE_LATENCY_FIRST_LOAD_SAMPLES ?? 5)
const PLAN_SAMPLES = Number(process.env.EPHE_LATENCY_PLAN_SAMPLES ?? 3)
// Set by tests/playwright/latency.config.ts. Without it the spec is being picked up by the
// shared lane, where it would add a timing run to a screenshot run.
const OWN_LANE = process.env.EPHE_LATENCY_LANE === '1'

const NIELSEN_INSTANT_MS = 100 // the 0.1 s limit, cited above
const NIELSEN_FLOW_MS = 1000 // the 1 s limit, same row
const INP_P75_MS = 200 // INP at p75, same row
// Row 9 of docs/PLAN_SURFACE_2026-10-11.md: the first readable plan line is on screen within 3 s
// of the engine emitting it. The budget is that row's own number.
const PLAN_READABLE_MS = 3000

// The answer a plan-mode turn gives — the block core/ephe_plan.py renders, split so the first
// chunk already carries a whole step line. A step line with words in it is what makes the card
// readable, so the instrument can anchor on the chunk that carries one.
const PLAN_CHUNKS = [
  '## Plan\n- [ ] Read the two route files the request names\n',
  '- [ ] Add the failing case to the existing pytest family\n',
  '- [ ] Change the handler and keep the response shape\n',
]

const CHAT_PANEL = '[data-testid="panel-chat"]'
const CHAT_INPUT = '[data-testid="chat-input"]'
const SLASH_MENU = '[data-testid="slash-menu"]'

type TurnRecord = {
  turnStartMs: number
  firstByteMs: number | null
  firstChunkMs: number | null
}

type PaintRecord = { mutationMs: number; frameMs: number }

type GestureRecord = {
  keyDownMs: number
  menuMutationMs: number
  menuFrameMs: number
  eventDurationMs: number | null
  eventDelayMs: number | null
  eventProcessingMs: number | null
}

type ProbeSummary = {
  turns: TurnRecord[]
  paints: PaintRecord[]
  gestures: GestureRecord[]
  plans: PaintRecord[]
  loafMs: number
  loafFrames: number
}

let fixtures: AppFixture[] = []

// What the fixture itself did, on its own clock: when a page leg stalls, this says whether
// the bytes were never written or only never read. Two very different bugs look the same
// from the page.
const fixtureMarks: string[] = []
// Every route the bundle asked for, per fixture. The boot path's own round trips are a
// count, which is the one figure here a loaded box cannot move.
const fixtureRequests: Record<FixtureKind, FixtureRequest[]> = { chat: [], 'first-run': [] }
// The injected leg measured on the server clock (first write to first content write), not
// assumed from the constant: a setTimeout fires late by its own jitter, and anchoring the
// plumbing leg on the nominal value pushed that leg negative (-7.7 ms, measured).
const fixtureGaps: number[] = []

// Runs in the page. Everything is one clock: a fetch wrapper for the arrival instants, one
// mutation watcher for the DOM and frame instants, Event Timing for the browser's own number.
// The window key is a literal because a serialized page function cannot see module scope.
function installLatencyProbe() {
  const turns: {
    turnStartMs: number
    firstByteMs: number | null
    firstChunkMs: number | null
  }[] = []
  const paints: { mutationMs: number; frameMs: number }[] = []
  // The plan card's own paint (row 9 of docs/PLAN_SURFACE_2026-10-11.md). The predicate reads the
  // first step row rather than the card element: the element arrives with the heading and a step
  // number before any line has words in it, and a mark alone is not something the reader reads.
  const plans: { mutationMs: number; frameMs: number }[] = []
  const planLineReadable = () => {
    const line = document.querySelector('[data-testid="plan-item-0"]')
    return (line?.textContent ?? '').replace(/[^A-Za-z]/g, '').length >= 4
  }
  const gestures: {
    keyDownMs: number
    menuMutationMs: number
    menuFrameMs: number
    eventDurationMs: number | null
    eventDelayMs: number | null
    eventProcessingMs: number | null
  }[] = []
  const loaf: { durationMs: number; blockingMs: number }[] = []

  // A watch asks a predicate about the DOM. React adds the answer paragraph as a subtree, so
  // record.target and record.addedNodes both sit ABOVE the block that carries the text, and a
  // selector match on the record misses the change being waited for. The baseline is the
  // assistant text already on screen, so turn 2 cannot be satisfied by turn 1's answer.
  const assistantBlockChars = () => {
    let total = 0
    const blocks = document.querySelectorAll(
      '[data-testid="message-bubble"][data-role="assistant"] [data-testid="stream-text-block"]',
    )
    for (const block of Array.from(blocks)) total += (block.textContent ?? '').trim().length
    return total
  }
  const menuPresent = () => Boolean(document.querySelector('[data-testid="slash-menu"]'))

  type Pending =
    | { kind: 'paint'; baseline: number }
    | { kind: 'plan' }
    | {
        kind: 'gesture'
        sample: {
          keyDownMs: number
          menuMutationMs: number
          menuFrameMs: number
          eventDurationMs: number | null
          eventDelayMs: number | null
          eventProcessingMs: number | null
        }
      }
  let pending: Pending | null = null

  const now = () => performance.now()
  const nextFrame = () => new Promise<number>((done) => requestAnimationFrame(() => done(now())))

  const fulfilled = () => {
    if (!pending) return false
    if (pending.kind === 'plan') return planLineReadable()
    return pending.kind === 'paint' ? assistantBlockChars() > pending.baseline : menuPresent()
  }

  // The observer watches `document` itself. An init script runs at document start, where
  // document.documentElement can still be null and the whole probe would abort.
  new MutationObserver(() => {
    if (!fulfilled()) return
    const mutationMs = now()
    const armed = pending
    pending = null
    void nextFrame().then((frameMs) => {
      if (armed.kind === 'paint') {
        paints.push({ mutationMs, frameMs })
        return
      }
      if (armed.kind === 'plan') {
        plans.push({ mutationMs, frameMs })
        return
      }
      armed.sample.menuMutationMs = mutationMs
      armed.sample.menuFrameMs = frameMs
      gestures.push(armed.sample)
    })
  }).observe(document, { childList: true, subtree: true, characterData: true })

  document.addEventListener(
    'keydown',
    (event) => {
      if (pending?.kind === 'gesture' && !pending.sample.keyDownMs && event.key === '/') {
        pending.sample.keyDownMs = now()
      }
    },
    true,
  )

  // Event Timing is the browser's own reading of the same interaction: input delay,
  // processing and the duration INP is built from. A gesture under the engine's reporting
  // floor yields no entry, and the frame measurement above still stands — the log line
  // prints how many entries arrived so that blindness stays visible.
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name !== 'keydown' || pending?.kind !== 'gesture') continue
        const timed = entry as PerformanceEntry & {
          processingStart: number
          processingEnd: number
        }
        pending.sample.eventDurationMs = Math.round(entry.duration)
        pending.sample.eventDelayMs = Math.round(timed.processingStart - entry.startTime)
        pending.sample.eventProcessingMs = Math.round(timed.processingEnd - timed.processingStart)
      }
    }).observe({ type: 'event', durationThreshold: 16 } as PerformanceObserverInit)
  } catch {
    // Event Timing is Chromium-only.
  }

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const wide = entry as PerformanceEntry & { blockingDuration?: number }
        loaf.push({
          durationMs: Math.round(entry.duration),
          blockingMs: Math.round(wide.blockingDuration ?? 0),
        })
      }
    }).observe({ type: 'long-animation-frame', buffered: false })
  } catch {
    // long-animation-frame is Chromium-only.
  }

  // Bound to window: fetch called with a bare receiver throws "Illegal invocation", and an
  // init script that swallows the stream makes every leg read as a missing paint.
  const nativeFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : String(input)
    const started = now()
    const response = await nativeFetch(input as RequestInfo, init)
    if (!url.includes('/api/chat/stream') || !response.body) return response
    const record = { turnStartMs: started, firstByteMs: null, firstChunkMs: null }
    turns.push(record)
    const source = response.body.getReader()
    const decoder = new TextDecoder()
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { done, value } = await source.read()
        if (done) {
          controller.close()
          return
        }
        controller.enqueue(value)
        if (record.firstByteMs === null) record.firstByteMs = now()
        if (record.firstChunkMs === null) {
          const text = decoder.decode(value, { stream: true })
          if (text.includes('"type":"chunk"')) record.firstChunkMs = now()
        }
      },
      cancel(reason) {
        return source.cancel(reason)
      },
    })
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  }

  ;(window as unknown as Record<string, unknown>).__pl = {
    counts: () => ({
      turns: turns.length,
      paints: paints.length,
      gestures: gestures.length,
      plans: plans.length,
    }),
    summary: () => ({
      turns,
      paints,
      gestures,
      plans,
      loafMs: loaf.reduce((total, entry) => total + entry.durationMs, 0),
      loafFrames: loaf.length,
    }),
    armPlan: () => {
      pending = { kind: 'plan' }
    },
    armPaint: () => {
      pending = { kind: 'paint', baseline: assistantBlockChars() }
    },
    armGesture: () => {
      pending = {
        kind: 'gesture',
        sample: {
          keyDownMs: 0,
          menuMutationMs: 0,
          menuFrameMs: 0,
          eventDurationMs: null,
          eventDelayMs: null,
          eventProcessingMs: null,
        },
      }
    },
  }
}

type WindowProbe = {
  armPaint(): void
  armPlan(): void
  armGesture(): void
  counts(): { turns: number; paints: number; gestures: number; plans: number }
  summary(): ProbeSummary
}

// Waits on the probe's own counters so a stall names the leg that did not record, instead of
// a 30 s timeout that says only "something never happened".
async function waitForProbeCounts(
  page: Page,
  want: Partial<{ turns: number; paints: number; gestures: number; plans: number }>,
  timeoutMs = 30_000,
) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const counts = await page.evaluate(() => (window as unknown as WindowProbe).__pl.counts())
    const enough =
      (want.turns === undefined || counts.turns >= want.turns) &&
      (want.paints === undefined || counts.paints >= want.paints) &&
      (want.gestures === undefined || counts.gestures >= want.gestures) &&
      (want.plans === undefined || counts.plans >= want.plans)
    if (enough) return counts
    if (Date.now() > deadline) {
      const state = await page.evaluate(() => ({
        assistantBlocks: Array.from(
          document.querySelectorAll(
            '[data-testid="message-bubble"][data-role="assistant"] [data-testid="stream-text-block"]',
          ),
        ).map((block) => (block.textContent ?? '').trim().slice(0, 24)),
        anyBlock: document.querySelectorAll('[data-testid="stream-text-block"]').length,
        bubbles: document.querySelectorAll('[data-testid="message-bubble"]').length,
        lastBubble: (() => {
          const bubbles = document.querySelectorAll('[data-testid="message-bubble"]')
          const last = bubbles[bubbles.length - 1]
          return `${last?.getAttribute('data-role') ?? 'none'}: ${(last?.textContent ?? '')
            .trim()
            .slice(0, 80)}`
        })(),
      }))
      const turn = await page.evaluate(
        () => (window as unknown as WindowProbe).__pl.summary().turns.slice(-1)[0],
      )
      const frames = await page.evaluate(
        () =>
          new Promise<number>((done) => {
            let count = 0
            const start = performance.now()
            const tick = (stamp: number) => {
              count += 1
              if (stamp - start >= 500) done(count)
              else requestAnimationFrame(tick)
            }
            requestAnimationFrame(tick)
          }),
      )
      throw new Error(
        `probe stalled: wanted ${JSON.stringify(want)}, counts ${JSON.stringify(counts)}, ` +
          `turn ${JSON.stringify(turn)}, fixtureWrites=[${fixtureMarks.slice(-6).join(' ')}], ` +
          `framesIn500ms=${frames}, dom ${JSON.stringify(state)}`,
      )
    }
    await page.waitForTimeout(100)
  }
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) return Number.NaN
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.max(0, Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1))
  return Number((sorted[index] ?? 0).toFixed(1))
}

function legLine(name: string, values: number[]): string {
  if (values.length === 0) {
    console.log(`r5-latency figure=${name} n=0 (no entry from this channel)`)
    return ''
  }
  const line =
    `r5-latency figure=${name} n=${values.length} ` +
    `min=${percentile(values, 0)} p50=${percentile(values, 50)} ` +
    `p75=${percentile(values, 75)} p95=${percentile(values, 95)} max=${percentile(values, 100)}`
  console.log(line)
  return line
}

test.describe.configure({ mode: 'serial' })

test.describe('R5 perceived latency', () => {
  test.skip(
    !OWN_LANE,
    'wave 3 runs under -c tests/playwright/latency.config.ts, not the shared lane',
  )
  test.setTimeout(240_000)

  test.beforeAll(async () => {
    // The built bundle is priced here and never rebuilt by this file: two other lanes hold
    // the right to app/dist and to :8765 tonight.
    await readFile(join(DIST_ROOT, 'index.html'))
    for (const kind of ['chat', 'first-run'] as FixtureKind[]) {
      const started = await startAppFixture({
        kind,
        engineMs: ENGINE_MS,
        gaps: fixtureGaps,
        marks: fixtureMarks,
        // Every request the bundle made, in arrival order: the boot round trips are a
        // count, and a count does not care how loaded the box is.
        requests: fixtureRequests[kind],
      })
      fixtures.push({ kind, ...started })
      console.log(
        `r5-latency FIXTURE kind=${kind} origin=${started.origin} port=${started.port} ` +
          `pid=${started.pid} engineMs=${ENGINE_MS} turns=${TURNS} gestures=${GESTURES} ` +
          `dist=${DIST_ROOT}`,
      )
    }
  })

  test.afterAll(async () => {
    const closing = fixtures
    fixtures = []
    for (const entry of closing) {
      await entry.close()
      console.log(
        `r5-latency FIXTURE-CLOSED kind=${entry.kind} port=${entry.port} pid=${entry.pid}`,
      )
    }
  })

  function originOf(kind: FixtureKind): string {
    const entry = fixtures.find((candidate) => candidate.kind === kind)
    if (!entry) throw new Error(`the ${kind} fixture is the only server this file talks to`)
    return entry.origin
  }

  async function openChat(page: Page, origin = originOf('chat')) {
    // An app error invalidates a latency figure, so the lane's own errors are printed
    // instead of being silently averaged into one.
    page.on('pageerror', (error) =>
      console.log(`r5-latency PAGEERROR ${String(error).slice(0, 200)}`),
    )
    page.on('console', (message) => {
      if (message.type() === 'error') {
        console.log(`r5-latency CONSOLE-ERROR ${message.text().slice(0, 200)}`)
      }
    })
    await page.addInitScript(installLatencyProbe)
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'de')
      localStorage.setItem('ephe_onboarded', '1')
      localStorage.setItem('ephe.intro.seen.v1', '1')
    })
    await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_PANEL, { timeout: 15_000 })
    await page.waitForTimeout(300)
  }

  test('the split of one wait: the upstream leg and our share of it', async ({ browser }) => {
    const wire: number[] = []
    const ttft: number[] = []
    const painted: number[] = []
    const skew: number[] = []
    const render: number[] = []
    const ours: number[] = []
    const engine: number[] = []
    let loafFrames = 0
    let loafMs = 0

    // One fresh context per turn. Twenty-one turns inside one session stopped being a
    // measurement of the first painted token: after about ten turns the built bundle keeps
    // the newest assistant bubble out of the DOM (the store holds the answer, the bubble
    // list does not show it), so the paint leg has nothing to observe. A turn of its own is
    // also what the figure describes: the wait of a user who just opened the app.
    for (let turn = 0; turn < TURNS; turn += 1) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
      const page = await context.newPage()
      await openChat(page)
      const gapIndex = fixtureGaps.length
      await page.evaluate(() => (window as unknown as WindowProbe).__pl.armPaint())
      await page.locator(CHAT_INPUT).fill('latency probe turn')
      await page.keyboard.press('Enter')
      await waitForProbeCounts(page, { turns: 1, paints: 1 }, 25_000)
      const summary = await page.evaluate(() => (window as unknown as WindowProbe).__pl.summary())
      await context.close()

      const record = summary.turns[0]!
      const paint = summary.paints[0]!
      const engineLeg = fixtureGaps[gapIndex] ?? Number.NaN
      const firstByte = record.firstByteMs ?? Number.NaN
      const firstChunk = record.firstChunkMs ?? Number.NaN
      const wireMs = firstByte - record.turnStartMs
      const totalMs = paint.frameMs - record.turnStartMs
      const renderMs = paint.frameMs - firstChunk
      // The split itself: our share is what the user waits ON TOP of the upstream leg, with
      // the upstream leg measured on the fixture's own clock. The legs are then not all
      // additive: wire and the comment frame's read delay fall INSIDE the upstream window
      // (the page idles while the fixture waits), so they cost the user nothing extra, while
      // render starts after the token and is waited for. `skew` names the overlap instead of
      // pretending to be a fourth leg — derived as a leg it read -23.5 ms at p95.
      const oursMs = totalMs - engineLeg
      const skewMs = firstChunk - firstByte - engineLeg
      engine.push(engineLeg)
      wire.push(wireMs)
      ttft.push(firstChunk - record.turnStartMs)
      painted.push(totalMs)
      skew.push(skewMs)
      render.push(renderMs)
      ours.push(oursMs)
      loafFrames += summary.loafFrames
      loafMs += summary.loafMs
      console.log(
        `r5-latency TURN ${turn + 1}/${TURNS} wire=${wireMs.toFixed(1)} ` +
          `engine=${engineLeg.toFixed(1)} skew=${skewMs.toFixed(1)} ` +
          `render=${renderMs.toFixed(1)} ttft=${(firstChunk - record.turnStartMs).toFixed(1)} ` +
          `painted=${totalMs.toFixed(1)} ours=${oursMs.toFixed(1)}`,
      )
    }

    legLine('engine-leg-measured', engine)
    legLine('wire-first-byte', wire)
    legLine('ttft-first-chunk', ttft)
    legLine('painted-after-send', painted)
    legLine('read-skew-overlapping-upstream', skew)
    legLine('our-render-after-token', render)
    legLine('our-share-of-the-wait', ours)
    const engineP95 = percentile(engine, 95)
    console.log(
      `r5-latency SPLIT engineNominalMs=${ENGINE_MS} engineMeasuredP95=${engineP95} ` +
        `turns=${TURNS} ourShareP50=${percentile(ours, 50)} ` +
        `ourShareP75=${percentile(ours, 75)} ourShareP95=${percentile(ours, 95)} ` +
        `ourShareMax=${percentile(ours, 100)} renderP95=${percentile(render, 95)} ` +
        `wireP95=${percentile(wire, 95)} ttftP95=${percentile(ttft, 95)} ` +
        `perceivedP95=${percentile(painted, 95)}`,
    )
    console.log(
      `r5-latency LOAF frames=${loafFrames} ms=${loafMs} ` +
        `note=a-zero-means-no-frame-crossed-50ms-in-${TURNS}-turns`,
    )

    // Only our legs are gated. The upstream leg is a fixture constant, and a real engine's
    // first-token rate is priced by the live Python budget elsewhere. The bar is the cited
    // 0.1 s on top of the leg this file injected, so a slower fixture cannot fake a green.
    expect(percentile(ours, 95)).toBeLessThanOrEqual(NIELSEN_INSTANT_MS)
    expect(percentile(painted, 95)).toBeLessThanOrEqual(engineP95 + NIELSEN_INSTANT_MS)
    expect(percentile(ttft, 95)).toBeLessThanOrEqual(engineP95 + NIELSEN_INSTANT_MS)
  })

  test('the plan card while the answer streams: the first readable step', async ({ browser }) => {
    // Row 9 of docs/PLAN_SURFACE_2026-10-11.md, and the one leg of it this file can price. The
    // card used to wait for the turn to end (`!m.streaming`), so a plan arrived after the answer
    // had finished arriving; the steps are now on screen while the block is still being written.
    // The engine leg is the same injected constant as the turns above, so what is measured is the
    // leg the surface owns: from the chunk carrying the first step line to the frame that paints
    // it. A plan lane needs a plan-shaped answer, which is why it starts its own fixture.
    const plan = await startAppFixture({
      kind: 'chat',
      engineMs: ENGINE_MS,
      gaps: fixtureGaps,
      marks: fixtureMarks,
      requests: fixtureRequests.chat,
      chunks: PLAN_CHUNKS,
    })
    fixtures.push({ kind: 'chat', ...plan })

    const engineToReadable: number[] = []
    const sendToReadable: number[] = []
    for (let sample = 0; sample < PLAN_SAMPLES; sample += 1) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
      const page = await context.newPage()
      await openChat(page, plan.origin)
      await page.evaluate(() => (window as unknown as WindowProbe).__pl.armPlan())
      await page.locator(CHAT_INPUT).fill('Plan the two route changes')
      await page.keyboard.press('Enter')
      await waitForProbeCounts(page, { turns: 1, plans: 1 }, 25_000)
      const summary = await page.evaluate(() => (window as unknown as WindowProbe).__pl.summary())
      await context.close()

      const turn = summary.turns[0]!
      const readable = summary.plans[0]!
      const firstChunk = turn.firstChunkMs ?? Number.NaN
      engineToReadable.push(readable.frameMs - firstChunk)
      sendToReadable.push(readable.frameMs - turn.turnStartMs)
    }

    legLine('plan-line-after-first-chunk', engineToReadable)
    legLine('plan-line-after-send', sendToReadable)
    console.log(
      `r5-latency PLAN samples=${PLAN_SAMPLES} ` +
        `p50ReadableAfterChunk=${percentile(engineToReadable, 50)} ` +
        `p95ReadableAfterChunk=${percentile(engineToReadable, 95)} ` +
        `p50ReadableAfterSend=${percentile(sendToReadable, 50)}`,
    )

    // The row's number is 3 s, and it is read on the leg between the engine's line and its paint.
    // The injected engine leg sits outside this window, so a slow fixture cannot make a green
    // here, and it cannot make a red either.
    expect(percentile(engineToReadable, 95)).toBeLessThanOrEqual(PLAN_READABLE_MS)
  })

  test('gesture to paint: the key that opens the slash menu', async ({ page }) => {
    await openChat(page)
    await page.locator(CHAT_INPUT).click()

    const keyToFrame: number[] = []
    const keyToDom: number[] = []
    const durations: number[] = []
    const delays: number[] = []
    const processing: number[] = []

    for (let attempt = 0; attempt < GESTURES; attempt += 1) {
      await page.evaluate(() => (window as unknown as WindowProbe).__pl.armGesture())
      await page.keyboard.press('/')
      await waitForProbeCounts(page, { gestures: attempt + 1 }, 10_000)
      const gesture = await page.evaluate(
        () => (window as unknown as WindowProbe).__pl.summary().gestures.slice(-1)[0]!,
      )
      keyToFrame.push(gesture.menuFrameMs - gesture.keyDownMs)
      keyToDom.push(gesture.menuMutationMs - gesture.keyDownMs)
      if (gesture.eventDurationMs !== null) durations.push(gesture.eventDurationMs)
      if (gesture.eventDelayMs !== null) delays.push(gesture.eventDelayMs)
      if (gesture.eventProcessingMs !== null) processing.push(gesture.eventProcessingMs)
      // Escape closes the menu so every press is the same first gesture.
      await page.keyboard.press('Escape')
      await page.locator(SLASH_MENU).waitFor({ state: 'hidden', timeout: 5000 })
      await page.locator(CHAT_INPUT).click()
      await page.waitForTimeout(40)
    }

    legLine('gesture-key-to-frame', keyToFrame)
    legLine('gesture-key-to-dom', keyToDom)
    legLine('event-timing-duration', durations)
    legLine('event-timing-input-delay', delays)
    legLine('event-timing-processing', processing)
    console.log(
      `r5-latency GESTURE samples=${keyToFrame.length} eventEntries=${durations.length} ` +
        `p75KeyToFrame=${percentile(keyToFrame, 75)} p95KeyToFrame=${percentile(keyToFrame, 95)}`,
    )

    expect(percentile(keyToFrame, 75)).toBeLessThanOrEqual(INP_P75_MS)
    if (durations.length > 0) {
      expect(percentile(durations, 75)).toBeLessThanOrEqual(INP_P75_MS)
    }
  })

  test('cold first load: navigation to a chat input you can type in', async ({ browser }) => {
    // The figure this file was missing: the load a returning visitor gets when they open the
    // app. Its gate answer is seeded (what every load after the first one has —
    // lib/setupGate.ts), so what is priced here is the bundle, the route chunk and the app's
    // own boot round trips.
    const firstContentPaint: number[] = []
    const panelVisible: number[] = []
    const inputReadable: number[] = []
    const gateRoundTrips: number[] = []
    const bootRoundTrips: number[] = []
    let sampleRoutes = ''

    const asked = fixtureRequests.chat
    for (let attempt = 0; attempt < FIRST_LOAD_SAMPLES; attempt += 1) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
      const page = await context.newPage()
      const from = asked.length
      await page.addInitScript(() => {
        localStorage.setItem('i18nextLng', 'de')
        localStorage.setItem('ephe_onboarded', '1')
        localStorage.setItem('ephe.intro.seen.v1', '1')
        localStorage.setItem(
          'ephe.setup_gate',
          JSON.stringify({ configured: true, skipped: false }),
        )
      })
      const started = Date.now()
      await page.goto(`${originOf('chat')}/#/chat`, { waitUntil: 'load' })
      await page.waitForSelector(CHAT_PANEL, { timeout: 30_000 })
      panelVisible.push(Date.now() - started)
      await page.waitForSelector(CHAT_INPUT, { timeout: 30_000 })
      inputReadable.push(Date.now() - started)
      // Read after the surface is up: at `load` the app has not committed a frame yet, so
      // the paint entries do not exist and the figure would be a -1.
      const fcp = await page.evaluate(() => {
        const entry = performance
          .getEntriesByType('paint')
          .find((candidate) => candidate.name === 'first-contentful-paint')
        return entry ? Math.round(entry.startTime) : -1
      })
      firstContentPaint.push(fcp)

      const api = asked.slice(from).filter((request) => request.path.startsWith('/api/'))
      bootRoundTrips.push(api.length)
      gateRoundTrips.push(api.filter((request) => request.path === '/api/setup/status').length)
      if (attempt === 0) {
        sampleRoutes = api.map((request) => `${request.atMs}:${request.path}`).join(' ')
      }
      await context.close()
    }

    legLine('first-load-first-content-paint', firstContentPaint)
    legLine('first-load-panel-visible', panelVisible)
    legLine('first-load-input-readable', inputReadable)
    legLine('first-load-api-round-trips', bootRoundTrips)
    legLine('first-load-gate-round-trips', gateRoundTrips)
    console.log(
      `r5-latency FIRST-LOAD samples=${FIRST_LOAD_SAMPLES} route=#/chat ` +
        `p50Input=${percentile(inputReadable, 50)} p95Input=${percentile(inputReadable, 95)} ` +
        `p95Fcp=${percentile(firstContentPaint, 95)} ` +
        `apiPerLoad=[${bootRoundTrips.join(',')}] gatePerLoad=[${gateRoundTrips.join(',')}] ` +
        `firstSampleRoutes=[${sampleRoutes}]`,
    )

    // The count is the assertion that survives a loaded box: the app asks the gate once per
    // load (the gate and the composer used to send separate calls for the same answer), and a
    // route change inside the session asks again never.
    expect(percentile(gateRoundTrips, 100)).toBeLessThanOrEqual(1)
    // The wall clock rides on the cited 1 s "stay in flow" limit, the same ruler the first-run
    // path uses. On a loaded box it is a floor; the run log carries the load it was read at.
    expect(percentile(inputReadable, 95)).toBeLessThanOrEqual(NIELSEN_FLOW_MS)
  })

  test('cold first-run path: a new visitor to the engine choice they can act on', async ({
    browser,
  }) => {
    let paints = ''
    let buttonsOnSurface = -1

    const firstControl: number[] = []
    const surfaceReady: number[] = []
    for (let attempt = 0; attempt < FIRST_RUN_SAMPLES; attempt += 1) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
      const page = await context.newPage()
      await page.addInitScript(installLatencyProbe)
      // No localStorage on purpose, and the first-run fixture answers the setup gate with
      // `configured: false`: this is the engine-choice screen a new visitor actually gets.
      const started = Date.now()
      await page.goto(`${originOf('first-run')}/`, { waitUntil: 'load' })
      await expect(page.locator('a[href], button').first()).toBeVisible({ timeout: 30_000 })
      firstControl.push(Date.now() - started)
      // The shell's skip link is not the product's first decision. SetupPage arrives on a
      // lazy chunk, so the figure that matters is when the engine choice can be acted on.
      await expect(page.locator('[data-testid="setup-page"] button').first()).toBeVisible({
        timeout: 30_000,
      })
      surfaceReady.push(Date.now() - started)
      if (attempt === 0) {
        paints = await page.evaluate(() =>
          performance
            .getEntriesByType('paint')
            .map((entry) => `${entry.name}=${Math.round(entry.startTime)}`)
            .join(','),
        )
        buttonsOnSurface = await page.locator('[data-testid="setup-page"] button').count()
      }
      await context.close()
    }

    legLine('first-run-first-control', firstControl)
    legLine('first-run-engine-choice-visible', surfaceReady)
    console.log(
      `r5-latency FIRST-RUN samples=${FIRST_RUN_SAMPLES} route=#/setup ` +
        `surfaceButtons=${buttonsOnSurface} paints=[${paints}] ` +
        `p50Choice=${percentile(surfaceReady, 50)} p95Choice=${percentile(surfaceReady, 95)}`,
    )

    // The gate is the cited 1 s "stay in flow" limit applied to the surface a new visitor
    // reaches for. The shell painting a link sooner would pass an easier test and say
    // nothing about the first decision.
    expect(percentile(surfaceReady, 95)).toBeLessThanOrEqual(NIELSEN_FLOW_MS)
    expect(buttonsOnSurface).toBeGreaterThan(0)
  })
})
