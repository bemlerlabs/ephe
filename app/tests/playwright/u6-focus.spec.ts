import { expect, test, type Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { startAppFixture, type AppFixture } from './appFixture'

/**
 * U6 item #70, part 2: the keyboard path through the chat surface, walked rather than read.
 *
 * Four questions, each answered by Tab presses and computed styles on the running surface:
 *
 * 1. Is every interactive thing reachable, and does the one that has focus look focused?
 *    An element with `outline: none` and no shadow change is invisible to a keyboard user
 *    whatever the aria says, so the indicator is read off `getComputedStyle` at the moment the
 *    element holds focus, and its contrast against the surface the ring borders is computed.
 *    Light is the default theme and dark is the glass surface the contrast ratchet is written
 *    against, so the walk runs in both.
 * 2. What does a composer menu cost to leave? The chips sit one or two Tabs from the text
 *    field, and the way back in the other direction is a walk through the conversation: both
 *    numbers are printed, because the cheap route is the one a user who just came from the
 *    composer takes.
 * 3. Is a produced file a keyboard object — reachable, named, and actionable with Enter as
 *    well as Space — and where does focus land when it is acted on?
 * 4. What does the tab order do while a plan or a tool card streams, and does Escape obey the
 *    conduct rule in both directions (no modal above: the pane closes; a modal above: only the
 *    modal closes)?
 *
 * On the dev origin by default (`:5173`, compiles from `src`) with every `/api/` route stubbed,
 * so nothing here touches the live product server on :8765 and nothing here needs a rebuild of
 * the one shared `app/dist`. `EPHE_U6_USE_FIXTURE=1` switches to the built bundle on a free
 * port, which is what the timing lane needs and nothing in this file does.
 */

const OWN_LANE = process.env.EPHE_LATENCY_LANE === '1'
/**
 * Where the surface comes from. The dev server on :5173 compiles from `src` and is the
 * default: `app/dist` is one shared directory and two lanes racing a rebuild inside a
 * desktop build is measured history (04:51, `inter-greek-ext-700-normal-*.woff2` missing).
 * `EPHE_U6_USE_FIXTURE=1` switches to the built bundle on a free port, which is what the
 * latency lane needs and what nothing in this file needs.
 */
const USE_FIXTURE = process.env.EPHE_U6_USE_FIXTURE === '1'
const DEV_ORIGIN = process.env.EPHE_U6_ORIGIN ?? 'http://localhost:5173'
const FILE_NAME = 'quadrant-report.pdf'
const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../../../out/u6-keyboard')
const MAX_STOPS = 160

const CHAT_INPUT = '[data-testid="chat-input"]'
const MODE_SELECTOR = '[data-testid="composer-mode-selector"]'
const ATTACH_PLUS = '[data-testid="composer-attach-plus"]'
const TOOL_ROWS = '[data-testid="tool-stream-rows"]'

type Stop = {
  index: number
  walkId?: string
  name: string
  indicator: string
  shadow: string
  outlineWidth: number
  hasRing: boolean
  visible: boolean
  ringContrast: number
  fillContrast: number
  outlineContrast: number
  outlineOffset: number
  surface: string
}

const walks: Record<string, Stop[]> = {}
let fixture: AppFixture | null = null

function installFocusProbe() {
  // Names repeat (a row of identical buttons), so identity is stamped on the element:
  // a walk that dedupes by label stops early and undercounts what it is meant to count.
  let stamped = 0

  const rgb = (value: string): [number, number, number, number] | null => {
    const m = /rgba?\(([^)]+)\)/.exec(value)
    if (!m) return null
    const parts = String(m[1])
      .split(/[\s,/]+/)
      .filter(Boolean)
      .map(Number)
    if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return null
    return [parts[0]!, parts[1]!, parts[2]!, parts.length > 3 ? parts[3]! : 1]
  }

  // Chrome reports a `color-mix`/token colour as `oklab(L a b)`, and that is exactly how the
  // glass tokens arrive here (`--color-forest-glow`). An unparseable cue would have been read
  // as "no cue" and the button would then look like a 1.1:1 ring.
  const oklab = (value: string): [number, number, number, number] | null => {
    const m = /oklab\(([^)]+)\)/.exec(value)
    if (!m) return null
    const parts = String(m[1])
      .split(/[\s/]+/)
      .filter(Boolean)
      .map(Number)
    if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return null
    const [L, A, B] = parts as [number, number, number]
    const alpha = parts.length > 3 ? parts[3]! : 1
    const l_ = L + 0.3963377774 * A + 0.2158037573 * B
    const m_ = L - 0.1055613458 * A - 0.0638541728 * B
    const s_ = L - 0.0894841775 * A - 1.291485548 * B
    const [l, mm, s] = [l_ ** 3, m_ ** 3, s_ ** 3]
    const encode = (v: number) => {
      const c = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.max(v, 0) ** (1 / 2.4) - 0.055
      return Math.round(Math.min(1, Math.max(0, c)) * 255)
    }
    return [
      encode(4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s),
      encode(-1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s),
      encode(-0.0038494008 * l - 0.7095617562 * mm + 1.7088535324 * s),
      alpha,
    ]
  }

  const color = (value: string): [number, number, number, number] | null =>
    rgb(value) ?? oklab(value)

  const luminance = (r: number, g: number, b: number): number => {
    const channel = (v: number) => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  }

  // The colour the ring is drawn against. `outline-offset` is what decides this: a ring
  // pushed 2 px out of the border box (`globals.css:663-664`, the program's only focus
  // outline) does not touch the element's own fill — the 2 px gap shows whatever is *behind*
  // the element, so the stack starts at the parent. Reading the element's own background
  // instead reported the skip links at 2.31:1 against their green pill, which is a colour the
  // ring never borders.
  //
  // `backdrop-filter` glass is not in this model and the figure is named an approximation
  // because of it; a ring measured against its own parent's `rgba(0,0,0,0)` would score
  // nothing at all.
  const surfaceUnder = (el: Element, skipOwnFill: boolean): [number, number, number] => {
    const stack: [number, number, number, number][] = []
    let node: Element | null = skipOwnFill ? el.parentElement : el
    while (node) {
      const parsed = color(getComputedStyle(node).backgroundColor)
      if (parsed && parsed[3] > 0) stack.push(parsed)
      node = node.parentElement
    }
    let out: [number, number, number] = [255, 255, 255]
    for (let i = stack.length - 1; i >= 0; i -= 1) {
      const [r, g, b, a] = stack[i]!
      const alpha = a > 1 ? 1 : a
      out = [
        out[0] + (r - out[0]) * alpha,
        out[1] + (g - out[1]) * alpha,
        out[2] + (b - out[2]) * alpha,
      ]
    }
    return out
  }

  const ratio = (fg: [number, number, number], bg: [number, number, number]): number => {
    const a = luminance(fg[0], fg[1], fg[2])
    const b = luminance(bg[0], bg[1], bg[2])
    return Number(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(2))
  }

  // The colours a focus indicator is actually drawn in. `.focus-ring:focus-visible` paints an
  // outline AND a two-part box-shadow (globals.css:543-546), and a stop whose outline is the
  // near-black outer part of that pair is not an invisible ring — the ring is the glow. Taking
  // the outline alone reported `new-session` at 1.1:1, which would have been a false finding
  // about somebody else's surface.
  const cueColors = (style: CSSStyleDeclaration): [number, number, number][] => {
    const out: [number, number, number][] = []
    if (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2) {
      const c = color(style.outlineColor)
      if (c && c[3] > 0) out.push([c[0], c[1], c[2]])
    }
    if (style.boxShadow !== 'none') {
      for (const part of style.boxShadow.split(/,(?![^(]*\))/)) {
        const c = color(part.trim())
        if (c && c[3] > 0) out.push([c[0], c[1], c[2]])
      }
    }
    return out
  }

  const outlineOnly = (style: CSSStyleDeclaration): [number, number, number] | null => {
    if (style.outlineStyle === 'none' || parseFloat(style.outlineWidth) < 2) return null
    const c = color(style.outlineColor)
    return c && c[3] > 0 ? [c[0], c[1], c[2]] : null
  }

  const describe = () => {
    const el = document.activeElement as HTMLElement | null
    if (!el || el === document.body) return null
    if (!el.dataset.walkId) el.dataset.walkId = String(++stamped)
    const style = getComputedStyle(el)
    const testid = el.getAttribute('data-testid')
    const role = el.getAttribute('role')
    const label = el.getAttribute('aria-label') ?? (el.textContent ?? '').trim().slice(0, 24) ?? ''
    const box = el.getBoundingClientRect()
    const offset = parseFloat(style.outlineOffset) || 0
    const behind = surfaceUnder(el, offset >= 2)
    const ownFill = surfaceUnder(el, false)
    return {
      index: 0,
      walkId: el.dataset.walkId,
      name: `${el.tagName.toLowerCase()}${testid ? `[${testid}]` : role ? `[role=${role}]` : ''}${
        el.id ? `#${el.id}` : ''
      }${label ? ` "${label}"` : ''}`,
      indicator: `${style.outlineWidth} ${style.outlineStyle} ${style.outlineColor} | ${
        style.boxShadow === 'none' ? 'no-shadow' : 'shadow'
      }`,
      shadow: style.boxShadow,
      outlineWidth: parseFloat(style.outlineWidth) || 0,
      // The old rule was `!(width < 2 && style === 'none')`, which called
      // `outline: 2px solid transparent` a focus indicator. A ring has to be drawn:
      // a style that is not none, a width a user can see, and a colour that is not the
      // absence of one. A box-shadow ring counts, because that is how the glass surfaces
      // draw theirs.
      hasRing:
        (style.outlineStyle !== 'none' &&
          parseFloat(style.outlineWidth) >= 2 &&
          style.outlineColor !== 'rgba(0, 0, 0, 0)') ||
        style.boxShadow !== 'none',
      visible: box.width > 0 && box.height > 0,
      // The strongest of the drawn cues against the surface the ring actually borders; -1 when
      // nothing is drawn at all. `fillContrast` is the same cue against the element's own fill,
      // which is the adjacency only when the ring has no offset.
      ringContrast: (() => {
        const cues = cueColors(style)
        if (!cues.length) return -1
        return Math.max(...cues.map((cue) => ratio(cue, behind)))
      })(),
      fillContrast: (() => {
        const cues = cueColors(style)
        if (!cues.length) return -1
        return Math.max(...cues.map((cue) => ratio(cue, ownFill)))
      })(),
      // The hard-edged cue alone, without the glow: a 16 px blurred shadow read as a solid
      // colour flatters the surface it is drawn on, so both numbers go in the record.
      outlineContrast: (() => {
        const cue = outlineOnly(style)
        return cue ? ratio(cue, behind) : -1
      })(),
      surface: `rgb(${behind.map((n) => Math.round(n)).join(',')})`,
      outlineOffset: offset,
    }
  }
  ;(window as unknown as Record<string, unknown>).__focusProbe = { describe }
}

type StopSnapshot = (Omit<Stop, 'index'> & { walkId?: string }) | null

async function describeFocused(page: Page): Promise<StopSnapshot> {
  return page.evaluate(() =>
    (window as unknown as { __focusProbe: { describe(): StopSnapshot } }).__focusProbe.describe(),
  )
}

/** The answer the surface gets to, with one produced file in it. No engine, no :8765. */
async function stubStream(route: import('@playwright/test').Route) {
  const url = route.request().url()
  if (url.includes('/api/chat/stream')) {
    // Held open long enough that "while a stream runs" is a state the walk can stand in.
    await new Promise((done) => setTimeout(done, 900))
    const frames = [
      { type: 'tool_start', tool: 'write_file', args: { path: FILE_NAME } },
      { type: 'stdout', tool: 'write_file', data: 'writing' },
      { type: 'tool_done', tool: 'write_file', result: 'ok', duration_ms: 12 },
      { type: 'file_result', file_type: 'pdf', path: `/workspace/${FILE_NAME}`, id: 'art-7' },
      { type: 'chunk', data: 'The report is ready. ' },
      { type: 'done' },
    ]
      .map((event) => `data: ${JSON.stringify(event)}\n\n`)
      .join('')
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: frames,
    })
  }
  if (url.includes('/api/setup/status')) {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        skipped: false,
        provider: 'openai_compatible',
        model: 'stub-model',
        url: null,
      }),
    })
  }
  if (url.includes('/api/health')) {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        version: 'stub',
        models: ['stub-model'],
        active_model: 'stub-model',
        active_provider: 'openai_compatible',
      }),
    })
  }
  return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
}

async function openChat(page: Page, theme: 'light' | 'dark' = 'light') {
  page.on('pageerror', (error) => console.log(`u6-focus PAGEERROR ${String(error).slice(0, 160)}`))
  // Installed before the first request: on the dev origin an unstubbed /api would reach
  // the live product server on :8765, which another lane is holding.
  // A glob on `/api/` would also catch the module Vite serves at
  // `/src/lib/api/endpoints.ts` and answer it with JSON, which kills the boot: the match is
  // on the request path, not on the substring.
  await page.route((url) => new URL(url).pathname.startsWith('/api/'), stubStream)
  await page.addInitScript(installFocusProbe)
  await page.addInitScript((mode) => {
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
    // theme.ts: getStoredTheme() reads 'dark' or falls back to light, and the class lives on
    // <html>. The ring is `--color-ring: var(--color-ink)` in both, so one theme proves
    // nothing about the other: light is the default and dark is the glass surface the
    // contrast ratchet is written against.
    if (mode === 'dark') localStorage.setItem('ephe.theme', 'dark')
  }, theme)
  const origin = USE_FIXTURE ? fixture?.origin : DEV_ORIGIN
  if (!origin) throw new Error('no origin: the fixture never started')
  await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
  if (!USE_FIXTURE) {
    // The bundle registers a service worker that answers /api from its own fetch context,
    // which silently bypasses page routing (`visual.spec.ts:242` pays for that lesson).
    await page
      .evaluate(async () => {
        if (!navigator.serviceWorker) return
        const registrations = await navigator.serviceWorker.getRegistrations()
        for (const registration of registrations) await registration.unregister()
      })
      .catch(() => undefined)
    await page.reload({ waitUntil: 'load' })
  }
  await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 20_000 })
  // Proving the theme actually applied, rather than assuming the init script did it: the ring
  // colours of two walks that were in the same theme would be byte-identical, and that reads
  // as "both themes pass" to anyone who is not looking.
  const applied = await page.evaluate(() => document.documentElement.className || '(no class)')
  console.log(`u6-focus THEME asked=${theme} htmlClass=${applied}`)
  expect(
    applied.includes('light'),
    `asked for ${theme} and the document carries class "${applied}" — the walk would silently ` +
      'measure the wrong theme',
  ).toBe(theme === 'light')
  await page.locator(CHAT_INPUT).click()
}

/**
 * Whether the pane is open, read off the toggle's own `aria-pressed`
 * (chat/index.tsx:439). The pane root carries no testid, and a locator over "any element
 * that looks like a panel" silently reads false when a tab bar is renamed.
 */
async function paneOpen(page: Page): Promise<boolean> {
  const value = await page.locator('[data-testid="side-panel-toggle"]').getAttribute('aria-pressed')
  return value === 'true'
}

/** One turn with a produced file in the answer, so the card exists to be reached. */
async function sendTurnWithFile(page: Page) {
  await page.locator(CHAT_INPUT).focus()
  await page.keyboard.type('produce the report')
  await page.keyboard.press('Enter')
  await page.waitForSelector('[data-testid^="message-file-"]', { timeout: 25_000 })
}

/** Walk the tab order from the current focus until it cycles back, or the budget runs out. */
async function walkTabOrder(page: Page, key: string, budget = MAX_STOPS): Promise<Stop[]> {
  const first = await describeFocused(page)
  const stops: Stop[] = []
  const seen = new Set<string>()
  for (let index = 1; index <= budget; index += 1) {
    await page.keyboard.press('Tab')
    const stop = await describeFocused(page)
    if (!stop) continue
    const id = stop.walkId ?? stop.name
    if (first && id === first.walkId) break
    if (seen.has(id)) break
    seen.add(id)
    stops.push({ ...stop, index })
  }
  walks[key] = stops
  // Written per walk, not only in afterAll: a failing assertion ends the run, and the
  // evidence a finding needs is exactly the walk that failed.
  await writeFile(resolve(OUT_DIR, 'focus-walks.json'), JSON.stringify(walks, null, 1), 'utf-8')
  return stops
}

/** Tabs from `selector` back to the text field, walking forward and back. */
async function returnCost(page: Page, selector: string) {
  await page.locator(selector).focus()
  let forward = -1
  for (let press = 1; press <= MAX_STOPS; press += 1) {
    await page.keyboard.press('Tab')
    if (
      await page.evaluate((target) => document.activeElement?.matches(target) === true, CHAT_INPUT)
    ) {
      forward = press
      break
    }
  }
  await page.locator(selector).focus()
  let backward = -1
  for (let press = 1; press <= MAX_STOPS; press += 1) {
    await page.keyboard.press('Shift+Tab')
    if (
      await page.evaluate((target) => document.activeElement?.matches(target) === true, CHAT_INPUT)
    ) {
      backward = press
      break
    }
  }
  console.log(
    `u6-focus RETURN from=${selector.replace('[data-testid="', '').replace('"]', '')} ` +
      `forwardTabs=${forward} backwardTabs=${backward}`,
  )
  return { forward, backward }
}

function logWalk(key: string, stops: Stop[]) {
  const blind = stops.filter((stop) => !stop.hasRing)
  const kinds = [...new Set(stops.map((stop) => stop.indicator))]
  const drawn = stops.filter((stop) => stop.ringContrast >= 0).map((stop) => stop.ringContrast)
  const worst = stops
    .filter((stop) => stop.ringContrast >= 0)
    .sort((a, b) => a.ringContrast - b.ringContrast)
    .slice(0, 3)
  console.log(
    `u6-focus WALK ${key} stops=${stops.length} withoutIndicator=${blind.length}` +
      (blind.length
        ? ` blind=[${blind
            .slice(0, 12)
            .map((stop) => stop.name)
            .join(', ')}]`
        : '') +
      ` indicatorKinds=${kinds.length} seen=[${kinds.slice(0, 4).join(' / ')}]` +
      (drawn.length
        ? ` ringContrastMedian=${median(drawn).toFixed(2)} min=${Math.min(...drawn).toFixed(2)} ` +
          // The under-3 list is the report's finding set; it is printed rather than asserted
          // because a ring has two adjacent colours and this probe reads one of them.
          `under3=[${stops
            .filter((stop) => stop.ringContrast >= 0 && stop.ringContrast < 3)
            .map(
              (stop) =>
                `${stop.name} ${stop.ringContrast}/${stop.outlineContrast} on ${stop.surface} (fill ${stop.fillContrast}, offset ${stop.outlineOffset})`,
            )
            .join(' | ')}] ` +
          `worst=[${worst
            .map(
              (stop) =>
                `${stop.name} ${stop.ringContrast}/${stop.outlineContrast} on ${stop.surface} fill=${stop.fillContrast} offset=${stop.outlineOffset} shadow=${stop.shadow.slice(0, 48)}`,
            )
            .join(' | ')}]`
        : ' ringContrast=none-drawn-as-outline'),
  )
}

function median(values: number[]): number {
  if (!values.length) return Number.NaN
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor((sorted.length - 1) / 2)] ?? Number.NaN
}

test.describe('U6 focus and tab order', () => {
  test.skip(!OWN_LANE, 'runs under tests/playwright/latency.config.ts, the timing lane')
  test.setTimeout(180_000)

  test.beforeAll(async () => {
    await mkdir(OUT_DIR, { recursive: true })
    if (USE_FIXTURE) {
      fixture = await startAppFixture({
        kind: 'chat',
        engineMs: 200,
        chunks: [
          { type: 'tool_start', tool: 'read_file', args: { path: 'a.ts' } },
          'reading ',
          { type: 'stdout', tool: 'read_file', data: 'export const' },
          'the ',
          { type: 'tool_done', tool: 'read_file', result: 'ok', duration_ms: 12 },
          // The card test needs a produced file in the answer, in fixture mode as well as on
          // the dev origin; without this frame the built bundle never renders one and the
          // wait for `[data-testid^="message-file-"]` runs out after 25 s.
          {
            type: 'file_result',
            file_type: 'pdf',
            path: '/workspace/quadrant-report.pdf',
            id: 'act-7',
          },
          'file ',
          { type: 'tool_start', tool: 'search', args: { q: 'x' } },
          'and ',
          'this ',
          { type: 'tool_done', tool: 'search', result: 'ok', duration_ms: 4 },
          'that.',
        ],
        chunkGapMs: 300,
      })
      console.log(`u6-focus ORIGIN fixture ${fixture.origin}`)
    } else {
      console.log(
        `u6-focus ORIGIN dev-server ${DEV_ORIGIN} (compiles from src, no shared dist rebuild)`,
      )
    }
  })

  test.afterAll(async () => {
    await fixture?.close()
    await writeFile(resolve(OUT_DIR, 'focus-walks.json'), JSON.stringify(walks, null, 1), 'utf-8')
    fixture = null
  })

  test('every stop in the chat tab order shows its own focus, in both themes', async ({
    browser,
  }) => {
    // One page per theme. Reusing the page and going to the same URL again is a same-document
    // navigation (`/#/chat` differs by nothing), which never re-runs the init script that sets
    // `ephe.theme` — the second walk then measured the first theme and printed byte-identical
    // figures for what looked like two.
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
      const page = await context.newPage()
      await openChat(page, theme)
      const stops = await walkTabOrder(page, `idle-${theme}`)
      logWalk(`idle-${theme}`, stops)
      expect(stops.length).toBeGreaterThan(0)
      await page.screenshot({ path: resolve(OUT_DIR, `tab-walk-idle-${theme}.png`) })
      const blind = stops.filter((stop) => !stop.hasRing)
      expect(
        blind,
        `${theme}: stops with no visible focus indicator: ${blind.map((s) => s.name).join(', ')}`,
      ).toHaveLength(0)
      // The figure that decides whether the walk is worth reading at all: a ring drawn in a
      // colour within 1.2 of its own surface is a ring nobody can see. The threshold is the
      // instrument's legibility floor, not a gate on the product — anything under 3 is printed
      // as a finding, because a ring has two adjacent colours and this probe reads one.
      const faint = stops.filter((stop) => stop.ringContrast >= 0 && stop.ringContrast < 1.2)
      expect(
        faint,
        `${theme}: outlines indistinguishable from their surface: ${faint
          .map((s) => `${s.name} ${s.ringContrast} on ${s.surface}`)
          .join(', ')}`,
      ).toHaveLength(0)
      await context.close()
    }
  })

  test('the composer is close behind the chips and far in front of them', async ({ page }) => {
    await openChat(page)
    let tabsToMode = 0
    await page.locator(CHAT_INPUT).focus()
    for (let press = 1; press <= 20; press += 1) {
      await page.keyboard.press('Tab')
      tabsToMode = press
      if (
        await page.evaluate(
          () => document.activeElement?.matches('[data-testid="composer-mode-selector"]') === true,
        )
      )
        break
    }
    const fromMode = await returnCost(page, MODE_SELECTOR)
    const fromAttach = await returnCost(page, ATTACH_PLUS)
    console.log(
      `u6-focus FROM-COMPOSER toModeChip=${tabsToMode} ` +
        `modeRoundTrip=${tabsToMode + fromMode.backward}`,
    )
    // A keyboard user leaving a chip must not have to walk the conversation: the round trip
    // forward is the bug this figure exists to notice.
    expect(fromMode.backward).toBeLessThanOrEqual(4)
    expect(fromAttach.backward).toBeLessThanOrEqual(4)
    expect(fromMode.forward).toBeGreaterThan(fromMode.backward)
  })

  test('the composer status control can hold focus', async ({ page }) => {
    // Tab reaches `agent-status-pill`, so it is part of the ring. What the walk cannot say
    // is whether a user can stop on it: the probe below focuses it and watches for a second
    // and a half, which is how long it takes to read a label and press on.
    await openChat(page)
    const pill = page.locator('[data-testid="agent-status-pill"]')
    test.skip((await pill.count()) === 0, 'the surface shows no status pill')
    await pill.focus()
    const samples: string[] = []
    for (let tick = 0; tick < 15; tick += 1) {
      samples.push((await describeFocused(page))?.name ?? 'body')
      await page.waitForTimeout(100)
    }
    const held = samples.every((name) => name.includes('agent-status-pill'))
    console.log(
      `u6-focus PILL held=${held} first=${samples[0]} last=${samples[samples.length - 1]} ` +
        `distinct=${[...new Set(samples)].join(' -> ')}`,
    )
    expect(held, `focus left the status pill on its own: ${samples.join(' ')}`).toBe(true)
  })

  test('a produced file is a keyboard object in the message that made it', async ({ page }) => {
    await openChat(page)
    await sendTurnWithFile(page)
    const card = page.locator(`[data-testid^="message-file-open-"]`)
    const count = await card.count()
    test.skip(count === 0, `the stubbed turn produced no file card (frames changed shape)`)

    // Named with the filename, not just an icon: a screen reader reading the card list has
    // to be able to tell three produced files apart.
    const names = await card.evaluateAll((els) =>
      els.map((el) => ({
        label: el.getAttribute('aria-label') ?? '',
        text: (el.textContent ?? '').trim(),
        tabindex: (el as HTMLElement).tabIndex,
      })),
    )
    console.log(`u6-focus CARD opens=${count} first=${JSON.stringify(names[0])}`)
    const firstName = names[0]
    expect(firstName, 'the produced file rendered no open button').toBeTruthy()
    expect(firstName?.label, 'the open button carries no filename').toContain(FILE_NAME)

    // Reachable by Tab from the composer, and Enter is enough to act on it.
    const stops = await walkTabOrder(page, 'with-file-card')
    const reached = stops.some((stop) => stop.name.includes('message-file-open-'))
    console.log(
      `u6-focus CARD reachableByTab=${reached} stops=${stops.length} ` +
        `blind=${stops
          .filter((stop) => !stop.hasRing)
          .map((s) => s.name)
          .join(',')}`,
    )
    expect(reached, 'no file-card action is in the tab order').toBe(true)

    await page.locator(`[data-testid^="message-file-open-"]`).first().focus()
    const before = await paneOpen(page)
    await page.keyboard.press('Enter')
    await expect.poll(() => paneOpen(page), { timeout: 5_000 }).toBe(true)
    // The landing point is walked for a second, not read once: `usePreviewNav.ts:113-118`
    // schedules the follow-through into the pane's address bar 60 ms after the open event and
    // skips it when focus already stands inside the panel, so a single read can catch either
    // side of the timer and the same product would report two different behaviours.
    const trail: string[] = []
    for (let tick = 0; tick < 9; tick += 1) {
      const stop = await describeFocused(page)
      const name = stop?.name ?? 'body'
      if (trail[trail.length - 1] !== name) trail.push(name)
      await page.waitForTimeout(110)
    }
    const landed = trail[trail.length - 1] ?? 'body'
    console.log(
      `u6-focus CARD enter paneBefore=${before} paneAfter=true focusTrail=[${trail.join(' → ')}]`,
    )
    await page.screenshot({ path: resolve(OUT_DIR, 'file-card-after-enter.png') })
    expect(landed, 'Enter dropped focus to the document body').not.toBe('body')
    // Space has to do the same thing: a button answers both, and a div styled as one does not.
    await page.locator('[data-testid^="message-file-open-"]').first().focus()
    await page.keyboard.press('Space')
    await expect.poll(() => paneOpen(page), { timeout: 5_000 }).toBe(true)
  })

  test('Escape closes the pane, and a modal above it keeps its own Escape', async ({ page }) => {
    await openChat(page)
    const toggle = page.locator('[data-testid="side-panel-toggle"]')
    const pane = () => paneOpen(page)

    // Direction 1: no modal above, so Escape belongs to the pane.
    await toggle.click()
    await expect.poll(pane).toBe(true)
    const focusOnOpen = await describeFocused(page)
    await page.keyboard.press('Escape')
    await expect.poll(pane).toBe(false)
    console.log(
      `u6-focus ESCAPE paneClosedByEscape=true focusWhenOpen=${focusOnOpen?.name ?? 'body'}`,
    )

    // Direction 2: a dialog is above the pane. The same key has to be consumed by the
    // dialog alone — an Escape that closes both is the same defect by another name, because
    // the user loses the pane they were reading while dismissing an overlay.
    await toggle.click()
    await expect.poll(pane).toBe(true)
    await page.keyboard.press('Control+k')
    const dialog = page.locator('[role="dialog"]')
    await expect.poll(() => dialog.count()).toBeGreaterThan(0)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
    const dialogLeft = await page.locator('[role="dialog"]').count()
    const paneLeft = await pane()
    console.log(`u6-focus ESCAPE withDialog dialogAfter=${dialogLeft} paneAfter=${paneLeft}`)
    expect(dialogLeft, 'the dialog did not take its own Escape').toBe(0)
    expect(paneLeft, 'Escape through a dialog closed the pane too').toBe(true)
    await page.keyboard.press('Escape')
    await expect.poll(pane).toBe(false)
    await page.screenshot({ path: resolve(OUT_DIR, 'escape-with-dialog.png') })
  })

  test('the tab order does not move under a streaming tool card', async ({ page }) => {
    await openChat(page)
    const before = await walkTabOrder(page, 'before-stream')
    logWalk('before-stream', before)

    await page.locator(CHAT_INPUT).focus()
    await page.keyboard.type('run the tool')
    await page.keyboard.press('Enter')
    await page.waitForSelector(TOOL_ROWS, { timeout: 20_000 })

    const during = await walkTabOrder(page, 'during-stream')
    logWalk('during-stream', during)

    const focused = await describeFocused(page)
    console.log(
      `u6-focus STREAM stopsBefore=${before.length} stopsDuring=${during.length} ` +
        `addedDuring=${during.length - before.length} focusAtEndOfWalk=${focused?.name ?? 'body'}`,
    )
    await page.screenshot({ path: resolve(OUT_DIR, 'tab-walk-during-stream.png') })

    // Rows added by the stream must not be the reason focus escapes the surface: the walk
    // still has to end where it started.
    // Identity, not the accessible name: the token counter is the same element the whole
    // time and only its label changes, so a name comparison reports a live control as
    // "removed from the tab order" every single run.
    // The one family allowed to leave is the empty state. chat/index.tsx:533 renders
    // `WelcomeEmptyState` only while the session has no messages, so sending a turn replaces
    // those four pills with the message list — that is the design, and a check that called it
    // a defect would be a check that can never go green.
    const ids = new Set(during.map((stop) => stop.walkId ?? stop.name))
    const gone = before.filter((stop) => !ids.has(stop.walkId ?? stop.name))
    const emptyState = gone.filter((stop) => stop.name.includes('[welcome-card-'))
    console.log(
      `u6-focus STREAM removed=${gone.length} emptyState=${emptyState.length} ` +
        `other=${gone.length - emptyState.length}`,
    )
    for (const stop of gone) {
      expect(
        stop.name,
        `the stream removed ${stop.name} from the tab order and it is not empty-state furniture`,
      ).toContain('[welcome-card-')
    }
    expect(during.length).toBeGreaterThanOrEqual(before.length)
  })
})
