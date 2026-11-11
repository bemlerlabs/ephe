import { createRequire } from 'node:module'
import { test, expect, type Page } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

/**
 * B6 and B13–B18: the phone widths the audit measured.
 *
 * The audit report (`A11Y-REPORT.md`, 2026-11-11) held 39 targets under 44 px at
 * 1280, 5 at 390 and 5 at 320 in the chat, and the header's palette button at
 * x=336..360 in a 320 px window — fully outside it, because the run bar clips
 * (`overflow: hidden`) instead of wrapping. The fixes hold the 44 px floor on a
 * coarse pointer, keep the palette button inside the viewport as an icon with a
 * name, wrap the settings action row instead of pushing it off the left edge,
 * make the task-list scroller a focusable region, and close the slash menu on
 * Tab instead of swallowing the key.
 *
 * These numbers are measured in the built bundle, not derived from the class
 * list: jsdom computes no box, so the unit contracts hold the tokens and this
 * file holds the rectangles. axe runs here too — the audit's acceptance is zero
 * violations on the three routes at both widths.
 */

const require_ = createRequire(import.meta.url)
const AXE = require_.resolve('axe-core/axe.min.js')
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']

/** Visible controls under the 44 px floor inside `scope`, named for the failure. */
async function underFloor(page: Page, scope: string): Promise<Array<Record<string, unknown>>> {
  return page.evaluate((selector) => {
    const host = document.querySelector(selector)
    if (!host) return [{ missing: selector }]
    const nodes =
      'button,a[href],input:not([type="hidden"]),select,textarea,[role="button"],[role="tab"],[role="menuitem"]'
    const out: Array<Record<string, unknown>> = []
    for (const el of Array.from(host.querySelectorAll(nodes))) {
      const box = el.getBoundingClientRect()
      const css = getComputedStyle(el)
      if (box.width === 0 || box.height === 0 || css.visibility === 'hidden') continue
      if (el.closest('[inert]') || el.closest('[aria-hidden="true"]')) continue
      // The skip links are the sr-only 1 px pair above the content, not thumb targets.
      if (box.width <= 2 && box.height <= 2) continue
      const square = el.tagName === 'BUTTON' && (el.textContent ?? '').trim() === ''
      if (box.height + 0.5 < 44 || (square && box.width + 0.5 < 44)) {
        out.push({
          testid: el.getAttribute('data-testid'),
          label: (el.getAttribute('aria-label') || (el.textContent ?? '').trim()).slice(0, 40),
          tag: el.tagName.toLowerCase(),
          w: Math.round(box.width),
          h: Math.round(box.height),
        })
      }
    }
    return out
  }, scope)
}

async function axeViolations(page: Page): Promise<Array<Record<string, unknown>>> {
  await page.addScriptTag({ path: AXE })
  return page.evaluate(async (tags) => {
    const axe = (
      window as unknown as {
        axe: {
          run: (
            ctx: Document,
            opts: unknown,
          ) => Promise<{ violations: Array<{ id: string; nodes: unknown[] }> }>
        }
      }
    ).axe
    const result = await axe.run(document, {
      runOnly: { type: 'tag', values: tags },
    })
    return result.violations.map((v: { id: string; nodes: unknown[] }) => ({
      id: v.id,
      nodes: v.nodes.length,
    }))
  }, TAGS)
}

for (const width of [320, 390]) {
  test.describe(`B6 at ${width}px`, () => {
    test.use({ viewport: { width, height: 800 }, hasTouch: true, serviceWorkers: 'block' })

    test.beforeEach(async ({ page }) => {
      await ensureOnboarded(page)
    })

    test('the chat header keeps the palette button on screen and every control at 44 px', async ({
      page,
    }) => {
      await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
      await page.waitForTimeout(400)

      const command = await page.getByTestId('workbench-command').boundingBox()
      expect(command, 'the palette button has a box').toBeTruthy()
      expect(command!.x, 'palette starts inside the viewport').toBeGreaterThanOrEqual(0)
      expect(command!.x + command!.width, 'palette ends inside the viewport').toBeLessThanOrEqual(
        width + 1,
      )
      expect(command!.width, 'palette 44 px target').toBeGreaterThanOrEqual(44)
      expect(command!.height, 'palette 44 px target').toBeGreaterThanOrEqual(44)
      await expect(page.getByTestId('workbench-command')).toHaveAttribute('aria-label', /.+/)

      expect(await underFloor(page, 'body')).toEqual([])
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1),
        'no sideways scroll',
      ).toBe(false)
    })

    test('the settings action row stays on the canvas and the nav strip scrolls', async ({
      page,
    }) => {
      await gotoHash(page, '/settings', '[data-testid="settings-page"]')
      await page.waitForTimeout(400)

      const save = await page.getByTestId('settings-image-save').boundingBox()
      expect(save, 'image save has a box').toBeTruthy()
      expect(save!.x, 'action row starts on canvas').toBeGreaterThanOrEqual(0)
      expect(save!.x + save!.width).toBeLessThanOrEqual(width + 1)

      // The register strip is a scroll region by design; the off-screen chips are
      // reachable when it actually scrolls, not clipped by a hidden overflow.
      const strip = await page.evaluate(() => {
        let rail = document.querySelector('[data-testid^="settings-nav-"]') as HTMLElement | null
        while (rail && getComputedStyle(rail).overflowX !== 'auto') rail = rail.parentElement
        return rail ? { scrollWidth: rail.scrollWidth, clientWidth: rail.clientWidth } : null
      })
      expect(strip).not.toBeNull()
      expect(strip!.scrollWidth, 'chips reach past the visible strip').toBeGreaterThan(
        strip!.clientWidth,
      )
      expect(await underFloor(page, '[data-testid="settings-page"]')).toEqual([])
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1),
        'no sideways scroll',
      ).toBe(false)
    })

    test('axe reports no violation on chat and settings', async ({ page }) => {
      for (const route of ['/chat', '/settings']) {
        await gotoHash(
          page,
          route,
          route === '/chat' ? '[data-testid="panel-chat"]' : '[data-testid="settings-page"]',
        )
        await page.waitForTimeout(500)
        expect(await axeViolations(page), `${route} at ${width}px`).toEqual([])
      }
    })
  })
}

test.describe('B16: the task list is a focusable scroll region', () => {
  test.use({ viewport: { width: 320, height: 568 }, hasTouch: true, serviceWorkers: 'block' })

  test('the open drawer exposes the list as a named region with its own tab stop', async ({
    page,
  }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('header-menu-toggle').click()
    const view = page.getByTestId('sessions-view')
    await expect(view).toBeVisible({ timeout: 5000 })
    await expect(view).toHaveAttribute('role', 'region')
    expect(await view.getAttribute('aria-label')).toBeTruthy()
    expect(await view.getAttribute('tabindex')).toBe('0')
  })
})

test.describe('B14: the slash menu lets Tab leave', () => {
  test.use({ viewport: { width: 1280, height: 800 }, serviceWorkers: 'block' })

  test('Tab closes the menu without picking and hands focus to the next control', async ({
    page,
  }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.getByTestId('chat-input').focus()
    await page.keyboard.type('/')
    await expect(page.getByTestId('slash-menu')).toBeVisible()

    await page.keyboard.press('Tab')
    await expect(page.getByTestId('slash-menu')).toBeHidden()
    expect(await page.getByTestId('chat-input').inputValue()).toBe('/')
    const active = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'))
    expect(active).not.toBe('chat-input')
  })
})
