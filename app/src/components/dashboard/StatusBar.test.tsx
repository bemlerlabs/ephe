import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { CONTEXT_WINDOW_TOKENS } from '@/lib/contextMeter'
import type { ChatMessage } from '@/types'

// W2: deterministic budget behaviour — Partial '{}' like the e2e stub.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

// R44 (P3): the storage pill reads the session count from the store — mock it as
// the data source so it stays testable without the i18n plumbing.
vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({
      sessions: [
        { id: 'a', messages: [] },
        { id: 'b', messages: [] },
      ],
    }),
}))

// i18n mock (StatusBar uses useTranslation for the compact button, Phase F)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.compactNow': 'Compact now',
        'chat.compactBanner': 'Context is getting full',
        'statusBar.breakdownHint': 'Token breakdown',
        'statusBar.storage': `${String(opts?.count ?? '')} sessions · ~${String(opts?.mb ?? '')} MB`,
        'statusBar.storageHint': 'Browser cache (IndexedDB)',
        'statusBar.remainingPercent': `${String(opts?.percent ?? '')}% free`,
        'statusBar.contextFreeOf': '{{free}} free of {{window}}',
        'statusBar.detailsTitle': 'Usage and storage',
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  }),
}))

function makeMsgs(role: 'user' | 'assistant', text: string): ChatMessage[] {
  return [{ id: `${role}-1`, role, content: text, timestamp: Date.now() }]
}

describe('StatusBar', () => {
  it('states the context remainder in percent, not the raw token pair', () => {
    const msgs = makeMsgs('user', 'x'.repeat(4200)) // ~1000 tok → 4% of the 24576 floor the render pins
    render(<StatusBar messages={msgs} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    expect(screen.getByTestId('statusbar-percent').textContent).toBe('96% free')
    // WCAG 2.5.3: the visible figure is part of the name the button answers to.
    expect(screen.getByTestId('statusbar-breakdown-toggle').getAttribute('aria-label')).toBe(
      'Token breakdown: 96% free',
    )
    // The raw figures are behind the status pill now, not in the row all day.
    expect(screen.queryByTestId('statusbar-storage-chip')).toBeNull()
    expect(screen.queryByText(/free of/)).toBeNull()
  })

  it('no warning text without onCompact (Action statt toter Hinweis, Phase F)', () => {
    const msgs = makeMsgs('user', 'x'.repeat(90000)) // ~21.4k tok > 75% of the floor
    render(<StatusBar messages={msgs} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    expect(screen.queryByText(/kompakt empfohlen/)).toBeNull()
  })

  it('shows the Compact-Button at high usage WHEN onCompact geparlt', () => {
    const onCompact = vi.fn()
    const msgs = makeMsgs('user', 'x'.repeat(90000)) // ~21.4k tok > 75% of the floor
    render(<StatusBar messages={msgs} onCompact={onCompact} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    const btn = screen.getByRole('button', { name: /Compact/i })
    fireEvent.click(btn)
    expect(onCompact).toHaveBeenCalledTimes(1)
  })

  it('no Compact-Button ohne onCompact (backwards-kompatibel)', () => {
    const msgs = makeMsgs('user', 'x'.repeat(90000))
    render(<StatusBar messages={msgs} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    expect(screen.queryByRole('button', { name: /Compact/i })).toBeNull()
  })

  // W2: the e2e route answers /api/context/budget with '{}' (truthy but partial).
  // The meter has to fall back to the offline estimate instead of crashing on
  // undefined.toLocaleString().
  it('W2: Partial-Budget {} faellt auf die Offline-Schaetzung zurueck', () => {
    const msgs = makeMsgs('user', 'x'.repeat(4200)) // ~1000 tok → 4% of the 24576 floor the render pins
    render(<StatusBar messages={msgs} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    expect(screen.getByTestId('statusbar-percent').textContent).toBe('96% free')
  })

  it('opens the context popover from the breakdown control', () => {
    const msgs = makeMsgs('assistant', 'a'.repeat(420)) // ~100 tok
    render(<StatusBar messages={msgs} windowTokens={CONTEXT_WINDOW_TOKENS} />)
    // The row no longer prints the breakdown inline — the popover is its home, so the
    // one control that opens it now just opens it (the number lives in the composer).
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    expect(screen.getByTestId('context-popover')).toBeTruthy()
  })

  it('zeigt tokens/sec nur während Streaming (aktive Assistant-Message)', () => {
    const streaming: ChatMessage[] = [
      {
        id: 'a-1',
        role: 'assistant',
        content: 'x'.repeat(4200), // ~1000 tok → 4% of the floor
        timestamp: Date.now() - 2000, // turn started 2s ago
        streaming: true,
      },
    ]
    render(<StatusBar messages={streaming} />)
    // W19 F5: tok/s lives in the context popover — open the toggle, then it is visible.
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    // ~1000 tok / 2s ≈ 500 tok/s → visible in the popover
    expect(screen.getByText(/tok\/s/)).toBeTruthy()
  })

  it('kein tokens/sec Badge ohne aktive Streaming-Message', () => {
    render(<StatusBar messages={makeMsgs('assistant', 'fertig')} />)
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    expect(screen.queryByText(/tok\/s/)).toBeNull()
  })

  it('DD-08: tok/s zaehlt den Thinking-Kanal mit (kein 0.0 waehrend Thinking streamt)', () => {
    // Pure thinking phase: content still empty, the channel already delivers ~1000 tok.
    const thinkingOnly: ChatMessage[] = [
      {
        id: 'a-think',
        role: 'assistant',
        content: '',
        thinking: { start: Date.now() - 2000, end: Date.now(), text: 'y'.repeat(4200) },
        timestamp: Date.now() - 2000,
        streaming: true,
      },
    ]
    render(<StatusBar messages={thinkingOnly} />)
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    const badge = screen.getByText(/tok\/s/)
    expect(parseFloat(badge.textContent!)).toBeGreaterThan(100)
  })

  it('DD-21: Breakdown-Tooltip kommt aus i18n (kein hartkodierte deutsche Zeichenkette)', () => {
    render(<StatusBar messages={makeMsgs('user', 'x'.repeat(420))} />)
    const btn = screen.getByTitle(/token breakdown/i)
    expect(btn.getAttribute('title')).toBe('Token breakdown')
  })

  it('holds no second token chip: one remainder figure, one opener', () => {
    render(<StatusBar messages={makeMsgs('user', 'x'.repeat(420))} />)
    expect(screen.queryByTestId('statusbar-tok-chip')).toBeNull()
    expect(screen.queryByTestId('statusbar-storage-chip')).toBeNull()
    expect(screen.getByTestId('statusbar-breakdown-toggle')).toBeTruthy()
  })

  it('Konnex-Cluster nur mit gelieferten Props (Bild-2-Auslagerung aus dem Header)', () => {
    render(
      <StatusBar
        messages={makeMsgs('user', 'x'.repeat(420))}
        backendOnline={true}
        engineOnline={true}
        typing={false}
      />,
    )
    expect(screen.getByTestId('agent-status-pill')).toBeTruthy()
    const statusEls = screen.getAllByRole('status')
    expect(
      statusEls.some((e) => (e.getAttribute('aria-label') || '').includes('chat.connected')),
    ).toBeTruthy()
  })
})
