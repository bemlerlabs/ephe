import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Round 14: implementing the UX-review findings — each spec verifies one
 * finding from docs/UX_ROLES_REVIEW_2026-09-05.md.
 */
test.describe('Runde 14 — Findings-Umsetzung', () => {
  test('F3: Frischer Browser ohne Sprachwahl = ENGLISCH (Default)', async ({ page }) => {
    // Both navigations go through the lane's own baseURL. They used to name
    // localhost:5173 in code, which is why this file was on the port-hygiene register
    // (a spec bound to an origin its leg does not start) and why a guard stood ahead of
    // the first line — no dev-store handle is needed here, only the app the lane serves.
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.goto('/#/chat')
    await page.waitForTimeout(1500)
    // The language anchor is the sidebar's new-task button. The labels it carried when
    // this test was written — "New Session" / "Neue Sitzung" — no longer exist anywhere in
    // the app: the surface is `nav.newChat`, "New task" (en) / "Neue Aufgabe" (de)
    // (measured 2026-10-14: with cleared storage the button reads "New task⌘N", with
    // i18nextLng=de "Neue Aufgabe⌘N"). The subject of the test — the default language — is
    // unchanged; only the name it looked for was.
    await expect(page.getByTestId('new-session')).toContainText('New task')
    await expect(page.getByText('Neue Aufgabe')).toHaveCount(0)
    // DE stays selectable: set the detector key → German (persisted)
    await page.evaluate(() => localStorage.setItem('i18nextLng', 'de'))
    await page.reload()
    await page.waitForTimeout(1200)
    await expect(page.getByTestId('new-session')).toContainText('Neue Aufgabe')
  })

  test('F8: Skip-Link-Ziel existiert (<main id="main-content">)', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    const exists = await page.evaluate(() => !!document.querySelector('main#main-content'))
    expect(exists).toBe(true)
    const landmark = await page.evaluate(
      () => document.querySelector('main')?.getAttribute('aria-label') ?? 'main',
    )
    expect(landmark).toBeTruthy()
  })

  test('F9: ⌘/ öffnet das Shortcut-Cheatsheet, ESC schließt', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // The trigger is no longer bare "?" — the central shortcut table (lib/shortcuts.ts,
    // id "thisOverlay") and its handler (chat/model.ts:363) bind meta/ctrl + "/".
    // Same overlay, new keys; the assertions below are unchanged.
    await page.keyboard.press('Meta+Slash')
    await expect(page.getByTestId('shortcuts-overlay')).toBeVisible()
    await expect(page.getByText(/Command palette|Befehlspalette/)).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('shortcuts-overlay')).toHaveCount(0)
  })

  test('F2: Prose-Typografie — h2 hebt sich vom Fließtext ab', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // The seed below goes through the DEV-only store handle (chatStore.ts under
    // `import.meta.env.DEV`): ask once the app page is loaded, not on about:blank.
    if (!(await hasDevHandle(page)))
      test.skip(true, 'needs vite dev server (DEV-only __epheStore handle)')
    await page.evaluate(() => {
      const store = (
        window as unknown as {
          __epheStore: {
            getState: () => {
              createSession: (t?: string) => void
              addMessage: (r: 'assistant', c: string) => void
            }
          }
        }
      ).__epheStore
      store.getState().createSession('Typo-Check')
      store.getState().addMessage('assistant', '## Überschrift Zwei\n\nFließtext zum Vergleich.')
    })
    await page.waitForTimeout(500)
    const styles = await page.evaluate(() => {
      const scope = document.querySelector('[data-testid="panel-chat"]')!
      const headings = scope.querySelectorAll('h2')
      const h2 = headings[headings.length - 1] ?? scope.querySelector('h2') // not first-child (mt:0 by design)
      const p = scope.querySelector('p')
      if (!h2 || !p) return null
      const h = getComputedStyle(h2)
      const pp = getComputedStyle(p)
      return {
        h2fs: parseFloat(h.fontSize),
        pfs: parseFloat(pp.fontSize),
        h2fw: parseInt(h.fontWeight),
      }
    })
    expect(styles).toBeTruthy()
    expect(styles!.h2fs).toBeGreaterThan(styles!.pfs)
    expect(styles!.h2fw).toBeGreaterThanOrEqual(600)
  })

  test('F6+F15: Bild-Paste-Handler vorhanden, "@" öffnet Datei-Mentions', async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.waitForTimeout(800)
    // File mentions resolve against the backend workspace API — without a
    // live backend (static dist serve) the popup can never list entries.
    const backendUp = await page.evaluate(() =>
      fetch('/api/health')
        .then((r) => r.ok)
        .catch(() => false),
    )
    if (!backendUp) test.skip(true, 'needs live backend for /api/fs workspace listing')
    // By test id: neither half of the old `/Write a message|Schreibe eine Nachricht/` // language-gate: ignore — quotes the removed copy probe verbatim, that is the evidence here
    // probe exists in any bundle — the composer says "What can I do for you?" and
    // "Womit kann ich dir helfen?" — so this step could only pass against an old build. // language-gate: ignore — quotes the composer copy that replaced the old probe (chat.placeholder, de.json:16 / en.json:16)
    const ta = page.getByTestId('chat-input')
    await ta.click()
    await ta.pressSequentially('@', { delay: 50 })
    await page.waitForTimeout(800)
    // Mention popup: the backend serves the workspace entries (ephe repo)
    const popup = page.getByTestId('mention-popup')
    await expect(popup).toBeVisible({ timeout: 5000 })
    const items = await popup.getByRole('button').count()
    expect(items).toBeGreaterThan(0)
    // Selecting one inserts the path
    await popup.getByRole('button').first().click()
    await page.waitForTimeout(200)
    const value = await ta.inputValue()
    expect(value.length).toBeGreaterThan(1)
    expect(value).not.toBe('@')
  })

  test('F11: Settings-Toggle schreibt ephe.bgAnimated + Event erreicht Canvas', async ({
    page,
  }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.evaluate(() => {
      const btn = document.querySelector(
        '[aria-label*="Settings"], [aria-label*="Einstellungen"]',
      ) as HTMLElement | null
      btn?.click()
    })
    await page.waitForTimeout(600)
    // Open the privacy tab and find the toggle
    const privacy = page.getByRole('button', { name: /Privacy|Datenschutz/i })
    if (await privacy.isVisible().catch(() => false)) {
      await privacy.click()
      await page.waitForTimeout(400)
    }
    // The surface this finding asked for is gone from the product: no
    // `bg-animated-toggle` testid exists anywhere under app/src, and no
    // `ephe.bgAnimated` writer remains (grep -rn bgAnimated app/src → 0 hits; the
    // privacy tab's rows are profile / sandbox / clear-local-data today). Skip with
    // that reason — the old else-branch wrote the key itself and asserted its own
    // write, which is a pass that proves nothing.
    const toggle = page.getByTestId('bg-animated-toggle')
    test.skip(
      (await toggle.count()) === 0,
      'F11 surface removed from the product (no bg-animated-toggle / ephe.bgAnimated writer in app/src)',
    )
    await expect(toggle).toBeVisible()
    await toggle.click()
    await expect.poll(() => page.evaluate(() => localStorage.getItem('ephe.bgAnimated'))).toBe('0')
    await toggle.click()
    await expect.poll(() => page.evaluate(() => localStorage.getItem('ephe.bgAnimated'))).toBe('1')
  })

  test('F13: prefers-reduced-motion — Welcome-Cards ohne Bewegung', async ({ page }) => {
    // BaseURL-relative like F3: the reduced-motion contract is about the app the lane
    // serves, not about a dev server, and the port-hygiene register no longer carries
    // this file for naming :5173.
    //
    // The metric is the one the design's own switch-off demands. globals.css books every
    // entrance onto its END STATE with `animation-duration: 0.01ms` + `fill-mode: both`
    // (its reduced-motion comment: "condense/dissolve become hard cuts, the mark stays, the
    // motion goes"), and an element parked that way still reports
    // `animationPlayState: running` — measured 2026-10-14 on the welcome hero, whose brand
    // mark keeps six loops "running" at 1e-05s (ephe-condense + 5× ephe-mark-part). So
    // counting the running state reads 6 for motion that is not there; what the contract
    // promises is that nothing is left with a material duration. An element that escaped
    // the switch-off — a 220 ms loop, the mark's own default — is what this catches.
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.addInitScript(() => localStorage.clear())
    await page.goto('/#/chat')
    await page.waitForTimeout(1200)
    const moving = await page.evaluate(() =>
      [...document.querySelectorAll('*')]
        .filter((el) => {
          const cs = getComputedStyle(el)
          return cs.animationName !== 'none' && parseFloat(cs.animationDuration) > 0.05
        })
        .map((el) => {
          const cs = getComputedStyle(el)
          const who = el.getAttribute('data-testid') ?? el.getAttribute('class') ?? el.tagName
          return `${cs.animationName}@${cs.animationDuration} (${who})`
        }),
    )
    expect(moving, `still animating under reduce: ${moving.join(', ')}`).toHaveLength(0)
  })
})
