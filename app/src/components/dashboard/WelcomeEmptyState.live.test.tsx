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
import type { DeepSection } from '@/types'

afterEach(() => seedDeepSettings(null))

function seed(entries: Record<string, string | number | boolean>) {
  seedDeepSettings([
    {
      fields: Object.entries(entries).map(([key, value]) => ({ key, value, default: value })),
    },
  ] as unknown as DeepSection[])
}

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
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(screen.queryByTestId('model-status-toast')).toBeNull()
    expect(screen.queryByTestId('model-status-line')).toBeNull()
    expect(screen.getByTestId('welcome-card-0')).toBeTruthy()
    expect(screen.getByTestId('welcome-card-2')).toBeTruthy()
    expect(screen.getByTestId('hero-greeting')).toBeTruthy()
  })

  it('has exactly one input surface: no second composer, chips or send button', () => {
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(screen.queryByTestId('smart-suggestions')).toBeNull()
    expect(screen.queryByTestId('welcome-input')).toBeNull()
    expect(screen.queryByTestId('welcome-send')).toBeNull()
    expect(screen.queryByTestId('welcome-chip-0')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'welcome.send' })).toBeNull()
  })

  it('card click starts the run with the card prompt', () => {
    const onStartMission = vi.fn()
    render(<WelcomeEmptyState onStartMission={onStartMission} />)
    fireEvent.click(screen.getByTestId('welcome-card-2'))
    expect(onStartMission).toHaveBeenCalledTimes(1)
    expect(onStartMission).toHaveBeenCalledWith('welcome.cards.2.prompt')
  })
})

// The register row for `appearance.companion_behavior` names four places for the
// companion. The start screen's hero belongs to none of them: it is the brand
// figure, it stands whatever the choice says — including `header`, where no other
// figure reaches this screen at all — and only the species choice decides whether
// it wears the companion's form. These cases hold that line, so the row cannot
// drift back into promising a place the canvas never gives the companion.
describe('the start-screen hero', () => {
  const hero = () => screen.getByTestId('ephe-mark-hero')

  it.each(['interactive', 'perch', 'header', 'welcome_only'] as const)(
    'carries the companion under the %s choice',
    (behavior) => {
      seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': behavior })
      render(<WelcomeEmptyState onStartMission={vi.fn()} />)
      expect(hero()).toBeTruthy()
      expect(hero().classList.contains('companion-actor')).toBe(true)
      expect(hero().dataset.species).toBe('paper_moth')
    },
  )

  it('wears the chosen species while the companion is on', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_species': 'fire_bee' })
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(hero().classList.contains('companion-actor')).toBe(true)
    expect(hero().dataset.species).toBe('fire_bee')
  })

  it('stays the brand moth when the companion is switched off', () => {
    seed({ 'appearance.companion_enabled': false, 'appearance.companion_species': 'fire_bee' })
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(hero()).toBeTruthy()
    expect(hero().classList.contains('companion-actor')).toBe(false)
  })

  it('takes the quiet mark for the minimal species', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_species': 'minimal' })
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(hero()).toBeTruthy()
    expect(hero().classList.contains('companion-actor')).toBe(false)
  })
})
