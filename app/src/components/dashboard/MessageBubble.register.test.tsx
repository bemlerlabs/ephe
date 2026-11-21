// I3-5: two chat register values that really act on the bubble's result.
// chat.show_reasoning (show the reasoning process) and chat.details_mode
// (tool details expanded/collapsed) were fields without a reader — the bubble
// always rendered both expanded.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import MessageBubble from '@/components/dashboard/MessageBubble'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { ChatMessage, DeepField, DeepSection } from '@/types'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => (
    <div data-testid="markdown">{String(children)}</div>
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: React.ReactNode }) => <pre>{children}</pre>,
}))
vi.mock('@/lib/utils', () => ({ formatTime: () => '12:00' }))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
    i18n: { language: 'de' },
  })) as never,
}))

function register(entries: Array<[string, string | number | boolean]>) {
  const fields: DeepField[] = entries.map(([key, value]) => ({
    key,
    type: typeof value === 'boolean' ? 'bool' : 'select',
    label: key,
    labelEn: key,
    default: value,
    value,
  }))
  seedDeepSettings([{ key: 'chat', fields } as DeepSection])
}

const THINKING_MSG = {
  id: 'a1',
  role: 'assistant',
  content: 'antwort',
  timestamp: 0,
  thinking: { start: 0, end: 5000, text: 'ich habe nachgedacht' },
} as unknown as ChatMessage

const TIMELINE_MSG = {
  id: 'a2',
  role: 'assistant',
  content: 'antwort',
  timestamp: 0,
  tool_calls: [
    { id: 't1', name: 'read_file', args: { path: '/tmp/a' }, result: 'inhalt', status: 'done' },
  ],
} as unknown as ChatMessage

beforeEach(() => seedDeepSettings(null))

describe('chat.show_reasoning (I3-5)', () => {
  it('shows the thinking phase when the switch is on', () => {
    register([['chat.show_reasoning', true]])
    render(<MessageBubble message={THINKING_MSG} />)
    expect(screen.getByTestId('thinking-block')).toBeTruthy()
  })

  it('hides the thinking phase when the switch is off', () => {
    register([['chat.show_reasoning', false]])
    render(<MessageBubble message={THINKING_MSG} />)
    expect(screen.queryByTestId('thinking-block')).toBeNull()
    // The answer itself stays put — only the reasoning process gets hidden.
    expect(screen.getByTestId('markdown').textContent).toBe('antwort')
  })

  it('without the register the thinking phase stays visible', () => {
    render(<MessageBubble message={THINKING_MSG} />)
    expect(screen.getByTestId('thinking-block')).toBeTruthy()
  })
})

describe('chat.details_mode (I3-5)', () => {
  it('the tool line starts expanded', () => {
    register([['chat.details_mode', 'expanded']])
    render(<MessageBubble message={TIMELINE_MSG} />)
    expect(screen.getByTestId('bubble-timeline').className).not.toContain('hidden')
  })

  it('it starts folded when the register says collapsed', () => {
    register([['chat.details_mode', 'collapsed']])
    render(<MessageBubble message={TIMELINE_MSG} />)
    expect(screen.getByTestId('bubble-timeline').className).toContain('hidden')
  })

  it('without the register the old default holds: expanded', () => {
    render(<MessageBubble message={TIMELINE_MSG} />)
    expect(screen.getByTestId('bubble-timeline').className).not.toContain('hidden')
  })
})
