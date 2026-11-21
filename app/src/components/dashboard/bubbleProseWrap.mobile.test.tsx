/**
 * WS3-20 responsive/mobile pass: long unbroken tokens (URLs, paths) in a message
 * must wrap instead of running past the bubble edge, where `body { overflow-x:
 * hidden }` would clip them with no way to scroll back.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'

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
vi.mock('@/lib/api', () => ({
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts_test.mp3')),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

import { useChatStore } from '@/store/chatStore'

beforeEach(() => {
  useChatStore.setState({ sessions: [], activeSessionId: null, checkpoints: {} })
})

describe('responsive pass — message prose wraps long tokens', () => {
  it('user bubble prose carries break-words', () => {
    const { container } = render(
      <MessageBubble role="user" content="https://example.com/averylongurl" />,
    )
    const prose = container.querySelector('.prose')
    expect(prose).toBeTruthy()
    expect(String(prose!.className)).toContain('break-words')
  })

  it('assistant bubble prose carries break-words', () => {
    const { container } = render(<MessageBubble role="assistant" content="ok" />)
    const prose = container.querySelector('.prose')
    expect(prose).toBeTruthy()
    expect(String(prose!.className)).toContain('break-words')
  })
})
