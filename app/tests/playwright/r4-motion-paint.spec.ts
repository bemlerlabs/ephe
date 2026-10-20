import { expect, test, webkit, type Browser, type Page } from '@playwright/test'
import { cpus, loadavg } from 'node:os'
import { ensureOnboarded, gotoHash } from './helpers'

// UI 4x programme, wave 2 (docs/UI_4X_PROGRAM_2026-10-11.md §6): the motion and paint
// budget as measured figures. Four windows, four figures per window, one log line per
// window and arm. Nothing here deletes or quiets an animation loop; the seven declared
// `infinite` loops stay and the removal is the next wave.
//
// The four figures:
//   longFrames        rAF intervals over 50 ms — the falling value the programme names.
//   meanMs / worstMs  the frame interval distribution of the same recorder, with the
//                     count over 25 ms (one dropped vsync) where a real cost shows up
//                     before 50 ms does.
//   glass             main-thread time attributed to the glass paint, differential: every
//                     window runs twice, arm=off with backdrop-filter ablated and arm=on
//                     with the blur the rule intends. The attribution line is the delta.
//   loops             animations at rest: `infinite` rules counted in the CSSOM, and the
//                     instances getAnimations() reports as running.
//
// What the recorder can and cannot see, measured on this machine 2026-10-11: the rAF clock
// of the headless Chromium lane is a BeginFrame clock. Ten spinning node processes on the
// host moved the idle mean by 0.01 ms (16.66 to 16.67), while a 220 ms spin inside a rAF
// callback moved the worst interval to 216.6 ms. These figures price this page's main
// thread, which is what a paint budget needs, and they cannot price the compositor or the
// GPU. The planted-long-frame test pins that the zero is a measurement.
//
// Why the glass figure is differential, measured: app/dist carries -webkit-backdrop-filter
// only for the three glass layers, the unprefixed declaration is absent from
// the built stylesheet, and the Chromium in this lane computes backdrop-filter:none for
// all 9 glass surfaces of /#/chat while WebKit 26 computes blur(20px). The shipped
// Chromium build paints no glass, so arm=off is the shipped state there and arm=on prices
// what an engine that honours the rule pays. Which tool dropped the declaration is a
// build-config question outside this wave; `painting=` in the log line keeps it checkable.
//
// Run this file alone: pnpm exec playwright test -c tests/playwright/playwright.config.ts
// r4-motion-paint.spec.ts --workers=1. The live-stream window is opt-in with
// EPHE_MOTION_LIVE=1, because it POSTs a real turn to the engine behind the product port
// and that server keeps the session in its own store.

type LoopInventory = {
  declaredInfinite: number
  declaredSelectors: string[]
  keyframeNames: string[]
  total: number
  running: number
  runningInfinite: number
  runningNames: string[]
}

type GlassInventory = { surfaces: number; painting: number }

type FrameFigures = {
  frames: number
  meanMs: number
  worstMs: number
  longFrames: number
  droppedFrames: number
  loafMs: number
  loafFrames: number
  busyMs: number
}

type WindowRecord = FrameFigures & { loops: LoopInventory; glass: GlassInventory }

type Probe = {
  start(): void
  frames(): FrameFigures
  loops(): LoopInventory
  glass(): GlassInventory
}

const GLASS_ARM_CSS = {
  off: '*,*::before,*::after{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}',
  on: '.glass-reading,.glass-control,.glass-float{backdrop-filter:blur(20px) saturate(1.4)!important;-webkit-backdrop-filter:blur(20px) saturate(1.4)!important}',
} as const

type Arm = keyof typeof GLASS_ARM_CSS

const CHAT_PANEL = '[data-testid="panel-chat"]'
const CHAT_INPUT = '[data-testid="chat-input"]'
const SLASH_SCROLL = '[data-testid="slash-menu-scroll"]'
const LIVE = process.env.EPHE_MOTION_LIVE === '1'
const LIVE_ORIGIN = process.env.EPHE_MOTION_ORIGIN ?? 'http://127.0.0.1:8765'

// The recorder lives in the page, so a Node-side action (typing, a stream) and the frame
// gaps run on one clock.
function installRecorder() {
  type Session = {
    gaps: number[]
    loaf: number[]
    busy: number[]
    last: number
    stop: boolean
    observers: PerformanceObserver[]
  }
  const blank = (): Session => ({
    gaps: [],
    loaf: [],
    busy: [],
    last: 0,
    stop: true,
    observers: [],
  })
  let session = blank()

  const observe = (type: string, sink: number[], observers: PerformanceObserver[]) => {
    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) sink.push(Math.round(entry.duration))
      })
      observer.observe({ type } as PerformanceObserverInit)
      observers.push(observer)
    } catch {
      // long-animation-frame and longtask are Chromium entry types.
    }
  }

  const nameOf = (animation: Animation) =>
    (animation as Animation & { animationName?: string }).animationName ?? 'unnamed'

  const runningInfinite = () =>
    document
      .getAnimations()
      .filter((animation) => animation.playState === 'running')
      .filter((animation) => animation.effect?.getComputedTiming().iterations === Infinity)

  // WebKit exposes no unprefixed animation-iteration-count longhand on a declared rule
  // (it answered undefined here), so the declaration is read through getPropertyValue and
  // both spellings, and the shorthand is read as the last route.
  const declaresInfinite = (style: CSSStyleDeclaration) =>
    [
      style.getPropertyValue('animation-iteration-count'),
      style.getPropertyValue('-webkit-animation-iteration-count'),
      style.getPropertyValue('animation'),
      style.getPropertyValue('-webkit-animation'),
    ]
      .filter(Boolean)
      .some((value) => value.includes('infinite'))

  const walkRules = (list: CSSRuleList, visit: (rule: CSSRule) => void) => {
    for (const rule of Array.from(list)) {
      // CSSKeyframesRule owns a cssRules list too, so it has to be recognised first or
      // its body would be read as ordinary style rules and its name lost.
      if (rule instanceof CSSKeyframesRule) {
        visit(rule)
        continue
      }
      const style = (rule as CSSStyleRule).style
      const nested = (rule as CSSRule & { cssRules?: CSSRuleList }).cssRules
      // CSSStyleRule carries an (usually empty) cssRules list since CSS nesting, so the
      // grouping test is "has a list and declares nothing itself".
      if (nested && !style) {
        walkRules(nested, visit)
        continue
      }
      visit(rule)
    }
  }

  const api = {
    start() {
      // One session per recording. A tick chain still in flight from the window before
      // reads its own stop flag and dies; sharing the flag across windows instead let a
      // pending chain see the next start() and keep pushing into the same gap list,
      // which halved the mean interval (measured: 16.67 -> 8.28 over two arms).
      const active = blank()
      active.last = performance.now()
      active.stop = false
      session = active
      observe('long-animation-frame', active.loaf, active.observers)
      observe('longtask', active.busy, active.observers)
      const tick = (now: number) => {
        active.gaps.push(now - active.last)
        active.last = now
        if (!active.stop) requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    },
    frames(): FrameFigures {
      session.stop = true
      for (const observer of session.observers) observer.disconnect()
      const intervals = session.gaps.slice(1)
      const sum = intervals.reduce((total, gap) => total + gap, 0)
      return {
        frames: intervals.length,
        meanMs: intervals.length ? Number((sum / intervals.length).toFixed(2)) : 0,
        worstMs: intervals.length ? Number(Math.max(...intervals).toFixed(2)) : 0,
        longFrames: intervals.filter((gap) => gap > 50).length,
        droppedFrames: intervals.filter((gap) => gap > 25).length,
        loafMs: session.loaf.reduce((total, duration) => total + duration, 0),
        loafFrames: session.loaf.length,
        busyMs: session.busy.reduce((total, duration) => total + duration, 0),
      }
    },
    loops(): LoopInventory {
      const declaredSelectors: string[] = []
      const keyframeNames: string[] = []
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList
        try {
          rules = sheet.cssRules
        } catch {
          continue // a cross-origin sheet hands out no rules to read
        }
        walkRules(rules, (rule) => {
          if (rule instanceof CSSKeyframesRule) {
            keyframeNames.push(rule.name)
            return
          }
          const style = (rule as CSSStyleRule).style
          if (!style) return
          if (declaresInfinite(style)) {
            declaredSelectors.push((rule as CSSStyleRule).selectorText ?? '')
          }
        })
      }
      const running = runningInfinite()
      return {
        declaredInfinite: declaredSelectors.length,
        declaredSelectors,
        keyframeNames,
        total: document.getAnimations().length,
        running: document.getAnimations().filter((animation) => animation.playState === 'running')
          .length,
        runningInfinite: running.length,
        runningNames: running.map(nameOf),
      }
    },
    glass(): GlassInventory {
      const surfaces = Array.from(
        new Set([
          ...document.querySelectorAll('.glass-reading, .glass-control, .glass-float'),
          ...document.querySelectorAll('[class*="backdrop-blur"]'),
        ]),
      )
      return {
        surfaces: surfaces.length,
        painting: surfaces.filter((element) => getComputedStyle(element).backdropFilter !== 'none')
          .length,
      }
    },
  }

  ;(window as unknown as { __r4: typeof api }).__r4 = api
}

const startRecorder = (page: Page) =>
  page.evaluate(() => (window as unknown as { __r4: Probe }).__r4.start())
const readFrames = (page: Page) =>
  page.evaluate(() => (window as unknown as { __r4: Probe }).__r4.frames())
const readLoops = (page: Page) =>
  page.evaluate(() => (window as unknown as { __r4: Probe }).__r4.loops())
const readGlass = (page: Page) =>
  page.evaluate(() => (window as unknown as { __r4: Probe }).__r4.glass())

async function armGlass(page: Page, arm: Arm) {
  await page.evaluate((css) => {
    document.getElementById('r4-arm')?.remove()
    const style = document.createElement('style')
    style.id = 'r4-arm'
    style.textContent = css
    document.head.appendChild(style)
  }, GLASS_ARM_CSS[arm])
}

function logLine(engine: string, name: string, arm: Arm, record: WindowRecord) {
  console.log(
    `r4-motion window=${name} arm=${arm} engine=${engine} ` +
      `longFrames=${record.longFrames} dropped25=${record.droppedFrames} ` +
      `meanMs=${record.meanMs} worstMs=${record.worstMs} frames=${record.frames} ` +
      `loafMs=${record.loafMs} busyMs=${record.busyMs} ` +
      `loopsDeclared=${record.loops.declaredInfinite} loopsRunning=${record.loops.running} ` +
      `loopsRunningInfinite=${record.loops.runningInfinite} ` +
      `loopNames=[${record.loops.runningNames.join(',')}] ` +
      `keyframes=${record.loops.keyframeNames.length} ` +
      `glassSurfaces=${record.glass.surfaces} painting=${record.glass.painting}`,
  )
}

function logAttribution(name: string, off: WindowRecord, on: WindowRecord) {
  console.log(
    `r4-motion GLASS-ATTRIBUTION window=${name} ` +
      `longFramesDelta=${on.longFrames - off.longFrames} ` +
      `dropped25Delta=${on.droppedFrames - off.droppedFrames} ` +
      `worstMsDelta=${Number((on.worstMs - off.worstMs).toFixed(2))} ` +
      `meanMsDelta=${Number((on.meanMs - off.meanMs).toFixed(2))} ` +
      `loafMsDelta=${on.loafMs - off.loafMs} busyMsDelta=${on.busyMs - off.busyMs} ` +
      `paintingOff=${off.glass.painting} paintingOn=${on.glass.painting}`,
  )
}

async function measureWindow(
  page: Page,
  engine: string,
  name: string,
  arm: Arm,
  drive: () => Promise<void>,
): Promise<WindowRecord> {
  await armGlass(page, arm)
  await startRecorder(page)
  await drive()
  // A long-task entry is delivered one task after the task it describes, so the sum is
  // read after a beat: without it the plant's busyMs stayed 0 while loafMs showed 222.
  await page.waitForTimeout(80)
  const frames = await readFrames(page)
  const record: WindowRecord = {
    ...frames,
    loops: await readLoops(page),
    glass: await readGlass(page),
  }
  logLine(engine, name, arm, record)
  // Every reported arm is checked for having measured something, so a delta is never taken
  // between a real window and an empty one.
  expectInstrumentAlive(record)
  return record
}

function expectInstrumentAlive(record: WindowRecord) {
  // A window that recorded no frames would report 0 long frames as an artifact of the
  // instrument, so the recorder has to prove it ran before any budget is read.
  expect(record.frames, 'frames recorded').toBeGreaterThan(20)
  // One tick chain on a 60 Hz lane cannot average below 10 ms; a second chain pushing into
  // the same gap list halves the mean and fakes a cheaper window.
  expect(record.meanMs, 'one tick chain per window').toBeGreaterThan(10)
  expect(record.worstMs).toBeGreaterThanOrEqual(record.meanMs)
  // Figure 4 is only a number against the declarations the built stylesheet carries.
  expect(record.loops.declaredInfinite).toBeGreaterThan(0)
  for (const name of record.loops.runningNames) {
    expect(
      record.loops.keyframeNames,
      `running loop ${name} is not a declared @keyframes`,
    ).toContain(name)
  }
}

test.describe.configure({ mode: 'serial' })

// The zero-long-frame budget is a host reading. When another workflow shares the runner, a
// single long frame describes the co-tenant, not the surface; the budget stands down with an
// annotation instead of being widened. The same bar and wording as q-quality QG1.
const LOAD_PER_CPU_BAR = 2.0

function expectNoLongFrames(record: WindowRecord, label: string) {
  const parallel = test.info().config.workers > 1
  const perCpu = loadavg()[0] / Math.max(cpus().length, 1)
  if (!parallel && perCpu <= LOAD_PER_CPU_BAR) {
    expect(record.longFrames, label).toBe(0)
    return
  }
  test.info().annotations.push({
    type: 'budget stood down',
    description: parallel
      ? `${label}: longFrames ${record.longFrames} not asserted; ${test.info().config.workers} workers share this run`
      : `${label}: longFrames ${record.longFrames} not asserted; ${perCpu.toFixed(2)} runnable tasks/CPU exceeds the ${LOAD_PER_CPU_BAR} bar`,
  })
}

test.describe('R4 motion and paint budget', () => {
  test.setTimeout(120_000)

  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await page.addInitScript(installRecorder)
    await gotoHash(page, '/chat', CHAT_PANEL)
    await page.waitForTimeout(400) // the mount animations land before anything is priced
  })

  test('window 1 idle: the settled /#/chat costs no long frame', async ({ page, browserName }) => {
    const shipped = await readGlass(page)
    console.log(
      `r4-motion SHIPPED-GLASS engine=${browserName} surfaces=${shipped.surfaces} painting=${shipped.painting}`,
    )

    const idle = () => page.waitForTimeout(1200)
    const off = await measureWindow(page, browserName, 'idle', 'off', idle)
    const on = await measureWindow(page, browserName, 'idle', 'on', idle)
    logAttribution('idle', off, on)

    expectNoLongFrames(off, 'window 1 idle')
    expect(off.glass.surfaces).toBeGreaterThan(0)
    expect(on.glass.painting).toBe(on.glass.surfaces) // the arm has to actually paint
    expect(off.glass.painting).toBe(0) // the shipped rule is the -webkit- alias only
  })

  test('window 2 scripted scroll: the slash menu scrolls without a backend', async ({
    page,
    browserName,
  }) => {
    await page.locator(CHAT_INPUT).click()
    await page.keyboard.press('/')
    await expect(page.locator(SLASH_SCROLL)).toBeVisible({ timeout: 3000 })

    const scroll = () =>
      page.evaluate((selector) => {
        return new Promise<void>((resolve) => {
          const el = document.querySelector(selector) as HTMLElement
          const start = performance.now()
          let position = 0
          let direction = 1
          const step = () => {
            position += direction * 6
            const max = el.scrollHeight - el.clientHeight
            if (position >= max) {
              position = max
              direction = -1
            } else if (position <= 0) {
              position = 0
              direction = 1
            }
            el.scrollTop = position
            if (performance.now() - start >= 1200) resolve()
            else requestAnimationFrame(step)
          }
          requestAnimationFrame(step)
        })
      }, SLASH_SCROLL)

    const off = await measureWindow(page, browserName, 'scroll', 'off', scroll)
    const on = await measureWindow(page, browserName, 'scroll', 'on', scroll)
    logAttribution('scroll', off, on)

    expectNoLongFrames(off, 'window 2 scroll')
  })

  test('window 3 local interaction: typing into the composer', async ({ page, browserName }) => {
    const text = 'Motion budget probe, one line of text that the composer has to render. '
    await page.locator(CHAT_INPUT).click()

    const clear = () =>
      page.evaluate(() => {
        const input = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement
        input.value = ''
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    const type = () => page.locator(CHAT_INPUT).pressSequentially(text, { delay: 8 })

    const off = await measureWindow(page, browserName, 'interaction', 'off', type)
    await clear()
    const on = await measureWindow(page, browserName, 'interaction', 'on', type)
    logAttribution('interaction', off, on)

    expectNoLongFrames(off, 'window 3 interaction')
  })

  test('window 4 live stream: one real turn on the product port', async ({
    page,
    request,
    browserName,
  }) => {
    if (!LIVE) {
      test.skip(
        true,
        'EPHE_MOTION_LIVE is unset: this window POSTs a real turn to the engine and the server keeps the session',
      )
      return
    }
    const health = await request.get(`${LIVE_ORIGIN}/api/health`).catch(() => null)
    if (!health || !health.ok()) {
      test.skip(true, `no product server answering GET ${LIVE_ORIGIN}/api/health`)
      return
    }
    test.setTimeout(300_000)

    await page.goto(`${LIVE_ORIGIN}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector(CHAT_PANEL, { timeout: 15000 })
    await page.waitForTimeout(400)

    const chars: number[] = []
    const stream = async () => {
      await page.locator(CHAT_INPUT).fill('Say only: OK')
      await page.keyboard.press('Enter')
      // The turn runs while the stop button is on screen and it is over when the send
      // button is back. Measured on the product port: the global aria-busy count sits at 1
      // while nothing streams, so it marks neither edge, and a restored session answers
      // inside an existing assistant bubble, so the bubble count does not move either.
      await expect(page.locator('[data-testid="stop-btn"]')).toBeVisible({ timeout: 20_000 })
      await expect(page.locator('[data-testid="send-btn"]')).toBeVisible({ timeout: 120_000 })
      chars.push(
        await page.evaluate(() => {
          const bubbles = document.querySelectorAll(
            '[data-testid="message-bubble"][data-role="assistant"]',
          )
          const newest = bubbles[bubbles.length - 1]
          return (newest?.textContent ?? '').trim().length
        }),
      )
    }

    const off = await measureWindow(page, browserName, 'stream', 'off', stream)
    const on = await measureWindow(page, browserName, 'stream', 'on', stream)
    // The two arms are two engine turns, so their token cadence differs: a delta of one
    // dropped frame here (measured: off worstMs=33.3/dropped25=1, on 16.8/0) is cadence,
    // and only a delta that survives repeats prices the glass.
    logAttribution('stream', off, on)
    console.log(
      `r4-motion STREAM-TURNS origin=${LIVE_ORIGIN} answerChars=[${chars.join(',')}] ` +
        `streamFramesOff=${off.frames} streamFramesOn=${on.frames}`,
    )

    expect(chars.length).toBe(2)
    expect(Math.min(...chars)).toBeGreaterThan(0) // the figures priced a real answer
  })

  test('the recorder sees a planted long frame, so a zero is a measurement', async ({
    page,
    browserName,
  }) => {
    const before = await measureWindow(page, browserName, 'plant-baseline', 'off', () =>
      page.waitForTimeout(600),
    )
    expectNoLongFrames(before, 'window 4 plant baseline')

    await startRecorder(page)
    await page.evaluate(() => {
      const until = performance.now() + 220
      while (performance.now() < until) {
        // the plant a frame budget has to be able to see
      }
    })
    await page.waitForTimeout(120) // the entry callbacks land after the blocking task
    const planted = await readFrames(page)
    logLine(browserName, 'plant', 'off', { ...planted, loops: before.loops, glass: before.glass })

    expect(planted.longFrames).toBeGreaterThanOrEqual(1)
    expect(planted.worstMs).toBeGreaterThan(150)
    expect(planted.busyMs + planted.loafMs).toBeGreaterThan(0)
  })

  test('figure 3 in an engine that honours the shipped glass rule', async ({
    page,
    browserName,
  }) => {
    let safari: Browser | null = null
    try {
      safari = await webkit.launch({ headless: true })
    } catch (error) {
      test.skip(true, `webkit is not installed: ${String(error).split('\n')[0]}`)
      return
    }
    const origin = new URL(page.url()).origin
    try {
      const context = await safari.newContext({
        viewport: { width: 1280, height: 800 },
        baseURL: origin,
      })
      const safariPage = await context.newPage()
      await ensureOnboarded(safariPage)
      await safariPage.addInitScript(installRecorder)
      await gotoHash(safariPage, '/chat', CHAT_PANEL)
      await safariPage.waitForTimeout(400)

      const shipped = await readGlass(safariPage)
      console.log(
        `r4-motion SHIPPED-GLASS engine=webkit surfaces=${shipped.surfaces} painting=${shipped.painting} (the lane above runs ${browserName})`,
      )
      const idle = () => safariPage.waitForTimeout(1200)
      const off = await measureWindow(safariPage, 'webkit', 'idle', 'off', idle)
      const on = await measureWindow(safariPage, 'webkit', 'idle', 'on', idle)
      logAttribution('idle-webkit', off, on)

      expect(shipped.painting).toBeGreaterThan(0) // WebKit applies the -webkit- alias
      expect(off.glass.painting).toBe(0)
      expect(on.glass.painting).toBe(on.glass.surfaces)
    } finally {
      await safari.close()
    }
  })
})
