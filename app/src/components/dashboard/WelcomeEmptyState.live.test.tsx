/**
 * WelcomeEmptyState — the empty canvas.
 *
 * B2: the engine's state used to float over this canvas as a box. It sits in
 * the top bar now, so this surface asserts the box is gone, that the cards and
 * the hero stay, and that a card click still seeds the one bottom composer.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'

afterEach(() => seedDeepSettings(null))

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'n' in opts ? `${key}:${opts.n}:${opts.name ?? ''}` : key,
  }),
}))

import WelcomeEmptyState from './WelcomeEmptyState'

describe('WelcomeEmptyState', () => {
  it('keeps the canvas free of a floating engine box', () => {
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    expect(screen.queryByTestId('model-status-toast')).toBeNull()
    expect(screen.queryByTestId('model-status-line')).toBeNull()
    expect(screen.getByTestId('welcome-card-0')).toBeTruthy()
    expect(screen.getByTestId('welcome-card-2')).toBeTruthy()
    expect(screen.getByTestId('hero-greeting')).toBeTruthy()
  })

  it('has exactly one input surface: no second composer, chips or send button', () => {
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    expect(screen.queryByTestId('smart-suggestions')).toBeNull()
    expect(screen.queryByTestId('welcome-input')).toBeNull()
    expect(screen.queryByTestId('welcome-send')).toBeNull()
    expect(screen.queryByTestId('welcome-chip-0')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'welcome.send' })).toBeNull()
  })

  it('card click seeds the bottom composer with the card prompt (never auto-sends)', () => {
    const onFillComposer = vi.fn()
    render(<WelcomeEmptyState onFillComposer={onFillComposer} />)
    fireEvent.click(screen.getByTestId('welcome-card-2'))
    expect(onFillComposer).toHaveBeenCalledTimes(1)
    expect(onFillComposer).toHaveBeenCalledWith('welcome.cards.2.prompt')
  })
})
