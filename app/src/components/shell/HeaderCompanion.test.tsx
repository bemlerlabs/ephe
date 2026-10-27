import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

import HeaderCompanion from './HeaderCompanion'

function seed(entries: Record<string, string | number | boolean>) {
  seedDeepSettings([
    {
      fields: Object.entries(entries).map(([key, value]) => ({ key, value, default: value })),
    },
  ] as unknown as DeepSection[])
}

afterEach(() => seedDeepSettings(null))

describe('HeaderCompanion', () => {
  it('reserves the slot and renders the actor at the perch', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    render(<HeaderCompanion runState="ready" hasMessages />)
    expect(screen.getByTestId('header-companion-slot')).toBeTruthy()
    const companion = screen.getByTestId('header-companion')
    expect(companion.dataset.state).toBe('ready')
    expect(companion.dataset.mood).toBe('rest')
    expect(companion.querySelector('.companion-actor')).toBeTruthy()
  })

  it('keeps the slot before the first message without a second actor', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    render(<HeaderCompanion runState="ready" hasMessages={false} />)
    expect(screen.getByTestId('header-companion-slot')).toBeTruthy()
    expect(screen.queryByTestId('header-companion')).toBeNull()
  })

  it('renders nothing when the behavior is not the header perch', () => {
    render(<HeaderCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('header-companion-slot')).toBeNull()
  })

  it('maps the one run state to the actor mood', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    const { rerender } = render(<HeaderCompanion runState="working" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('moving')
    rerender(<HeaderCompanion runState="waiting" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('still')
    rerender(<HeaderCompanion runState="done" hasMessages />)
    expect(screen.getByTestId('header-companion').dataset.mood).toBe('settle')
  })
})
