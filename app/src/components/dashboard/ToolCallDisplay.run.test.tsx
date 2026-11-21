import { describe, expect, it, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from '@/i18n'
import ToolCallDisplay from './ToolCallDisplay'
import type { ToolCall } from '@/store/chatStore'

beforeAll(async () => {
  await i18n.changeLanguage('en')
})

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => []),
}))

vi.mock('./agent/RunWatch', () => ({
  RunWatch: ({ session }: { session: string }) => <div data-testid="run-watch">{session}</div>,
}))

vi.mock('./agent/BrowserWatch', () => ({
  BrowserWatch: () => <div data-testid="browser-watch" />,
}))

function tool(partial: Partial<ToolCall> & { id: string; name: string }): ToolCall {
  return { args: {}, status: 'completed', ...partial }
}

describe('the run view comes up with a live browser step', () => {
  it('shows one run view for a pending browser step and hides the card picture', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tool({
            id: '1',
            name: 'browser_go',
            status: 'pending',
            args: { url: 'https://example.com/' },
          }),
        ]}
      />,
    )
    expect(screen.getByTestId('run-watch').textContent).toBe('default')
    expect(screen.queryByTestId('browser-watch')).toBeNull()
  })

  it('leaves a finished browser step inside the card', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tool({
            id: '1',
            name: 'browser_go',
            status: 'completed',
            args: { url: 'https://example.com/' },
          }),
        ]}
      />,
    )
    expect(screen.queryByTestId('run-watch')).toBeNull()
  })
})
