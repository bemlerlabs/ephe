/**
 * P6-Timeline (ref-01): the turn head on the assistant bubble.
 *
 * GIVEN  a finished assistant turn with measured wall time and tool rows
 * WHEN   the head gets rendered
 * THEN   it shows „Worked for …" (chat.turnWorked) with a chevron; one click
 *        collapses the event rows (bubble-timeline) while the answer stays.
 *        During streaming the head reads „Working for …" with a spinner.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from './MessageBubble'
import type { ChatMessage, ToolCall } from '@/types'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'time' in opts ? `${key}<${opts.time}>` : key,
    i18n: { language: 'de' },
  }),
}))

const TOOLS: ToolCall[] = [
  {
    id: 't1',
    name: 'run_shell',
    args: { command: 'ls' },
    status: 'completed',
    duration_ms: 1200,
  },
]

const FINISHED: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: 'Fertige Antwort',
  timestamp: Date.now() - 140_000,
  durationMs: 134_000,
  streaming: false,
  tool_calls: TOOLS,
}

describe('MessageBubble Turn-Kopf (P6-Timeline, ref-01)', () => {
  it('zeigt Worked for mit gemessener Dauer und klappt die Timeline zu', () => {
    render(<MessageBubble message={FINISHED} />)
    const head = screen.getByTestId('bubble-turn-head')
    expect(head.textContent).toContain('chat.turnWorked')
    expect(head.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByTestId('bubble-timeline')).toBeTruthy()
    expect(screen.getByTestId('tool-stream-rows')).toBeTruthy()

    fireEvent.click(head)
    expect(head.getAttribute('aria-expanded')).toBe('false')
    // the event rows are gone (hidden class), the answer text stays visible
    const timeline = screen.getByTestId('bubble-timeline')
    expect(timeline.className).toContain('hidden')
    expect(screen.getByText('Fertige Antwort')).toBeTruthy()
  })

  it('streamender Turn zeigt Working for mit Spinner und kollabiert nicht', () => {
    render(
      <MessageBubble
        message={{
          id: 'a2',
          role: 'assistant',
          content: 'teil',
          timestamp: Date.now() - 4_000,
          streaming: true,
          tool_calls: TOOLS,
        }}
      />,
    )
    const head = screen.getByTestId('bubble-turn-head')
    expect(head.textContent).toContain('chat.turnWorking')
    expect(head.querySelector('.animate-spin')).toBeTruthy()
    fireEvent.click(head)
    expect(screen.getByTestId('bubble-timeline').className).not.toContain('hidden')
  })

  it('ohne Dauer und ohne Stream kein Kopf (Legacy-Messages bleiben ruhig)', () => {
    render(
      <MessageBubble
        message={{
          id: 'a3',
          role: 'assistant',
          content: 'alt',
          timestamp: Date.now(),
          streaming: false,
        }}
      />,
    )
    expect(screen.queryByTestId('bubble-turn-head')).toBeNull()
  })
})
