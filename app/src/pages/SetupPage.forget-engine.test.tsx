// W19 keep-its-word: "Forget engine selection (choose again)" is an undo for a
// choice. On a first run nothing has been chosen, and the row must not offer to
// forget a selection that was never made; once a choice exists, it is the way back.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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

const status = vi.hoisted(() => ({
  current: {
    configured: false,
    skipped: false,
    provider: '',
    model: null as string | null,
    url: null,
    reachable: false,
    available_models: [] as string[],
  },
}))

vi.mock('@/lib/api', () => ({
  probeProvider: vi.fn(async () => ({ reachable: false, models: [], state: 'unreachable' })),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(async () => ({ configured: false })),
  skipSetup: vi.fn(async () => ({ configured: false, skipped: true })),
  getSetupStatus: vi.fn(async () => status.current),
  detectEngines: vi.fn(async () => ({ candidates: [], detected: [], first_reachable: -1 })),
}))

import SetupPage from './SetupPage'

beforeEach(() => {
  status.current = {
    configured: false,
    skipped: false,
    provider: '',
    model: null,
    url: null,
    reachable: false,
    available_models: [],
  }
})

describe('SetupPage forget-engine row', () => {
  it('stays away on a first run, where nothing was chosen to forget', async () => {
    render(<SetupPage onDone={vi.fn()} />)
    await screen.findByTestId('setup-skip')
    expect(screen.queryByTestId('setup-reset')).toBeNull()
  })

  it('appears when the device holds an engine choice', async () => {
    status.current = {
      configured: true,
      skipped: false,
      provider: 'local_ollama',
      model: 'gemma4:12b',
      url: null,
      reachable: true,
      available_models: ['gemma4:12b'],
    }
    render(<SetupPage onDone={vi.fn()} />)
    const forget = await screen.findByTestId('setup-reset')
    expect(forget.textContent).toContain('setup.reset')
  })
})
