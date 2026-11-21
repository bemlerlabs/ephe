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
import { seedDeepSettings } from '@/lib/deepSettings'
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

describe('MessageBubble turn head (P6 timeline, ref-01)', () => {
  it('shows Worked for with the measured duration and folds the timeline', () => {
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

  it('a streaming turn shows Working for with a spinner and does not collapse', () => {
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

  it('without a duration and a stream there is no head (legacy messages stay quiet)', () => {
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

/**
 * I6-3: `chat.duration_format` is the display form of the durations the product
 * shows. The head is the duration a person reads most often, so it follows the
 * dial; a turn that ended inside a second keeps its millisecond read in both
 * forms, because „512ms" is an instrument fact and „0s" is a wrong answer.
 */
function seedDurationFormat(value: string | null) {
  if (value === null) {
    seedDeepSettings(null)
    return
  }
  seedDeepSettings([
    {
      key: 'chat',
      fields: [
        {
          key: 'chat.duration_format',
          type: 'select',
          label: 'Duration format',
          labelEn: 'Duration format',
          default: 'compact',
          value,
        },
      ],
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ] as any)
}

function finishedWith(ms: number): ChatMessage {
  return { ...FINISHED, id: `dial-${ms}`, durationMs: ms }
}

describe('MessageBubble turn head and chat.duration_format (I6-3)', () => {
  it('the dial on clock puts the finished head on a clock', () => {
    seedDurationFormat('clock')
    try {
      render(<MessageBubble message={finishedWith(134_000)} />)
      expect(screen.getByTestId('bubble-turn-head').textContent).toContain('chat.turnWorked<02:14>')
    } finally {
      seedDurationFormat(null)
    }
  })

  it('the dial on compact keeps the terse Ephe norm on the head', () => {
    seedDurationFormat('compact')
    try {
      render(<MessageBubble message={finishedWith(134_000)} />)
      expect(screen.getByTestId('bubble-turn-head').textContent).toContain(
        'chat.turnWorked<2m 14s>',
      )
    } finally {
      seedDurationFormat(null)
    }
  })

  it('the live head takes the dial too', () => {
    seedDurationFormat('clock')
    try {
      render(
        <MessageBubble
          message={{
            id: 'dial-live',
            role: 'assistant',
            content: 'teil',
            timestamp: Date.now() - 70_000,
            streaming: true,
            tool_calls: TOOLS,
          }}
        />,
      )
      expect(screen.getByTestId('bubble-turn-head').textContent).toContain(
        'chat.turnWorking<01:10>',
      )
    } finally {
      seedDurationFormat(null)
    }
  })

  it('below a second the head keeps the millisecond read in both forms', () => {
    try {
      for (const form of ['compact', 'clock'] as const) {
        seedDurationFormat(form)
        const first = render(<MessageBubble message={finishedWith(512)} />)
        expect(first.getByTestId('bubble-turn-head').textContent).toContain(
          'chat.turnWorked<512ms>',
        )
        first.unmount()
      }
    } finally {
      seedDurationFormat(null)
    }
  })

  it('with no register stored the head stays on the terse norm', () => {
    seedDurationFormat(null)
    render(<MessageBubble message={finishedWith(3_852_000)} />)
    expect(screen.getByTestId('bubble-turn-head').textContent).toContain('chat.turnWorked<1h 4m>')
  })
})
