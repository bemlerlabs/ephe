/**
 * F2: the two context numbers that were only reachable by hover.
 *
 * Measured 2026-10-10 at 390x844: the meter's source sentence lived in a `title`
 * and the composer ring was an `aria-hidden` arc inside a plain div — `aria-label`
 * null, `role` null. A tooltip never renders on a phone, so both facts existed only
 * for someone with a mouse. After: the popover the token pill opens says the source
 * out loud, and the ring wrapper carries `role="img"` with the same sentence as its
 * name (`f2-after-5173-popover-390.png`, `f2-proof.json`).
 *
 * jsdom cannot hover either, which is exactly why the assertion is about the DOM:
 * a name that is present is reachable by keyboard and by a screen reader, a title
 * is not.
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, fireEvent } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { contextRingLabel } from '@/components/dashboard/ChatInput'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getContextBudget: vi.fn(
      async () =>
        ({
          window_tokens: 8192,
          window_source: 'env',
          estimated_tokens: 5950,
          percent: 72.63,
          message_count: 12,
          tokenizer: 'tiktoken-bpe',
          compaction_active: false,
          breakdown: [],
        }) as never,
    ),
  }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({ sessions: [], currentSession: null, enginePricing: null, lastTurnUsage: null }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'statusBar.windowSetting': `Window ${String(opts?.window)} · from your setting`,
        'statusBar.contextWindowTitle': 'Context windows',
        'statusBar.breakdownHint': 'Token breakdown',
        'chat.contextRing': `Context used: ${String(opts?.percent)}%`,
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  }),
}))

const messages: ChatMessage[] = [
  { id: 'm1', role: 'user', content: 'one', timestamp: Date.now() },
  { id: 'm2', role: 'assistant', content: 'two', timestamp: Date.now() },
] as ChatMessage[]

describe('the context popover', () => {
  it('says where the window number comes from, without a hover', async () => {
    render(<StatusBar messages={messages} sessionId="s1" backendOnline engineOnline />)
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    const line = await screen.findByTestId('statusbar-window-source')
    expect(line.textContent).toContain('from your setting')
    expect(line.textContent).toContain('8,192')
  })
})

describe('contextRingLabel', () => {
  // Rendering the composer for one attribute is not worth its import graph, so
  // the second half of the rule is held as a source contract: the name must be
  // wired to the ring's wrapper, not only to exist as a function.
  // P3 wave 2026-10-05: the composer was split into submodules — the ring
  // wrapper lives in chat/ComposerSendButton.tsx now (the public name still
  // comes from ChatInput.tsx); the contract follows the wiring.
  const RING_WRAPPER = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), 'chat', 'ComposerSendButton.tsx'),
    'utf8',
  )

  it('is wired to the ring wrapper as its accessible name', () => {
    expect(RING_WRAPPER).toMatch(
      /aria-label=\{contextRingLabel\(t, contextPercent, i18n\.language\)\}/,
    )
    expect(RING_WRAPPER).toMatch(/role="img"/)
  })

  it('names the ring with the percent it draws', () => {
    expect(contextRingLabel((_, o) => `Context used: ${String(o?.percent)}%`, 3.75)).toBe(
      'Context used: 3.8%',
    )
    expect(contextRingLabel((_, o) => `Context used: ${String(o?.percent)}%`, 42.6)).toBe(
      'Context used: 43%',
    )
    expect(contextRingLabel((_, o) => `Context used: ${String(o?.percent)}%`, null)).toBe(
      'Context used: 0.0%',
    )
  })
})
