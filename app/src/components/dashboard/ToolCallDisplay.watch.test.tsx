/**
 * The boot 404 (measured 2026-11-10 on the live crawl): a restored, failed
 * `web_search` card opened with the chat, and every web-family card rendered
 * `BrowserWatch` — a stream for a browser session that a search never opened.
 * The route answered `404 GET /api/browser/watch/default` on every boot.
 *
 * Two rules hold the fix: only a `browser_*` step owns a page, and only a turn
 * that streams in this page life opens its stream by itself. A restored step
 * keeps its page one click away.
 */
import { describe, expect, it, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
  BrowserWatch: ({ session }: { session: string }) => (
    <div data-testid="browser-watch">{session}</div>
  ),
}))

function tool(partial: Partial<ToolCall> & { id: string; name: string }): ToolCall {
  return { args: {}, status: 'completed', ...partial }
}

describe('a search is not a page', () => {
  it('never opens a watch for a failed web_search that is open by default', () => {
    render(
      <ToolCallDisplay
        live
        tool_calls={[
          tool({
            id: '1',
            name: 'web_search',
            status: 'failed',
            args: { query: 'weather' },
            result: 'fetch failed',
          }),
        ]}
      />,
    )
    // The failure card is open on its own — the old path asked for `default` here.
    expect(screen.getByTestId('tool-card').getAttribute('data-family')).toBe('web')
    expect(screen.queryByTestId('browser-watch')).toBeNull()
    expect(screen.queryByTestId('run-watch')).toBeNull()
    expect(screen.queryByTestId('browser-watch-open')).toBeNull()
  })
})

describe('a restored browser step waits for the reader', () => {
  it('opens the page on click, not at mount, when the turn is not streaming', () => {
    render(
      <ToolCallDisplay
        live={false}
        tool_calls={[tool({ id: '1', name: 'browser_go', args: { url: 'https://x.test' } })]}
      />,
    )
    fireEvent.click(screen.getByLabelText(/browser_go Details/))
    expect(screen.queryByTestId('browser-watch')).toBeNull()
    const open = screen.getByTestId('browser-watch-open')
    fireEvent.click(open)
    expect(screen.getByTestId('browser-watch').textContent).toBe('default')
  })

  it('opens by itself while the turn streams', () => {
    render(
      <ToolCallDisplay
        live
        tool_calls={[tool({ id: '1', name: 'browser_go', args: { url: 'https://x.test' } })]}
      />,
    )
    fireEvent.click(screen.getByLabelText(/browser_go Details/))
    expect(screen.getByTestId('browser-watch').textContent).toBe('default')
  })

  it('does not resurrect a pending step of a run that ended with the last tab', () => {
    render(
      <ToolCallDisplay
        live={false}
        tool_calls={[
          tool({ id: '1', name: 'browser_go', status: 'pending', args: { url: 'https://x.test' } }),
        ]}
      />,
    )
    // The calm row keeps a restored step folded, so the reader opens it first; what the rule
    // forbids is a stream at mount, not the details.
    fireEvent.click(screen.getByLabelText(/browser_go Details/))
    expect(screen.queryByTestId('run-watch')).toBeNull()
    expect(screen.queryByTestId('browser-watch')).toBeNull()
    expect(screen.getByTestId('browser-watch-open')).toBeTruthy()
  })
})
