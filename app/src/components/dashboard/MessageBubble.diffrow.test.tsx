/**
 * M3 (reference parity): one diff-stat line per run —
 * "N files changed +A −D  ↶ Undo" as the last line of the assistant bubble.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
  useTranslation: (() => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
    i18n: { language: 'de' },
  })) as never,
}))

import type { ChatMessage } from '@/types'
import { useChatStore } from '@/store/chatStore'
import { createCheckpoint } from '@/lib/checkpoints'

const TOOL_MSG: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: 'erledigt',
  timestamp: 0,
  tool_calls: [
    {
      id: 't1',
      name: 'edit_file',
      args: { path: '/tmp/a.ts' },
      result: '--- a.ts\n+++ a.ts\n@@\n+const x = 1\n+const y = 2\n+const z = 3\n-old = 0\n',
    } as unknown as NonNullable<ChatMessage['tool_calls']>[number],
  ],
} as ChatMessage

beforeEach(() => {
  useChatStore.setState({ sessions: [], activeSessionId: null, checkpoints: {} })
})

describe('Diff-Stat-Zeile (M3)', () => {
  it('rendert Dateien + Plus/Minus nach der Tool-Gruppe; ohne Checkpoints kein Undo (F-9)', () => {
    render(<MessageBubble message={TOOL_MSG} />)
    const line = screen.getByTestId('diff-summary-line')
    expect(line).toBeTruthy()
    expect(screen.getByTestId('diff-summary-files').textContent).toContain('agentPanel.diffFiles:1')
    expect(screen.getByTestId('diff-summary-add').textContent).toBe('+3')
    expect(screen.getByTestId('diff-summary-del').textContent).toBe('-1')
    expect(screen.queryByTestId('diff-summary-undo')).toBeNull()
  })

  it('ohne Datei-Calls: keine Stat-Zeile', () => {
    render(
      <MessageBubble
        message={{ id: 'a2', role: 'assistant', content: 'x', timestamp: 0 } as ChatMessage}
      />,
    )
    expect(screen.queryByTestId('diff-summary-line')).toBeNull()
  })

  it('Undo rollt die Session auf den letzten Checkpoint zurueck', () => {
    const snapshot: ChatMessage[] = [
      { id: 's1m1', role: 'user', content: 'vorher', timestamp: 0 } as ChatMessage,
    ]
    const cp = createCheckpoint(snapshot, 'cp1')
    useChatStore.setState({
      sessions: [{ id: 's1', title: 'T', createdAt: 0, messages: [snapshot[0]!, TOOL_MSG] }],
      activeSessionId: 's1',
      currentSession: { id: 's1', title: 'T', createdAt: 0, messages: [snapshot[0]!, TOOL_MSG] },
      checkpoints: { s1: [cp] },
    })
    render(<MessageBubble message={TOOL_MSG} />)
    fireEvent.click(screen.getByTestId('diff-summary-undo'))
    const st = useChatStore.getState()
    expect(st.currentSession?.messages).toHaveLength(1)
  })
})
