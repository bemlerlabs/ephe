import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ToolStreamRows } from './toolStreamRows'
import { useDeepBool, useDeepSelect } from '@/lib/deepSettings'

// UI-CHAT: a finished round is ONE line — tool name · duration · outcome. The
// arguments, the output and the proof appear only when the reader opens it,
// and the thought of the round travels inside the same row.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.roundOk': 'ok',
        'chat.rowWorking': 'Working',
        'chat.rowFailed': 'Failed',
        'chat.toolWaiting': 'Waiting for approval',
        'chat.thoughtForSeconds': 'Thought for {{duration}}',
        'chat.thoughtForSecondsCount': 'Thought for {{duration}} · {{count}} pauses',
        'chat.thinkingEmpty': 'No reasoning recorded',
        'chat.proof.expert': 'passed · {{ms}} ms',
        'chat.proof.expertNoTime': 'passed',
        'chat.proof.everyday': 'checked · {{seconds}} s',
        'chat.proof.failed': 'did not pass',
      }
      const pattern = map[key] ?? key
      if (!values) return pattern
      return pattern.replace(/\{\{(\w+)\}\}/g, (_, name) => String(values[name] ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/lib/deepSettings', () => ({
  useDeepBool: vi.fn((key: string) => key === 'chat.show_tool_count'),
  useDeepSelect: vi.fn(() => 'expanded'),
}))

vi.mock('../ToolCallDisplay', () => ({
  ToolCallDetails: () => <div data-testid="tool-details" />,
  TaskBody: () => null,
  default: () => <div data-testid="tool-cards" />,
}))

const calls = [
  { id: 't1', name: 'run_shell', args: { command: 'pytest -q' }, status: 'done', duration_ms: 13 },
  {
    id: 't2',
    name: 'run_shell',
    args: { command: 'ruff check .' },
    status: 'done',
    duration_ms: 21,
  },
  { id: 't3', name: 'run_shell', args: { command: 'echo ok' }, status: 'done', duration_ms: 4 },
]

describe('ToolStreamRows — a finished round is one calm line', () => {
  beforeEach(() => {
    vi.mocked(useDeepBool).mockImplementation((key: string) => key === 'chat.show_tool_count')
    vi.mocked(useDeepSelect).mockReturnValue('expanded')
  })

  it('summarises the round as name · duration · outcome', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.textContent).toContain('run_shell')
    expect(row.textContent).toContain('3×')
    expect(row.textContent).toContain('38ms')
    expect(row.textContent).toContain('ok')
  })

  it('keeps the proof and the details out of the collapsed row', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    expect(screen.queryByTestId('tool-row-proof')).toBeNull()
    expect(screen.queryByTestId('tool-details')).toBeNull()
  })

  it('shows the one proof once the reader opens it', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    const row = screen.getByTestId('tool-stream-row-shell')
    fireEvent.click(within(row).getByRole('button'))
    expect(within(row).getByTestId('tool-row-proof').textContent).toBe('passed · 38 ms')
    expect(within(row).getAllByTestId('tool-details')).toHaveLength(3)
  })

  it('renders no template placeholder anywhere in the row', () => {
    const { container } = render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    fireEvent.click(screen.getByTestId('tool-stream-row-shell').querySelector('button')!)
    expect(container.textContent ?? '').not.toContain('{{')
  })

  it('folds the thought that belongs to the run into the first row', () => {
    const now = Date.now()
    render(
      <ToolStreamRows
        tool_calls={calls as never}
        thoughts={[{ start: now - 6000, end: now, text: 'erst planen' }]}
        streaming={false}
      />,
    )
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(within(row).getByTestId('round-thought').textContent).toBe('6s')
    // no second chrome line for the thought
    expect(screen.getAllByTestId('round-thought')).toHaveLength(1)
  })

  it('one running row per family, each with its own spinner', () => {
    const running = [
      { id: 'a1', name: 'run_shell', args: { command: 'pytest -q' }, status: 'pending' },
      { id: 'a2', name: 'read_file', args: { path: 'README.md' }, status: 'pending' },
    ]
    render(<ToolStreamRows tool_calls={running as never} streaming startTs={Date.now()} />)
    expect(screen.queryByTestId('tool-run-header')).toBeNull()
    expect(screen.getAllByTestId('tool-row-spinner')).toHaveLength(2)
    expect(screen.getAllByTestId('tool-stream-row-active')).toHaveLength(2)
  })

  it('counts a running round done/total and keeps the live tail in the row', () => {
    const running = [
      {
        id: 't1',
        name: 'run_shell',
        args: { command: 'pytest -q' },
        status: 'done',
        duration_ms: 13,
      },
      {
        id: 't2',
        name: 'run_shell',
        args: { command: 'ruff check .' },
        status: 'pending',
        stdout: 'a\nb\nLAST',
      },
    ]
    render(
      <ToolStreamRows tool_calls={running as never} streaming startTs={Date.now() - 245_000} />,
    )
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.textContent).toContain('1/2')
    expect(within(row).getByTestId('tool-row-tail').textContent).toContain('LAST')
    expect(within(row).getByTestId('tool-row-status').textContent).toContain('Working')
  })
})
