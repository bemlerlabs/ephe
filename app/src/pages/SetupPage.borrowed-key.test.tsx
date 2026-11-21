// S4 (owner decision 2026-10-18) — a probe that answered with a key found beside Ephe
// says so. The credential mirror may authenticate the onboarding check, but a chat turn
// reads only Ephe's own store, so "reachable" bought with someone else's token is a
// answer the user cannot keep by clicking through. Both surfaces that can produce such
// an answer are pinned: the probe result and the detection offer.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const probeProvider = vi.fn(async () => ({
  reachable: true,
  models: ['picked-model'],
  detail: 'server-prosa', // language-gate: ignore — the server detail the route really returns
  url: 'http://10.1.2.3:8000/v1',
  state: 'ok',
}))
const getSetupStatus = vi.fn(async () => ({
  configured: false,
  skipped: false,
  provider: '',
  model: null,
  url: null,
  reachable: false,
  available_models: [],
  candidates: [],
}))
let detectPayload: Record<string, unknown> = {
  candidates: [],
  detected: [],
  first_reachable: -1,
}

vi.mock('@/lib/api', () => ({
  probeProvider: (...a: unknown[]) => probeProvider(...(a as [])),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(async () => ({ configured: false })),
  skipSetup: vi.fn(async () => ({ configured: false, skipped: true })),
  getSetupStatus: () => getSetupStatus(),
  detectEngines: async () => detectPayload as never,
}))

import SetupPage from './SetupPage'

function probeWithKeySource(key_source?: string) {
  probeProvider.mockResolvedValue({
    reachable: true,
    models: ['picked-model'],
    detail: 'server-prosa',
    url: 'http://10.1.2.3:8000/v1',
    state: 'ok',
    ...(key_source ? { key_source } : {}),
  } as never)
  render(<SetupPage onDone={vi.fn()} />)
  fireEvent.click(screen.getByTestId('setup-option-openai'))
  fireEvent.change(screen.getByTestId('setup-endpoint'), {
    target: { value: 'http://10.1.2.3:8000/v1' },
  })
  fireEvent.click(screen.getByTestId('setup-probe'))
}

beforeEach(() => {
  probeProvider.mockClear()
  detectPayload = { candidates: [], detected: [], first_reachable: -1 }
})

describe('SetupPage borrowed-key visibility (S4)', () => {
  it('names a borrowed key under the model list the probe found', async () => {
    probeWithKeySource('foreign')
    expect(await screen.findByTestId('setup-borrowed-key')).toHaveTextContent(
      'setup.probeBorrowedKey',
    )
  })

  it('says nothing when the user’s own key answered', async () => {
    probeWithKeySource('own')
    await screen.findByTestId('setup-model')
    expect(screen.queryByTestId('setup-borrowed-key')).toBeNull()
  })

  it('says nothing for a key typed into this very screen', async () => {
    probeWithKeySource('given')
    await screen.findByTestId('setup-model')
    expect(screen.queryByTestId('setup-borrowed-key')).toBeNull()
  })

  it('names a borrowed key inside the detection offer too', async () => {
    detectPayload = {
      candidates: [{ provider: 'openai_compatible', url: 'http://10.1.2.3:8000/v1' }],
      detected: [
        {
          provider: 'openai_compatible',
          url: 'http://10.1.2.3:8000/v1',
          reachable: true,
          models: ['a-model'],
          detail: '',
          state: 'ok',
          key_source: 'foreign',
        },
      ],
      first_reachable: 0,
    }
    render(<SetupPage onDone={vi.fn()} />)
    const note = await screen.findByTestId('setup-offer-borrowed-key')
    expect(note).toHaveTextContent('setup.probeBorrowedKey')
    expect(screen.getByTestId('setup-offer')).toBeInTheDocument()
  })

  it('leaves the offer silent for a scan that used Ephe’s own key', async () => {
    detectPayload = {
      candidates: [{ provider: 'openai_compatible', url: 'http://10.1.2.3:8000/v1' }],
      detected: [
        {
          provider: 'openai_compatible',
          url: 'http://10.1.2.3:8000/v1',
          reachable: true,
          models: ['a-model'],
          detail: '',
          state: 'ok',
          key_source: 'own',
        },
      ],
      first_reachable: 0,
    }
    render(<SetupPage onDone={vi.fn()} />)
    await screen.findByTestId('setup-offer')
    await waitFor(() => expect(screen.queryByTestId('setup-offer-borrowed-key')).toBeNull())
  })
})
