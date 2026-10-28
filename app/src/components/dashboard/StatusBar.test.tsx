import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
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
  it('renders a percent meter from the message estimate', () => {
    const msgs = makeMsgs('user', 'x'.repeat(4200)) // ~1000 tok
    render(<StatusBar messages={msgs} />)
    // percentage visible (1000/8192 ≈ 12%)
    expect(screen.getByText(/12%/)).toBeTruthy()
    // DD-10: both the desktop breakdown and the mobile chip carry the tok figure
    expect(screen.getAllByText(/tok/).length).toBeGreaterThanOrEqual(1)
  })

  it('no warning text without onCompact (Action statt toter Hinweis, Phase F)', () => {
    const msgs = makeMsgs('user', 'x'.repeat(70000)) // ~16k tok > 75%
    render(<StatusBar messages={msgs} />)
    expect(screen.queryByText(/kompakt empfohlen/)).toBeNull()
  })

  it('shows the Compact-Button at high usage WHEN onCompact geparlt', () => {
    const onCompact = vi.fn()
    const msgs = makeMsgs('user', 'x'.repeat(70000)) // ~16k tok > 75%
    render(<StatusBar messages={msgs} onCompact={onCompact} />)
    const btn = screen.getByRole('button', { name: /Compact/i })
    fireEvent.click(btn)
    expect(onCompact).toHaveBeenCalledTimes(1)
  })

  it('no Compact-Button ohne onCompact (backwards-kompatibel)', () => {
    const msgs = makeMsgs('user', 'x'.repeat(70000))
    render(<StatusBar messages={msgs} />)
    expect(screen.queryByRole('button', { name: /Compact/i })).toBeNull()
  })

  // W2: the e2e route answers /api/context/budget with '{}' (truthy but partial).
  // The meter has to fall back to the offline estimate instead of crashing on
  // undefined.toLocaleString().
  it('W2: Partial-Budget {} faellt auf die Offline-Schaetzung zurueck', () => {
    const msgs = makeMsgs('user', 'x'.repeat(4200)) // ~1000 tok → 12%
    render(<StatusBar messages={msgs} />)
    expect(screen.getByText(/12%/)).toBeTruthy()
  })

  it('shows the breakdown when expanded', () => {
    const msgs = makeMsgs('assistant', 'a'.repeat(420)) // ~100 tok
    render(<StatusBar messages={msgs} />)
    fireEvent.click(screen.getByTitle(/token breakdown/i))
    expect(screen.getByText(/U \d|A \d|S \d/)).toBeTruthy()
  })

  it('zeigt tokens/sec nur während Streaming (aktive Assistant-Message)', () => {
    const streaming: ChatMessage[] = [
      {
        id: 'a-1',
        role: 'assistant',
        content: 'x'.repeat(4200), // ~1000 tok
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

  it('DD-10: kompakter tok-Chip ist auch auf Mobile da (lg:hidden Gegenstueck zum Breakdown-Button)', () => {
    render(<StatusBar messages={makeMsgs('user', 'x'.repeat(420))} />)
    const chip = screen.getByTestId('statusbar-tok-chip')
    expect(chip.textContent).toMatch(/\d[\d,.]* tok/)
    // QD-015 V1: the pair moved to lg — md belongs to the free-token figure now,
    // so the compact chip still covers the whole range below the breakdown.
    expect(chip.className).toContain('lg:hidden')
    expect(screen.getByTitle(/token breakdown/i).className).toContain('lg:flex')
  })

  it('DD-10b: ein Klick auf den Chip oeffnet das Rollen-Breakdown (U/A/S)', () => {
    render(<StatusBar messages={makeMsgs('user', 'x'.repeat(420))} />)
    fireEvent.click(screen.getByTestId('statusbar-tok-chip'))
    expect(screen.getByText(/U \d|A \d|S \d/)).toBeTruthy()
  })

  it('R44/P3: Speicher-Pille zaehlt Sessions mit MB-Schaetzung aus dem Store', () => {
    render(<StatusBar messages={makeMsgs('user', 'x'.repeat(42))} />)
    const chip = screen.getByTestId('statusbar-storage-chip')
    expect(chip.textContent).toMatch(/2 sessions/)
    expect(chip.textContent).toMatch(/\d+(\.\d+)? MB/)
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
    expect(screen.getByTestId('agent-status-expand')).toBeTruthy()
    const statusEls = screen.getAllByRole('status')
    expect(
      statusEls.some((e) => (e.getAttribute('aria-label') || '').includes('chat.connected')),
    ).toBeTruthy()
  })
})
