/**
 * WorkspaceCompanion — the companion settings decide what the chat shows.
 *
 * GIVEN the five appearance.companion_* fields
 * WHEN  the chat has messages
 * THEN  the figure appears with the chosen form, retires on `welcome_only`,
 *       disappears when the companion is switched off, and takes its mood from
 *       the one run state the bar shows.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

import WorkspaceCompanion from './WorkspaceCompanion'

function seed(entries: Record<string, string | number | boolean>) {
  seedDeepSettings([
    {
      fields: Object.entries(entries).map(([key, value]) => ({ key, value, default: value })),
    },
  ] as unknown as DeepSection[])
}

afterEach(() => seedDeepSettings(null))

describe('WorkspaceCompanion', () => {
  it('shows the bee in the active chat by default', () => {
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.behavior).toBe('interactive')
    expect(companion.dataset.species).toBe('fire_bee')
    expect(companion.dataset.state).toBe('ready')
    expect(companion.dataset.mood).toBe('rest')
    expect(companion.querySelector('.companion-body')).toBeTruthy()
    expect(companion.querySelectorAll('.companion-wing')).toHaveLength(2)
    expect(companion.querySelector('.companion-flame')).toBeTruthy()
  })

  it('shows nothing before the first message', () => {
    render(<WorkspaceCompanion runState="ready" hasMessages={false} />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('retires on welcome_only once the chat has messages', () => {
    seed({ 'appearance.companion_behavior': 'welcome_only' })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('stays out of the header perch', () => {
    seed({ 'appearance.companion_behavior': 'header' })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('respects the master switch', () => {
    seed({ 'appearance.companion_enabled': false })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('takes the spark form and the saved scale', () => {
    seed({ 'appearance.companion_species': 'ember_spark', 'appearance.companion_scale': 120 })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.species).toBe('ember_spark')
    expect(companion.querySelector('.companion-spark-eyes')).toBeTruthy()
    const actor = companion.querySelector<HTMLElement>('.companion-actor')
    expect(actor?.style.getPropertyValue('--companion-scale')).toBe('1.2')
  })

  it('takes its mood from the one run state the bar shows', () => {
    const { rerender } = render(<WorkspaceCompanion runState="working" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.state).toBe('working')
    expect(companion.dataset.mood).toBe('moving')
    expect(companion.className).toContain('is-streaming')

    rerender(<WorkspaceCompanion runState="waiting" hasMessages />)
    expect(companion.dataset.mood).toBe('still')
    expect(companion.className).toContain('is-quiet')

    rerender(<WorkspaceCompanion runState="done" hasMessages />)
    expect(companion.dataset.mood).toBe('settle')
    expect(companion.className).toContain('is-settle')
  })
})
