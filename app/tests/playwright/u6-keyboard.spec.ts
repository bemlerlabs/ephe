import { expect, test, type Browser, type Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { startAppFixture, type AppFixture, type FixtureRequest } from './appFixture'

/**
 * U6 item #70, part 1: the keystroke path and the time to a first answer, counted as a user.
 *
 * Three intents, counted in real key events from a focused empty composer to the moment the
 * message is on screen, and one wait split that adds the leg `r5-perceived-latency.spec.ts`
 * does not price: the settle, from the first painted line until the answer stops moving. r5
 * ends its render leg at the next frame after the first token, which prices the batcher and
 * not what the user keeps watching — a streaming answer grows, re-wraps, and drags the
 * scroll bottom along with it.
 *
 * Keystroke counts are walked, not written down: the cost of reaching the mode chip or the
 * attach chip is whatever the current tab order charges, measured the way a keyboard-only
 * user pays it. A hand-counted number would be stale the first time a button is inserted,
 * and the whole point of this file is to notice that.
 *
 * The engine leg is the shared fixture (`appFixture.ts`) on a free port, never :8765 and
 * never the static dist server on :9199: a figure taken from a server this lane did not
 * start belongs to somebody else's bundle.
 */

const OWN_LANE = process.env.EPHE_LATENCY_LANE === '1'
const ENGINE_MS = Number(process.env.EPHE_U6_ENGINE_MS ?? 400)
const SAMPLES = Number(process.env.EPHE_U6_SAMPLES ?? 5)
const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../../../out/u6-keyboard')

const CHAT_PANEL = '[data-testid="panel-chat"]'
const CHAT_INPUT = '[data-testid="chat-input"]'
const ATTACH_PLUS = '[data-testid="composer-attach-plus"]'
const MENTION_LIST = '#mention-listbox'

const PROMPTS = {
  'write-a-page': 'Write a page about the composer.',
  'ask-about-a-file': 'what does this file do?',
  'task-with-attachment': 'plan the migration',
} as const

type Intent = keyof typeof PROMPTS

type Sample = {
  intent: Intent
  sample: number
  keys: number
  textChars: number
  chromeKeys: number
  toSentMs: number
  toFirstTokenMs: number
  toFirstPaintMs: number
  toLastMoveMs: number
  toStreamDoneMs: number
  toSettleMs: number
  movesAt: number[]
  layoutMovesAt: number[]
  textOnlyChanges: number
}

const samples: Sample[] = []
const requests: FixtureRequest[] = []
let fixture: AppFixture | null = null

/**
 * One clock, one loop. Arms on demand and records the instants of one wait: the first key,
 * the user's own bubble on screen, the first token read, the first painted line, and the
 * frame after which the answer's geometry stopped changing.
 *
 * "Stopped changing" is anchored to the stream, not to a frame-stability heuristic. Six
 * identical frames at 60 fps is ~100 ms, and an injected 80 ms chunk gap is steadier than
 * that, so a pure stability window declared the answer settled after its first pause: the
 * figure it printed priced the instrument. The window now only counts after the engine's
 * own `done` frame has been read.
 */
function armMeasurementProbe() {
  type State = {
    armed: boolean
    keys: number
    textChars: number
    firstKeyMs: number
    sentMs: number
    tokenMs: number
    paintMs: number
    movedMs: number
    doneMs: number
    moves: number[]
    layoutMoves: number[]
    textOnly: number
    settleMs: number
  }
  const state: State = {
    armed: false,
    keys: 0,
    textChars: 0,
    firstKeyMs: 0,
    sentMs: 0,
    tokenMs: 0,
    paintMs: 0,
    movedMs: 0,
    doneMs: 0,
    moves: [],
    layoutMoves: [],
    textOnly: 0,
    settleMs: 0,
  }
  const now = () => performance.now()
  const STABLE_FRAMES = 6

  document.addEventListener(
    'keydown',
    (event) => {
      if (!state.armed) return
      state.keys += 1
      // A printable key adds a column of text; a modifier or a navigation key does not.
      if (event.key.length === 1) state.textChars += 1
      if (!state.firstKeyMs) state.firstKeyMs = now()
    },
    true,
  )

  // Whether the app actually clicked its hidden file input, and what the document could see
  // at that instant. A lost file chooser has two very different causes — the product never
  // clicked the input, or the browser swallowed a click that did happen — and this is the one
  // line of the page that tells them apart.
  ;(window as unknown as Record<string, unknown>).__u6Clicks = []
  document.addEventListener(
    'click',
    (event) => {
      const target = event.target as HTMLInputElement | null
      if (target?.tagName !== 'INPUT' || target.type !== 'file') return
      const active = document.activeElement as HTMLElement | null
      ;(window as unknown as { __u6Clicks: unknown[] }).__u6Clicks.push({
        atMs: Number(now().toFixed(1)),
        trusted: event.isTrusted,
        accept: target.accept,
        hidden: target.classList.contains('hidden'),
        focus: `${active?.tagName.toLowerCase() ?? '?'}[${active?.getAttribute('data-testid') ?? ''}]`,
      })
    },
    true,
  )

  // Literal selectors: the probe is serialized into the page and cannot see module scope.
  const SCROLL = '[data-testid="chat-scroll-region"]'
  const TEXT =
    '[data-testid="message-bubble"][data-role="assistant"] [data-testid="stream-text-block"]'

  // Two signals, because they answer different questions. `layout` is what moves on screen:
  // the scroll position and the height of the bubble carrying the answer. `text` is what the
  // batcher hands the reader. A stream that grows its text with no layout change is a
  // different product from one that re-wraps and drags the scroll bottom along, and the
  // earlier version of this probe folded them into one signature, which could only ever
  // report "moved".
  const layout = () => {
    const region = document.querySelector(SCROLL) as HTMLElement | null
    const bubbles = document.querySelectorAll('[data-testid="message-bubble"]')
    const last = bubbles[bubbles.length - 1] as HTMLElement | undefined
    const box = last?.getBoundingClientRect()
    return [
      region ? Math.round(region.scrollTop) : -1,
      region ? Math.round(region.scrollHeight) : -1,
      box ? Math.round(box.height) : -1,
      bubbles.length,
    ].join(':')
  }

  const text = () => {
    let chars = 0
    document.querySelectorAll(TEXT).forEach((block) => {
      chars += (block.textContent ?? '').length
    })
    return String(chars)
  }

  const seen = () => `${layout()}|${text()}`

  let previous = ''
  let previousLayout = ''
  let stable = 0
  const tick = () => {
    if (state.armed) {
      if (
        !state.sentMs &&
        document.querySelector('[data-testid="message-bubble"][data-role="user"]')
      ) {
        state.sentMs = now()
      }
      const first = document.querySelector(TEXT)
      const painted = first && (first.textContent ?? '').trim().length > 0
      if (state.tokenMs && !state.paintMs && painted) {
        state.paintMs = now()
        state.movedMs = state.paintMs
        previous = seen()
        previousLayout = layout()
        stable = 0
      } else if (state.paintMs && !state.settleMs) {
        const signature = seen()
        const geometryNow = layout()
        stable = signature === previous ? stable + 1 : 0
        if (signature !== previous) {
          state.movedMs = now()
          // Every change is kept, not just the last: one painted line for twelve injected
          // chunks is a product statement about the batcher, and it needs the frames to prove
          // it, not a tail figure that could also be an instrument that stopped looking.
          state.moves.push(Number((now() - state.firstKeyMs).toFixed(0)))
          if (geometryNow === previousLayout) state.textOnly += 1
          else state.layoutMoves.push(Number((now() - state.firstKeyMs).toFixed(0)))
          previousLayout = geometryNow
        }
        previous = signature
        // The window only closes once the engine has said it is finished; before that the
        // answer is still arriving and a pause between two chunks is not the end of it. The
        // extra 100 ms is the final flush: React paints the last chunk after the frame that
        // carries it, and settling on the frame of `done` would cut the tail off.
        if (state.doneMs && stable >= STABLE_FRAMES && now() - state.doneMs >= 100) {
          state.settleMs = now()
        }
      }
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)

  const nativeFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : String(input)
    const response = await nativeFetch(input as RequestInfo, init)
    if (!url.includes('/api/chat/stream') || !response.body) return response
    const source = response.body.getReader()
    const decoder = new TextDecoder()
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { done, value } = await source.read()
        if (done) {
          if (!state.doneMs) state.doneMs = now()
          controller.close()
          return
        }
        controller.enqueue(value)
        const frame = decoder.decode(value, { stream: true })
        if (!state.tokenMs && frame.includes('"type":"chunk"')) state.tokenMs = now()
        if (!state.doneMs && frame.includes('"type":"done"')) state.doneMs = now()
      },
      cancel: (reason) => source.cancel(reason),
    })
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  }

  ;(window as unknown as Record<string, unknown>).__u6 = {
    arm: () => {
      state.armed = true
      state.keys = 0
      state.textChars = 0
      state.firstKeyMs = 0
      state.sentMs = 0
      state.tokenMs = 0
      state.paintMs = 0
      state.movedMs = 0
      state.doneMs = 0
      // A new array, not a cleared one: `read()` hands out the same object the loop writes,
      // so clearing in place would rewrite the sample that was already recorded.
      state.moves = []
      state.layoutMoves = []
      state.textOnly = 0
      state.settleMs = 0
    },
    stop: () => {
      state.armed = false
    },
    read: () => ({ ...state }),
  }
}

type ReadState = {
  keys: number
  textChars: number
  firstKeyMs: number
  sentMs: number
  tokenMs: number
  paintMs: number
  movedMs: number
  doneMs: number
  moves: number[]
  layoutMoves: number[]
  textOnly: number
  settleMs: number
}

async function arm(page: Page) {
  await page.evaluate(() => (window as unknown as { __u6: { arm(): void } }).__u6.arm())
}

async function readState(page: Page): Promise<ReadState> {
  return page.evaluate(() => (window as unknown as { __u6: { read(): ReadState } }).__u6.read())
}

async function freshChat(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const page = await context.newPage()
  await openChat(page)
  return page
}

async function openChat(page: Page) {
  page.on('pageerror', (error) =>
    console.log(`u6-keyboard PAGEERROR ${String(error).slice(0, 160)}`),
  )
  page.on('console', (message) => {
    if (message.type() === 'error') {
      console.log(`u6-keyboard CONSOLE-ERROR ${message.text().slice(0, 160)}`)
    }
  })
  await page.addInitScript(armMeasurementProbe)
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
  })
  const origin = fixture?.origin
  if (!origin) throw new Error('the fixture is the only server this file talks to')
  await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
  await page.waitForSelector(CHAT_PANEL, { timeout: 15_000 })
  await page.locator(CHAT_INPUT).click()
  await expect(page.locator(CHAT_INPUT)).toBeFocused()
}

/** The identity of whatever holds focus right now, for the focus-landing figures. */
async function focusHere(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return 'body'
    const testid = el.getAttribute('data-testid')
    return `${el.tagName.toLowerCase()}${testid ? `[${testid}]` : ''}`
  })
}

/**
 * Tab until focus lands on `selector`, counting the presses: the cost, as paid.
 *
 * `back` walks in the direction a user who just came from that element would try. Pricing a
 * return trip by the long way round (52 stops through the conversation) would be a number
 * this instrument invented, and `u6-focus.spec.ts` already shows the other direction costs
 * 1-2.
 */
async function tabUntil(page: Page, selector: string, limit = 25, back = false) {
  for (let press = 1; press <= limit; press += 1) {
    await page.keyboard.press(back ? 'Shift+Tab' : 'Tab')
    if (
      await page.evaluate((target) => document.activeElement?.matches(target) === true, selector)
    ) {
      return press
    }
  }
  throw new Error(`nothing matched ${selector} within ${limit} Tab presses`)
}

/**
 * What the attach menu, the focus and the hidden inputs look like right now. Printed into the
 * failure message so a lost file chooser says which of its two causes it has.
 */
async function attachState(page: Page): Promise<string> {
  return page.evaluate(() => {
    const list = document.querySelector('[data-testid="composer-attach-list"]')
    const rows = list ? [...list.querySelectorAll('[role="menuitem"]')] : []
    const active = document.activeElement as HTMLElement | null
    const clicks = (window as unknown as { __u6Clicks?: unknown[] }).__u6Clicks ?? []
    return (
      `focus=${active?.tagName.toLowerCase()}[${active?.getAttribute('data-testid') ?? ''}] ` +
      `menu=${list ? `open rows=${rows.length}` : 'closed'} ` +
      `inputs=${document.querySelectorAll('input[type="file"]').length} ` +
      `clicks=${JSON.stringify(clicks)}`
    )
  })
}

async function waitSettled(page: Page) {
  await page.waitForFunction(
    () => (window as unknown as { __u6: { read(): ReadState } }).__u6.read().settleMs > 0,
    null,
    { timeout: 20_000 },
  )
}

function record(intent: Intent, sample: number, read: ReadState) {
  const text = PROMPTS[intent]
  const entry: Sample = {
    intent,
    sample,
    keys: read.keys,
    textChars: text.length,
    chromeKeys: read.keys - text.length,
    toSentMs: Number((read.sentMs - read.firstKeyMs).toFixed(1)),
    toFirstTokenMs: Number((read.tokenMs - read.firstKeyMs).toFixed(1)),
    toFirstPaintMs: Number((read.paintMs - read.firstKeyMs).toFixed(1)),
    toLastMoveMs: Number((read.movedMs - read.firstKeyMs).toFixed(1)),
    toStreamDoneMs: Number((read.doneMs - read.firstKeyMs).toFixed(1)),
    toSettleMs: Number((read.settleMs - read.firstKeyMs).toFixed(1)),
    movesAt: read.moves,
    layoutMovesAt: read.layoutMoves,
    textOnlyChanges: read.textOnly,
  }
  samples.push(entry)
  console.log(
    `u6-keyboard INTENT=${intent} sample=${sample} keys=${entry.keys} text=${entry.textChars} ` +
      `chrome=${entry.chromeKeys} toSent=${entry.toSentMs} firstToken=${entry.toFirstTokenMs} ` +
      `firstPaint=${entry.toFirstPaintMs} lastMove=${entry.toLastMoveMs} ` +
      `moveTail=${Number((entry.toLastMoveMs - entry.toFirstPaintMs).toFixed(1))} ` +
      `streamDone=${entry.toStreamDoneMs} moves=${entry.movesAt.length} ` +
      `layout=${entry.layoutMovesAt.length} textOnly=${entry.textOnlyChanges} ` +
      `at=[${entry.movesAt.join(',')}] ` +
      `settledAfterDone=${Number((entry.toSettleMs - entry.toStreamDoneMs).toFixed(1))}`,
  )
}

function median(values: number[]): number {
  if (!values.length) return Number.NaN
  const sorted = [...values].sort((a, b) => a - b)
  return Number(sorted[Math.floor((sorted.length - 1) / 2)])
}

test.describe.configure({ mode: 'serial' })

test.describe('U6 keyboard path and first answer', () => {
  test.skip(!OWN_LANE, 'runs under tests/playwright/latency.config.ts, the timing lane')
  test.setTimeout(300_000)

  test.beforeAll(async () => {
    await mkdir(OUT_DIR, { recursive: true })
    fixture = await startAppFixture({
      kind: 'chat',
      engineMs: ENGINE_MS,
      requests,
      // A stream that streams, and streams long. r5's three chunks land inside 60 ms, which
      // prices the first token only; twelve words of `word0 word1 …` paint one line, so the
      // answer grows without ever re-wrapping and the layout leg stays flat. A paragraph is
      // what a user actually watches: it re-wraps, and the pinned scroll bottom moves.
      chunks: Array.from({ length: 24 }, (_unused, i) => `sentence${i} alpha beta gamma `),
      chunkGapMs: 80,
      routes: [
        (req, res) => {
          if (!String(req.url ?? '').startsWith('/api/fs')) return false
          res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          res.end(
            JSON.stringify({
              path: '/workspace',
              entries: [
                { name: 'README.md', path: '/workspace/README.md', type: 'file' },
                { name: 'model.ts', path: '/workspace/model.ts', type: 'file' },
                { name: 'notes', path: '/workspace/notes', type: 'dir' },
              ],
            }),
          )
          return true
        },
      ],
    })
    console.log(
      `u6-keyboard FIXTURE origin=${fixture.origin} port=${fixture.port} ` +
        `engineMs=${ENGINE_MS} samples=${SAMPLES}`,
    )
  })

  test.afterAll(async () => {
    await fixture?.close()
    await writeFile(
      resolve(OUT_DIR, 'intents.json'),
      JSON.stringify({ engineMs: ENGINE_MS, samples, requests }, null, 1),
      'utf-8',
    )
    for (const intent of Object.keys(PROMPTS) as Intent[]) {
      const entries = samples.filter((entry) => entry.intent === intent)
      if (!entries.length) continue
      console.log(
        `u6-keyboard FIGURE intent=${intent} n=${entries.length} ` +
          `keysMedian=${median(entries.map((e) => e.keys))} ` +
          `chromeMedian=${median(entries.map((e) => e.chromeKeys))} ` +
          `toSentMedian=${median(entries.map((e) => e.toSentMs))} ` +
          `firstTokenMedian=${median(entries.map((e) => e.toFirstTokenMs))} ` +
          `firstPaintMedian=${median(entries.map((e) => e.toFirstPaintMs))} ` +
          `lastMoveMedian=${median(entries.map((e) => e.toLastMoveMs))} ` +
          `moveTailMedian=${median(
            entries.map((e) => Number((e.toLastMoveMs - e.toFirstPaintMs).toFixed(1))),
          )} ` +
          `streamDoneMedian=${median(entries.map((e) => e.toStreamDoneMs))} ` +
          `textChangesMedian=${median(entries.map((e) => e.movesAt.length))} ` +
          `layoutChangesMedian=${median(entries.map((e) => e.layoutMovesAt.length))}`,
      )
    }
    fixture = null
  })

  // The shipped default mode already writes (full access), so "write a page" is the plain
  // path; what a menu costs on the way back is measured in u6-focus.spec.ts.
  test('intent 1: write a page', async ({ browser }) => {
    for (let sample = 1; sample <= SAMPLES; sample += 1) {
      const page = await freshChat(browser)
      await arm(page)
      const text = PROMPTS['write-a-page']
      await page.keyboard.type(text)
      await page.keyboard.press('Enter')
      await waitSettled(page)
      record('write-a-page', sample, await readState(page))
      if (sample === 1)
        await page.screenshot({ path: resolve(OUT_DIR, 'intent-1-write-a-page.png') })
      await page.context().close()
    }
  })

  test('intent 2: ask about a file in this project', async ({ browser }) => {
    for (let sample = 1; sample <= SAMPLES; sample += 1) {
      const page = await freshChat(browser)
      await arm(page)
      await page.keyboard.type('@mod')
      await page.waitForSelector(MENTION_LIST, { timeout: 8_000 }).catch(() => {
        console.log(
          `u6-keyboard DEBUG mention-list-missing requests=${JSON.stringify(requests.slice(-10))}`,
        )
      })
      await page.keyboard.press('Enter')
      await expect
        .poll(async () => (await page.locator(CHAT_INPUT).inputValue()).includes('model.ts'), {
          message: 'the mention did not land in the composer',
        })
        .toBe(true)
      await page.keyboard.type(` ${PROMPTS['ask-about-a-file']}`)
      await page.keyboard.press('Enter')
      await waitSettled(page)
      record('ask-about-a-file', sample, await readState(page))
      if (sample === 1) {
        await page.screenshot({ path: resolve(OUT_DIR, 'intent-2-ask-about-a-file.png') })
      }
      await page.context().close()
    }
  })

  test('intent 3: start a task with an attachment', async ({ browser }) => {
    for (let sample = 1; sample <= SAMPLES; sample += 1) {
      const page = await freshChat(browser)
      await arm(page)
      await tabUntil(page, ATTACH_PLUS)
      await page.keyboard.press('Enter')
      await page.waitForSelector('[data-testid="composer-attach-list"]', { timeout: 5_000 })
      // The list takes focus one effect after it mounts; poll for that instead of sleeping,
      // so a row that never receives focus fails here rather than looking like a slow test.
      await expect
        .poll(async () => await focusHere(page), {
          message: 'the attach menu opened without moving focus into its rows',
          timeout: 3_000,
        })
        .toBe('div[composer-attach-list]')
      const chooser = page.waitForEvent('filechooser', { timeout: 6_000 })
      await page.keyboard.press('Enter')
      const picked = await chooser.catch(() => null)
      expect(
        picked,
        `the attach menu opened no file chooser from the keyboard — at the failure: ` +
          (await attachState(page)),
      ).not.toBeNull()
      await picked!.setFiles([
        { name: 'spec.md', mimeType: 'text/markdown', buffer: Buffer.from('# spec\n') },
      ])
      await expect(page.getByText('spec.md').first()).toBeVisible({ timeout: 8_000 })
      const landedAfterAttach = await focusHere(page)
      const backFromAttach = await tabUntil(page, CHAT_INPUT, 60, true)
      console.log(
        `u6-keyboard FOCUS after=attach-pick landed=${landedAfterAttach} ` +
          `shiftTabsBackToComposer=${backFromAttach} ${await attachState(page)}`,
      )
      await page.keyboard.type(PROMPTS['task-with-attachment'])
      await page.keyboard.press('Enter')
      await waitSettled(page)
      record('task-with-attachment', sample, await readState(page))
      if (sample === 1) {
        await page.screenshot({ path: resolve(OUT_DIR, 'intent-3-task-with-attachment.png') })
        console.log(
          `u6-keyboard ROUTES intent-3 ${requests
            .map((entry) => `${entry.method} ${entry.path.split('?')[0]}`)
            .filter((value, index, all) => all.indexOf(value) === index)
            .join(' ')}`,
        )
      }
      await page.context().close()
    }
  })
})
