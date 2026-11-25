/**
 * WelcomeEmptyState — the figure on the start screen.
 *
 * `appearance.companion_behavior` decides where the creature lives while a chat runs:
 * at the composer, above the input, in the header, or only here. The register's hint
 * states that the start screen keeps its figure under every one of those, and the
 * header choice is the case that could break the sentence: the workspace instance hides
 * itself there, and its own note names QA-0.1.11 for an earlier version of that screen
 * that showed nothing and read as a broken control. These cases hold the sentence.
 *
 * The two hero forms are stubbed so the assertion is about this surface's decision, not
 * about what the actor draws: the 3D figure and the flat moth fallback are different
 * branches of the same `ephe-mark-hero` slot.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/components/shell/CompanionActor', () => ({
  CompanionActor: ({ species }: { species: string }) => <div data-testid={`actor-${species}`} />,
}))

vi.mock('@/components/brand/PaperMoth', () => ({
  PaperMoth: () => <div data-testid="moth-fallback" />,
}))

import WelcomeEmptyState from './WelcomeEmptyState'

const BEHAVIOURS = ['interactive', 'perch', 'header', 'welcome_only'] as const

type Field = DeepSection['fields'][number]

function field(key: string, type: Field['type'], value: string | number | boolean | null): Field {
  return { key, type, label: key, labelEn: key, default: value, value }
}

function seed(...fields: Field[]): void {
  act(() => seedDeepSettings([{ key: 'appearance', fields }]))
}

afterEach(() => act(() => seedDeepSettings(null)))

describe.each(BEHAVIOURS)('the start screen under "%s"', (behavior) => {
  it('keeps the companion figure when the companion is on', () => {
    seed(
      field('appearance.companion_enabled', 'bool', true),
      field('appearance.companion_species', 'select', 'paper_moth'),
      field('appearance.companion_behavior', 'select', behavior),
    )
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(screen.getByTestId('actor-paper_moth')).toBeTruthy()
    expect(screen.queryByTestId('moth-fallback')).toBeNull()
  })

  it('puts a saved fire_bee choice on the moth', () => {
    seed(
      field('appearance.companion_enabled', 'bool', true),
      field('appearance.companion_species', 'select', 'fire_bee'),
      field('appearance.companion_behavior', 'select', behavior),
    )
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(screen.getByTestId('actor-paper_moth')).toBeTruthy()
    expect(screen.queryByTestId('actor-fire_bee')).toBeNull()
  })

  it('falls back to the brand figure when the companion is off', () => {
    seed(
      field('appearance.companion_enabled', 'bool', false),
      field('appearance.companion_species', 'select', 'paper_moth'),
      field('appearance.companion_behavior', 'select', behavior),
    )
    render(<WelcomeEmptyState onStartMission={vi.fn()} />)
    expect(screen.queryByTestId('actor-fire_bee')).toBeNull()
    expect(screen.getByTestId('moth-fallback')).toBeTruthy()
  })
})
