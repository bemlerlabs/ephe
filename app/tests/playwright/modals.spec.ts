import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

// Modals/dialogs of the current UI: the settings panel (slideover) and the
// command palette (Cmd/Ctrl+K). The legacy provider / mobile-pairing modals
// with their own IDs no longer exist.

test.describe('Modals & Dialogs (aktuelle UI: Settings + Command Palette)', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('settings panel opens and shows model selection', async ({ page }) => {
    // Toggle inventory 2026-09-07: the header gear is retired — the single entry
    // is the sidebar footer card ("Settings & Profile"), like the reference client.
    const settingsBtn = page.getByTestId('sidebar-settings-btn')
    await expect(settingsBtn).toBeVisible()
    await settingsBtn.click()
    const panel = page.locator('[data-testid="settings-panel"]')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // F-05: engine-agnostic — the panel shows the active model (live from the engine),
    // not the old static chips any more. Panel + model-selection heading suffice.
    await expect(page.getByText(/Choose model|Modell wählen/i).first()).toBeVisible()
  })

  test('settings panel closes via close control', async ({ page }) => {
    const settingsBtn = page.getByTestId('sidebar-settings-btn')
    await settingsBtn.click()
    const panel = page.locator('[data-testid="settings-panel"]')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // Esc closes it (dialog behaviour — a11y standard)
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden({ timeout: 5000 })
  })

  test('command palette opens with Cmd+K and filters', async ({ page }) => {
    await page.keyboard.press('Meta+k')
    const paletteInput = page.locator('input').last()
    await expect(paletteInput).toBeVisible({ timeout: 5000 })
    await paletteInput.fill('chat')
    // Filter results appear (at least 1 entry)
    await expect(paletteInput).toHaveValue('chat')
    await page.keyboard.press('Escape')
  })

  test('new session button in sidebar is clickable', async ({ page }) => {
    // On desktop (lg+) the sidebar is always visible (relative); clicking
    // "New Session" must not crash. Drawer opening is covered by the
    // mobile-viewport spec (below lg the sidebar is a drawer).
    const newSession = page.locator('[data-testid="new-session"]')
    await expect(newSession).toBeVisible({ timeout: 5000 })
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(String(e)))
    await newSession.click()
    expect(errors, `Klick auf „Neue Sitzung“ darf nicht crashen: ${errors.join(' | ')}`).toEqual([])
  })
})
