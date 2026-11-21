import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

/**
 * Round 36 / deep-dive DD-27: at exactly 1280px (xl) the right-hand header group
 * measured ~904px against a 960px layout — the telemetry spans lay over the
 * navigation arrows and the title, so clicks landed on the gauges. These pins
 * demand that the hit point under every title/nav centre belongs to the control
 * itself while the gauges really are present.
 */
test.describe('DD-27 — Header-Budget @1280 mit aktiven Gauges', () => {
  test.beforeEach(async ({ page }) => {
    const metricsLive = await page.request
      .get('/api/system/metrics')
      .then((r) => r.ok())
      .catch(() => false)
    test.skip(!metricsLive, 'braucht laufendes Backend (psutil-Metriete fuellen die Gauges)')
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // The gauge group only fills once the backend has delivered its data.
    await expect(page.getByTestId('metrics-gauges')).toBeVisible({ timeout: 20000 })
  })

  test('Titel-Trefferpunkt gehoert dem Titel (kein Gauge-Span davor)', async ({ page }) => {
    const tag = await page.evaluate(() => {
      const t = document.querySelector('[data-testid="session-title"]')!.getBoundingClientRect()
      const el = document.elementFromPoint(t.x + t.width / 2, t.y + t.height / 2)!
      return el.tagName
    })
    expect(tag).toBe('H1')
  })

  test('Navigationspfeil-Trefferpunkte sind frei (keine Telemetrie-Overlay)', async ({ page }) => {
    for (const testid of ['session-nav-back', 'session-nav-forward']) {
      const verdict = await page.evaluate((id) => {
        const b = document.querySelector(`[data-testid="${id}"]`)!.getBoundingClientRect()
        const el = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2)!
        return el.closest('[data-testid="metrics-gauges"]') ? 'GAUGE-OVERLAP' : 'FREE'
      }, testid)
      expect(verdict, testid).toBe('FREE')
    }
  })

  test('Gauges-Gruppe ueberlappt die linke Steuer-Spalte nicht', async ({ page }) => {
    const geom = await page.evaluate(() => {
      const r = (s: string) => document.querySelector(s)!.getBoundingClientRect()
      const title = r('[data-testid="session-title"]')
      const gauges = r('[data-testid="metrics-gauges"]')
      return {
        titleRight: title.right,
        titleLeft: title.left,
        titleTop: title.top,
        titleBottom: title.bottom,
        gaugesLeft: gauges.left,
        gaugesRight: gauges.right,
        gaugesTop: gauges.top,
        gaugesBottom: gauges.bottom,
      }
    })
    // J2: the gauges now live in the status bar (their own row under the header) —
    // overlap only when BOTH axes intersect (the rows are vertically separated).
    const disjoint =
      geom.gaugesLeft >= geom.titleRight ||
      geom.titleLeft >= geom.gaugesRight ||
      geom.gaugesTop >= geom.titleBottom ||
      geom.titleTop >= geom.gaugesBottom
    expect(
      disjoint,
      `title ${geom.titleLeft}..${geom.titleRight} vs gauges ${geom.gaugesLeft}..${geom.gaugesRight}`,
    ).toBe(true)
  })
})
