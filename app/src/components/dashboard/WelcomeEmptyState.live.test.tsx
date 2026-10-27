/**
 * R26 — WelcomeEmptyState live data (mockup redesign)
 *
 * GIVEN the backend serves projects, artifacts and health
 * WHEN the empty state renders
 * THEN the 4 action cards and the model status toast appear with live
 *      descriptions, and a card click seeds the single bottom composer
 *      via onFillComposer (the duplicate Smart-Suggestions input box was
 *      removed on owner request — this file locks that in).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

const api = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listArtifacts: vi.fn(),
  healthCheck: vi.fn(),
  // S4: the Sky card is part of the empty state — offline it stays hidden.
  getSky: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

vi.mock('@/lib/api', () => ({
  listProjects: api.listProjects,
  listArtifacts: api.listArtifacts,
  healthCheck: api.healthCheck,
  getSky: api.getSky,
}))

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

const emptyApis = () => {
  api.listProjects.mockResolvedValue({ workspace: '', projects: [], generated_at: '' })
  api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
  api.healthCheck.mockResolvedValue({ active_model: 'm', active_tier: 't', status: 'ok' })
}

describe('WelcomeEmptyState (R26)', () => {
  it('renders 4 action cards with live project data and the model toast', async () => {
    api.listProjects.mockResolvedValue({
      workspace: '/tmp/ws',
      projects: [
        {
          name: 'proj-alpha',
          path: '/tmp/ws/proj-alpha',
          stacks: ['py'],
          score: 5,
          workspace: true,
        },
      ],
      generated_at: '',
    })
    api.listArtifacts.mockResolvedValue({
      artifacts: [{ id: 'a1', name: 'report.pdf', kind: 'pdf' }],
      total: 1,
    })
    api.healthCheck.mockResolvedValue({
      active_model: 'ephe-v5',
      active_tier: 'hybrid',
      status: 'ok',
      engine_online: true,
      dgx_online: true,
    })

    // QD-005: the fresh boot leaves the companion off, so this file summons it
    // before asserting the living hero.
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          {
            key: 'appearance.companion_enabled',
            type: 'bool',
            label: 'Begleiter',
            labelEn: 'Companion',
            default: false,
            value: true,
          },
        ],
      },
    ] as unknown as DeepSection[])
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)

    expect(screen.getByTestId('welcome-card-0')).toBeTruthy()
    expect(screen.getByTestId('welcome-card-3')).toBeTruthy()
    // The hero is the living actor, not the flat mark, while the companion is on.
    expect(screen.getByTestId('ephe-mark-hero').getAttribute('data-species')).toBe('fire_bee')
    await waitFor(() => {
      expect(screen.getByTestId('model-status-toast').textContent).toContain('ephe-v5')
      // DD-06: honest label — online state, never a hard-coded "Optimized".
      expect(screen.getByTestId('model-status-toast').textContent).toContain('welcome.modelOnline')
      // I2 Clean empty state: the chips carry only the title, no live data anymore
      expect(screen.getByTestId('welcome-card-0').textContent).toContain('welcome.cards.0.title')
      expect(screen.getByTestId('hero-greeting')).toBeTruthy()
      // Mock-i18n returns keys — this pin asserts on the hero-title key
      expect(screen.getByTestId('hero-brand').textContent).toContain('welcome.heroTitle')
    })
  })

  it('prints an em dash where the engine named no model and no tier', async () => {
    // Found in the Wave 1 desktop capture: an unreachable engine answered with an
    // empty model and an empty tier, and the line read "Model: ()".
    api.listProjects.mockResolvedValue({ workspace: '', projects: [], generated_at: '' })
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    api.healthCheck.mockResolvedValue({ active_model: '', active_tier: '', status: 'ok' })
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const line = await screen.findByTestId('model-status-line')
    expect(line.textContent).toBe('welcome.modelLabel: —')
    expect(line.textContent).not.toContain('()')
  })

  it('falls back to the static descriptions when the backend is offline', async () => {
    api.listProjects.mockRejectedValue(new Error('offline'))
    api.listArtifacts.mockRejectedValue(new Error('offline'))
    api.healthCheck.mockRejectedValue(new Error('offline'))
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    // Offline too: slim chips with titles (no static descriptions anymore)
    expect(screen.getByTestId('welcome-card-1').textContent).toContain('welcome.cards.1.title')
    expect(screen.getByTestId('hero-greeting')).toBeTruthy()
    expect(screen.queryByTestId('model-status-toast')).toBeNull()
  })

  it('has exactly one input surface: no second composer, chips or send button', () => {
    emptyApis()
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    // The removed Smart-Suggestions box must never come back.
    expect(screen.queryByTestId('smart-suggestions')).toBeNull()
    expect(screen.queryByTestId('welcome-input')).toBeNull()
    expect(screen.queryByTestId('welcome-send')).toBeNull()
    expect(screen.queryByTestId('welcome-chip-0')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'welcome.send' })).toBeNull()
  })

  it('card click seeds the bottom composer with the card prompt (never auto-sends)', () => {
    emptyApis()
    const onFillComposer = vi.fn()
    render(<WelcomeEmptyState onFillComposer={onFillComposer} />)
    fireEvent.click(screen.getByTestId('welcome-card-2'))
    expect(onFillComposer).toHaveBeenCalledTimes(1)
    expect(onFillComposer).toHaveBeenCalledWith('welcome.cards.2.prompt')
  })

  it('labels the pill offline when the engine is down (DD-06)', async () => {
    api.listProjects.mockResolvedValue({ workspace: '', projects: [], generated_at: '' })
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    api.healthCheck.mockResolvedValue({
      active_model: 'ephe-v5',
      active_tier: 'hybrid',
      status: 'ok',
      engine_online: false,
      dgx_online: false,
    })
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByTestId('model-status-toast').textContent).toContain('welcome.modelOffline')
    })
  })

  it('names a refused credential as refused on the first screen, not as offline', async () => {
    api.listProjects.mockResolvedValue({ workspace: '', projects: [], generated_at: '' })
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    api.healthCheck.mockResolvedValue({
      active_model: 'ephe-v5',
      active_tier: 'hybrid',
      status: 'ok',
      engine_online: false,
      dgx_online: false,
      engine_state: 'unreachable',
      engine_key_challenge: true,
      engine_key_configured: false,
    })
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const pill = await screen.findByTestId('model-status-toast')
    await waitFor(() => {
      expect(pill.querySelector('[data-model-status]')).toHaveAttribute(
        'data-model-status',
        'refused',
      )
    })
    expect(pill.textContent).toContain('welcome.modelKeyRefused')
    expect(pill.textContent).not.toContain('welcome.modelOffline')
  })
})
