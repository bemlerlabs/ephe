/**
 * A6 — the setup surface has to say what it is doing and what went wrong in the
 * accessibility tree, not only in colour and a spinner.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import axe from 'axe-core'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const probeProvider = vi.fn(async () => ({
  reachable: true,
  models: ['served-model'],
  detail: 'http://10.1.2.3:8000/v1 · 1 model',
  url: 'http://10.1.2.3:8000/v1',
  state: 'ok' as const,
}))

vi.mock('@/lib/api', () => ({
  probeProvider: (...a: unknown[]) => probeProvider(...(a as [])),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(async () => ({})),
  skipSetup: vi.fn(async () => ({})),
  getSetupStatus: vi.fn(async () => ({
    configured: false,
    skipped: false,
    provider: '',
    model: null,
    url: null,
    reachable: false,
    available_models: [],
  })),
  detectEngines: vi.fn(async () => ({ candidates: [], detected: [], first_reachable: -1 })),
}))

import SetupPage from './SetupPage'

beforeEach(() => {
  probeProvider.mockClear()
})

describe('SetupPage accessibility', () => {
  it('announces progress in a status region while the probe runs', async () => {
    let settle: (value: unknown) => void = () => {}
    probeProvider.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          settle = resolve
        }) as never,
    )
    render(<SetupPage onDone={vi.fn()} />)
    await screen.findByTestId('setup-page')
    await waitFor(() => expect(screen.getByTestId('setup-progress').textContent).toBe(''))
    fireEvent.click(screen.getByTestId('setup-probe'))

    const progress = screen.getByTestId('setup-progress')
    expect(progress.getAttribute('role')).toBe('status')
    expect(progress.textContent).toBe('setup.probing')

    settle({ reachable: false, models: [], detail: '', state: 'unreachable' })
    await waitFor(() => expect(screen.getByTestId('setup-progress').textContent).toBe(''))
  })

  it('reports a failed probe in an alert region', async () => {
    probeProvider.mockRejectedValueOnce(new Error('connection refused'))
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))

    const error = await screen.findByTestId('setup-error')
    expect(error.getAttribute('role')).toBe('alert')
    expect(error.textContent).toContain('connection refused')
  })

  it('passes the WCAG rules axe checks', async () => {
    const { container } = render(<SetupPage onDone={vi.fn()} />)
    await screen.findByTestId('setup-page')
    await waitFor(() => expect(screen.getByTestId('setup-progress').textContent).toBe(''))
    const results = await axe.run(container, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    })
    expect(results.violations).toEqual([])
  })
})
