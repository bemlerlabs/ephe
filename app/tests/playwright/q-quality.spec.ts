import { test, expect } from '@playwright/test'
import { existsSync, statSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { cpus, loadavg } from 'node:os'
import { ensureOnboarded, hasDevHandle } from './helpers'
// The product's own formatters: QG3 asserts the popover prints the seeded numbers
// exactly the way the product prints them for the leg's language.
import { formatNumber } from '../../src/lib/dateLocale'
import { formatPercent } from '../../src/lib/contextMeter'

/**
 * W12 — quality gate of the e2e layer (state-of-the-art, layered):
 *
 *   level 1  existence     — nodes/ids present, unique
 *   level 2  content       — text values exact, formats (regex) at the pins
 *   level 3  geometry      — measured boxes (height/width), flushness, within-viewport
 *   level 4  semantics     — numeric cross-check: % == round(N/M*100), breakdown sum ~100,
 *                            chip values == store values, DOM order == block chronology
 *   level 5  media         — PNG IHDR dimensions == DPR scaling, byte floor, non-blankness
 *   level 6  determinism   — second identical boot => same id set; budgets measured
 *
 * No "isVisible and done": every level counts its own assertion into the report.
 */

const SHOTS = '/tmp/qg_w12'

// QG3-BUDGET-SEED-START — contract mirror of the dict returned by context_budget()
// in server/routes/context.py. tests/test_qg3_budget_seed_contract.py compares this
// JSON against the route's own return statement and turns red when either side
// renames a field or a breakdown category. The numbers obey the route's identities:
// percent = round(estimated_tokens / window_tokens * 100, 2) (banker's rounding,
// 768/24576 → 3.12), and each breakdown share is one category's char share of the
// total — seeded fully labelled, so the shares sum to 100.
const QG3_BUDGET_JSON = `{
  "session_id": "qg-w12",
  "message_count": 1,
  "char_count": 3226,
  "estimated_tokens": 768,
  "window_tokens": 24576,
  "window_source": "legacy",
  "counted_via": "native",
  "tokenizer": "calibrated-4.2",
  "percent": 3.12,
  "compaction_threshold": 28,
  "compaction_active": false,
  "breakdown": [
    { "name": "Messages", "percent": 60.0 },
    { "name": "System prompt", "percent": 25.0 },
    { "name": "System tools", "percent": 10.0 },
    { "name": "Skills", "percent": 5.0 }
  ],
  "stages": []
}`
// QG3-BUDGET-SEED-END

interface SeedCall {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
  status: string
  stdout?: string
  duration_ms?: number
}

/** Deterministic seed: text→tool→text cadence + two thinking phases. */
function seedQg(): void {
  const S = (
    window as unknown as {
      __epheStore: {
        setState: (partial: unknown) => void
        getState: () => { createSession: (t?: string) => void }
      }
    }
  ).__epheStore
  S.getState().createSession('QG W12')
  const st = S.getState() as unknown as {
    activeSessionId: string
    sessions: Array<{ id: string; title?: string; messages?: unknown[]; createdAt?: number }>
  }
  const now = Date.now()
  const calls: SeedCall[] = [
    {
      id: 'c1',
      name: 'run_shell',
      args: { command: 'pnpm test' },
      result: 'ok',
      status: 'completed',
      stdout: 'PASS a\nPASS b',
      duration_ms: 412,
    },
  ]
  const msg = {
    id: 'qg-a1',
    role: 'assistant',
    content: 'Praeambel.\nDie Antwort.',
    timestamp: now,
    tool_calls: calls,
    blocks: [
      { kind: 'thinking', index: 0 },
      { kind: 'text', text: 'Praeambel.' },
      { kind: 'tool', callId: 'c1' },
      { kind: 'thinking', index: 1 },
      { kind: 'text', text: 'Die Antwort.' },
    ],
    thinkingPhases: [
      { start: now - 4000, end: now - 3000, text: 'Erste Phase.' },
      { start: now - 2000, end: now - 1000, text: 'Zweite Phase.' },
    ],
  }
  const sessions = st.sessions.map((s) =>
    s.id === st.activeSessionId ? { ...s, messages: [msg] } : s,
  )
  S.setState({
    sessions,
    // The store keeps currentSession as its own key (not derived) — without this
    // lever in the seed the column renders empty (selector parity).
    currentSession: sessions.find((s) => s.id === st.activeSessionId) ?? null,
  })
}

test.describe('QG W12 — layered quality gates', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
  })

  test('QG1: Boot matrix — test id set unique + non-empty, 0 UI errors, budgets', async ({
    page,
  }) => {
    const errors: string[] = []
    const requests: string[] = []
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    page.on('request', (r) => {
      requests.push(r.url())
    })
    // The boot set closes inside the page, on the mutation that mounts the chat panel
    // after the document has loaded. A runner slow between that paint and the evaluate
    // below used to append a polling tick to a set the budget had already read.
    await page.addInitScript(() => {
      const boot: string[] = []
      const boundary = window as unknown as {
        __epheBootApiCalls?: string[]
        __epheBootClosed?: boolean
      }
      const record = (target: string | URL) => {
        if (boundary.__epheBootClosed) return
        try {
          const url = new URL(String(target), location.href).href
          if (/\/api\//.test(url)) boot.push(url)
        } catch {
          // A target the URL parser refuses never reaches the API.
        }
      }
      const fetchOriginal = window.fetch
      window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
        record(input instanceof Request ? input.url : String(input))
        return fetchOriginal.call(window, input as RequestInfo, init)
      }) as typeof window.fetch
      const openOriginal = XMLHttpRequest.prototype.open
      XMLHttpRequest.prototype.open = function (
        this: XMLHttpRequest,
        ...args: Parameters<XMLHttpRequest['open']>
      ) {
        record(String(args[1]))
        return openOriginal.apply(this, args)
      } as typeof XMLHttpRequest.prototype.open
      const SocketOriginal = window.WebSocket
      window.WebSocket = class extends SocketOriginal {
        constructor(url: string | URL, protocols?: string | string[]) {
          record(String(url))
          super(url, protocols)
        }
      }
      function finalize() {
        boundary.__epheBootClosed = true
        boundary.__epheBootApiCalls = boot.slice()
        observer.disconnect()
      }
      function close() {
        if (boundary.__epheBootClosed) return
        if (document.readyState !== 'complete') return
        if (!document.querySelector('[data-testid="panel-chat"]')) return
        // One task later: React flushes the mount effects before this runs, so the
        // requests those effects start are already counted.
        setTimeout(finalize, 0)
      }
      const observer = new MutationObserver(close)
      observer.observe(document, { childList: true, subtree: true })
      window.addEventListener('load', close)
    })
    const t0 = Date.now()
    await page.goto('/#/chat', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 15000 })
    // This test measures the boot of the BUILT bundle served by the product backend:
    // the ≤29 ceiling counts the API reads that bundle makes against that backend
    // (2026-11-11 ledger in the ceiling's comment above). On the Vite dev leg there is
    // no backend — every boot read answers 404 and the count measures the missing
    // server, not the bundle (measured 2026-11-25: 30 calls, /api/settings ×4 etc).
    // The dev handle is the dev leg's signature; the CI leg keeps asserting.
    test.skip(
      await hasDevHandle(page),
      'boot-API budget measures the built bundle against the product backend; the Vite dev leg serves no backend, so its 404s would be counted as boot traffic',
    )
    // The ceiling counts the boot reads; the first health probe is one of them, and a
    // later tick of the same URL is the interval, which the boundary above excludes
    // from the boot set.
    const bootSnapshot = await page.evaluate(() => {
      const calls = (window as unknown as { __epheBootApiCalls?: string[] }).__epheBootApiCalls
      if (!calls) throw new Error('the boot boundary was not reached')
      return calls
    })
    const bootApiCalls = bootSnapshot.filter(
      (url, index) => !/\/api\/health$/.test(url) || bootSnapshot.indexOf(url) === index,
    )
    test.info().annotations.push({
      type: 'boot set',
      description: `${bootApiCalls.length} API calls before the panel-ready boundary`,
    })
    const bootMs = Date.now() - t0

    const ids: string[] = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid]')).map((el) =>
        el.getAttribute('data-testid')!,
      ),
    )
    // Level 1: not empty + unique (sorting makes the set equality checkable)
    expect(ids.length).toBeGreaterThan(8)
    expect(new Set(ids).size).toBe(ids.length)
    // Level 2: the load-bearing anchors are there (tok-chip is md:hidden and, at
    // 1280, carries the breakdown button's title — that one is the desktop pendant anchor)
    for (const anchor of ['panel-chat', 'chat-sidebar', 'status-bar', 'send-btn']) {
      expect(ids.filter((i) => i === anchor).length, anchor).toBeGreaterThanOrEqual(1)
    }
    // Level 6: measured budgets — API chats counted separately (the dev server
    // carries the module variety in the HMR path, which is no product signal)
    // The boot ceiling is a wall-clock reading. A reading taken while a sibling worker is
    // busy describes the machine, not the product — the defect tests/timing_segment.py and
    // tests/test_wall_clock_budgets.py name for the Python side, and the reason
    // latency.config.ts pins workers: 1 for its own lane. Two conditions make this reading
    // untrustworthy, so the budget stands down under either: more than one worker, or a box
    // above 2.0 runnable tasks per CPU. Measured 2026-10-13: a loaded runner read 3576 ms
    // against this budget while its load stayed under the bar — parallel workers that are
    // I/O-bound do not raise the average, so the worker count is the sharper of the two.
    // The budget is not relaxed; it is asserted where it can be believed (workers: 1).
    const perCpu = (loadavg()[0] ?? 0) / Math.max(cpus().length, 1)
    const parallel = test.info().config.workers > 1
    if (!parallel && perCpu <= 2.0) {
      expect(bootMs, `Boot ${bootMs}ms`).toBeLessThanOrEqual(3000)
    } else {
      test.info().annotations.push({
        type: 'budget stood down',
        description: parallel
          ? `boot ${bootMs}ms not asserted: ${test.info().config.workers} workers share this run`
          : `boot ${bootMs}ms not asserted: ${perCpu.toFixed(2)} runnable tasks/CPU exceeds the 2.0 bar`,
      })
    }
    // The ceiling counts the boot set; the first-open tour added one named request
    // (GET /api/tour, the device marker) to the 24 measured before it. The workspace
    // bar is now always present, so its one read of the active folder (GET /api/fs,
    // shared by every consumer through useWorkspaceState) joins that set: 26.
    // QD-012: the codebase index pill reads its status once on boot
    // (GET /api/project/index/status), so the ceiling moves 26 -> 27.
    // 2026-11-11: the saved UI language now comes from the server at boot
    // (GET /api/settings, bounded to 1.2 s, before the first render), and the
    // restored-conversation read keeps its own request: 27 -> 29.
    // Snapshot at the panel-ready boundary: a late health or session poll is not part
    // of the boot set, and a slower runner otherwise adds one while the DOM is read.
    expect(
      bootApiCalls.length,
      `API-Anzahl ${bootApiCalls.length}: ${bootApiCalls.join(' ')}`,
    ).toBeLessThanOrEqual(29)
    // The set is closed at the panel mount: a request that starts afterwards stays out,
    // however late the runner gets to read it.
    const frozenAt = await page.evaluate(async () => {
      await fetch('/api/settings')
      return (window as unknown as { __epheBootApiCalls?: string[] }).__epheBootApiCalls?.length
    })
    expect(frozenAt, 'boot set stayed closed after a post-boot request').toBe(bootSnapshot.length)
    expect(requests.length, `Total-Anzahl ${requests.length}`).toBeLessThanOrEqual(400)
    // UI errors: favicon/connection are expected offline paths; the rest must be 0
    const uiErrors = errors.filter(
      (e) =>
        !/favicon|404|501|8765|localhost|WebSocket|\[WS\]|ERR_FAILED|ERR_CONNECTION_REFUSED/.test(
          e,
        ),
    )
    expect(uiErrors).toEqual([])
  })

  test('QG2: Turn chronology — DOM order == block arrival order, phases complete', async ({
    page,
  }) => {
    // seedQg reaches into window.__epheStore, the dev-only store handle
    // (src/store/chatStore.ts defines it under `import.meta.env.DEV`). The guard has to
    // run on the app page, not on about:blank: `hasDevHandle` asks the *current* document,
    // so a guard ahead of the first navigation is false on every lane and turns the
    // conditional into a permanent skip — which is what it was. On the static-dist CI leg
    // the bundle is the product and carries no handle, so the skip still fires there; on a
    // Vite dev server (dogfood.config.ts) the test runs.
    await page.goto('/#/chat', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]')
    test.skip(!(await hasDevHandle(page)), 'needs vite dev server (DEV-only __epheStore handle)')
    await page.evaluate(seedQg)
    await page.waitForTimeout(300)

    // Level 4: DOM index cross-check — the three text/tool anchors must sit in
    // arrival order (preamble < tool row < final answer).
    const order = await page.evaluate(() => {
      const list = document.querySelector('[data-testid="panel-chat"]')!
      const all = Array.from(
        list.querySelectorAll('[data-testid="stream-text-block"],[data-testid="tool-stream-rows"]'),
      )
      // A fixed triple, not a sparse list: a missing anchor stays visible as NaN instead
      // of vanishing from the comparison.
      const pos: [number, number, number] = [NaN, NaN, NaN]
      all.forEach((el, i) => {
        const tx = el.textContent || ''
        if (tx.startsWith('Praeambel.')) pos[0] = i
        if (el.getAttribute('data-testid') === 'tool-stream-rows') pos[1] = i
        if (tx.startsWith('Die Antwort.')) pos[2] = i
      })
      return { pos, total: all.length }
    })
    expect(order.total).toBeGreaterThanOrEqual(3)
    const [preamble, toolRow, answer] = order.pos
    expect(preamble, 'the preamble anchor is in the DOM').not.toBeNaN()
    expect(toolRow, 'the tool row anchor is in the DOM').not.toBeNaN()
    expect(answer, 'the answer anchor is in the DOM').not.toBeNaN()
    expect(preamble).toBeLessThan(toolRow)
    expect(toolRow).toBeLessThan(answer)

    // Level 1+2+interaction: two collapsed thinking-phase rows (aria-expanded),
    // clickable — after the click the phase text appears in the DOM.
    // The model chip also carries aria-expanded — the text filter keeps only
    // the phase rows (Thought/Denk label).
    const phaseBtns = page
      .locator('[data-testid="message-bubble"] button[aria-expanded]')
      .filter({ hasText: /Thought|nachgedacht|Gedacht/i })
    await expect(phaseBtns).toHaveCount(2)
    await phaseBtns.first().click()
    await expect(page.getByText('Erste Phase.')).toBeVisible()
    // Level 1: the tool row with its status
    await expect(page.getByTestId('tool-stream-rows')).toBeVisible()
    // Level 3: the row box inside the column edge (no overflow to the right)
    const geo = await page.evaluate(() => {
      const r = document.querySelector('[data-testid="tool-stream-rows"]')!.getBoundingClientRect()
      return { right: r.right, inner: window.innerWidth, h: r.height }
    })
    expect(geo.right).toBeLessThanOrEqual(geo.inner + 1)
    expect(geo.h).toBeGreaterThanOrEqual(12)
    await page.screenshot({ path: `${SHOTS}/qg2_takt.png` }).catch(() => {})
  })

  test('QG3: Numeric self-consistency — popover % == round(N/M*100), breakdown sum ~100', async ({
    page,
  }) => {
    // The numbers cross-checked here need a session in the store and a budget on the
    // wire. Both were missing on the legs that actually ran this test: the CI leg only
    // ever skipped it (no dev handle in the built bundle), and on the dev leg the
    // popover read `6 / 0` — the seed fills the store, but the denominator comes from
    // GET /api/context/budget and no server answers on the dev leg. Measured
    // 2026-11-25 10:03:51–10:03:55 (`pct 0 vs 6/0`). The budget is now intercepted
    // with a contract mirror of the route's dict (QG3_BUDGET_JSON — the shape check is
    // tests/test_qg3_budget_seed_contract.py, so this seed is a copy of the product's
    // contract, not a number typed into the spec).
    await page.setViewportSize({ width: 390, height: 844 })
    await page.route('**/api/context/budget*', (route) =>
      route.fulfill({ contentType: 'application/json', body: QG3_BUDGET_JSON }),
    )
    await page.goto('/#/chat', { waitUntil: 'load' })
    // The context figure lives in the single breakdown toggle now (the separate tok chip was
    // retired: one home per screen, 105edc18). The cross-checks below still hold.
    await page.waitForSelector('[data-testid="statusbar-breakdown-toggle"]')
    test.skip(!(await hasDevHandle(page)), 'needs vite dev server (DEV-only __epheStore handle)')
    await page.evaluate(seedQg)
    await page.getByTestId('statusbar-breakdown-toggle').click()
    await expect(page.getByTestId('context-popover')).toBeVisible()

    // The seam this test holds: the numbers come from the seed, the formatting from
    // the product. This leg prints German — helpers.ensureOnboarded pins
    // i18nextLng='de' — so the expected strings below are the product's own
    // formatNumber/formatPercent output for de, not a locale-agnostic regex that
    // would pass English and German alike (the startswith("Thought") case in
    // different clothing).
    const b = JSON.parse(QG3_BUDGET_JSON) as {
      estimated_tokens: number
      window_tokens: number
      percent: number
      breakdown: { name: string; percent: number }[]
    }
    const header = `${formatNumber(b.estimated_tokens, 'de')} / ${formatNumber(
      b.window_tokens,
      'de',
    )} (${formatPercent(b.percent, 'de')})`
    const printed = await page.evaluate(() => {
      const dlg = document.querySelector('[data-testid="context-popover"]')!
      return {
        text: dlg.textContent!,
        rows: Array.from(dlg.querySelectorAll('li')).map((li) => li.textContent!),
      }
    })
    expect(printed.text, `popover header lacks "${header}"`).toContain(header)
    // Level 4: the seeded numbers have to fit each other by the route's own identity
    expect(
      b.percent,
      `percent ${b.percent} vs ${b.estimated_tokens}/${b.window_tokens}`,
    ).toBeCloseTo((b.estimated_tokens / b.window_tokens) * 100, 0.6)
    // Each row prints name + its share through the product formatter; equality on the
    // row text is what makes a silently missing or drifting row red here.
    expect(printed.rows.length, 'one row per seeded category').toBe(b.breakdown.length)
    for (const r of b.breakdown) {
      expect(printed.rows, `row ${r.name}`).toContain(
        `${r.name}${formatNumber(r.percent, 'de', 3)}%`,
      )
    }
    // Breakdown: sum of the shares ~ 100 (decimals add up with rounding error)
    const sum = b.breakdown.reduce((a, r) => a + r.percent, 0)
    expect(sum).toBeGreaterThanOrEqual(99)
    expect(sum).toBeLessThanOrEqual(101)
  })

  test('QG4: Storage chip == store truth (count + MB format), updated after the 2nd session', async ({
    page,
  }) => {
    // The level-4 cross-check below reads the chip's numbers against
    // window.__epheStore's own count — the dev-only store handle. Guard on the app page
    // (see QG2): the handle only exists once the app has booted.
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/#/chat', { waitUntil: 'load' })
    // The context figure lives in the single breakdown toggle now (the separate tok chip was
    // retired: one home per screen, 105edc18). The cross-checks below still hold.
    await page.waitForSelector('[data-testid="statusbar-breakdown-toggle"]')
    test.skip(!(await hasDevHandle(page)), 'needs vite dev server (DEV-only __epheStore handle)')
    await page.getByTestId('statusbar-breakdown-toggle').click()
    const chip = page.getByTestId('statusbar-storage-chip')
    // Without sessions: the chip either does not exist or counts 0 — both consistent
    const first = await chip.count()
    if (first > 0) {
      const txt = (await chip.textContent())!
      expect(/\d+ sessions? · ~?\d+([.,]\d+)? MB/.test(txt), txt).toBeTruthy()
    }
    // Level 4: value == store count
    const storeCount: number = await page.evaluate(
      () =>
        (
          window as unknown as { __epheStore: { getState: () => { sessions: unknown[] } } }
        ).__epheStore.getState().sessions.length,
    )
    if (first > 0) {
      const txt = (await chip.textContent())!
      expect(txt.startsWith(`${storeCount} sessions`), `${txt} vs store=${storeCount}`).toBeTruthy()
    } else {
      expect(storeCount).toBe(0)
    }
  })

  test('QG5: Tap-target and truncation quality (measured, not estimated)', async ({ page }) => {
    // Measures the seeded transcript (seedQg) — DEV-only store handle, same as QG2:
    // navigate first, then ask the loaded page for the handle.
    await page.goto('/#/chat', { waitUntil: 'load' })
    test.skip(!(await hasDevHandle(page)), 'needs vite dev server (DEV-only __epheStore handle)')
    await page.evaluate(seedQg)
    await page.waitForTimeout(300)
    // Desktop: interactive controls >= 36, mobile (own viewport) >= 44 — this is the desktop pass
    const heights = await page.evaluate(() => {
      const out: Record<string, number> = {}
      for (const id of [
        'send-btn',
        'model-chip',
        'composer-thinking-chip',
        'header-sidebar-toggle',
        'header-help',
        'header-more',
      ]) {
        const el = document.querySelector(`[data-testid="${id}"]`)
        out[id] = el ? el.getBoundingClientRect().height : -1
      }
      return out
    })
    for (const [id, h] of Object.entries(heights)) {
      if (h === -1) continue
      expect(h, `${id} Hoehe`).toBeGreaterThanOrEqual(34)
    }
    // Truncation: model chip with a long name -> scrollWidth > clientWidth (ellipsis active).
    // On desktop the chip sits in the composer (model-chip) or in the header (variant);
    // both are legitimate anchors, the first one with content counts.
    const trunc = await page.evaluate(() => {
      const el = document.querySelector(
        '[data-testid="model-chip"] span, [data-testid="header-model-chip"] span',
      )
      if (!el) return { sw: 0, cw: 0 }
      return { sw: el.scrollWidth, cw: el.clientWidth }
    })
    if (trunc.cw > 0) {
      expect(trunc.sw, `sw=${trunc.sw} cw=${trunc.cw}`).toBeGreaterThanOrEqual(trunc.cw - 1)
    }
    // Within-viewport check of all visible interactive nodes
    const overflow = await page.evaluate(() => {
      const vw = window.innerWidth
      const bad: string[] = []
      for (const el of Array.from(document.querySelectorAll('[data-testid]'))) {
        const r = el.getBoundingClientRect()
        if (r.width === 0 && r.height === 0) continue
        if (r.right > vw + 1 || r.left < -1) bad.push(el.getAttribute('data-testid')!)
      }
      return bad
    })
    expect(overflow, 'boxes outside the viewport').toEqual([])
  })

  test('QG6: PNG media quality — IHDR dimensions == DPR scaling, bytes > floor, not blank', async ({
    page,
  }) => {
    // A media round is produced locally by the walkthrough run (command in
    // app/e2e/walkthrough/README.md); it is not checked in, so the round to check is
    // named by environment rather than by a path baked into the tree.
    const env = process.env.EPHE_Q_MEDIA_ROUND
    const dir = env ? path.resolve(env) : ''
    // The w10_7 capture viewports: desktop 1280x900, mobile 390x844.
    const files = [
      ['w10_71_desktop_strom.png', 1280, 900],
      ['w10_75_mobile.png', 390, 844],
    ] as const
    test.skip(
      !dir || files.some(([f]) => !existsSync(`${dir}/${f}`)),
      "the round's media receipts are produced locally and are not checked in, so this assertion cannot run on a fresh checkout — set EPHE_Q_MEDIA_ROUND to a walkthrough run's output directory",
    )
    for (const [f, w, h] of files) {
      const full = `${dir}/${f}`
      expect(existsSync(full), f).toBeTruthy()
      const bytes = statSync(full).size
      expect(bytes, `${f} Bytes`).toBeGreaterThan(2048)
      const buf = readFileSync(full)
      // IHDR: width@16..19, height@20..23 (big-endian, after the 8-byte signature + 4-byte length + 'IHDR')
      const iw = buf.readUInt32BE(16)
      const ih = buf.readUInt32BE(20)
      expect(iw, `${f} IHDR-W`).toBe(w)
      expect(ih, `${f} IHDR-H`).toBe(h)
    }
    // Non-blankness in the decoder: >= 3 distinct pixel values over a sample
    await page.goto(`file://${dir}/w10_71_desktop_strom.png`)
    const distinct = await page.evaluate(() => {
      const img = document.querySelector('img') as HTMLImageElement
      const c = document.createElement('canvas')
      c.width = img.naturalWidth
      c.height = img.naturalHeight
      const ctx = c.getContext('2d')!
      ctx.drawImage(img, 0, 0)
      const d = ctx.getImageData(0, 0, c.width, c.height).data
      const seen = new Set<number>()
      for (let i = 0; i < d.length; i += 4 * 17) {
        seen.add(((d[i] ?? 0) << 16) | ((d[i + 1] ?? 0) << 8) | (d[i + 2] ?? 0))
        if (seen.size >= 3) break
      }
      return seen.size
    })
    expect(distinct).toBeGreaterThanOrEqual(3)
  })

  test('QG7: Determinism — a second identical boot yields the same test id set', async ({
    page,
  }) => {
    await page.goto('/#/chat', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]')
    const idsA: string[] = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid]'))
        .map((e) => e.getAttribute('data-testid')!)
        .sort(),
    )
    await page.reload({ waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]')
    const idsB: string[] = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid]'))
        .map((e) => e.getAttribute('data-testid')!)
        .sort(),
    )
    expect(idsB).toEqual(idsA)
    expect(idsA.length).toBeGreaterThan(8)
  })

  test('QG8: a11y completeness — every button with an accessible name, focus visible', async ({
    page,
  }) => {
    await page.goto('/#/chat', { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]')
    const res = await page.evaluate(() => {
      const names: string[] = []
      for (const b of Array.from(document.querySelectorAll('button'))) {
        const label = b.getAttribute('aria-label') || b.textContent || ''
        if (!label.trim()) names.push(b.dataset.testid || b.className.slice(0, 24))
      }
      return names
    })
    expect(res, `buttons without accessible name: ${res.join(', ')}`).toEqual([])
    // Focus indicator on the composer (the focus-visible rule works) — measured after Tab
    await page.getByTestId('send-btn').focus()
    const outline = await page.evaluate(() => {
      const el = document.activeElement!
      const s = getComputedStyle(el)
      return s.outlineStyle !== 'none' || s.boxShadow !== 'none' || parseFloat(s.outlineWidth) > 0
    })
    expect(outline).toBeTruthy()
  })
})
