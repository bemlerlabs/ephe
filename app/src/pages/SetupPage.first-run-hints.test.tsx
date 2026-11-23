// N1 first-run: a stranger must be able to choose an engine without leaving the
// app. These two hints carry the steps the product cannot do for the user — where
// a hosted key comes from, and what to do when no local engine answers.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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
  models: ['my-served-model'],
  detail: 'reachable',
  url: 'http://10.1.2.3:8000/v1',
  state: 'ok' as const,
}))
const updateSettings = vi.fn(async () => ({}))
const resetSetup = vi.fn(async () => ({ configured: false }))
const skipSetup = vi.fn(async () => ({ configured: false, skipped: true }))
const getSetupStatus = vi.fn(async () => ({
  configured: false,
  skipped: false,
  provider: '',
  model: null,
  url: null,
  reachable: false,
  available_models: [],
}))
const detectEngines = vi.fn(async () => ({
  candidates: [],
  detected: [],
  first_reachable: -1,
}))

vi.mock('@/lib/api', () => ({
  probeProvider: (...a: unknown[]) => probeProvider(...(a as [])),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
  resetSetup: () => resetSetup(),
  skipSetup: () => skipSetup(),
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
}))

import SetupPage from './SetupPage'

describe('SetupPage first-run hints (N1)', () => {
  it('pre-selects no engine: the three classes stand unchecked until a choice is made', () => {
    // The product's own rule (AGENTS.md): no engine is chosen for the user, so a fresh
    // screen shows no selection at all — not even a leaning one.
    render(<SetupPage onDone={vi.fn()} />)
    for (const id of ['setup-option-local', 'setup-option-custom', 'setup-option-openai']) {
      expect(screen.getByTestId(id).getAttribute('aria-checked')).toBe('false')
    }
  })

  it('hands a local choice the Ollama download once the user takes it', () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-local'))
    expect(screen.getByTestId('setup-option-local').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByTestId('setup-local-hint')).toBeTruthy()
    expect(screen.getByText('setup.localHintLink').getAttribute('href')).toBe(
      'https://ollama.com/download',
    )
  })

  it('hands a hosted choice the providers that issue a key', () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    expect(screen.getByTestId('setup-key-help')).toBeTruthy()
    expect(screen.getByText('setup.keyHelpOpenrouter').getAttribute('href')).toBe(
      'https://openrouter.ai/keys',
    )
    // The endpoint that answers only its own program is offered nowhere: not as a key link,
    // not as a quick pick, so a first run cannot walk into a refusal it was sold as a path.
    const offered = Array.from(document.querySelectorAll('a[href], [data-testid^="setup-quick"]'))
      .map((node) => `${node.getAttribute('href') ?? ''} ${node.textContent ?? ''}`)
      .join(' ')
    expect(offered.toLowerCase()).not.toContain('opencode')
  })
})
