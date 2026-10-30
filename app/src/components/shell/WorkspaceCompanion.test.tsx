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
import { announceSetupRepair } from '@/lib/companionRepair'
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

afterEach(() => {
  seedDeepSettings(null)
  announceSetupRepair(false)
})

describe('WorkspaceCompanion', () => {
  it('a fresh boot stays calm until the companion is summoned', () => {
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('shows the moth in the active chat once it is switched on', () => {
    seed({ 'appearance.companion_enabled': true })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.behavior).toBe('interactive')
    expect(companion.dataset.species).toBe('paper_moth')
    expect(companion.querySelector('img.companion-body')?.getAttribute('src')).toBe(
      '/onboarding/paper-moth-actor.webp',
    )
    expect(companion.dataset.state).toBe('ready')
    expect(companion.dataset.mood).toBe('rest')
    expect(companion.dataset['copilotMode']).toBe('copilot')
    expect(companion.querySelector('.companion-body')).toBeTruthy()
    expect(companion.querySelectorAll('.companion-wing')).toHaveLength(2)
    expect(companion.querySelector('.companion-flame')).toBeTruthy()
  })

  it('keeps the bee as a chosen species with its own sprites', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_species': 'fire_bee' })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.species).toBe('fire_bee')
    expect(companion.querySelector('img.companion-body')?.getAttribute('src')).toBe(
      '/onboarding/bee-3d-actor.webp',
    )
  })

  it('appears on the welcome screen too, so the summon switch answers visibly', () => {
    seed({ 'appearance.companion_enabled': true })
    render(<WorkspaceCompanion runState="ready" hasMessages={false} />)
    expect(screen.getByTestId('workspace-companion')).toBeTruthy()
  })

  it('welcome_only now means the welcome screen', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'welcome_only' })
    render(<WorkspaceCompanion runState="ready" hasMessages={false} />)
    expect(screen.getByTestId('workspace-companion')).toBeTruthy()
  })

  it('retires on welcome_only once the chat has messages', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'welcome_only' })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('stays out of the header perch', () => {
    seed({ 'appearance.companion_enabled': true, 'appearance.companion_behavior': 'header' })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('respects the master switch', () => {
    seed({ 'appearance.companion_enabled': false })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.queryByTestId('workspace-companion')).toBeNull()
  })

  it('takes the spark form and the saved scale', () => {
    seed({
      'appearance.companion_enabled': true,
      'appearance.companion_species': 'ember_spark',
      'appearance.companion_scale': 120,
    })
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    const companion = screen.getByTestId('workspace-companion')
    expect(companion.dataset.species).toBe('ember_spark')
    expect(companion.querySelector('.companion-spark-eyes')).toBeTruthy()
    const actor = companion.querySelector<HTMLElement>('.companion-actor')
    expect(actor?.style.getPropertyValue('--companion-scale')).toBe('1.2')
  })

  it('points at the repair the setup screen announced', () => {
    seed({ 'appearance.companion_enabled': true })
    announceSetupRepair(true)
    render(<WorkspaceCompanion runState="ready" hasMessages />)
    expect(screen.getByTestId('companion-copilot-chip').dataset.verdict).toBe('focus')
  })

  it('takes its mood from the one run state the bar shows', () => {
    seed({ 'appearance.companion_enabled': true })
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
