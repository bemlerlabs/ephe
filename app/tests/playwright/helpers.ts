import { Page } from '@playwright/test'

/**
 * Helpers for the current React+Vite UI (hash router: /, /onboarding, /chat).
 *
 * The legacy UI (the tab-based PWA with #welcome-screen / #mobile-bottomnav)
 * no longer exists — so the old dismiss* overlays are obsolete with it.
 *
 * The onboarding gate: localStorage 'ephe_onboarded'='1' (set it before the app
 * boots, otherwise the app renders the landing page directly — hash router, no
 * imperative overlay anymore).
 */

export async function ensureOnboarded(page: Page) {
  await page.addInitScript(() => {
    // Pin the language to German deterministically — i18next-browser-languagedetector
    // persists the locale in the key 'i18nextLng' (order: localStorage,
    // navigator). Without this the labels would depend on the navigator (a test
    // run with an en-US navigator renders English labels).
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
    // The first-run scene carries its own flag (`src/lib/firstRun.ts`, key
    // INTRO_SEEN_KEY). Without it every fresh profile boots underneath an aria-modal
    // dialog, and a keyboard walk never reaches the composer behind it.
    localStorage.setItem('ephe.intro.seen.v1', '1')
  })
}

/**
 * True when the DEV-only store handle is exposed — i.e. on a Vite dev server, where
 * `src/store/chatStore.ts` assigns `window.__epheStore` under `import.meta.env.DEV`.
 * A production build replaces that flag with `false`, so the static-dist leg (the product
 * bundle) answers false and the dev-seeded specs skip there. Call it *after* the first
 * navigation: on `about:blank` the answer is false on every lane, which is how a guard
 * ahead of the first `goto` turns into a permanent skip.
 */
export async function hasDevHandle(page: Page): Promise<boolean> {
  return page.evaluate(() => '__epheStore' in window)
}

/** Navigates to a hash route (/chat → /#/chat) and waits for the content. */
export async function gotoHash(page: Page, route: string, selector: string) {
  // pass the route without a leading slash: '/chat' → 'http://127.0.0.1:9199/#/chat'
  const hash = `#/${route.replace(/^\//, '')}`
  await page.goto(hash, { waitUntil: 'load' })
  await page.waitForSelector(selector, { timeout: 15000 })
}

/**
 * Open one of the sidebar's two collapsible nav tiers (#71). A row inside a
 * closed tier is still in the document, but a real browser refuses the click —
 * so a spec that targets `sidebar-action-files` or `sidebar-action-automations`
 * opens its tier first. Idempotent: the open/closed state is a stored
 * preference, so a later run in the same profile finds the tier already open.
 */
export async function openSidebarTier(page: Page, tier: 'tools' | 'more') {
  const head = page.getByTestId(`sidebar-tier-${tier}-toggle`)
  if ((await head.count()) === 0) return
  if ((await head.getAttribute('aria-expanded')) !== 'true') {
    await head.click()
    await page.waitForTimeout(150)
  }
}
