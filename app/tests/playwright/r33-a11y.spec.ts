import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

// R33 (closing round): a11y and performance budgets that can be measured, as tests.
// - Keyboard-only walkthrough: tab reach, slash-menu control, Esc.
// - Focus visibility: the globals.css :focus-visible rule has to land on the
//   active input element (outline-none utilities must not beat it).
// - reduced-motion audit: under prefers-reduced-motion: reduce there may be NO
//   running animation at rest (the CSS media rule and
//   framer-motion useReducedMotion together).
// - Frame budget: no pathological rAF loops at rest.
// Purely client-side — runs against dist (playwright.config.ts) like every
// spec here, with no backend dependency.

async function tabUntilTestId(
  page: import('@playwright/test').Page,
  testId: string,
  maxPresses = 40,
) {
  for (let i = 0; i < maxPresses; i += 1) {
    const active = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      return el ? (el.getAttribute('data-testid') ?? el.tagName.toLowerCase()) : 'none'
    })
    if (active === testId) return true
    await page.keyboard.press('Tab')
  }
  const final = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null
    return el ? (el.getAttribute('data-testid') ?? el.tagName.toLowerCase()) : 'none'
  })
  return final === testId
}

test.describe('R33 Keyboard-Only + A11y-Budgets', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
  })

  test('keyboard-only: Tab reaches the chat input without any mouse use', async ({ page }) => {
    // No click, no mouse — the keyboard only in this test.
    // Measured 2026-10-06 in the built dist: stop 44. The way is long (sidebar,
    // header, ten toolbar pills each with their own action button, four welcome
    // cards) and it grows with the number of tasks in the sidebar — that is why
    // the skip link below is the design's answer, not this run's. The budget
    // only records the reach here; the next case checks the shortness.
    const reached = await tabUntilTestId(page, 'chat-input', 60)
    expect(reached).toBe(true)
  })

  test('keyboard-only: the skip link lands the caret in the chat input', async ({ page }) => {
    // R33: without the skip link the input sits behind ~30 tab stops — a real
    // finding for keyboard users. One Tab plus Enter has to be enough.
    await page.keyboard.press('Tab') // first stop = skip link (sr-only, visible on focus)
    await page.keyboard.press('Enter')
    const active = await page.evaluate(() =>
      (document.activeElement as HTMLElement | null)?.getAttribute('data-testid'),
    )
    expect(active).toBe('chat-input')
  })

  test('keyboard-only: slash menu arrows walk the highlight, Enter picks it', async ({ page }) => {
    await page.keyboard.press('Tab')
    await page.keyboard.press('Enter') // skip link → chat input
    await page.keyboard.press('/')
    const menu = page.locator('[data-testid="slash-menu"]')
    await expect(menu).toBeVisible({ timeout: 3000 })
    await expect(page.locator('[data-testid="slash-menu-scroll"]')).toBeVisible()
    // R33: exactly one row is highlighted (aria-selected); ArrowDown moves it.
    const sel = page.locator('[data-testid="slash-menu"] [role="option"][aria-selected="true"]')
    await expect(sel).toHaveCount(1)
    const firstId = await sel.first().getAttribute('id')
    await page.keyboard.press('ArrowDown')
    const secondId = await sel.first().getAttribute('id')
    expect(secondId).not.toBe(firstId)
    // Enter takes the highlighted row into the input.
    await page.keyboard.press('Enter')
    const value = await page.locator('[data-testid="chat-input"]').inputValue()
    expect(value.startsWith('/')).toBe(true)
  })

  test('keyboard-only: Escape dismisses the slash menu, focus stays on the input', async ({
    page,
  }) => {
    await page.keyboard.press('Tab')
    await page.keyboard.press('Enter') // skip link → chat input
    await page.keyboard.press('/')
    const menu = page.locator('[data-testid="slash-menu"]')
    await expect(menu).toBeVisible({ timeout: 3000 })
    await page.keyboard.press('Escape')
    await expect(menu).toBeHidden({ timeout: 3000 })
    // After Esc the input keeps focus (no focus loss).
    const active = await page.evaluate(() =>
      (document.activeElement as HTMLElement | null)?.getAttribute('data-testid'),
    )
    expect(active).toBe('chat-input')
  })

  test('focus visibility: keyboard focus paints a real outline on the input', async ({ page }) => {
    await page.keyboard.press('Tab')
    await page.keyboard.press('Enter') // skip link → chat input (keyboard-only path)
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement
      const cs = getComputedStyle(el)
      return { style: cs.outlineStyle, width: cs.outlineWidth }
    })
    // the globals.css :focus-visible rule has to hold against outline-none.
    expect(outline.style).not.toBe('none')
    expect(parseFloat(outline.width)).toBeGreaterThanOrEqual(2)
  })

  test('reduced-motion audit: no running animations at rest under reduce', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForTimeout(800) // settling time + wait out the last CSS transitions
    // by default getAnimations covers the whole document subtree.
    const running = await page.evaluate(
      () => document.getAnimations().filter((a) => a.playState === 'running').length,
    )
    expect(running).toBe(0)
  })

  test('loop inventory: the loops at rest, as a number, in both motion states', async ({
    page,
  }) => {
    // R4 wave 2 (docs/UI_4X_PROGRAM_2026-10-11.md §6) prices the motion budget against this
    // count, so it is read here in the a11y lane as well: the loop rules the stylesheet
    // declares, the instances running at rest, and what `reduce` leaves. The removal is a
    // design call that needs the number first; nothing in this test quiets a loop.
    const inventory = () =>
      page.evaluate(() => {
        const declared = (list: CSSRuleList): number =>
          Array.from(list).reduce<number>((total, rule) => {
            if (rule instanceof CSSKeyframesRule) return total
            const style = (rule as CSSStyleRule).style
            if (!style) {
              const nested = (rule as CSSGroupingRule).cssRules
              return nested ? total + declared(nested) : total
            }
            // WebKit exposes no unprefixed animation longhand on a declared rule, so both
            // spellings and the shorthand are read.
            const spelled = [
              style.getPropertyValue('animation-iteration-count'),
              style.getPropertyValue('-webkit-animation-iteration-count'),
              style.getPropertyValue('animation'),
              style.getPropertyValue('-webkit-animation'),
            ]
            return total + (spelled.some((value) => (value ?? '').includes('infinite')) ? 1 : 0)
          }, 0)

        let declaredInfinite = 0
        for (const sheet of Array.from(document.styleSheets)) {
          let rules: CSSRuleList
          try {
            rules = sheet.cssRules
          } catch {
            continue // a cross-origin sheet hands out no rules to read
          }
          declaredInfinite += declared(rules)
        }

        const running = document
          .getAnimations()
          .filter((animation) => animation.playState === 'running')
        const infinite = running.filter(
          (animation) => animation.effect?.getComputedTiming().iterations === Infinity,
        )
        const perRule: Record<string, number> = {}
        for (const animation of infinite) {
          const name =
            (animation as Animation & { animationName?: string }).animationName ?? 'unnamed'
          perRule[name] = (perRule[name] ?? 0) + 1
        }
        return {
          declaredInfinite,
          running: running.length,
          runningInfinite: infinite.length,
          perRule,
        }
      })

    const atRest = await inventory()
    console.log(
      `r33 loops state=no-preference declared=${atRest.declaredInfinite} ` +
        `running=${atRest.running} runningInfinite=${atRest.runningInfinite} ` +
        `perRule=${JSON.stringify(atRest.perRule)}`,
    )

    // QD-014 B3 removed the brand's breathing dots, so the surface ships no loop at
    // rest. The instrument still has to see one: a synthetic loop the page never
    // shipped is injected, counted and taken out again while the media is still
    // no-preference, which keeps the zero below a measurement.
    const probeSeen = await page.evaluate(() => {
      const style = document.createElement('style')
      style.textContent =
        '@keyframes r33-probe{from{opacity:0}to{opacity:1}}.r33-probe{animation:r33-probe 1s infinite}'
      document.head.appendChild(style)
      const el = document.createElement('div')
      el.className = 'r33-probe'
      el.setAttribute('aria-hidden', 'true')
      document.body.appendChild(el)
      const seen = document
        .getAnimations()
        .some(
          (animation) =>
            animation.playState === 'running' &&
            animation.effect?.getComputedTiming().iterations === Infinity,
        )
      el.remove()
      style.remove()
      return seen
    })
    expect(probeSeen).toBe(true)

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForTimeout(800)
    const reduced = await inventory()
    console.log(
      `r33 loops state=reduce declared=${reduced.declaredInfinite} ` +
        `running=${reduced.running} runningInfinite=${reduced.runningInfinite}`,
    )

    // The switch is allowed to leave the declarations in the stylesheet — it has to leave
    // nothing running.
    expect(reduced.declaredInfinite).toBeGreaterThan(0)
    expect(reduced.runningInfinite).toBe(0)
    expect(atRest.runningInfinite).toBe(0)
  })

  test('frame budget: no pathological rAF loops while idle on /chat', async ({ page }) => {
    // The same 1.5 s window twice: on a page with no app in it, then on /chat with the
    // entrance settled. A shared runner stalls on both, so the first window is the host's
    // own noise and the second may carry that much again — a budget that cannot tell the
    // host from the product is a coin toss. Measured 2026-10-16 on a two-core shared
    // runner: four, next to the three this budget was written with.
    //
    // The absolute line stays, because a loop that pins the thread does not count four: at
    // 60 Hz a 60 ms frame yields ~25 of these inside the window.
    const longFrames = (): Promise<number> =>
      page.evaluate(async () => {
        return await new Promise<number>((resolve) => {
          let last = performance.now()
          let long = 0
          const deadline = last + 1500
          const tick = (t: number) => {
            if (t - last > 50) long += 1 // > 3 frames missed at 60 Hz
            last = t
            if (t >= deadline) resolve(long)
            else requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        })
      })

    await page.goto('about:blank')
    const control = await longFrames()
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    await page.waitForTimeout(600)
    const chat = await longFrames()
    console.log(`r33 frame budget control=${control} chat=${chat}`)
    expect(chat).toBeLessThanOrEqual(control + 5)
    expect(chat).toBeLessThanOrEqual(15)
  })
})
