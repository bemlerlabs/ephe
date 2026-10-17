/**
 * W3-53 — First-run: the welcome screen is the entry into engine setup.
 *
 * GIVEN a down or refused engine (a first-run user who skipped setup, or a
 *       machine whose engine went away)
 * WHEN  the empty state renders
 * THEN  the status toast names the next step — a click straight into /setup —
 *       on every breakpoint, and only there: an engine that is up gets no
 *       call to action. The re-entry the composer chip offers must already
 *       exist on the first screen, otherwise the pill is a dead end.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listArtifacts: vi.fn(),
  healthCheck: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  listProjects: api.listProjects,
  listArtifacts: api.listArtifacts,
  healthCheck: api.healthCheck,
}))

vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => true }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import WelcomeEmptyState from './WelcomeEmptyState'
import { SETUP_INTENT_KEY } from '@/lib/setupGate'

const health = (extra: Record<string, unknown>) => ({
  active_model: 'ephe-v5',
  active_tier: 'hybrid',
  status: 'ok',
  ...extra,
})

beforeEach(() => {
  sessionStorage.clear()
  window.location.hash = ''
  api.listProjects.mockReset()
  api.listArtifacts.mockReset()
  api.healthCheck.mockReset()
  api.listProjects.mockResolvedValue({ workspace: '', projects: [], generated_at: '' })
  api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
})

describe('WelcomeEmptyState first-run engine path (W3-53)', () => {
  it('offers the engine-setup entry when the engine is down', async () => {
    api.healthCheck.mockResolvedValue(health({ engine_online: false, dgx_online: false }))
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const cta = await screen.findByTestId('welcome-engine-setup')
    expect(cta.textContent).toContain('welcome.openSetup')
  })

  it('walks from the first screen into /setup and states the intent', async () => {
    api.healthCheck.mockResolvedValue(health({ engine_online: false, dgx_online: false }))
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    fireEvent.click(await screen.findByTestId('welcome-engine-setup'))
    expect(sessionStorage.getItem(SETUP_INTENT_KEY)).toBe('1')
    expect(window.location.hash).toBe('#/setup')
  })

  it('a refused credential is also a path into setup, not a dead end', async () => {
    api.healthCheck.mockResolvedValue(
      health({
        engine_online: false,
        dgx_online: false,
        engine_state: 'unreachable',
        engine_key_challenge: true,
        engine_key_configured: false,
      }),
    )
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const toast = await screen.findByTestId('model-status-toast')
    await waitFor(() =>
      expect(toast.querySelector('[data-model-status]')).toHaveAttribute(
        'data-model-status',
        'refused',
      ),
    )
    expect(screen.getByTestId('welcome-engine-setup')).toBeTruthy()
  })

  it('is not a dead end on a phone: the status is visible below sm', async () => {
    api.healthCheck.mockResolvedValue(health({ engine_online: false, dgx_online: false }))
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const toast = await screen.findByTestId('model-status-toast')
    // the old `hidden sm:block` kept the engine state off a phone entirely
    expect(toast.className).not.toMatch(/(?:^|\s)hidden(?:\s|$)/)
  })

  it('stays quiet when the engine is up — no call to action', async () => {
    api.healthCheck.mockResolvedValue(health({ engine_online: true, dgx_online: false }))
    render(<WelcomeEmptyState onFillComposer={vi.fn()} />)
    const toast = await screen.findByTestId('model-status-toast')
    await waitFor(() =>
      expect(toast.querySelector('[data-model-status]')).toHaveAttribute('data-model-status', 'up'),
    )
    expect(screen.queryByTestId('welcome-engine-setup')).toBeNull()
  })
})
