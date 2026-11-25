import { expect, test, type Page } from '@playwright/test'
import { mkdirSync, existsSync } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { startAppFixture, type AppFixture } from './appFixture'
import { ensureOnboarded } from './helpers'

/**
 * The thinking sign in the running app: the letter that turns into the moth while a
 * turn reasons, and the word that stands beside it.
 *
 * The leg is the fixture in `appFixture.ts` — `dist` on an OS-assigned port with the
 * engine answer injected here on the server clock. No real engine turn runs (app/AGENTS.md);
 * the timings below are values this file sets.
 *
 * Two runs, one page, so the comparison the owner asked for is a measurement and not a
 * claim: the same turn under the operating system's reduced-motion switch must show the
 * same sentence with no motion on it. The word itself is never quoted — the bundles are
 * written elsewhere, and a spec that pins the copy would be a second home for it.
 *
 * The frames land in /tmp and are named by the phase of the cycle they hold. They are
 * evidence for the motion specification in docs/BRAND.md; nothing here writes to docs/.
 */

const FRAMES = '/tmp/brand-eng-thinking-frames'
const THINK_MS = 4200 // the open reasoning phase this turn injects — longer than one cycle
const CYCLE_MS = 3600 // six scene beats, the figure docs/BRAND.md specifies
const FIRST_TOKEN_MS = THINK_MS + 320 // three content chunks, 80 ms apart, after the phase

type StreamEvent = Record<string, unknown>

/** The turn this spec owns: reasoning opens, holds, then the answer arrives. */
function thinkingTurn(req: IncomingMessage, res: ServerResponse): boolean {
  const path = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
  if (path !== '/api/chat/stream') return false
  res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8' })
  const send = (event: StreamEvent) => res.write(`data: ${JSON.stringify(event)}\n\n`)
  const timers: ReturnType<typeof setTimeout>[] = []
  timers.push(setTimeout(() => send({ type: 'thinking_start' }), 120))
  for (const [index, text] of ['The ', 'work is ', 'done.'].entries()) {
    timers.push(setTimeout(() => send({ type: 'chunk', data: text }), FIRST_TOKEN_MS + index * 80))
  }
  timers.push(
    setTimeout(() => {
      send({ type: 'done' })
      res.end()
    }, FIRST_TOKEN_MS + 260),
  )
  req.on('aborted', () => timers.forEach(clearTimeout))
  return true
}

async function sendTurn(page: Page, text: string) {
  const input = page.getByTestId('chat-input')
  await input.fill(text)
  await input.press('Enter')
}

/** Wait until the sign's own clock, read off the running animation, reaches `target`. */
async function waitForCycleTime(page: Page, target: number) {
  await page.waitForFunction(
    (ms) => {
      const stage = document.querySelector('.ephe-think-stage')
      if (!stage) return false
      const [animation] = stage.getAnimations()
      return Number(animation?.currentTime ?? 0) >= ms
    },
    target,
    { timeout: 6000 },
  )
}

let fixture: AppFixture | undefined
let wordWithMotion = ''

test.beforeAll(async () => {
  fixture = await startAppFixture({ kind: 'chat', engineMs: 0, preRoutes: [thinkingTurn] })
})

test.afterAll(async () => {
  await fixture?.close()
  fixture = undefined
})

test.describe('the thinking sign during a run', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(45000) // the turn is paced by the injected leg, not by the surface
    const origin = fixture?.origin
    if (!origin) throw new Error('the app fixture did not start')
    await ensureOnboarded(page)
    // The page is loaded from the fixture's own origin: the chat leg below answers
    // relative requests there, and the shared static server of this lane never sees them.
    await page.goto(`${origin}/#/chat`, { waitUntil: 'load' })
    await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 15000 })
  })

  test('turns while the turn reasons, stands still once it answers', async ({ page }) => {
    if (!existsSync(FRAMES)) mkdirSync(FRAMES, { recursive: true })
    await page.setViewportSize({ width: 1280, height: 860 })

    await sendTurn(page, 'Denke kurz über diese Aufgabe nach.') // language-gate: ignore (product German —
    // the prompt a German session types; app/src/locales/de.json answers it)
    const mark = page.getByTestId('thinking-mark')
    await expect(mark).toBeVisible()

    // The live region: one status line, the sign out of its name, the word in it.
    const status = page.getByTestId('thinking-status')
    await expect(status).toHaveAttribute('role', 'status')
    await expect(status).toHaveAttribute('aria-live', 'polite')
    await expect(mark).toHaveAttribute('aria-hidden', 'true')
    wordWithMotion = ((await status.textContent()) ?? '').trim()
    expect(wordWithMotion.length).toBeGreaterThan(0)

    const motion = await page.evaluate(() => {
      const stage = document.querySelector('.ephe-think-stage')
      const letter = document.querySelector('.ephe-think-frame[data-face="letter"]')
      const moth = document.querySelector('.ephe-think-frame[data-face="moth"]')
      if (!stage || !letter || !moth) return null
      const stageStyle = getComputedStyle(stage)
      const face = (el: Element) => getComputedStyle(el)
      return {
        name: stageStyle.animationName,
        duration: stageStyle.animationDuration,
        iteration: stageStyle.animationIterationCount,
        timing: stageStyle.animationTimingFunction,
        letterBackface: face(letter).backfaceVisibility,
        mothBackface: face(moth).backfaceVisibility,
      }
    })
    expect(motion).not.toBeNull()
    expect(motion?.name).toBe('ephe-think-turn')
    expect(motion?.duration).toBe(`${CYCLE_MS / 1000}s`)
    expect(motion?.iteration).toBe('infinite')
    expect(motion?.timing).toContain('linear')
    expect(motion?.letterBackface).toBe('hidden')
    expect(motion?.mothBackface).toBe('hidden')

    // Five frames across one cycle, each taken at the cycle time that holds it.
    const shots: Array<[string, number]> = [
      ['frame-1-letter', 400],
      ['frame-2-turn-to-moth', 900],
      ['frame-3-moth', 1800],
      ['frame-4-turn-to-letter', 2700],
      ['frame-5-letter', 3400],
    ]
    for (const [name, atMs] of shots) {
      await waitForCycleTime(page, atMs)
      await page.getByTestId('thinking-block').screenshot({ path: `${FRAMES}/${name}.png` })
    }

    // The answer ends the thinking state: the sign is gone with it, the word with it.
    await expect(page.getByTestId('thinking-mark')).toHaveCount(0, { timeout: 8000 })
    await expect(page.getByTestId('thinking-status')).toHaveCount(0)
    await page.screenshot({ path: `${FRAMES}/frame-6-answered.png` })
  })

  test('the same sentence, no motion, under the reduced-motion switch', async ({ page }) => {
    const origin = fixture?.origin
    if (!origin) throw new Error('the app fixture did not start')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await sendTurn(page, 'Und noch einmal, ohne Bewegung.') // language-gate: ignore (product German —
    // the same prompt as the first case; the motion switch is the variable)
    const mark = page.getByTestId('thinking-mark')
    await expect(mark).toBeVisible()

    const still = await page.evaluate(() => {
      const stage = document.querySelector('.ephe-think-stage')
      const letter = document.querySelector('.ephe-think-frame[data-face="letter"]')
      const moth = document.querySelector('.ephe-think-frame[data-face="moth"]')
      if (!stage || !letter || !moth) return null
      return {
        name: getComputedStyle(stage).animationName,
        transform: getComputedStyle(stage).transform,
        letterOpacity: getComputedStyle(letter).opacity,
        mothOpacity: getComputedStyle(moth).opacity,
      }
    })
    expect(still).not.toBeNull()
    expect(still?.name).toBe('none')
    expect(still?.transform).toBe('none')
    expect(still?.letterOpacity).toBe('1')
    expect(still?.mothOpacity).toBe('0')

    // The point of the pair: a run without the motion window says exactly the same.
    const word = ((await page.getByTestId('thinking-status').textContent()) ?? '').trim()
    expect(word).toBe(wordWithMotion)
    await page.getByTestId('thinking-block').screenshot({
      path: `${FRAMES}/frame-7-reduced-motion.png`,
    })
    await expect(page.getByTestId('thinking-mark')).toHaveCount(0, { timeout: 8000 })
  })

  test('the same sentence, no motion, under the product’s own switch', async ({ page }) => {
    const origin = fixture?.origin
    if (!origin) throw new Error('the app fixture did not start')
    await sendTurn(page, 'Und noch einmal, mit ausgeschalteten Animationen.') // language-gate: ignore
    // (product German — the same prompt; the product's own switch is the variable)
    const mark = page.getByTestId('thinking-mark')
    await expect(mark).toBeVisible()

    // The product's own switch: `applyDeepAppearance()` puts `no-motion` on <html> when
    // `appearance.animations_enabled` is off. The class goes on here; the settings panel
    // belongs to another lane's leg, so this spec does not open it.
    await page.evaluate(() => document.documentElement.classList.add('no-motion'))
    // Two frames before reading: `html.no-motion *` gives every element a
    // `transition-property: all` with a 10 µs duration, and a style read in the frame
    // the switch lands still returns the pre-transition value (measured: opacity 1).
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    )
    const still = await page.evaluate(() => {
      const stage = document.querySelector('.ephe-think-stage')
      const letter = document.querySelector('.ephe-think-frame[data-face="letter"]')
      const moth = document.querySelector('.ephe-think-frame[data-face="moth"]')
      if (!stage || !letter || !moth) return null
      return {
        name: getComputedStyle(stage).animationName,
        transform: getComputedStyle(stage).transform,
        letterOpacity: getComputedStyle(letter).opacity,
        mothOpacity: getComputedStyle(moth).opacity,
      }
    })
    expect(still).not.toBeNull()
    expect(still?.name).toBe('none')
    expect(still?.transform).toBe('none')
    expect(still?.letterOpacity).toBe('1')
    expect(still?.mothOpacity).toBe('0')
    expect(((await page.getByTestId('thinking-status').textContent()) ?? '').trim()).toBe(
      wordWithMotion,
    )
    // The sign spends no accent: it asks for the paper tones and the figure's own
    // firefly, never for `--color-brand`. So switching the accent — including `mono`,
    // the one that drops the brand red — cannot recolour it. Resolved paint is compared
    // rather than pixels; a re-shot element screenshot jitters by a pixel at the edge.
    const readPaint = () => {
      const sign = document.querySelector('[data-testid="thinking-mark"]')
      if (!sign) return null
      return Array.from(sign.querySelectorAll('polygon, circle')).map((shape) => {
        const style = getComputedStyle(shape)
        return [style.fill, style.stroke].join(' ')
      })
    }
    const onEmber = await page.evaluate(readPaint)
    await page.getByTestId('thinking-block').screenshot({
      path: `${FRAMES}/frame-8-user-switch.png`,
    })
    await page.evaluate(() => {
      document.documentElement.dataset.accent = 'mono'
    })
    const onMono = await page.evaluate(readPaint)
    await page.getByTestId('thinking-block').screenshot({
      path: `${FRAMES}/frame-9-accent-mono.png`,
    })
    expect(onMono).not.toBeNull()
    expect(onMono).toEqual(onEmber)
    await page.evaluate(() => {
      delete document.documentElement.dataset.accent
    })

    await expect(page.getByTestId('thinking-mark')).toHaveCount(0, { timeout: 8000 })
  })
})
