import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Round 12: navigation up to reference-B level — inline title rename,
 * ←/→ session navigation, drag-resize, command-palette actions,
 * branch dropdown, artifact filter.
 */
test.describe('Runde 12 — Navigation & Tiefe', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('Session-Titel: Doppelklick → Edit → Enter speichert', async ({ page }) => {
    if (!(await hasDevHandle(page)))
      test.skip(true, 'needs vite dev server (DEV-only __epheStore handle)')
    await page.evaluate(() => {
      const s = (
        window as unknown as {
          __epheStore: {
            getState: () => { createSession: (t?: string) => void; currentSession: unknown }
          }
        }
      ).__epheStore.getState()
      s.createSession('Alter Titel')
    })
    await page.waitForTimeout(300)
    const title = page.getByTestId('session-title')
    await expect(title).toHaveText('Alter Titel')
    await title.dblclick()
    const input = page.getByTestId('session-title-input')
    await expect(input).toBeVisible()
    await input.fill('Neuer Titel')
    await input.press('Enter')
    await expect(page.getByTestId('session-title')).toHaveText('Neuer Titel')
    // persisted in the store
    const stored = await page.evaluate(() => {
      const s = (
        window as unknown as {
          __epheStore: { getState: () => { currentSession: { title: string } | null } }
        }
      ).__epheStore.getState()
      return s.currentSession?.title ?? ''
    })
    expect(stored).toBe('Neuer Titel')
  })

  test('←/→ Navigation: zwei Sessions, zurück + vorwärts', async ({ page }) => {
    if (!(await hasDevHandle(page)))
      test.skip(true, 'needs vite dev server (DEV-only __epheStore handle)')
    const ids = await page.evaluate(() => {
      // getState() FRESH on every read — snapshots taken after set() go stale
      const store = (
        window as unknown as {
          __epheStore: {
            getState: () => {
              createSession: (t?: string) => void
              setActiveSession: (id: string) => void
              currentSession: { id: string } | null
            }
          }
        }
      ).__epheStore
      store.getState().createSession('Erste')
      const first = store.getState().currentSession!.id
      store.getState().createSession('Zweite')
      const second = store.getState().currentSession!.id
      return { first, second }
    })
    await page.waitForTimeout(300)
    const back = page.getByTestId('session-nav-back')
    const fwd = page.getByTestId('session-nav-forward')
    await expect(back).toBeDisabled() // only one session in the history
    // activate the first session → history: [second, first]
    await page.evaluate((id) => {
      ;(
        window as unknown as {
          __epheStore: { getState: () => { setActiveSession: (id: string) => void } }
        }
      ).__epheStore
        .getState()
        .setActiveSession(id)
    }, ids.first)
    await page.waitForTimeout(200)
    await expect(back).toBeEnabled()
    await expect(fwd).toBeDisabled()
    await back.click() // back → the second session
    await expect(page.getByTestId('session-title')).toHaveText('Zweite')
    await expect(fwd).toBeEnabled()
    await fwd.click() // forward → the first session
    await expect(page.getByTestId('session-title')).toHaveText('Erste')
    await expect(back).toBeEnabled()
  })

  test('Drag-Resize: Panel-Breite per Ziehkante ändern, persistiert', async ({ page }) => {
    await page.evaluate(() => localStorage.setItem('ephe.panel.width', '420'))
    await page.reload()
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // Open the panel via the side-panel toggle in the header (tab choice inside/palette/⌘1–5)
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await expect.poll(async () => (await panel.boundingBox())?.width).toBeLessThan(460)
    // DD-27: let the panel's open bounce animation run out — otherwise the
    // handle box is sampled mid-animation, the mouse-down lands on
    // the stale rect inside the content and the width stays untouched (race).
    let lastW = -1
    for (let i = 0; i < 30; i++) {
      const w = (await panel.boundingBox())?.width ?? -1
      if (w === lastW && w > 0) break
      lastW = w
      await page.waitForTimeout(80)
    }
    const handle = page.getByTestId('panel-resize-handle')
    const box = await handle.boundingBox()
    expect(box).toBeTruthy()
    // drag 150px to the left (right dock → dragging right would narrow it; we drag to widen)
    // Right-Dock (default): the inner edge is the left border — dragging left = wider
    await page.mouse.move(box!.x + box!.width / 2, box!.y + 300)
    await page.mouse.down()
    await page.mouse.move(box!.x + box!.width / 2 - 160, box!.y + 300, { steps: 8 })
    await page.mouse.up()
    await expect.poll(async () => (await panel.boundingBox())?.width).toBeGreaterThan(540)
    await expect
      .poll(() => page.evaluate(() => Number(localStorage.getItem('ephe.panel.width'))))
      .toBeGreaterThan(540)
  })

  test('Command-Palette: „Sidebar ein-/ausklappen"-Aktion klappt die Sidebar um', async ({
    page,
  }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    // The hotkey listener hangs off an effect; without this pause the
    // keypress lands on a surface that is not listening yet.
    await page.waitForTimeout(400)
    await page.keyboard.press('Meta+k')
    const input = page.getByRole('dialog').getByRole('combobox')
    await expect(input).toBeVisible({ timeout: 5000 })
    await input.fill('Sidebar')
    await page
      .getByRole('option', { name: /Sidebar ein-\/ausklappen/ })
      .first()
      .click()
    await expect(sidebar).toHaveAttribute('data-collapsed')
  })

  test('Command-Palette: „Änderungen öffnen" öffnet das Änderungen-Panel', async ({ page }) => {
    // The palette entry was NOT lost — it is commandPalette.items.panel_git, renamed
    // from "Panel: Review" (126ce895) to "Änderungen öffnen" (de) / "Open changes" (en)
    // by 833cb32a ("one thing, one word"). Point the probe at the current label; the
    // tab assertion below already accepts the renamed pill.
    await page.waitForTimeout(400)
    await page.keyboard.press('Meta+k')
    const input = page.getByRole('dialog').getByRole('combobox')
    await expect(input).toBeVisible({ timeout: 5000 })
    await input.fill('Änderungen')
    await page.getByRole('option', { name: 'Änderungen öffnen' }).first().click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // R20 moved the panel tabs to real tab semantics (role=tab + aria-selected).
    await expect(panel.getByRole('tab', { name: /Änderungen|Review|Git/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })
})
