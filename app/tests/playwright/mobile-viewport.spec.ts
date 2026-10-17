import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

// The widths and surfaces are the ones `scripts/tauri_parity.py` checks against the app: the
// manifest is the input, not a second list that can drift from it. 320 is the narrowest screen
// the product claims (iPhone SE, small Android in a split window); 375 and 390 are the current
// phone floors the earlier specs already used one at a time.
const MANIFEST = JSON.parse(
  readFileSync(fileURLToPath(new URL('./shell-parity.manifest.json', import.meta.url)), 'utf8'),
) as {
  mobile: { widths: number[]; surfaces: Array<{ path: string; anchor: string; reach: string }> }
}

// Mobile viewport: the legacy #mobile-bottomnav tab bar no longer exists.
// Current mobile logic: the menu button in the chat header opens the sidebar
// (fixed, slide-in); the panels stay responsive.

test.describe('Mobile Viewport (aktuelle UI: Sidebar-Drawer statt Bottom-Nav)', () => {
  test.use({ viewport: { width: 375, height: 667 } })

  test('landing has no horizontal overflow on mobile', async ({ page }) => {
    await ensureOnboarded(page)
    await page.goto('/', { waitUntil: 'load' })
    await page.waitForSelector('h1', { timeout: 10000 })
    await page.waitForTimeout(500)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    )
    expect(overflow).toBe(false)
  })

  test('chat header shows the mobile menu button', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    const menuBtn = page.locator('header button:has(svg.lucide-menu)')
    await expect(menuBtn).toBeVisible()
  })

  test('menu button opens the sidebar drawer', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.locator('header button:has(svg.lucide-menu)').click()
    await expect(page.locator('[data-testid="sessions-view"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-testid="new-session"]')).toBeVisible()
  })

  test('chat workspace has no horizontal overflow on mobile', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.waitForTimeout(500)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 2,
    )
    expect(overflow).toBe(false)
  })
})

/*
 * The three coding surfaces at the 390 px phone floor — chat, the fleet/workspaces
 * view, and the change-set review.
 *
 * Two numbers are held here, both measured in a real browser at 390 x 844 rather than
 * derived from the class list:
 *
 *   - the 44 px touch floor. Below lg (1024 px) a control a thumb has to hit is at
 *     least 44 x 44; a control that misses it is named in the failure.
 *   - the 16 px text-entry floor on this surface. iOS Safari zooms the whole viewport
 *     when a focused `input`/`select`/`textarea` computes under 16 px, which pushes the
 *     review's own submit row off the screen — the product's `--text-ui-input` token is
 *     the floor, and every other entry in the app (composer, settings) already sits on it.
 *
 * The API is stubbed rather than the UI: the bundle, its CSS and its components are the
 * ones in `dist`, and only the backend this leg does not start is answered from fixtures.
 * The context blocks service workers, which would otherwise answer the fetches below
 * Playwright's route layer (the product registers a PWA service worker).
 */
const FIXTURE_WORKSPACES = [
  {
    id: 'ws-fixture-0001',
    path: '/tmp/ephe-wt/wt-cart-checkout-hardening',
    branch: 'agent/cart-checkout-hardening',
    state: 'ready',
    owner: 'cart-checkout-hardening',
    created_at: '2026-10-14T14:02:00+00:00',
  },
  {
    id: 'ws-fixture-0002',
    path: '/tmp/ephe-wt/wt-pricing-and-tax-rules',
    branch: 'agent/pricing-and-tax',
    state: 'dirty',
    owner: 'pricing-and-tax-rules',
    created_at: '2026-10-14T09:41:00+00:00',
  },
]

const FIXTURE_CHANGE_SET = {
  id: 'cs-fixture-0001',
  workspace_id: 'ws-fixture-0001',
  summary: 'Harden checkout amount parsing against locale separators',
  files: [
    { path: 'src/payments/amount.ts', op: 'modify', diff_sha: 'f3a91c07b2d4' },
    { path: 'src/payments/__tests__/amount.test.ts', op: 'create', diff_sha: '9c1de440aa71' },
  ],
  provenance: {
    session_id: 'sess-fixture-0001',
    agent_id: 'agent-claude-worker-04',
    why: 'A checkout in de-DE read "12,50" as 1250.',
  },
  state: 'review',
  created_at: '2026-10-14T14:02:00+00:00',
}

async function stubReadableApi(page: import('@playwright/test').Page) {
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.includes('/api/workspaces'))
      return route.fulfill({ json: { workspaces: FIXTURE_WORKSPACES, runs: [] } })
    if (url.includes('/api/change-sets'))
      return route.fulfill({ json: { change_sets: [FIXTURE_CHANGE_SET] } })
    if (url.includes('/api/memory/stats')) return json({ total: 0, deleted: 0, scope: 'fixture' })
    if (url.includes('/api/memory/list')) return json({ entries: [], total: 0 })
    if (url.includes('/api/memory/search')) return json({ results: [] })
    if (url.includes('/api/memory/deleted'))
      return json({ entries: [], restore_supported: true, detail: '' })
    if (url.includes('/api/artifacts/stats'))
      return json({
        count: 0,
        bytes: 0,
        by_kind: [],
        expiring_count: 0,
        expiring_bytes: 0,
        next_expiry: null,
      })
    if (url.includes('/api/artifacts/expiry'))
      return json({ due: [], count: 0, bytes: 0, days: 30 })
    if (url.includes('/api/artifacts')) return json({ artifacts: [], total: 0 })
    if (url.includes('/api/sessions/restore')) return route.fulfill({ json: { sessions: [] } })
    if (url.includes('/api/settings')) {
      return route.fulfill({ json: { workspace_dir: '/tmp/ephe', approval_profile: 'strict' } })
    }
    if (url.includes('/api/setup/status')) {
      return route.fulfill({ json: { configured: true, provider: 'local_ollama' } })
    }
    // Empty rather than 404: these pages read their root before their data, and a refusal would
    // make the layout under test an error state instead of the surface.
    return json({})
  })
}

/**
 * The visible controls inside `scope` that miss the floor, each named the way a reader
 * can find it. A control is measured on its own box: a square icon button needs both
 * sides, a labelled one only its height (its width follows the word it carries).
 */
async function underFloor(
  page: import('@playwright/test').Page,
  scope: string,
  floor = 44,
): Promise<Array<Record<string, unknown>>> {
  return page.evaluate(
    ({ scope, floor }) => {
      const host = document.querySelector(scope)
      if (!host) return [{ missing: scope }]
      const sel =
        'button,input:not([type="checkbox"]),select,textarea,[role="button"],[role="tab"],[role="menuitem"]'
      const out: Array<Record<string, unknown>> = []
      for (const el of Array.from(host.querySelectorAll(sel))) {
        const r = el.getBoundingClientRect()
        const cs = getComputedStyle(el)
        if (r.width === 0 || r.height === 0 || cs.visibility === 'hidden') continue
        const square = el.matches('button') && (el.textContent ?? '').trim() === ''
        if (r.height + 0.5 < floor || (square && r.width + 0.5 < floor)) {
          out.push({
            testid: el.getAttribute('data-testid'),
            label: (el.getAttribute('aria-label') || (el.textContent ?? '').trim()).slice(0, 48),
            tag: el.tagName.toLowerCase(),
            w: Math.round(r.width),
            h: Math.round(r.height),
          })
        }
      }
      return out
    },
    { scope, floor },
  )
}

/** Text entries whose computed size would make iOS Safari zoom the viewport on focus. */
async function autoZoomEntries(
  page: import('@playwright/test').Page,
  scope: string,
): Promise<Array<Record<string, unknown>>> {
  return page.evaluate((scope) => {
    const host = document.querySelector(scope)
    if (!host) return [{ missing: scope }]
    return Array.from(host.querySelectorAll('input,select,textarea'))
      .filter((el) => (el as HTMLElement).getBoundingClientRect().width > 0)
      .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
      .map((el) => ({
        testid: el.getAttribute('data-testid'),
        tag: el.tagName.toLowerCase(),
        fontSize: getComputedStyle(el).fontSize,
      }))
  }, scope)
}

test.describe('Coding surfaces at the 390 px phone floor', () => {
  test.use({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' })

  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await stubReadableApi(page)
  })

  test('the fleet list fits 390 px with nothing cut off past the right edge', async ({ page }) => {
    await gotoHash(page, '/workspaces', '[data-testid="workspaces-list"]')
    await page.waitForTimeout(300)
    const g = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
      past: Array.from(document.querySelectorAll('body *'))
        .filter((el) => {
          const r = el.getBoundingClientRect()
          return r.width > 0 && r.height > 0 && r.right > window.innerWidth + 1
        })
        .map((el) => el.getAttribute('data-testid') || el.tagName.toLowerCase()),
      rows: document.querySelectorAll('[data-testid^="workspace-row-"]').length,
    }))
    expect(g.rows).toBe(FIXTURE_WORKSPACES.length)
    expect(g.past).toEqual([])
    expect(g.overflow).toBe(false)
  })

  test('the fleet filter is a 44 px field and does not zoom the viewport', async ({ page }) => {
    await gotoHash(page, '/workspaces', '[data-testid="workspaces-list"]')
    await page.waitForTimeout(300)
    await page.getByTestId('workspaces-filter').fill('cart')
    await page.waitForTimeout(200)
    const box = await page.evaluate(() => {
      const f = document.querySelector('[data-testid="workspaces-filter"]') as HTMLElement
      const c = document.querySelector('[data-testid="workspaces-filter-clear"]') as HTMLElement
      const r = f.getBoundingClientRect()
      const cr = c.getBoundingClientRect()
      return {
        h: Math.round(r.height),
        fontSize: getComputedStyle(f).fontSize,
        clearInside: cr.right <= r.right + 1 && cr.left >= r.left - 1,
        clearW: Math.round(cr.width),
        clearH: Math.round(cr.height),
      }
    })
    expect(box.h).toBeGreaterThanOrEqual(44)
    expect(parseFloat(box.fontSize)).toBeGreaterThanOrEqual(16)
    // The clear button must not spill out of its field, and must itself be a target.
    expect(box.clearInside).toBe(true)
    expect(box.clearW).toBeGreaterThanOrEqual(44)
    expect(box.clearH).toBeGreaterThanOrEqual(44)
  })

  test('the change-set review is writable at 390 px', async ({ page }) => {
    await gotoHash(page, '/workspaces', '[data-testid="workspaces-list"]')
    await page.locator('[data-testid^="workspace-row-"]').first().click()
    await page.waitForSelector('[data-testid="changesets-list"]', { timeout: 15000 })
    await page.locator('[data-testid^="changeset-review-open-"]').first().click()
    await page.waitForSelector('[data-testid="review-form-cs-fixture-0001"]', { timeout: 15000 })
    await page.waitForTimeout(300)

    const form = '[data-testid="review-form-cs-fixture-0001"]'
    expect(await autoZoomEntries(page, form)).toEqual([])
    expect(await underFloor(page, form)).toEqual([])

    // The verdict row is what a reviewer reaches for last, and the one a zoomed
    // viewport pushes off-screen — it has to stay inside 390 after the entries settle.
    const verdicts = await page.evaluate((form) => {
      const host = document.querySelector(form)!
      const row = host.lastElementChild as HTMLElement
      const r = row.getBoundingClientRect()
      return {
        right: Math.round(r.right),
        entries: Array.from(host.querySelectorAll('input,select,textarea')).map((el) =>
          Math.round(el.getBoundingClientRect().height),
        ),
      }
    }, form)
    expect(verdicts.right).toBeLessThanOrEqual(390)
    expect(verdicts.entries.every((h) => h >= 44)).toBe(true)
  })

  test('the chat drawer reaches the phone floor and its search does not zoom', async ({ page }) => {
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.locator('[data-testid="header-menu-toggle"]').click()
    await page.waitForSelector('[data-testid="sessions-view"]', { timeout: 10000 })
    await page.waitForTimeout(300)

    // `chat-sidebar` is the drawer itself (role="dialog" off desktop); `sessions-view`
    // is only the task list below its controls.
    const drawer = '[data-testid="chat-sidebar"]'
    // Only the drawer's own controls: the two skip links live above it.
    expect((await underFloor(page, drawer)).filter((c) => c.tag !== 'a')).toEqual([])

    // The filter popover is the drawer's other surface. Opening it here is what makes
    // its eight controls measured instead of skipped as unrendered.
    await page.getByTestId('sidebar-filter-toggle').click()
    await page.waitForSelector('[data-testid="sidebar-filter-popover"]', { timeout: 5000 })
    await page.waitForTimeout(200)
    expect((await underFloor(page, drawer)).filter((c) => c.tag !== 'a')).toEqual([])

    const search = await page.evaluate((sel) => {
      const el = document.querySelector(`${sel} [data-testid="sidebar-search"]`)
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { h: Math.round(r.height), fontSize: getComputedStyle(el).fontSize }
    }, drawer)
    expect(search).not.toBeNull()
    expect(search!.h).toBeGreaterThanOrEqual(44)
    expect(parseFloat(search!.fontSize)).toBeGreaterThanOrEqual(16)

    // The field's clear button only exists once there is a query, and it is a target
    // a thumb has to hit inside the field it clears.
    await page.getByTestId('sidebar-search').fill('amount')
    await page.waitForTimeout(250)
    const clear = await page.evaluate((sel) => {
      const field = document.querySelector(`${sel} [data-testid="sidebar-search"]`)!
      const btn = document.querySelector(
        `${sel} [data-testid="sidebar-search-clear"]`,
      ) as HTMLElement | null
      if (!btn) return null
      const f = field.getBoundingClientRect()
      const b = btn.getBoundingClientRect()
      return {
        w: Math.round(b.width),
        h: Math.round(b.height),
        inside: b.right <= f.right + 1 && b.left >= f.left - 1,
      }
    }, drawer)
    expect(clear).not.toBeNull()
    expect(clear!.w).toBeGreaterThanOrEqual(44)
    expect(clear!.h).toBeGreaterThanOrEqual(44)
    expect(clear!.inside).toBe(true)
  })
})

/**
 * Horizontal scroll that should not be there: the document itself, or a layout region
 * (main, header, a dialog, an aria-labelled nav, the surface's own root) whose content is
 * wider than the box it was given. A strip that declares `overflow-x: auto|scroll` is a
 * scroll region by design — the register's chip row is one — and is not counted; content
 * clipped by `overflow: hidden` or spilling out of a visible box is.
 */
async function horizontalOverflow(
  page: Page,
  anchor: string,
): Promise<Array<Record<string, unknown>>> {
  return page.evaluate((scope) => {
    const out: Array<Record<string, unknown>> = []
    const document_ = document.documentElement
    if (document_.scrollWidth > window.innerWidth + 1) {
      out.push({ region: 'document', scrollWidth: document_.scrollWidth, width: window.innerWidth })
    }
    const seen = new Set<Element>()
    for (const selector of ['main', 'header', '[role="dialog"]', 'nav[aria-label]', scope]) {
      for (const element of Array.from(document.querySelectorAll(selector))) {
        if (seen.has(element)) continue
        seen.add(element)
        const box = element.getBoundingClientRect()
        if (box.width === 0 || box.height === 0) continue
        const overflowX = getComputedStyle(element).overflowX
        if (overflowX === 'auto' || overflowX === 'scroll') continue
        if (element.scrollWidth > element.clientWidth + 1) {
          const id = element.getAttribute('data-testid')
          out.push({
            region: id ? `${selector}#${id}` : selector,
            scrollWidth: element.scrollWidth,
            clientWidth: element.clientWidth,
            overflowX,
          })
        }
      }
    }
    return out
  }, anchor)
}

/** The surface's declared route, or the register reached the only way a phone has: the drawer. */
async function reachSurface(page: Page, surface: { path: string; anchor: string; reach: string }) {
  if (surface.reach === 'route') {
    await gotoHash(page, surface.path, surface.anchor)
    return
  }
  if (surface.reach === 'settings-register') {
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('header-menu-toggle').click()
    await page.waitForSelector('[data-testid="chat-sidebar"]', { timeout: 10000 })
    await page.getByTestId('sidebar-settings-btn').first().click()
    await page.waitForSelector(surface.anchor, { timeout: 10000 })
    return
  }
  throw new Error(`the manifest names an unknown reach: ${surface.reach}`)
}

/**
 * The width sweep: every declared mobile surface at every declared width, with a touch screen
 * (the 44 px floor and the 16 px entry floor are thumb rules, not pointer rules). One test per
 * surface and width, so a failure names the screen and the measurement that missed.
 */
for (const width of MANIFEST.mobile.widths) {
  test.describe(`mobile floor ${width}x800`, () => {
    test.use({ viewport: { width, height: 800 }, hasTouch: true, serviceWorkers: 'block' })

    test.beforeEach(async ({ page }) => {
      await ensureOnboarded(page)
      await stubReadableApi(page)
    })

    for (const surface of MANIFEST.mobile.surfaces) {
      test(`${surface.path} fits ${width} px without sideways scroll or small targets`, async ({
        page,
      }) => {
        await reachSurface(page, surface)
        await page.waitForTimeout(400)

        // All three measurements run before the assertion, and one object carries all of them:
        // a red surface names every floor it misses, not only the first one checked.
        const measured = {
          sideways: await horizontalOverflow(page, surface.anchor),
          small: await underFloor(page, surface.anchor),
          zooms: await autoZoomEntries(page, surface.anchor),
        }
        expect(
          measured,
          `${surface.path} at ${width} px misses the mobile floors: ${JSON.stringify(measured)}`,
        ).toEqual({ sideways: [], small: [], zooms: [] })
      })
    }
  })
}
