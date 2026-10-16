/**
 * Ephe — EphemeralWordmark (the brand moment in the empty chat state)
 *
 * GIVEN the brand name with a fading dot trail
 * WHEN the component renders
 * THEN the text stays one contiguous text node (the hero-brand test's
 *      textContent pin still applies), 4 dots of decreasing size are present,
 *      and Reduced Motion halts the animation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const motionState = vi.hoisted(() => ({ reduce: false }))

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => motionState.reduce }
})

import EphemeralWordmark from './EphemeralWordmark'

describe('EphemeralWordmark', () => {
  beforeEach(() => {
    motionState.reduce = false
  })

  it('rendert den Text als einen zusammenhängenden Knoten + 4 dots', () => {
    render(<EphemeralWordmark text="Ephe Agent" />)
    const wm = screen.getByTestId('ephemeral-wordmark')
    expect(wm.textContent).toContain('Ephe Agent')
    for (let i = 0; i < 4; i += 1) {
      expect(screen.getByTestId(`ephemeral-dot-${i}`)).toBeTruthy()
    }
    expect(screen.queryByTestId('ephemeral-dot-4')).toBeNull()
  })

  it('dots klingen in Größe ab (Fading-Motiv)', () => {
    render(<EphemeralWordmark text="Ephe" />)
    const widths = [0, 1, 2, 3].map((i) =>
      Number(
        (screen.getByTestId(`ephemeral-dot-${i}`) as HTMLElement).style.width.replace(/em$/, ''),
      ),
    )
    expect(widths.every((w, i) => i === 0 || w < widths[i - 1]!)).toBe(true)
  })

  it('Reduced Motion pausiert die Atmung (animationPlayState paused)', () => {
    motionState.reduce = true
    render(<EphemeralWordmark text="Ephe" />)
    const dot = screen.getByTestId('ephemeral-dot-0') as HTMLElement
    expect(dot.style.animationPlayState).toBe('paused')
  })

  it('ohne Reduced Motion läuft die Animation (Play-State nicht gesetzt)', () => {
    render(<EphemeralWordmark text="Ephe" />)
    const dot = screen.getByTestId('ephemeral-dot-0') as HTMLElement
    expect(dot.style.animationPlayState).toBe('')
  })
})
