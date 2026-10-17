import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'

/**
 * PWA / desktop shell parity: the same route, the same surface, two platforms.
 *
 * The audit's finding was not that the two shells differ — they do, and they must: one has window
 * controls, a native updater and a local backend, the other has a service worker and none of
 * those. The finding was that nothing measured where they are the same. This spec opens every
 * route declared in `shell-parity.manifest.json` twice, once as the PWA and once with the shell's
 * `window.__TAURI__` bridge present, and compares the visible text and the structural landmarks.
 * A difference is allowed only when the manifest names it under `platform_only`; the comparison
 * removes those selectors from both sides before it looks.
 *
 * The route list is the manifest, not a list in this file: `scripts/tauri_parity.py` refuses a
 * route in `app/src/App.tsx` that the manifest does not carry, so a new screen cannot ship outside
 * this comparison. The same file also counts every `isTauri` / `isDesktopShell` / `__TAURI__`
 * read, which is what makes the list of platform branches a contract rather than a comment.
 *
 * Both contexts block service workers. A worker answers `/api/*` from its own fetch context, below
 * `page.route` (`app/public/service-worker.js`, and the note in visual.spec.ts that paid for it);
 * the PWA's registration is proven in its own test below, where nothing is stubbed underneath it.
 *
 * The API is stubbed, the bundle is the one in `dist` (the static leg serves it). The desktop stub
 * also carries `__TAURI_INTERNALS__`: `@tauri-apps/plugin-updater` reaches the shell through that
 * namespace, and a stub that only defined `__TAURI__` would make the update check throw where the
 * real shell answers.
 */

type RouteEntry = { path: string; probe: string; page: string; anchor: string }
type BranchEntry = {
  file: string
  marker: string
  count: number
  surface: string
  web: string
  desktop: string
}
type PlatformOnly = {
  id: string
  kind: 'dom' | 'capability'
  selector: string | null
  present_on: 'web' | 'desktop' | 'both'
  reason: string
}
type Manifest = {
  schema: number
  routes: RouteEntry[]
  platform_branches: BranchEntry[]
  platform_only: PlatformOnly[]
  mobile: { widths: number[]; surfaces: Array<{ path: string; anchor: string; reach: string }> }
}

const MANIFEST: Manifest = JSON.parse(
  readFileSync(fileURLToPath(new URL('./shell-parity.manifest.json', import.meta.url)), 'utf8'),
)

const FROZEN_TIME = new Date('2026-10-16T09:00:00Z')
const VIEWPORT = { width: 1280, height: 800 }

const FIXTURE_WORKSPACES = [
  {
    id: 'ws-fixture-0001',
    path: '/tmp/ephe-wt/wt-cart-checkout-hardening',
    branch: 'agent/cart-checkout-hardening',
    state: 'ready',
    owner: 'cart-checkout-hardening',
    created_at: '2026-10-14T14:02:00+00:00',
  },
]

const FIXTURE_CHANGE_SET = {
  id: 'cs-fixture-0001',
  workspace_id: 'ws-fixture-0001',
  summary: 'Harden checkout amount parsing against locale separators',
  files: [{ path: 'src/payments/amount.ts', op: 'modify', diff_sha: 'f3a91c07b2d4' }],
  provenance: {
    session_id: 'sess-fixture-0001',
    agent_id: 'agent-worker-04',
    why: 'A checkout read 12,50 as 1250.',
  },
  state: 'review',
  created_at: '2026-10-14T14:02:00+00:00',
}

const FIXTURE_CUSTODY = {
  change_set: FIXTURE_CHANGE_SET,
  author: 'agent-worker-04',
  approval: null,
  custodians: ['agent-reviewer-01'],
  files: [
    {
      path: 'src/payments/amount.ts',
      op: 'modify',
      recorded: 'sha256:f3a91c07b2d4',
      current: 'sha256:f3a91c07b2d4',
      moved: false,
    },
  ],
  checked: true,
  publishable: false,
  refusal: { code: 'unsigned', sentence: 'No reviewer has signed this change set.' },
}

// The desktop shell fetches http://127.0.0.1:8765 (lib/desktopBaseUrl.ts), so every stubbed
// answer has to be a cross-origin answer the browser will accept.
const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': '*',
}

async function stubApi(page: Page) {
  await page.route('**/api/**', (route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      return route.fulfill({ status: 204, headers: CORS })
    }
    const { pathname } = new URL(request.url())
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        headers: CORS,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

    if (pathname === '/api/setup/status') {
      // configured=false keeps /setup on screen; skipped=true keeps the gate open for every other
      // route. Both sides see the same answer, so the comparison is over the difference under test.
      return json({ configured: false, skipped: true, provider: null, model: null, url: null })
    }
    if (pathname.endsWith('/custody')) return json(FIXTURE_CUSTODY)
    if (pathname === '/api/workspaces') return json({ workspaces: FIXTURE_WORKSPACES, runs: [] })
    if (pathname === '/api/change-sets') return json({ change_sets: [FIXTURE_CHANGE_SET] })
    if (pathname === '/api/memory/stats') return json({ total: 0, deleted: 0, scope: 'fixture' })
    if (pathname === '/api/memory/list') return json({ entries: [], total: 0 })
    if (pathname === '/api/memory/search') return json({ results: [] })
    if (pathname === '/api/memory/deleted')
      return json({ entries: [], restore_supported: true, detail: '' })
    if (pathname === '/api/artifacts') return json({ artifacts: [], total: 0 })
    if (pathname === '/api/artifacts/stats') {
      return json({
        count: 0,
        bytes: 0,
        by_kind: [],
        expiring_count: 0,
        expiring_bytes: 0,
        next_expiry: null,
      })
    }
    if (pathname === '/api/artifacts/expiry') return json({ due: [], count: 0, bytes: 0, days: 30 })
    if (pathname === '/api/sessions/restore') return json({ sessions: [] })
    if (pathname === '/api/skills') return json({ skills: [], total: 0 })
    return json({})
  })
}

function installTauriStub() {
  const invoke = async () => null
  const bridge = {
    core: { invoke },
    event: { listen: async () => () => {} },
    app: { getVersion: async () => '0.1.0-fixture' },
    process: { relaunch: async () => {} },
  }
  Object.defineProperty(window, '__TAURI__', { value: bridge, configurable: true })
  Object.defineProperty(window, '__TAURI_INTERNALS__', {
    value: { invoke, transformCallback: (callback: unknown) => callback },
    configurable: true,
  })
}

async function prepare(page: Page, anchor: string, probe: string) {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
    localStorage.setItem('ephe.intro.seen.v1', '1')
  })
  await page.clock.setFixedTime(FROZEN_TIME)
  await stubApi(page)
  await page.goto(`/#${probe}`, { waitUntil: 'load' })
  await page.waitForSelector(anchor, { timeout: 15000 })
  await expect(page.locator('[data-testid="route-skeleton"]')).toHaveCount(0)
  // The anchor is the route's first paint; one beat lets the reads behind it land. Both sides get
  // the same beat, so a difference is content, not timing.
  await page.waitForTimeout(600)
}

type Snapshot = { text: string; landmarks: string[] }

/** Visible text and structural landmarks, minus the subtrees the manifest calls platform-only. */
async function snapshot(page: Page, excluded: string[]): Promise<Snapshot> {
  return page.evaluate((excludedSelectors) => {
    const root = document.getElementById('root')
    if (!root) return { text: '', landmarks: [] }
    const skip = (el: Element | null): boolean => {
      if (!el) return true
      return excludedSelectors.some((selector) => {
        try {
          return el.matches(selector) || el.closest(selector) !== null
        } catch {
          return false
        }
      })
    }
    const visible = (el: Element) => el.getClientRects().length > 0

    const words: string[] = []
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    for (let node = walk.nextNode(); node; node = walk.nextNode()) {
      const parent = node.parentElement
      if (!parent || skip(parent) || !visible(parent)) continue
      const text = (node.textContent ?? '').replace(/\s+/g, ' ').trim()
      if (text) words.push(text)
    }

    const selector =
      'header, nav, main, aside, [role="dialog"], [role="navigation"], [role="region"], h1, h2, h3, [data-testid]'
    const landmarks = Array.from(root.querySelectorAll(selector))
      .filter((el) => !skip(el) && visible(el))
      .map((el) => {
        const id = el.getAttribute('data-testid')
        const role = el.getAttribute('role')
        return `${el.tagName.toLowerCase()}${id ? `#${id}` : ''}${role ? `[${role}]` : ''}`
      })

    return { text: words.join(' '), landmarks }
  }, excluded)
}

function firstDifference(web: string, desktop: string): string {
  if (web === desktop) return ''
  let at = 0
  while (at < web.length && at < desktop.length && web[at] === desktop[at]) at += 1
  const from = Math.max(0, at - 60)
  return (
    `\n  first difference at character ${at}:` +
    `\n  web:     …${web.slice(from, at + 100)}…` +
    `\n  desktop: …${desktop.slice(from, at + 100)}…`
  )
}

test.describe.configure({ timeout: 60_000 })

test.describe('shell parity at 1280x800', () => {
  test.use({ viewport: VIEWPORT, deviceScaleFactor: 1, serviceWorkers: 'block' })

  for (const route of MANIFEST.routes) {
    test(`${route.path} renders the same surface in the PWA and the shell`, async ({ browser }) => {
      const baseURL = test.info().project.use.baseURL
      expect(baseURL, 'the static leg has no baseURL').toBeTruthy()
      const excluded = MANIFEST.platform_only
        .filter((entry) => entry.kind === 'dom' && entry.selector)
        .map((entry) => entry.selector as string)

      const webContext = await browser.newContext({
        baseURL,
        viewport: VIEWPORT,
        deviceScaleFactor: 1,
        serviceWorkers: 'block',
      })
      const desktopContext = await browser.newContext({
        baseURL,
        viewport: VIEWPORT,
        deviceScaleFactor: 1,
        serviceWorkers: 'block',
      })
      await desktopContext.addInitScript(installTauriStub)
      try {
        const web = await webContext.newPage()
        await prepare(web, route.anchor, route.probe)
        const asWeb = await snapshot(web, excluded)

        const desktop = await desktopContext.newPage()
        const bridged = await desktop.evaluate(() => '__TAURI__' in window)
        expect(bridged, 'the desktop context must boot with the shell bridge').toBe(true)
        await prepare(desktop, route.anchor, route.probe)
        const asDesktop = await snapshot(desktop, excluded)

        expect(
          asDesktop.text,
          `${route.path}: the visible text differs between the PWA and the shell${firstDifference(asWeb.text, asDesktop.text)}`,
        ).toBe(asWeb.text)
        expect(
          asDesktop.landmarks,
          `${route.path}: the structural landmarks differ between the PWA and the shell`,
        ).toEqual(asWeb.landmarks)
      } finally {
        await webContext.close()
        await desktopContext.close()
      }
    })
  }

  test('the declared DOM difference is the only one: window controls exist in the shell only', async ({
    browser,
  }) => {
    const baseURL = test.info().project.use.baseURL
    expect(baseURL).toBeTruthy()
    const controls = MANIFEST.platform_only.find((entry) => entry.id === 'window-controls')
    expect(controls, 'the manifest no longer declares window-controls').toBeTruthy()
    expect(controls?.kind).toBe('dom')
    expect(controls?.present_on).toBe('desktop')
    const selector = controls?.selector
    expect(selector).toBeTruthy()

    const webContext = await browser.newContext({
      baseURL,
      viewport: VIEWPORT,
      serviceWorkers: 'block',
    })
    const desktopContext = await browser.newContext({
      baseURL,
      viewport: VIEWPORT,
      serviceWorkers: 'block',
    })
    await desktopContext.addInitScript(installTauriStub)
    try {
      const web = await webContext.newPage()
      await prepare(web, '[data-testid="panel-chat"]', '/chat')
      expect(await web.locator(selector as string).count()).toBe(0)

      const desktop = await desktopContext.newPage()
      await prepare(desktop, '[data-testid="panel-chat"]', '/chat')
      expect(await desktop.locator(selector as string).count()).toBe(2)
    } finally {
      await webContext.close()
      await desktopContext.close()
    }
  })

  test('the service worker belongs to the PWA, and the shell comparison runs without one', async ({
    browser,
  }) => {
    const baseURL = test.info().project.use.baseURL
    expect(baseURL).toBeTruthy()
    const declared = MANIFEST.platform_only.find((entry) => entry.id === 'service-worker')
    expect(declared, 'the manifest no longer declares the service worker').toBeTruthy()
    expect(declared?.present_on).toBe('web')

    // Allowed here: the registration is the thing being measured, and no /api answer is stubbed
    // underneath it.
    const webContext = await browser.newContext({
      baseURL,
      viewport: VIEWPORT,
      serviceWorkers: 'allow',
    })
    try {
      const web = await webContext.newPage()
      const problems: string[] = []
      web.on('console', (message) => {
        if (message.type() === 'error') problems.push(message.text())
      })
      web.on('pageerror', (error) => problems.push(error.message))
      await web.addInitScript(() => {
        localStorage.setItem('ephe_onboarded', '1')
        localStorage.setItem('ephe.intro.seen.v1', '1')
      })
      await web.goto('/#/chat', { waitUntil: 'load' })
      await expect
        .poll(
          () =>
            web.evaluate(async () => {
              const registrations = await navigator.serviceWorker.getRegistrations()
              return registrations.map(
                (registration) =>
                  registration.active?.scriptURL ??
                  registration.installing?.scriptURL ??
                  registration.waiting?.scriptURL ??
                  '',
              )
            }),
          {
            timeout: 20000,
            message: `the PWA did not register /service-worker.js; console: ${problems.join(' | ')}`,
          },
        )
        .toContainEqual(expect.stringContaining('/service-worker.js'))
    } finally {
      await webContext.close()
    }

    // Blocked here, as in every parity test above: a worker would answer /api below page.route.
    const blockedContext = await browser.newContext({
      baseURL,
      viewport: VIEWPORT,
      serviceWorkers: 'block',
    })
    try {
      const blocked = await blockedContext.newPage()
      await blocked.goto('/#/chat', { waitUntil: 'load' })
      expect(
        await blocked.evaluate(() =>
          navigator.serviceWorker.getRegistrations().then((r) => r.length),
        ),
      ).toBe(0)
    } finally {
      await blockedContext.close()
    }
  })
})

test('the manifest does not repeat a route or lose a platform branch', () => {
  const paths = MANIFEST.routes.map((route) => route.path)
  expect(new Set(paths).size, 'a route is declared twice').toBe(paths.length)
  const branches = MANIFEST.platform_branches.map((branch) => `${branch.file}:${branch.marker}`)
  expect(new Set(branches).size, 'a platform read is declared twice').toBe(branches.length)
  expect(MANIFEST.platform_only.map((entry) => entry.id).sort()).toContain('window-controls')
  expect(MANIFEST.platform_only.map((entry) => entry.id).sort()).toContain('service-worker')
})
