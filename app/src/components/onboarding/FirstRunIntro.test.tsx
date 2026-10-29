/**
 * FirstRunIntro — the four-act Black Forest film.
 *
 * GIVEN a browser that has never stored the install flag
 * WHEN  the film mounts
 * THEN  the stage stands in the DOM, the spark runs its four acts on the clock, the
 *       copy waits for the awakening, and only the skip control, the CTA, Escape,
 *       Enter or Space end it — a click on the stage throws sparks instead.
 * GIVEN a viewer who asked for less motion
 * WHEN  the film mounts
 * THEN  it draws the awakened still and closes after one short hold.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
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
  DECAY_MS,
  TITLE_AT_MS,
  LINE_AT_MS,
  CTA_AT_MS,
  SCENE_MS,
  STILL_MS,
} from './FirstRunIntro'

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
  it('deals the whole film into the DOM on a browser that has never seen it', () => {
    render(<FirstRunIntro />)
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByTestId('intro-film')).toBeTruthy()
    expect(screen.getByTestId('intro-skip')).toBeTruthy()
    expect(screen.getByTestId('intro-cta')).toBeTruthy()
    expect(screen.getByText('welcome.introTitle')).toBeTruthy()
    expect(screen.getByText('welcome.introLine')).toBeTruthy()
  })

  it('hangs the act delays on the copy and leaves the skip control undelayed', () => {
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
    expect(document.activeElement).not.toBe(screen.getByTestId('intro-skip'))
  })

  it('keeps Tab inside the film', () => {
    render(<FirstRunIntro />)
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByTestId('intro-skip'))
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByTestId('intro-cta'))
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByTestId('intro-skip'))
  })

  it('shows nothing on a browser that has been through the film', () => {
    window.localStorage.setItem(INTRO_SEEN_KEY, '1')
    render(<FirstRunIntro />)
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
    expect(INTRO_SEEN_KEY).toBe(BOOT_SEEN_KEY)
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
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it.each(['Escape', 'Enter', ' '])('ends on %s', (key) => {
    render(<FirstRunIntro />)
    act(() => {
      fireEvent.keyDown(window, { key })
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('leaving')
    act(() => {
      vi.advanceTimersByTime(DECAY_MS)
    })
    expect(screen.queryByTestId('first-run-intro')).toBeNull()
  })

  it('does not end on a stray key', () => {
    render(<FirstRunIntro />)
    act(() => {
      fireEvent.keyDown(window, { key: 'a' })
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('running')
  })

  it('turns a click on the stage into sparks, never into an exit', () => {
    render(<FirstRunIntro />)
    act(() => {
      fireEvent.pointerDown(screen.getByTestId('first-run-intro'), { clientX: 120, clientY: 200 })
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('running')
    act(() => {
      vi.advanceTimersByTime(SCENE_MS - 1)
    })
    expect(screen.getByTestId('first-run-intro').dataset.phase).toBe('running')
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

  it('draws the awakened still for a viewer who asked for less motion', () => {
    motion.reduced = true
    render(<FirstRunIntro />)
    const overlay = screen.getByTestId('first-run-intro')
    expect(overlay.dataset.reduced).toBe('true')
    expect(overlay.dataset.act).toBe('awakening')
    expect(screen.getByTestId('intro-still-moth')).toBeTruthy()
    expect(screen.getByText('welcome.introTitle').style.animationDelay).toBe('0ms')
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

  it('keeps the four acts on their clock and turns the being at the vortex', () => {
    render(<FirstRunIntro />)
    const overlay = screen.getByTestId('first-run-intro')
    expect(overlay.dataset.act).toBe('ignition')
    act(() => {
      vi.advanceTimersByTime(2200)
    })
    expect(overlay.dataset.act).toBe('chase')
    act(() => {
      vi.advanceTimersByTime(4400)
    })
    expect(overlay.dataset.act).toBe('vortex')
    act(() => {
      vi.advanceTimersByTime(2800)
    })
    expect(overlay.dataset.act).toBe('awakening')
  })

  it('keeps the copy waiting until the awakening', () => {
    render(<FirstRunIntro />)
    const copy = screen.getByTestId('first-run-intro').querySelector('.intro-copy')
    expect(copy?.className).not.toContain('is-in')
    act(() => {
      vi.advanceTimersByTime(9400)
    })
    expect(screen.getByTestId('first-run-intro').querySelector('.intro-copy')?.className).toContain(
      'is-in',
    )
  })

  it('mounts the live actor with its wing layers and the separate forehead flame', () => {
    render(<FirstRunIntro />)
    const stage = screen.getByTestId('intro-film')
    expect(stage.querySelector('img[src*="paper-moth-actor"]')).toBeTruthy()
    expect(stage.querySelectorAll('img[src*="paper-moth-wing-"]')).toHaveLength(2)
    expect(stage.querySelector('img[src*="paper-moth-thread"]')).toBeTruthy()
    expect(stage.querySelector('.intro-live-spark')).toBeTruthy()
  })

  it('stands the forest stage out of the reading order', () => {
    render(<FirstRunIntro />)
    for (const layer of ['intro-media', 'intro-vignette', 'intro-sparks']) {
      const node = screen.getByTestId('first-run-intro').querySelector(`.${layer}`)
      expect(node, layer).toBeTruthy()
      expect(node?.getAttribute('aria-hidden')).toBe('true')
    }
  })

  it('keeps the still out of the acts', () => {
    motion.reduced = true
    render(<FirstRunIntro />)
    expect(screen.getByTestId('first-run-intro').dataset.act).toBe('awakening')
    act(() => {
      vi.advanceTimersByTime(STILL_MS - 1)
    })
    expect(screen.getByTestId('first-run-intro').dataset.act).toBe('awakening')
  })

  it('places the way in at the awakening, not in the opening second', () => {
    expect(CTA_AT_MS).toBeGreaterThanOrEqual(9000)
    expect(CTA_AT_MS).toBeLessThan(SCENE_MS)
    expect(TITLE_AT_MS).toBeLessThan(LINE_AT_MS)
    expect(LINE_AT_MS).toBeLessThan(CTA_AT_MS)
  })
})
