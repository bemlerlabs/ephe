/**
 * FirstRunIntro — the scene runs once, holds three breaths of the mark, and hands the
 * surface behind it over to the viewer.
 *
 * GIVEN a browser that has never stored the install flag
 * WHEN  the scene mounts
 * THEN  every block stands in the DOM at once with the sheet's own delays on them, the
 *       skip control holds the focus, and a key, a pointer or the clock ends the scene
 *       with the flag written.
 * GIVEN a viewer who asked for less motion, or a browser that carries the flag
 * WHEN  the scene mounts
 * THEN  it draws one still, and a browser with the flag sees nothing at all.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import type { DeepSection } from '@/types'
import { seedDeepSettings } from '@/lib/deepSettings'
import { INTRO_SEEN_KEY as BOOT_SEEN_KEY } from '@/lib/firstRun'

const motion = vi.hoisted(() => ({ reduced: false }))
vi.mock('framer-motion', () => ({ useReducedMotion: () => motion.reduced }))

const gate = vi.hoisted(() => ({ configured: null as boolean | null }))
vi.mock('@/lib/setupGate', () => ({
  readSetupGateHint: () =>
    gate.configured === null ? null : { ready: true, configured: gate.configured, skipped: false },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import FirstRunIntro, {
  INTRO_SEEN_KEY,
  CONDENSE_MS,
  WORK_PERIOD_MS,
  DECAY_MS,
  BEAT_MS,
  TITLE_AT_MS,
  LINE_AT_MS,
  CTA_AT_MS,
  SCENE_MS,
  STILL_MS,
} from './FirstRunIntro'

const SHEET = readFileSync('src/styles/globals.css', 'utf8')

/** One motion token from the sheet, in ms. */
function token(name: string): number {
  const match = new RegExp(`--${name}:\\s*(\\d+(?:\\.\\d+)?)(ms|s)\\b`).exec(SHEET)
  if (!match) throw new Error(`--${name} is not declared in globals.css`)
  const value = Number(match[1])
  return match[2] === 's' ? value * 1000 : value
}

function delayOf(el: HTMLElement): number {
  return Number.parseFloat(el.style.animationDelay)
}

beforeEach(() => {
  window.localStorage.clear()
  motion.reduced = false
  gate.configured = null
  vi.useFakeTimers()
})

afterEach(() => {
  seedDeepSettings(null)
  vi.useRealTimers()
})

describe('FirstRunIntro', () => {
  it('deals the whole scene into the DOM on a browser that has never seen it', () => {
    render(<FirstRunIntro />)
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByTestId('intro-spirit')).toBeTruthy()
    expect(screen.getByTestId('intro-skip')).toBeTruthy()
    expect(screen.getByTestId('intro-cta')).toBeTruthy()
    expect(screen.getByText('welcome.introTitle')).toBeTruthy()
    expect(screen.getByText('welcome.introLine')).toBeTruthy()
  })

  it('hangs the sheet delays on the blocks and leaves the skip control undelayed', () => {
    render(<FirstRunIntro />)
    expect(delayOf(screen.getByText('welcome.introTitle'))).toBe(TITLE_AT_MS)
    expect(delayOf(screen.getByText('welcome.introLine'))).toBe(LINE_AT_MS)
    expect(delayOf(screen.getByTestId('intro-cta'))).toBe(CTA_AT_MS)
    expect(screen.getByTestId('intro-skip').style.animationDelay).toBe('')
    expect(delayOf(screen.getByText('welcome.introSkipHint'))).toBe(CTA_AT_MS)
  })

  it('names itself through the nodes that carry the copy', () => {
    render(<FirstRunIntro />)
    const dialog = screen.getByRole('dialog')
    const title = screen.getByText('welcome.introTitle')
    const line = screen.getByText('welcome.introLine')
    expect(dialog.getAttribute('aria-labelledby')).toBe(title.id)
    expect(dialog.getAttribute('aria-describedby')).toBe(line.id)
    expect(dialog.getAttribute('aria-modal')).toBe('true')
  })

  it('takes the focus itself, so the first Tab lands on the way out', () => {
    render(<FirstRunIntro />)
    expect(document.activeElement).toBe(screen.getByRole('dialog'))
    // The dialog holds the focus and paints no ring; the skip control is the first stop.
    expect(document.activeElement).not.toBe(screen.getByTestId('intro-skip'))
  })

  it('keeps Tab inside the scene', () => {
    render(<FirstRunIntro />)
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByTestId('intro-skip'))
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByTestId('intro-cta'))
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByTestId('intro-skip'))
  })

  it('shows nothing on a browser that has been through the scene', () => {
    window.localStorage.setItem(INTRO_SEEN_KEY, '1')
    render(<FirstRunIntro />)
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('gates on the one key the boot gate in main.tsx reads', () => {
    // Two spellings of the flag would let a returning browser fetch a chunk it then
    // declines to render, which is the cost the lazy import exists to avoid.
    expect(INTRO_SEEN_KEY).toBe(BOOT_SEEN_KEY)
    window.localStorage.setItem(BOOT_SEEN_KEY, '1')
    render(<FirstRunIntro />)
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('shows nothing when the store refuses to be read', () => {
    const original = Storage.prototype.getItem
    Storage.prototype.getItem = () => {
      throw new Error('storage refused')
    }
    try {
      render(<FirstRunIntro />)
      expect(screen.queryByTestId('first-run-intro')).toBeNull()
    } finally {
      Storage.prototype.getItem = original
    }
  })

  it('ends on the skip button, writes the flag and plays the decay out', () => {
    const onDone = vi.fn()
    render(<FirstRunIntro onDone={onDone} />)
    act(() => {
      fireEvent.click(screen.getByTestId('intro-skip'))
    })
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem(INTRO_SEEN_KEY)).not.toBeNull()
    // The overlay stays for its own exit motion, then leaves the tree.
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('ends on any key', () => {
    render(<FirstRunIntro />)
    act(() => {
      fireEvent.keyDown(window, { key: 'a' })
    })
    expect(window.localStorage.getItem(INTRO_SEEN_KEY)).not.toBeNull()
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('ends on a pointer anywhere', () => {
    render(<FirstRunIntro />)
    act(() => {
      window.dispatchEvent(new Event('pointerdown'))
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('closes by itself at the end of the clock', () => {
    render(<FirstRunIntro />)
    act(() => {
      vi.advanceTimersByTime(SCENE_MS - 1)
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('running')
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('names the engine choice when the gate has no remembered answer', () => {
    gate.configured = false
    render(<FirstRunIntro />)
    expect(screen.getByText('welcome.introLine')).toBeTruthy()
  })

  it('names the workspace when the gate remembered a chosen engine', () => {
    gate.configured = true
    render(<FirstRunIntro />)
    expect(screen.getByText('welcome.introLineReady')).toBeTruthy()
  })

  it('draws one still for a viewer who asked the system for less motion', () => {
    motion.reduced = true
    render(<FirstRunIntro />)
    const overlay = screen.getByTestId('first-run-intro')
    expect(overlay.dataset.reduced).toBe('true')
    const spirit = screen.getByTestId('intro-spirit')
    expect(spirit.dataset.register).toBe('calm')
    expect(spirit.dataset.state).toBe('rest')
    for (const el of [
      screen.getByText('welcome.introTitle'),
      screen.getByText('welcome.introLine'),
      screen.getByTestId('intro-cta'),
    ]) {
      expect(delayOf(el)).toBe(0)
    }
    act(() => {
      vi.advanceTimersByTime(STILL_MS - 1)
    })
    expect(screen.getByTestId('first-run-intro')).toBeTruthy()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('treats the product animations switch as the same still', () => {
    seedDeepSettings([
      { fields: [{ key: 'appearance.animations_enabled', value: false }] },
    ] as unknown as DeepSection[])
    render(<FirstRunIntro />)
    expect(screen.getByTestId('first-run-intro').dataset.reduced).toBe('true')
  })

  it('keeps the clock on the sheet motion tokens', () => {
    expect(CONDENSE_MS).toBe(token('ephe-mark-condense-duration'))
    expect(WORK_PERIOD_MS).toBe(token('ephe-mark-work-period'))
    expect(DECAY_MS).toBe(token('ephe-decay-duration'))
    expect(BEAT_MS).toBe(token('ephe-scene-beat'))
    // Ten beats carry the arc — two and a half work periods — then the decay closes it.
    expect(SCENE_MS).toBe(BEAT_MS * 10)
    expect(SCENE_MS).toBe(WORK_PERIOD_MS * 2.5)
    expect(SCENE_MS + DECAY_MS).toBeLessThanOrEqual(10_000)
    expect(STILL_MS).toBeLessThan(SCENE_MS)
  })

  it('walks the arc beat by beat and turns the being at the turn', () => {
    render(<FirstRunIntro />)
    const overlay = screen.getByTestId('first-run-intro')
    expect(overlay.dataset.beat).toBe('light')
    expect(screen.getByTestId('intro-spirit').dataset.register).toBe('fierce')
    act(() => {
      vi.advanceTimersByTime(BEAT_MS)
    })
    expect(overlay.dataset.beat).toBe('wall')
    act(() => {
      vi.advanceTimersByTime(BEAT_MS * 3)
    })
    expect(overlay.dataset.beat).toBe('land')
    act(() => {
      vi.advanceTimersByTime(BEAT_MS * 3)
    })
    expect(overlay.dataset.beat).toBe('turn')
    expect(screen.getByTestId('intro-spirit').dataset.register).toBe('calm')
    act(() => {
      vi.advanceTimersByTime(BEAT_MS * 2)
    })
    expect(overlay.dataset.beat).toBe('lead')
  })

  it('stands the ground light on the stage, out of the reading order', () => {
    render(<FirstRunIntro />)
    for (const layer of [
      'ephe-scene-ground',
      'ephe-scene-embers',
      'ephe-scene-core',
      'ephe-scene-flash',
    ]) {
      const node = screen.getByTestId('first-run-intro').querySelector(`.${layer}`)
      expect(node).toBeTruthy()
      expect(node?.getAttribute('aria-hidden')).toBe('true')
    }
  })

  it('keeps the still out of the arc', () => {
    motion.reduced = true
    render(<FirstRunIntro />)
    expect(screen.getByTestId('first-run-intro').dataset.beat).toBe('still')
    act(() => {
      vi.advanceTimersByTime(STILL_MS - 1)
    })
    expect(screen.getByTestId('first-run-intro').dataset.beat).toBe('still')
  })

  it('has the way out on screen inside the opening second', () => {
    // The bounds in the research sit on the wait for interaction, and this is that number:
    // a viewer who wants to act never waits the light out.
    expect(CTA_AT_MS).toBeLessThanOrEqual(1_200)
    expect(CTA_AT_MS).toBeGreaterThan(LINE_AT_MS)
  })
})
