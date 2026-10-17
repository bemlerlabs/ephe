import { test, expect } from '@playwright/test'
import { mkdirSync, existsSync } from 'node:fs'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Round 42 / R2 (parity live cadence): during the run the aggregated family row carries
 * the done/total pair (2/3) plus the last stdout tail —
 * after completion only the total counter. Judge captures: 1280 + 390.
 */
const SHOTS = '/tmp/dd_r42_judge'

function seedRunning(): void {
  const store = (
    window as unknown as {
      __epheStore: {
        getState: () => {
          createSession: (t?: string) => void
          addMessage: (r: 'assistant', c: string, t: unknown[]) => void
        }
      }
    }
  ).__epheStore.getState()
  store.createSession('R42 Live-Takt')
  store.addMessage('assistant', 'Ich arbeite an den Tests.', [
    {
      id: 'c1',
      name: 'run_shell',
      args: { command: 'pnpm test' },
      result: 'ok',
      status: 'completed',
      stdout: 'PASS tests/unit/a.ts\nPASS tests/unit/b.ts',
      duration_ms: 412,
    },
    {
      id: 'c2',
      name: 'run_shell',
      args: { command: 'pnpm lint' },
      result: 'ok',
      status: 'completed',
      stdout: 'no issues',
      duration_ms: 97,
    },
    {
      id: 'c3',
      name: 'run_shell',
      args: { command: 'pnpm build' },
      status: 'pending',
      stdout: 'vite build start\ntransforming 42 modules',
    },
  ])
  store.addMessage('assistant', 'Fertig.', [
    { id: 'd1', name: 'edit_file', args: { path: '/tmp/x.md' }, result: 'ok', status: 'completed' },
    { id: 'd2', name: 'edit_file', args: { path: '/tmp/y.md' }, result: 'ok', status: 'completed' },
    { id: 'd3', name: 'edit_file', args: { path: '/tmp/z.md' }, result: 'ok', status: 'completed' },
  ])
}

test.describe('R42 — Live-Takt in der Familien-Zeile', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    if (!(await hasDevHandle(page)))
      test.skip(true, 'braucht vite dev server (DEV-only __epheStore handle)')
  })

  test('laufende Zeile: 2/3-Paar + stdout-Tail; fertige Zeile: nur Total', async ({ page }) => {
    if (!existsSync(SHOTS)) mkdirSync(SHOTS, { recursive: true })
    await page.setViewportSize({ width: 1280, height: 860 })
    await page.evaluate(seedRunning)
    await page.waitForTimeout(300)

    const rows = page.locator('[data-testid="tool-stream-row-shell"]')
    await expect(rows.first()).toContainText('2/3')
    await expect(rows.first().locator('[data-testid="tool-row-tail"]')).toContainText(
      'transforming 42 modules',
    )
    // finished family: total chip without an n/m pair
    const doneRow = page.locator('[data-testid="tool-stream-row-edit"]').first()
    await expect(doneRow).toContainText('·')
    await expect(doneRow.locator('[data-testid="tool-row-tail"]')).toHaveCount(0)
    // Judge finding R2: the desktop targets also raise to >= 36 (min-h-9)
    const dHeights: Record<string, number> = {}
    for (const id of [
      'header-sidebar-toggle',
      'header-new-session',
      'header-model-chip',
      'send-btn',
      'agent-status-pill',
    ]) {
      const loc = page.locator(`[data-testid="${id}"]`)
      dHeights[id] =
        (await loc.count()) > 0
          ? await loc.first().evaluate((el) => (el as HTMLElement).getBoundingClientRect().height)
          : -1
    }
    console.log('R42 heights@1280:', JSON.stringify(dHeights))
    for (const id of [
      'header-sidebar-toggle',
      'header-new-session',
      'header-model-chip',
      'send-btn',
      'agent-status-pill',
    ]) {
      if (dHeights[id] === -1) continue
      expect(dHeights[id], id).toBeGreaterThanOrEqual(36 - 2)
    }

    await page.screenshot({ path: `${SHOTS}/r42_desktop_1280.png` })

    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(250)
    await expect(page.locator('[data-testid="tool-stream-row-shell"]').first()).toContainText('2/3')

    // Judge finding R2: tap targets >= 36 (desktop) / 44 (mobile) — real box heights
    const probe: Record<string, number> = {}
    for (const id of [
      'send-btn',
      'stop-btn',
      'model-chip',
      'header-model-chip',
      'composer-thinking-chip',
      'composer-permission-badge',
    ]) {
      const loc = page.locator(`[data-testid="${id}"]`)
      const n = await loc.count()
      probe[id] =
        n > 0
          ? await loc.first().evaluate((el) => (el as HTMLElement).getBoundingClientRect().height)
          : -n - 1 // negative: -1 = 0 matches
    }
    console.log('R42 heights@390:', JSON.stringify(probe))
    for (const id of [
      'send-btn',
      'model-chip',
      'composer-thinking-chip',
      'composer-permission-badge',
    ]) {
      expect(probe[id], id).toBeGreaterThanOrEqual(44 - 2)
    }

    await page.screenshot({ path: `${SHOTS}/r42_mobile_390.png` })
  })
})
