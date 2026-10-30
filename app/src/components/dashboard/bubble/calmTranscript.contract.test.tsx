/**
 * PAKET X6.1 — the calm-transcript contract.
 *
 * A finished assistant turn may render: one run line, the answer prose, and
 * file/artifact capsules. Anything that already has a home in the right-side
 * panel (replay steps, subagent rows, a second iframe preview) must not come
 * back into the transcript.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', () => ({
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts_test.mp3')),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  getCapabilities: vi.fn(async () => ({ subagent: { tool_count: null } })),
  fileUrl: (p: string) => `/api/files/${p}`,
  artifactFileUrl: (id: string) => `/api/artifacts/${id}`,
  ApiError: class ApiError extends Error {
    status = 0
  },
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}<${JSON.stringify(opts)}>` : key,
    i18n: { language: 'de' },
  }),
}))

const RICH_TURN: ChatMessage = {
  id: 'rich',
  role: 'assistant',
  content: 'Der Bericht ist fertig.\n\n```py\nprint(1)\n```',
  timestamp: Date.now() - 5000,
  durationMs: 3800,
  streaming: false,
  tool_calls: [
    {
      id: 't1',
      name: 'edit_file',
      args: { path: 'app/src/a.ts' },
      result: '--- a.ts\n+++ a.ts\n@@\n+const a = 1\n-old = 0\n',
      status: 'done',
    } as unknown as NonNullable<ChatMessage['tool_calls']>[number],
  ],
  activities: [
    { id: 'sa1', label: 'SubAgent e1 (explore)', status: 'done' },
    { id: 'f1', label: 'report.html', path: '/tmp/report.html', status: 'done', fileType: 'html' },
  ],
  artifacts: [
    {
      id: 'art1',
      artifact_type: 'code_py',
      content: 'print(1)',
      language: 'python',
      title: 'demo.py',
      filename: 'demo.py',
    },
  ],
} as ChatMessage

describe('calm transcript contract (PAKET X6.1)', () => {
  it('renders one run line, prose and capsules — no panel content in the bubble', () => {
    render(<MessageBubble message={RICH_TURN} />)

    expect(document.querySelectorAll('[data-testid="diff-summary-line"]')).toHaveLength(1)
    expect(screen.getByTestId('replay-link')).toBeTruthy()

    // panel-only content
    expect(document.querySelector('[data-testid^="tool-replay-kader"]')).toBeNull()
    expect(document.querySelector('[data-testid="agent-activity-rows"]')).toBeNull()
    expect(document.querySelector('iframe')).toBeNull()
    expect(document.querySelector('.h-72')).toBeNull()

    // the artifact is a one-line way into the panel, not a second code dump
    expect(screen.getByTestId('message-artifact-art1')).toBeTruthy()
    expect(screen.getByTestId('artifact-open-panel')).toBeTruthy()
  })
})
