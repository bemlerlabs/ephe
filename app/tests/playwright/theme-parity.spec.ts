import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page, type Browser } from '@playwright/test'
import { startAppFixture, type AppFixture } from './appFixture'

/**
 * Wave D0 — the parity gate, now on one ground.
 *
 * The product ships one visual language and one theme: the forest (owner decision 2026-10-19
 * removed the paper ground, `docs/DESIGN.md` §3). What this spec exists for has not changed —
 * until it ran, the contrast question was answered per screen by hand, and an assumption is
 * what lets a token reach a canvas it was never measured on.
 *
 * For every surface the app can be navigated to — the run states, the four registers, the
 * onboarding and all 23 settings tabs — at both the phone and the desktop width, it walks the
 * painted DOM and computes the WCAG contrast of every visible text run against the background
 * it is actually composited onto (the ancestor stack, so a glass veil counts as the blend it
 * paints, not as its own alpha) and every control boundary against the ground behind it. The
 * third class this wave carried, an unbent dark surface on paper, left with the paper ground:
 * its subject no longer exists, and a metric that can never fire is not coverage.
 *
 *
 * No axe-core: the wave rule is no new npm package, and the audit needs only
 * `getComputedStyle`, which the r33 lane already trusts.
 *
 * The gate is a ratchet, not a claim of zero: `theme-parity.baseline.json` holds the count per
 * surface and metric that the tree measured when this instrument landed, and a surface that
 * exceeds its entry, or appears without one, is red. A baseline moves in its own commit with
 * the before/after count, exactly like `.design-tokens-baseline.json` (DESIGN.md §12).
 *
 * `EPHE_THEME_SWEEP=1` additionally writes one PNG per surface/ground/width into
 * `out/forest-sweep-2026-10-19/` named `<surface>-<ground>-<width>.png` and the full list
 * beside it. That is the evidence pass; the committed lane only measures.
 *
 * Runner: `pnpm exec playwright test -c tests/playwright/playwright.config.ts theme-parity --workers=1`
 * Add `EPHE_THEME_SWEEP=1` for the captures. The bundle has to be current: `npm run build` first.
 */

const HERE = dirname(fileURLToPath(import.meta.url))
const SWEEP = process.env.EPHE_THEME_SWEEP === '1'
const OUT_DIR = resolve(HERE, '../../../out/forest-sweep-2026-10-19')
const BASELINE_PATH = resolve(HERE, 'theme-parity.baseline.json')

const TEXT_FLOOR = 4.5
const LARGE_TEXT_FLOOR = 3
const BOUNDARY_FLOOR = 3

type Metric = 'text' | 'boundary' | 'render-error'

type Finding = {
  metric: Metric
  path: string
  detail: string
  ratio: number
}

type Counts = Record<Metric, number>

type Baseline = Record<string, Counts>

/** The last uncaught error the bundle reported. A route that lands on the crash fallback shows
 *  its message in a collapsed disclosure the audit cannot always read, so the page's own error
 *  event is the record this instrument trusts. */
let lastPageError = ''

const watchErrors = (page: Page, label: string) => {
  const note = (where: string, text: string) => {
    if (lastPageError) return
    lastPageError = `${label} (${where}): ${text.slice(0, 200)}`
    console.log(`theme-parity ERROR ${lastPageError}`)
  }
  page.on('pageerror', (error) => note('pageerror', String(error.message ?? error)))
  // A render throw is caught by the boundary and reaches the log, not the window, so the
  // console is where the message actually is.
  page.on('console', (message) => {
    if (message.type() === 'error') note('console', message.text())
  })
}

/** The reads every surface needs, so a row is a named payload and not this machine's data.
 *  Anchored and ordered specific-to-generic: the fixture takes the first match, and an
 *  unanchored `/api/artifacts` also answers `/api/artifacts/<id>/preview`, which hands the
 *  preview caller a list and the page a render crash. */
const HASH_A = `sha256:${'9f'.repeat(32)}`
const READS: Array<[RegExp, () => unknown]> = [
  [
    /^\/api\/memory\/list$/,
    () => ({
      entries: [
        {
          id: 'd0-1',
          content: 'The studio keeps one warm light source: the fire-spirit bee.',
          type: 'fact',
          source: 'session:d0',
          tags: ['design'],
          created_at: '2026-10-18T08:00:00+00:00',
          pinned: true,
        },
        {
          id: 'd0-2',
          content: 'A token that exists only in the dark block is a defect on the shipped ground.',
          type: 'preference',
          source: 'session:d0',
          tags: [],
          created_at: '2026-10-17T18:00:00+00:00',
          pinned: false,
        },
        {
          id: 'd0-3',
          content: 'Contrast is measured against the composited ground, never the veil alone.',
          type: 'fact',
          source: 'kepta',
          tags: ['a11y'],
          created_at: '2026-10-16T11:20:00+00:00',
          superseded_by: 'd0-2',
        },
      ],
      total: 3,
    }),
  ],
  [
    /^\/api\/memory\/stats$/,
    () => ({
      total: 3,
      provider: 'kepta',
      vector_leg: true,
      lexical_leg: true,
      deleted: 1,
    }),
  ],
  [
    /^\/api\/artifacts\/stats$/,
    () => ({
      count: 2,
      bytes: 4096,
      by_kind: [
        { kind: 'pdf', count: 1, bytes: 2048 },
        { kind: 'text', count: 1, bytes: 2048 },
      ],
      expiring_count: 1,
      expiring_bytes: 2048,
      next_expiry: '2026-11-17T08:00:00+00:00',
    }),
  ],
  [
    /^\/api\/artifacts\/expiry$/,
    () => ({
      due: [{ id: 'd0-a1', name: 'parity-report.pdf', expires_at: '2026-11-17T08:00:00+00:00' }],
      count: 1,
      bytes: 2048,
      days: 30,
    }),
  ],
  [
    /^\/api\/artifacts\/[^/]+\/versions$/,
    () => ({
      versions: [
        {
          id: 'd0-a1',
          version: 2,
          name: 'parity-report.pdf',
          created_at: '2026-10-18T08:00:00+00:00',
          size: 2048,
        },
        {
          id: 'd0-a1',
          version: 1,
          name: 'parity-report.pdf',
          created_at: '2026-10-17T08:00:00+00:00',
          size: 1900,
        },
      ],
    }),
  ],
  [/^\/api\/artifacts\/[^/]+\/preview$/, () => ({ mode: 'none', reason: 'no-text-preview' })],
  [
    /^\/api\/artifacts\/[^/]+\/provenance$/,
    () => ({
      known: true,
      turn_id: 'd0turn01',
      call_id: 'd0call-0',
      args_hash: 'sha256:args',
      session_id: 'sess-d0',
      calls: [{ call_id: 'd0call-0', tool: 'create_pdf', args: { topic: 'Theme parity sweep' } }],
    }),
  ],
  [
    /^\/api\/artifacts\/[^/]+$/,
    () => ({
      id: 'd0-a1',
      root_id: 'd0-a1',
      version: 2,
      session_id: 'sess-d0',
      name: 'parity-report.pdf',
      path: '/home/d0/.ephe/artifacts/sess-d0/parity-report.pdf',
      kind: 'pdf',
      size: 2048,
      topic: 'Theme parity sweep',
      created_at: '2026-10-18T08:00:00+00:00',
      favorite: true,
      tags: ['d0'],
      adopted_state: 'none',
    }),
  ],
  [
    /^\/api\/artifacts$/,
    () => ({
      artifacts: [
        {
          id: 'd0-a1',
          root_id: 'd0-a1',
          version: 2,
          session_id: 'sess-d0',
          name: 'parity-report.pdf',
          path: '/home/d0/.ephe/artifacts/sess-d0/parity-report.pdf',
          kind: 'pdf',
          size: 2048,
          topic: 'Theme parity sweep',
          created_at: '2026-10-18T08:00:00+00:00',
          favorite: true,
          tags: ['d0'],
          origin_path: '/home/d0/.ephe/artifacts/sess-d0/parity-report.pdf',
          adopted_path: '',
          content_hash: 'sha256:d0-a1',
          viewed_at: null,
          turn_id: 'd0turn01',
          call_id: 'd0call-0',
          expires_at: '2026-11-17T08:00:00+00:00',
          keep: false,
        },
        {
          id: 'd0-a2',
          root_id: 'd0-a2',
          version: 1,
          session_id: 'sess-d0',
          name: 'findings.txt',
          path: '/home/d0/.ephe/artifacts/sess-d0/findings.txt',
          kind: 'text',
          size: 2048,
          topic: '',
          created_at: '2026-10-17T19:00:00+00:00',
          favorite: false,
          tags: [],
          origin_path: '/home/d0/.ephe/artifacts/sess-d0/findings.txt',
          adopted_path: '/home/d0/Desktop/findings.txt',
          content_hash: 'sha256:d0-a2',
          viewed_at: null,
          turn_id: 'd0turn02',
          call_id: 'd0call-1',
          expires_at: null,
          keep: true,
        },
      ],
      total: 2,
    }),
  ],
  [
    /^\/api\/workspaces$/,
    () => ({
      workspaces: [
        {
          id: 'ws-d0',
          name: 'ephe',
          path: '/home/d0/ephe',
          state: 'waiting_on_human',
          needs_you: true,
          last_event: 'run_shell is waiting for approval',
          running_for_seconds: 42,
          agent: 'ephe-agent',
          task: 'Sweep the ground',
          change_summary: '3 files changed',
        },
        {
          id: 'ws-d1',
          name: 'kepta',
          path: '/home/d0/kepta',
          state: 'running',
          needs_you: false,
          last_event: 'indexing 214 facts',
          running_for_seconds: 128,
          agent: 'ephe-agent',
          task: 'Index the store',
        },
        {
          id: 'ws-d2',
          name: 'ephemora-cell',
          path: '/home/d0/ephemora-cell',
          state: 'blocked',
          needs_you: false,
          last_event: '',
          running_for_seconds: 0,
          agent: 'ephe-agent',
          task: 'Cold start the cell',
        },
      ],
      runs: [],
    }),
  ],
  [
    /^\/api\/change-sets\/[^/]+\/custody$/,
    () => ({
      change_set: {
        id: 'cs-d0',
        workspace_id: '/home/d0/ephe',
        summary: 'the theme sweep touched the token block',
        files: [{ path: 'app/src/styles/globals.css', op: 'modify', diff_sha: HASH_A }],
        provenance: { session_id: 'sess-d0', agent_id: 'agent-d0', why: 'parity defects' },
        state: 'draft',
      },
      author: 'agent-d0',
      approval: null,
      custodians: ['agent-review'],
      files: [
        {
          path: 'app/src/styles/globals.css',
          op: 'modify',
          recorded: HASH_A,
          current: HASH_A,
          moved: false,
        },
      ],
      checked: true,
      publishable: false,
      refusal: {
        code: 'publish_without_approval',
        sentence: "change set 'cs-d0' carries no approval from a reviewer other than its author",
      },
    }),
  ],
  [
    /^\/api\/change-sets$/,
    () => ({
      change_sets: [
        {
          id: 'cs-d0',
          workspace_id: 'ws-d0',
          session_id: 'sess-d0',
          summary: 'the theme sweep touched the token block',
          state: 'draft',
          files: [
            { path: 'app/src/styles/globals.css', op: 'modify', additions: 12, deletions: 3 },
          ],
          created_at: '2026-10-18T08:10:00+00:00',
        },
      ],
      total: 1,
    }),
  ],
  [
    /^\/api\/tasks$/,
    () => [
      { id: 't1', title: 'Sweep the shipped ground', status: 'open', project: 'd0' },
      { id: 't2', title: 'Fix the token roots', status: 'done', project: 'd0' },
    ],
  ],
  [/^\/api\/skills\/pack-index$/, () => ({ version: 1, packs: [] })],
  [
    /^\/api\/skills$/,
    () => ({
      skills: [
        {
          name: 'theme-parity',
          trigger: 'parity',
          description: 'Measures every surface on the shipped ground.',
          is_builtin: true,
          version: '1.0.0',
        },
      ],
      total: 1,
    }),
  ],
  [
    /^\/api\/settings\/hooks$/,
    () => ({
      // The shape `core/user_hooks.py::hooks_status` answers with today. The sweep used
      // to send the pre-I6-4 one (`{name, matched}` / `{event, ok, at}`), which measured
      // a payload no current user ever receives; the surface's own guards for an older
      // backend are pinned in sections-hooks and utils.
      enabled: true,
      path: '~/.ephe/hooks.json',
      exists: true,
      events: [
        {
          key: 'on_turn_end',
          live: true,
          hooks: [{ command: 'scripts/notify.sh', match: '*', priority: 100 }],
        },
        { key: 'pre_tool', live: false, hooks: [] },
      ],
      recent: [
        {
          ts: '2026-10-18T08:00:00+00:00',
          tool: 'write_file',
          status: 'ok',
          detail: 'on_turn_end',
        },
      ],
    }),
  ],
  [/^\/api\/settings$/, () => ({ language: 'en', memory_enabled: true })],
  [
    /^\/api\/model\/providers$/,
    () => ({ active: {}, providers: [], local_models: [], local_model_options: [] }),
  ],
  [/^\/api\/sessions\/restore$/, () => ({ sessions: [] })],
  [
    /^\/api\/context\/budget$/,
    () => ({
      message_count: 0,
      char_count: 0,
      estimated_tokens: 0,
      window_tokens: 8192,
      window_source: 'legacy',
      percent: 0,
      compaction_threshold: 28,
      compaction_active: false,
    }),
  ],
  [/^\/api\/ephemeris$/, () => ({ days: [] })],
  [/^\/api\/cell$/, () => ({ cell: {} })],
]

/**
 * The painted contrast audit, run in the page. It reads what is on screen, not the source.
 *
 * The ground of an element is computed on the way *down* — one `getComputedStyle` per node and
 * one blend per ancestor step — because the alternative (each text node walking its own ancestor
 * chain) costs a style resolution per level: on the workspaces board, with its fleet panel, list
 * and detail pane, that version of this function took minutes and stalled the sweep.
 */
async function auditPage(page: Page): Promise<Finding[]> {
  return page.evaluate(
    ({ textFloor, largeFloor, boundaryFloor }) => {
      type Rgb = { r: number; g: number; b: number; a: number }
      type Row = {
        metric: 'text' | 'boundary'
        path: string
        detail: string
        ratio: number
      }
      const rows: Row[] = []
      const CAP = 400

      const parse = (value: string): Rgb | null => {
        const m = /rgba?\(([^)]+)\)/.exec(value)
        if (!m) return null
        const parts = m[1]
          .split(/[\s,/]+/)
          .filter(Boolean)
          .map((token) => (token.endsWith('%') ? Number(token.slice(0, -1)) / 100 : Number(token)))
        if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return null
        return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 }
      }

      const blend = (fg: Rgb, ground: Rgb): Rgb => ({
        r: fg.r * fg.a + ground.r * (1 - fg.a),
        g: fg.g * fg.a + ground.g * (1 - fg.a),
        b: fg.b * fg.a + ground.b * (1 - fg.a),
        a: 1,
      })

      const channel = (value: number) => {
        const c = value / 255
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
      }

      const luminance = (rgb: Rgb) =>
        0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b)

      const ratio = (a: Rgb, b: Rgb) => {
        const hi = Math.max(luminance(a), luminance(b))
        const lo = Math.min(luminance(a), luminance(b))
        return (hi + 0.05) / (lo + 0.05)
      }

      const pathOf = (el: Element) => {
        const node = el as HTMLElement
        const testid = node.dataset.testid
        if (testid) return `[data-testid="${testid}"]`
        if (node.id) return `#${node.id}`
        const classes = Array.from(node.classList).slice(0, 2).join('.')
        return `${node.tagName.toLowerCase()}${classes ? `.${classes}` : ''}`
      }

      const describe = (rgb: Rgb) =>
        `${Math.round(rgb.r)},${Math.round(rgb.g)},${Math.round(rgb.b)}`

      /** The mean colour a `linear-gradient()` paints, or null.
       *
       * `backgroundColor` of a gradient-filled box is `rgba(0,0,0,0)`, so a control that
       * takes its fill from a stop list had no ground at all and was measured against
       * whatever its ancestors painted: the intro's amber action, whose own ink sits at
       * 9:1 on the gradient, came back as 1.08 against the page. Averaging the stops is
       * an approximation of a box the gradient varies across, and it is the reading the
       * eye gets. An image (`url(…)`) is not: its pixels are outside the sheet. */
      const gradientOf = (value: string): Rgb | null => {
        if (!value.includes('gradient(')) return null
        const stops = [...value.matchAll(/rgba?\([^)]*\)/g)]
          .map((m) => parse(m[0]))
          .filter((c): c is Rgb => c !== null)
        if (!stops.length) return null
        const mean = (pick: (c: Rgb) => number) =>
          stops.reduce((sum, c) => sum + pick(c), 0) / stops.length
        return {
          r: mean((c) => c.r),
          g: mean((c) => c.g),
          b: mean((c) => c.b),
          a: mean((c) => c.a),
        }
      }

      const CONTROL_ROLES = [
        'button',
        'tab',
        'checkbox',
        'radio',
        'switch',
        'combobox',
        'slider',
        'textbox',
        'searchbox',
      ]
      const isControl = (el: Element) =>
        ['BUTTON', 'INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) ||
        CONTROL_ROLES.includes(el.getAttribute('role') ?? '')

      const canvas = parse(getComputedStyle(document.documentElement).backgroundColor) ?? {
        r: 255,
        g: 255,
        b: 255,
        a: 1,
      }

      const walk = (el: Element, ground: Rgb) => {
        if (rows.length >= CAP) return
        const style = getComputedStyle(el)
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          Number(style.opacity) < 0.02
        )
          return
        const own = parse(style.backgroundColor)
        const filled = own && own.a > 0 ? blend(own, ground) : ground
        const gradient = gradientOf(style.backgroundImage)
        const paintedGround = gradient ? blend(gradient, filled) : filled
        const box = (el as HTMLElement).getBoundingClientRect()
        const srOnly =
          box.width <= 2 ||
          box.height <= 2 ||
          (style.position === 'absolute' && style.clipPath.includes('inset'))
        const onScreen = box.bottom > 0 && box.right > 0 && box.top < innerHeight + 4000

        if (!srOnly && onScreen) {
          const text = Array.from(el.childNodes).some(
            (node) => node.nodeType === 3 && (node.textContent ?? '').trim().length > 0,
          )
          const gradient =
            style.backgroundClip.includes('text') || style.webkitBackgroundClip.includes('text')
          if (text && !gradient) {
            const ink = parse(style.color)
            if (ink && ink.a > 0) {
              const size = Number.parseFloat(style.fontSize) || 16
              const weight = Number(style.fontWeight) || 400
              const floor = size >= 18 || (size >= 14 && weight >= 700) ? largeFloor : textFloor
              const measured = ratio(blend(ink, paintedGround), paintedGround)
              if (measured < floor) {
                rows.push({
                  metric: 'text',
                  path: pathOf(el),
                  detail: `"${(el.textContent ?? '').trim().slice(0, 42)}" ${size.toFixed(0)}px/${weight} ink ${style.color} on ${describe(paintedGround)}`,
                  ratio: Number(measured.toFixed(2)),
                })
              }
            }
          }

          // A control's only edge is a boundary (DESIGN.md §8); the decorative hairline is not
          // one, so this is scoped to elements that carry a control.
          const width = Number.parseFloat(style.borderTopWidth) || 0
          const edge = parse(style.borderTopColor)
          if (isControl(el) && width >= 1 && edge && edge.a > 0) {
            // 1.4.11 compares the edge with what lies beyond it, so the ground here is the
            // parent's, not the box's own fill: `border-ink bg-ink` is a filled button, not a
            // boundary nobody can see.
            const measured = ratio(blend(edge, ground), ground)
            if (measured < boundaryFloor) {
              rows.push({
                metric: 'boundary',
                path: pathOf(el),
                detail: `edge ${style.borderTopColor} ${width}px on ${describe(ground)}`,
                ratio: Number(measured.toFixed(2)),
              })
            }
          }
        }

        for (const child of Array.from(el.children)) walk(child, paintedGround)
      }

      walk(document.body, canvas)
      return rows
    },
    {
      textFloor: TEXT_FLOOR,
      largeFloor: LARGE_TEXT_FLOOR,
      boundaryFloor: BOUNDARY_FLOOR,
    },
  )
}

const METRICS: Metric[] = ['text', 'boundary', 'render-error']

const countOf = (findings: Finding[]): Counts =>
  METRICS.reduce(
    (totals, metric) => ({
      ...totals,
      [metric]: findings.filter((f) => f.metric === metric).length,
    }),
    { text: 0, boundary: 0, 'render-error': 0 },
  ) as Counts

/**
 * Navigate to a surface and say what answered: its own root, the page error boundary, or
 * neither. A route that lands on `crash-fallback` is a finding this wave owns — the sweep
 * payload is a named fixture, so a page that cannot render it is a page that cannot render
 * that shape — and a route whose root never appears is measured as empty rather than skipped.
 */
async function openRoot(page: Page, url: string, selector: string): Promise<Finding | null> {
  await page.goto(url, { waitUntil: 'load' })
  // Eight seconds, not fifteen: the bundle paints a route in under one, so a root that has not
  // appeared by eight is not coming, and a sweep that waits the difference spends its whole
  // budget on routes it already knows are broken.
  const settled = await Promise.race([
    page.waitForSelector(selector, { timeout: 8_000 }).then(() => 'root' as const),
    page
      .waitForSelector('[data-testid="crash-fallback"]', { timeout: 8_000 })
      .then(() => 'crash' as const),
  ]).catch(() => 'missing' as const)
  if (settled === 'root') {
    lastPageError = ''
    return null
  }
  // `textContent()` is a query, not an action: it waits for the node on its own clock, so the
  // message is read with a timeout of its own and a missing disclosure is simply no message.
  const message =
    settled === 'crash'
      ? ((await page
          .locator('[data-testid="crash-fallback"] pre')
          .textContent({ timeout: 2_000 })
          .catch(() => '')) ?? '')
      : ''
  return {
    metric: 'render-error',
    path: 'PageErrorBoundary',
    detail: `${settled === 'crash' ? 'crash fallback' : 'no root within 8s'}: ${(message || lastPageError).slice(0, 200)}`,
    ratio: 0,
  }
}

/** The boundary replaces the route, and a hash navigation inside the same document keeps it up:
 *  after one crash the page has to come back from the URL, or every later surface on it is
 *  measured against the same fallback. */
const resetToChat = async (page: Page, origin: string) => {
  await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
  await page.reload({ waitUntil: 'load' })
  await page
    .waitForSelector('[data-testid="panel-chat"]', { timeout: 15_000 })
    .catch(() => undefined)
}

/** One surface in one theme: open the page, settle, measure, and optionally shoot it. */
async function capture(
  page: Page,
  surface: string,
  theme: string,
  width: number,
  findings: Record<string, Finding[]>,
  failure: Finding | null = null,
) {
  await page.waitForTimeout(400) // entrance and the store's first reads land before anything is measured
  const rows = await auditPage(page)
  if (failure) rows.push(failure)
  const key = `${surface}/${theme}/${width}`
  findings[key] = rows
  const counts = countOf(rows)
  console.log(
    `theme-parity ${key} text=${counts.text} boundary=${counts.boundary} ` +
      `render=${counts['render-error']}` +
      (rows.length ? ` worst=${JSON.stringify(rows.slice(0, 2))}` : ''),
  )
  if (SWEEP) {
    await page.screenshot({ path: resolve(OUT_DIR, `${surface}-${theme}-${width}.png`) })
  }
}

const boot = async (page: Page, theme: string, origin: string, label = 'page') => {
  watchErrors(page, label)
  page.setDefaultNavigationTimeout(20_000)
  page.setDefaultTimeout(10_000)
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en')
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('ephe.intro.seen.v1', '1')
  })
  await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
  await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 20_000 })
  // One ground, so the walk has nothing to select and nothing to verify it selected: a
  // stored mode or a bent class would mean a second ground came back, and the guard in
  // `tests/test_forest_only.py` refuses that at the source instead of here.
  const applied = await page.evaluate(() => document.documentElement.className || '(none)')
  expect(applied.includes('light'), `the document carries a second ground: "${applied}"`).toBe(
    false,
  )
}

/// The grounds the product ships. A second entry here doubles the matrix and the baseline;
/// the sweep is written so adding one is a deliberate edit, not a default.
const GROUNDS = ['forest'] as const

/**
 * Open the settings register and say whether it opened. At phone width the sidebar is a drawer
 * that has to be opened first, and a drawer that takes the page down with it is a finding this
 * wave has to report rather than a click that eats the run.
 */
const openSettings = async (page: Page, width: number): Promise<Finding | null> => {
  lastPageError = ''
  const reach = async () => {
    if (width < 768) {
      // Below md the sidebar is a drawer behind `header-menu-toggle`; the desktop collapse
      // control beside it is `hidden md:inline-flex` and does not exist on a phone.
      await page.getByTestId('header-menu-toggle').click({ timeout: 5_000 })
    }
    await page.getByTestId('sidebar-settings-btn').click({ timeout: 5_000 })
    await page.waitForSelector('[data-testid="settings-panel"]', { timeout: 8_000 })
  }
  const failure = await reach()
    .then(() => null)
    .catch((error: Error) => error.message)
  if (!failure) return null
  return {
    metric: 'render-error',
    path: width < 768 ? 'header-menu-toggle' : 'sidebar-settings-btn',
    detail: `the register could not be reached: ${failure.slice(0, 120)}${lastPageError ? ` | ${lastPageError}` : ''}`,
    ratio: 0,
  }
}

const clickSettingsTab = async (page: Page, tab: string): Promise<string | null> => {
  const row = page.locator(`[data-testid="settings-nav-${tab}"]`)
  const unreachable = await row
    .click({ timeout: 5_000 })
    .then(() => null)
    .catch((error: Error) => error.message)
  await page.waitForTimeout(250)
  return unreachable
}

/** Each register names the element that says it rendered: a blank page would measure nothing
 *  and read as a pass, so every route is waited for by its own root. */
const REGISTERS: Array<[string, string, string]> = [
  ['artifacts', '#/artifacts', '[data-testid="artifacts-page"]'],
  ['artifacts-ablage', '#/artifacts/ablage', '[data-testid="artifacts-page"]'],
  ['memory-bestand', '#/memory/bestand', '[data-testid="memory-page"]'],
  ['memory-korrekturen', '#/memory/korrekturen', '[data-testid="memory-page"]'],
  ['memory-papierkorb', '#/memory/papierkorb', '[data-testid="memory-page"]'],
  ['memory-gehirne', '#/memory/gehirne', '[data-testid="memory-page"]'],
  ['workspaces', '#/workspaces', '[data-testid="workspaces-page"]'],
  ['custody', '#/workspaces/change/cs-d0', '[data-testid="custody-page"]'],
  ['tools', '#/tools', '[data-testid="tools-vision"]'],
]

test.describe('D0 contrast parity on the one ground', () => {
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(600_000)

  let chatFixture: AppFixture | null = null
  let freshFixture: AppFixture | null = null
  let offlineFixture: AppFixture | null = null
  const findings: Record<string, Finding[]> = {}

  test.beforeAll(async () => {
    if (SWEEP) await mkdir(OUT_DIR, { recursive: true })
    chatFixture = await startAppFixture({
      kind: 'chat',
      engineMs: 120,
      chunkGapMs: 220,
      chunks: [
        { type: 'tool_start', tool: 'read_file', args: { path: 'globals.css' } },
        'reading ',
        { type: 'stdout', tool: 'read_file', data: '--color-canvas: hsl(30 16.7% 7.06%);' },
        { type: 'tool_done', tool: 'read_file', result: 'ok', duration_ms: 34 },
        'the studio ',
        {
          type: 'file_result',
          file_type: 'pdf',
          path: '/home/d0/.ephe/artifacts/sess-d0/parity-report.pdf',
          id: 'act-d0',
        },
        'answers. ',
        {
          type: 'sandbox_confirm',
          token: 'd0-token',
          tool: 'run_shell',
          args: { command: 'rg --color-canvas globals.css' },
          rememberable: true,
          diff: '@@ -1 +1 @@',
        },
      ],
      routes: [
        (req, res) => {
          const path = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
          const hit = READS.find(([re]) => re.test(path))
          if (!hit) return false
          res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          res.end(JSON.stringify(hit[1]()))
          return true
        },
      ],
    })
    freshFixture = await startAppFixture({ kind: 'first-run', engineMs: 120 })
    // The engine that answers but refuses: `lib/engineState.ts` calls this `unreachable`, and
    // the welcome owes it a sentence with a next step rather than an empty transcript.
    offlineFixture = await startAppFixture({
      kind: 'chat',
      engineMs: 120,
      preRoutes: [
        (req, res) => {
          const path = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
          if (path !== '/api/health') return false
          res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
          res.end(
            JSON.stringify({
              status: 'ok',
              version: 'fixture',
              models: [],
              engine_online: false,
              engine_state: 'unreachable',
              detail: 'theme sweep: the configured endpoint is not answering',
            }),
          )
          return true
        },
      ],
    })
    console.log(
      `theme-parity fixtures ${chatFixture.origin}, ${freshFixture.origin}, ${offlineFixture.origin}`,
    )
  })

  test.afterAll(async () => {
    await chatFixture?.close()
    await freshFixture?.close()
    await offlineFixture?.close()
    chatFixture = null
    freshFixture = null
    await writeFile(
      resolve(OUT_DIR, 'findings.json'),
      JSON.stringify(findings, null, 1),
      'utf-8',
    ).catch(() => undefined)
  })

  test('every surface on the one ground at both widths, measured', async ({
    browser,
  }: {
    browser: Browser
  }) => {
    const origin = chatFixture?.origin
    const fresh = freshFixture?.origin
    const offline = offlineFixture?.origin
    if (!origin || !fresh || !offline) throw new Error('fixtures did not start')

    for (const theme of GROUNDS) {
      for (const width of [1280, 390] as const) {
        const context = await browser.newContext({
          viewport: { width, height: width === 390 ? 844 : 800 },
          reducedMotion: 'reduce',
          // The bundle registers a service worker that answers /api/* from its own fetch context, so
          // every reload after the first would ask the worker instead of this fixture and read
          // index.html as JSON (`visual.spec.ts:239` pays for the same lesson).
          serviceWorkers: 'block',
          // No action waits forever: a control that cannot be reached is a finding this wave
          // reads, not a run that spends its ten-minute budget staring at it.
          actionTimeout: 8_000,
        })

        // The registers, the run states and the settings tabs.
        const page = await context.newPage()
        await boot(page, theme, origin, `registers/${theme}/${width}`)
        await capture(page, 'chat-empty', theme, width, findings)

        const offlinePage = await context.newPage()
        await boot(offlinePage, theme, offline, `offline/${theme}/${width}`)
        await capture(offlinePage, 'chat-offline', theme, width, findings)
        await offlinePage.close()

        await page.getByTestId('chat-input').focus()
        await page.keyboard.type('sweep the ground')
        await page.keyboard.press('Enter')
        await page.waitForSelector('[data-testid="message-row"]', { timeout: 20_000 })
        await capture(page, 'chat-turn', theme, width, findings)
        await page.waitForSelector('[data-testid="approval-blast-radius"]', { timeout: 15_000 })
        await capture(page, 'chat-approval', theme, width, findings)

        for (const [surface, route, selector] of REGISTERS) {
          const failure = await openRoot(page, `${origin}/${route}`, selector)
          await capture(page, surface, theme, width, findings, failure)
          if (failure) await resetToChat(page, origin)
        }

        await page.goto(`${origin}/#/workspaces`, { waitUntil: 'load' })
        await page.waitForTimeout(400)
        console.log(`theme-parity BLOCK workspaces-detail ${theme}/${width}`)
        const row = page.locator('[data-testid="workspaces-list"] li button').first()
        if (await row.count()) {
          const unreachable = await row
            .click()
            .then(() => null)
            .catch((error: Error) => error.message)
          await page.waitForTimeout(400)
          await capture(
            page,
            'workspaces-detail',
            theme,
            width,
            findings,
            unreachable
              ? {
                  metric: 'render-error',
                  path: '[data-testid="workspaces-list"] li button',
                  detail: `the row could not be reached: ${unreachable.slice(0, 120)}`,
                  ratio: 0,
                }
              : null,
          )
        }

        // Every settings tab is its own surface: a group head can pass and a row inside it
        // fail. The list is read from the nav rather than written here, so a tab added to
        // `TabKey` is measured on the next run instead of waiting for this file to notice.
        // The panel is opened once and the tabs are clicked inside it: `#/chat` to `#/chat` is
        // a same-document navigation, so a reload here would not reload anything and the walk
        // would keep staring at the boundary a crashed tab left behind.
        console.log(`theme-parity BLOCK settings ${theme}/${width}`)
        let settings = await context.newPage()
        await boot(settings, theme, origin, `settings/${theme}/${width}`)
        const blocked = await openSettings(settings, width)
        if (blocked) {
          await capture(settings, 'settings-blocked', theme, width, findings, blocked)
          await settings.close()
        }
        const tabs = blocked
          ? []
          : await settings.evaluate(() =>
              Array.from(document.querySelectorAll('[data-testid^="settings-nav-"]')).map((el) =>
                (el.getAttribute('data-testid') ?? '').replace('settings-nav-', ''),
              ),
            )
        // The register has to be complete whenever it can be opened at all; a cycle blocked by
        // the defect above carries its own finding instead of a second one here.
        expect(
          Boolean(blocked) || tabs.length >= 23,
          `the nav offered ${tabs.length} tabs: ${tabs.join(', ')}`,
        ).toBe(true)
        for (const tab of tabs) {
          const unreachable = await clickSettingsTab(settings, tab)
          const crashed = (await settings.locator('[data-testid="crash-fallback"]').count()) > 0
          const failure: Finding | null = crashed
            ? {
                metric: 'render-error',
                path: `settings-tab-${tab}`,
                detail: `the tab answered with the crash fallback: ${(
                  (await settings.locator('[data-testid="crash-fallback"] pre').textContent()) ?? ''
                ).slice(0, 160)}`,
                ratio: 0,
              }
            : null
          await capture(
            settings,
            `settings-${tab}`,
            theme,
            width,
            findings,
            failure ??
              (unreachable
                ? {
                    metric: 'render-error',
                    path: `settings-nav-${tab}`,
                    detail: `the nav row could not be reached: ${unreachable.slice(0, 120)}`,
                    ratio: 0,
                  }
                : null),
          )
          if (crashed) {
            // The boundary replaced the panel, so the next row is unreachable from this page.
            await settings.close()
            settings = await context.newPage()
            await boot(settings, theme, origin, `settings/${theme}/${width}`)
            await openSettings(settings, width)
          }
        }

        await settings.close()
        await page.close()

        // The setup chooser and the first open, from a profile that has seen neither.
        console.log(`theme-parity BLOCK first-open ${theme}/${width}`)
        const freshPage = await context.newPage()
        await freshPage.addInitScript(() => {
          localStorage.setItem('i18nextLng', 'en')
        })
        await freshPage.goto(`${fresh}/#/setup`, { waitUntil: 'load' })
        await freshPage.waitForSelector('[data-testid="setup-page"]', { timeout: 20_000 })
        await capture(freshPage, 'setup', theme, width, findings)
        await freshPage.goto(`${fresh}/#/chat`, { waitUntil: 'load' })
        await freshPage.waitForSelector('[data-testid="first-run-intro"]', { timeout: 20_000 })
        await capture(freshPage, 'intro-scene', theme, width, findings)
        await freshPage.getByTestId('intro-cta').click()
        await freshPage.waitForSelector('[data-testid="first-run-tour"]', { timeout: 20_000 })
        await capture(freshPage, 'tour-usage', theme, width, findings)
        for (let step = 0; step < 4; step += 1) {
          const next = freshPage.getByTestId('tour-next')
          if (!(await next.count())) break
          await next.click()
          await freshPage.waitForTimeout(500)
          await capture(freshPage, `tour-step-${step + 1}`, theme, width, findings)
        }
        await freshPage.close()
        await context.close()
      }
    }

    const measured = Object.fromEntries(
      Object.entries(findings).map(([key, rows]) => [key, countOf(rows)]),
    ) as Baseline
    if (SWEEP) {
      // The capture pass reports what the tree measures and stops short of judging it: the
      // numbers it prints become the committed ratchet, and only after the defects behind
      // them have been read. `findings.json` is the read itself — every row, not the two
      // the console line carries, so a class can be grouped by the control that owns it
      // instead of by the screen that shows it.
      await writeFile(
        resolve(OUT_DIR, 'measured.json'),
        JSON.stringify(measured, null, 1),
        'utf-8',
      ).catch(() => undefined)
      await writeFile(
        resolve(OUT_DIR, 'findings.json'),
        JSON.stringify(findings, null, 1),
        'utf-8',
      ).catch(() => undefined)
      return
    }

    const baseline = JSON.parse(await readFile(BASELINE_PATH, 'utf-8')) as Baseline
    const regressions: string[] = []
    for (const [key, rows] of Object.entries(findings)) {
      const counts = countOf(rows)
      const entry = baseline[key]
      if (!entry) {
        regressions.push(`${key}: measured ${JSON.stringify(counts)} with no baseline entry`)
        continue
      }
      for (const metric of METRICS) {
        if (counts[metric] > entry[metric]) {
          regressions.push(`${key}: ${metric} ${counts[metric]} > baseline ${entry[metric]}`)
        }
      }
    }
    expect(regressions, regressions.join('\n')).toEqual([])
  })
})
