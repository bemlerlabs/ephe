import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash, hasDevHandle, openSidebarTier } from './helpers'

// Round 9: regression for the round 5/7 features — reference-B toggle panel,
// dock left/right, ⌘1–5 shortcuts, frost-pulse classes.
test.describe('Agent-Panel Toggles & Dock (Runde 5/7)', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('side-panel-toggle: ein Knopf offnet und schliesst das Panel (Referenz-B-Muster toggleSidePane)', async ({
    page,
  }) => {
    const toggle = page.getByTestId('side-panel-toggle')
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await toggle.click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await toggle.click()
    await expect(panel).toBeHidden({ timeout: 5000 })
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  })

  test('Tab-Wahl liegt in der Panel-Tab-Bar (der Header-Cluster ist entfent)', async ({ page }) => {
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // Rounds-G: multi-tab — new pages through the tab bar's +-menu (reference pattern).
    await panel.getByTestId('panel-add-tab').click()
    await panel.getByTestId('panel-new-tab-item-terminal').click()
    await expect(panel.getByRole('tab', { name: /Terminals?/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    // The former 5-button header cluster no longer exists — exactly ONE header toggle.
    await expect(page.getByRole('group', { name: 'Agent-Panel-Toggles' })).toHaveCount(0)
  })

  test('Leerzustand mit Offnen-Karten, +-Menue mit Zuletzt geschlossen (Referenz-Paritaet)', async ({
    page,
  }) => {
    await page.evaluate(() => localStorage.setItem('ephe.panel.tabs', '[]'))
    await page.reload()
    await page.waitForSelector('[data-testid="panel-chat"]')
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    // All-closed state: a large card grid for opening (like the reference).
    await expect(panel.getByTestId('panel-empty-state')).toBeVisible()
    await expect(panel.getByTestId('panel-tab-card-terminal')).toBeVisible()
    await panel.getByTestId('panel-tab-card-terminal').click()
    await expect(panel.getByRole('tab', { name: /Terminals?/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    // Closing the last pill returns to the card empty state.
    await panel.getByTestId('panel-tab-close-terminal').click()
    await expect(panel.getByTestId('panel-empty-state')).toBeVisible()
    // +-menu: the recently-closed entry restores the tab.
    await panel.getByTestId('panel-add-tab').click()
    await expect(panel.getByTestId('panel-recent-terminal')).toBeVisible()
    await panel.getByTestId('panel-recent-terminal').click()
    await expect(panel.getByRole('tab', { name: /Terminals?/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('dock switch: Panel wechselt die Seite (persistiert)', async ({ page }) => {
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await panel.getByRole('button', { name: 'Seite wechseln (links/rechts)' }).click()
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('ephe.panel.dock')))
      .toBe('left')
  })

  test('⌘3 öffnet das Review-Panel per Shortcut', async ({ page }) => {
    await page.keyboard.press('Meta+3')
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await expect(panel.getByRole('tab', { name: /Änderungen|Review|Git/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('offenes Panel verdraengt die Chat-Saeule — Senden bleibt moeglich (Judge page-5 Befund)', async ({
    page,
  }) => {
    // Reference pattern: the side pane and the content column are a split, not an
    // overlay — the composer (send button, model chips) must stay fully reachable
    // left of the panel edge while the panel is open.
    await page.getByTestId('side-panel-toggle').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    const send = page.getByRole('button', { name: /Senden|^Send$/i }).first()
    await expect(send).toBeVisible()
    const row = page.getByTestId('composer-actions-row')
    await expect
      .poll(
        async () => {
          const s = await send.boundingBox()
          const p = await panel.boundingBox()
          const r = await row.boundingBox()
          // The send button must sit inside the action row (no overflow toward the
          // panel) AND stay reachable left of the panel edge.
          return (
            s !== null &&
            p !== null &&
            r !== null &&
            s.x + s.width <= p.x + 2 &&
            s.x + s.width <= r.x + r.width + 1
          )
        },
        { timeout: 5000 },
      )
      .toBe(true)
    // Real operability: type and send, the user bubble appears.
    // Only when a backend is reachable (the static dist suite has none).
    const hasApi = await page.request
      .get('/api/health')
      .then((r) => r.ok())
      .catch(() => false)
    test.skip(!hasApi, 'Senden braucht ein Backend (statische Dist-Suite hat keins)')
    await page.getByTestId('chat-input').fill('split-check')
    await page
      .getByRole('button', { name: /Senden|^Send$/i })
      .first()
      .click()
    await expect(
      page.getByTestId('message-bubble').filter({ hasText: 'split-check' }).first(),
    ).toBeVisible({ timeout: 10000 })
  })
})

// Round 10: session sidebar collapse/expand — topbar toggle (reference-B parity)
// AND the expand button in the rail (regression: it was clipped in the w-14 rail).
test.describe('Session-Sidebar Toggle (Runde 10)', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('Topbar-Toggle: zuklappen -> data-collapsed, aufklappen -> weg', async ({ page }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    const toggle = page.getByTestId('header-sidebar-toggle')
    await expect(toggle).toBeVisible()
    await expect(sidebar).not.toHaveAttribute('data-collapsed')
    await toggle.click()
    await expect(sidebar).toHaveAttribute('data-collapsed')
    // the sidebar really is narrow (w-14 = 56px)
    await expect.poll(async () => (await sidebar.boundingBox())?.width).toBeLessThan(70)
    await toggle.click()
    await expect(sidebar).not.toHaveAttribute('data-collapsed')
    await expect.poll(async () => (await sidebar.boundingBox())?.width).toBeGreaterThan(200)
  })

  test('Expand-Button im Rail: zugeklappt wieder aufklappbar (User-Bug)', async ({ page }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    await page.getByTestId('header-sidebar-toggle').click()
    await expect(sidebar).toHaveAttribute('data-collapsed')
    // The button must be visible AND clickable (no clipping through overflow-hidden)
    const expand = sidebar.getByRole('button', { name: 'Sidebar ausklappen' })
    await expect(expand).toBeVisible()
    await expand.click()
    await expect(sidebar).not.toHaveAttribute('data-collapsed')
  })

  test('⌘B klappt die Sidebar um', async ({ page }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    await page.keyboard.press('Meta+b')
    await expect(sidebar).toHaveAttribute('data-collapsed')
    await page.keyboard.press('Meta+b')
    await expect(sidebar).not.toHaveAttribute('data-collapsed')
  })

  test('Mobile: persistiertes collapsed=1 bricht den Drawer nicht (X-Close bleibt)', async ({
    page,
  }) => {
    // Desktop state "inherited" in localStorage (same browser), then the mobile viewport
    await page.addInitScript(() => localStorage.setItem('ephe-sidebar-collapsed', '1'))
    await page.setViewportSize({ width: 390, height: 844 })
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    const sidebar = page.getByTestId('chat-sidebar')
    await expect(sidebar).not.toHaveAttribute('data-collapsed')
    // Drawer closed, then open it via the burger and close it via the X
    await page.getByRole('button', { name: 'Menü umschalten' }).click()
    await expect(sidebar.getByRole('button', { name: 'Schließen' })).toBeVisible()
    await sidebar.getByRole('button', { name: 'Schließen' }).click()
    // The drawer slides out with a spring (x=-320) instead of unmounting —
    // so check the backdrop gone + the transform, rather than toBeVisible().
    await expect(page.getByTestId('sidebar-backdrop')).toHaveCount(0)
    await expect
      .poll(() => sidebar.evaluate((el) => getComputedStyle(el).transform))
      .toContain('-320')
  })
})

test.describe('Sidebar Aktionszeilen (Runden-G3, Referenz-Paritaet)', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('Aktionszeilen sichtbar und bedienbar: neu, Helfer, Dateien, Automatisierungen', async ({
    page,
  }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    // R5: the rows are named the way the surface names them — "new/search" existed
    // once; today Neu (new-session) and Suchen live separately from it. // language-gate: ignore — "Neu"/"Suchen" are the German row labels the sidebar renders (locales/de.json:243 newChat, :285 actionSearch)
    await expect(sidebar.getByTestId('new-session')).toBeVisible()

    // #71: the rail is three tiers now. The primary one has no head and is always
    // open; the other two start closed, and a closed tier's rows are hidden (they
    // keep their place in the document). This spec walks the same way a person
    // does: read the two heads, open a tier, then click inside it.
    await expect(sidebar.getByTestId('sidebar-tier-tools-toggle')).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    await expect(sidebar.getByTestId('sidebar-tier-more-toggle')).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    for (const row of ['sidebar-action-files', 'sidebar-action-automations']) {
      await expect(sidebar.getByTestId(row)).toBeHidden()
    }

    await openSidebarTier(page, 'tools')
    await openSidebarTier(page, 'more')
    for (const row of [
      'sidebar-action-skills',
      'sidebar-action-helpers',
      'sidebar-action-files',
      'sidebar-action-automations',
    ]) {
      await expect(sidebar.getByTestId(row)).toBeVisible()
    }
    // The automations row opens settings on its cron group.
    await sidebar.getByTestId('sidebar-action-automations').click()
    await expect(
      page
        .getByRole('dialog')
        .getByText(/Automatis|Cron/)
        .first(),
    ).toBeVisible({ timeout: 5000 })
    await page.keyboard.press('Escape')
    // The helpers row pulls the pane open.
    await sidebar.getByTestId('sidebar-action-helpers').click()
    const panel = page.getByRole('tabpanel')
    await expect(panel).toBeVisible({ timeout: 5000 })
    await expect(panel.getByRole('tab', { name: /Helfer/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  // The comparison needs the dev server's store handle — the built dist does not
  // have it. Skip with a reason instead of a wrong verdict.
  test('⌘N (Tastatur) erzeugt eine neue Aufgabe wie die Sidebar-Zeile', async ({ page }) => {
    test.skip(!(await hasDevHandle(page)), 'benötigt __epheStore (nur Dev-Server)')
    const before = await page.evaluate(() => window.__epheStore?.getState().sessions.length ?? -1)
    await page.keyboard.press('Meta+n')
    await expect
      .poll(async () => page.evaluate(() => window.__epheStore?.getState().sessions.length ?? -1))
      .toBe(before + 1)
  })

  test('Group/Project-Umschalter persistiert die Ansicht', async ({ page }) => {
    const sidebar = page.getByTestId('chat-sidebar')
    const toggle = sidebar.getByTestId('sidebar-view-toggle')
    await expect(toggle).toBeVisible()
    await toggle.locator('button[aria-pressed="false"]').click()
    await expect(sidebar.getByTestId('sidebar-view-project-active')).toBeVisible()
    await page.reload()
    await page.waitForSelector('[data-testid="panel-chat"]')
    await expect(
      page.getByTestId('chat-sidebar').getByTestId('sidebar-view-project-active'),
    ).toBeVisible()
    // back to Group for the following specs
    await page
      .getByTestId('chat-sidebar')
      .getByTestId('sidebar-view-toggle')
      .locator('button[aria-pressed="false"]')
      .click()
  })
})

test.describe('Agent-Status-Pille (H3, Referenz-Paritaet)', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('Pille oben rechts, Popover oeffnet die Schritte-Seite (Durchklick)', async ({ page }) => {
    const pill = page.getByTestId('agent-status-pill')
    await expect(pill).toBeVisible()
    await pill.click()
    const popover = page.getByTestId('agent-status-popover')
    await expect(popover).toBeVisible()
    // w2-timeline retired the pane's Schritte tab and moved the surface onto the
    // register, so the row now sends the pair the settings rows have used since G3 —
    // `ephe:open-settings` plus `ephe:settings-tab` with `tasks` (AgentStatusButton's
    // openStepsPage). The Durchklick therefore has to land on the steps page, not in
    // the pane.
    await page.getByTestId('agent-status-tasks-link').click()
    await expect(page.getByTestId('settings-page')).toBeVisible({ timeout: 5000 })
    // The landing is the steps page, not merely "a register opened": the content
    // column is named by the active tab, in the product's own i18n value — "Schritte"
    // (de) / "Steps" (en) since the rename round renamed the task list, and
    // ensureOnboarded pins de for this lane.
    await expect(page.getByTestId('settings-panel')).toHaveAttribute('aria-label', 'Schritte')
    // ...and the steps surface itself rendered — its own groups and count pill, which
    // no tab-agnostic assertion would prove.
    await expect(page.getByTestId('tasks-group-new')).toBeVisible()
    await expect(page.getByTestId('tasks-group-list')).toBeVisible()
    await expect(page.getByTestId('task-count-pill')).toBeVisible()
    // The register is this row's only surface now: it must not pull the pane's retired
    // steps tab back as a side effect (no role=tabpanel in the document at all).
    await expect(page.getByRole('tabpanel')).toHaveCount(0)
    // The popover is closed after the jump
    await expect(popover).toBeHidden()
  })
})
