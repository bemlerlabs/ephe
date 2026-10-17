/**
 * B2 (persona audit 2026-10-10): a `system` row in the transcript is Ephe's own
 * context — the working-memory ledger compaction writes — and it used to render
 * with Ephe's avatar, `data-role="assistant"` and no word saying what it is.
 * These cases hold the distinction the audit asked for: labelled, reachable,
 * collapsed by default, and never dressed as the answer.
 */
import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'

vi.mock('react-markdown', () => ({
  default: vi.fn(({ children }: { children: ReactNode }) => (
    <div data-testid="markdown">{String(children)}</div>
  )),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: ReactNode }) => <pre>{children}</pre>,
}))
vi.mock('@/lib/utils', () => ({ formatTime: () => '12:00' }))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
    i18n: { language: 'en' },
  })) as never,
}))

import type { ChatMessage } from '@/types'

const LEDGER = [
  'Working Memory Ledger for Ephe.',
  'Use this compact context as durable state; do not expose it verbatim.',
  '',
  '## User preferences',
  '- no stable facts recognised',
  '',
  '## Project facts',
  '- the deck lives in the downloads folder',
].join('\n')

function systemMsg(content: string): ChatMessage {
  return { id: 's1', role: 'system', content, timestamp: 0 } as ChatMessage
}

const bubble = () => screen.getByTestId('message-bubble')

describe('MessageBubble with a system row', () => {
  it('reports the row as system, which is what the old form got wrong', () => {
    render(<MessageBubble message={systemMsg(LEDGER)} />)
    expect(bubble().getAttribute('data-role')).toBe('system')
    expect(screen.getByTestId('system-context-block')).toBeTruthy()
  })

  it('says in words what the block is, and how much of it there is', () => {
    render(<MessageBubble message={systemMsg(LEDGER)} />)
    const toggle = screen.getByTestId('system-context-toggle')
    expect(toggle.textContent).toContain('chat.systemContext')
    expect(toggle.textContent).toContain(
      `chat.systemContextSize ${JSON.stringify({ chars: LEDGER.length })}`,
    )
  })

  it('holds the ledger back until the reader asks for it', () => {
    render(<MessageBubble message={systemMsg(LEDGER)} />)
    expect(screen.queryByTestId('system-context-body')).toBeNull()
    fireEvent.click(screen.getByTestId('system-context-toggle'))
    const body = screen.getByTestId('system-context-body')
    expect(body.textContent).toContain('Working Memory Ledger for Ephe.')
    expect(screen.getByTestId('system-context-toggle').getAttribute('aria-expanded')).toBe('true')
  })

  it('leaves a one-line system note open — it is a sentence, not a ledger', () => {
    render(
      <MessageBubble message={systemMsg('Context compacted — older messages were summarized.')} />,
    )
    expect(screen.getByTestId('system-context-body').textContent).toContain('Context compacted')
    expect(screen.getByTestId('system-context-toggle').getAttribute('aria-expanded')).toBe('true')
  })

  it('answers are untouched by the distinction', () => {
    render(
      <MessageBubble
        message={
          {
            id: 'a1',
            role: 'assistant',
            content: 'Here is the answer.',
            timestamp: 0,
          } as ChatMessage
        }
      />,
    )
    expect(bubble().getAttribute('data-role')).toBe('assistant')
    expect(screen.queryByTestId('system-context-block')).toBeNull()
    expect(screen.getByTestId('markdown').textContent).toContain('Here is the answer.')
  })
})
