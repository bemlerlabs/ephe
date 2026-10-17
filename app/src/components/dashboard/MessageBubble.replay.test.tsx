// N2 — a tool replay frame per turn: collapsed to one row (the header), expanded
// into numbered steps (TYPE, shortened text, duration) from the trajectory snapshot.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import MessageBubble from './MessageBubble'
import { useChatStore } from '@/store/chatStore'
import type { ChatMessage } from '@/types'

function fixtureTurns() {
  return [
    {
      sid: 's1',
      model: 'm',
      ts: 1761806357,
      duration_ms: 3500,
      steps: [
        { n: 1, type: 'user', title: 'prompt text', ms: 120, state: 'ok' },
        { n: 2, type: 'tool_call', title: 'run_shell ls', ms: 450, state: 'ok', text: 'OUT-TEXT' },
      ],
    },
    {
      sid: 's1',
      model: 'm',
      ts: 1761806359,
      duration_ms: 2100,
      steps: [{ n: 1, type: 'message', title: 'answer', ms: 2000, state: 'ok' }],
    },
  ]
}

vi.mock('@/lib/api', () => ({
  getTrajectory: vi.fn(async () => ({ turns: fixtureTurns() })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}<${JSON.stringify(opts)}>` : key,
    i18n: { language: 'de' },
  }),
}))

const FIRST: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: 'Antwort 1',
  timestamp: Date.now() - 20_000,
  durationMs: 3500,
  streaming: false,
}
const SECOND: ChatMessage = {
  id: 'a2',
  role: 'assistant',
  content: 'Antwort 2',
  timestamp: Date.now() - 10_000,
  durationMs: 2100,
  streaming: false,
}

function setupStore() {
  useChatStore.setState({
    activeSessionId: 's1',
    currentSession: {
      id: 's1',
      title: 'T',
      messages: [
        { id: 'u1', role: 'user', content: 'frage', timestamp: Date.now() - 21_000 },
        FIRST,
        SECOND,
      ],
      created_at: 1,
      updated_at: 2,
    } as never,
  })
}

describe('Tool-Replay-Kader (N2)', () => {
  beforeEach(() => {
    setupStore()
  })

  it('zeigt je Assistant-Turn einen Kader — der zweite zeigt seinen eigenen Turn', async () => {
    render(
      <>
        <MessageBubble message={FIRST} />
        <MessageBubble message={SECOND} />
      </>,
    )
    const k0 = await screen.findByTestId('tool-replay-kader-0')
    expect(k0.textContent).toContain('2 steps') // 2 Steps · 0.6s
    const k1 = await screen.findByTestId('tool-replay-kader-1')
    expect(k1.textContent).toContain('1 steps')
  })

  it('zugeklappt eine Zeile; Klick oeffnet nummerierte Steps mit Dauer', async () => {
    render(<MessageBubble message={FIRST} />)
    const kader = await screen.findByTestId('tool-replay-kader-0')
    // closed: no step row in the DOM
    expect(document.querySelector('[data-testid="replay-row-0-0"]')).toBeNull()
    fireEvent.click(kader.querySelector('button')!)
    // Turn ti=0, step index i=1 is the tool_call — testid schema: replay-row-{ti}-{i}
    await waitFor(() =>
      expect(document.querySelector('[data-testid="replay-row-0-1"]')).toBeTruthy(),
    )
    const row = document.querySelector('[data-testid="replay-row-0-1"]')
    expect(row?.textContent).toContain('02')
    expect(row?.textContent).toContain('tool_call')
    expect(row?.textContent).toContain('450ms')
    // this step shows its text body instead of the title
    expect(row?.textContent).toContain('OUT-TEXT')
  })
})
