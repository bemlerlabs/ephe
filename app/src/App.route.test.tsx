/**
 * W10 — a hash route that does not exist says so.
 *
 * FINDINGS.md (walkthrough 2026-10-12, low): `#/this/hash/does/not/exist` was
 * rewritten to `/` with no word to the reader, so a wrong deep link read as one
 * the app ignored. The `*` entry now renders a notice; the setup gate still runs
 * first, which is what an old `#/onboarding` bookmark reaches.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts ? `${k}:${Object.values(opts).join('|')}` : k,
  }),
}))

vi.mock('@/lib/api', () => ({
  getSetupStatus: () => Promise.resolve({ configured: true, skipped: false }),
}))

const readyGate = { ready: true, configured: true, skipped: false }
vi.mock('@/lib', () => ({
  consumeSetupIntent: () => false,
  shouldLeaveSetup: () => false,
  gateSnapshot: () => readyGate,
  loadSetupGate: async () => {},
  subscribeGate: () => () => {},
}))

vi.mock('@/hooks', () => ({
  useCommandPalette: () => ({
    open: false,
    setOpen: () => {},
    query: '',
    setQuery: () => {},
    inputRef: { current: null },
    grouped: [],
    t: (k: string) => k,
    recordUsage: () => {},
  }),
}))

vi.mock('./pages/ChatPage', () => ({ default: () => <div data-testid="chat-page" /> }))

import App from './App'

const BAD = '#/this/hash/does/not/exist'

beforeEach(() => {
  window.location.hash = BAD
})

describe('an unknown hash route (W10)', () => {
  it('names the address it cannot open instead of rewriting it in silence', async () => {
    render(<App />)

    const notice = await screen.findByTestId('route-unknown')
    expect(notice.textContent).toContain(BAD)
    expect(window.location.hash).toBe(BAD)
  })

  it('offers the chat and the offer reaches it', async () => {
    render(<App />)

    const link = await screen.findByTestId('route-unknown-chat')
    expect(link).toHaveAttribute('href', '#/chat')
    fireEvent.click(link)
    expect(await screen.findByTestId('chat-page')).toBeInTheDocument()
  })
})
