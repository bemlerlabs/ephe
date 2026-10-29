import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ToolStreamRows } from './toolStreamRows'
import { useDeepBool, useDeepSelect } from '@/lib/deepSettings'

// The run surface: a finished step is one line ("Ran 16 tools"); the detail, the
// proof and the measurement appear only when the reader opens it, and once.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.ranOneTool': 'Ran 1 tool',
        'chat.ranTools': 'Ran {{count}} tools',
        'chat.rowWorking': 'Working',
        'chat.runRunning': 'Running',
        'chat.rowFailed': 'Failed',
        'streamGroup.terminal': 'Terminal',
        'streamGroup.count': '{{count}} calls',
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
  // count on, auto-expand off: the tests open the group themselves.
  useDeepBool: vi.fn((key: string) => key === 'chat.show_tool_count'),
  useDeepSelect: vi.fn(() => 'expanded'),
}))

vi.mock('../ToolCallDisplay', () => ({
  default: () => <div data-testid="tool-cards" />,
  ICONS: new Proxy({}, { get: () => () => <svg aria-hidden="true" /> }),
}))

const calls = [
  { id: 't1', name: 'run_shell', args: { command: 'pytest -q' }, status: 'done', duration_ms: 13 },
  { id: 't2', name: 'run_shell', args: { command: 'ruff check .' }, status: 'done', duration_ms: 21 },
  { id: 't3', name: 'run_shell', args: { command: 'echo ok' }, status: 'done', duration_ms: 4 },
]

describe('ToolStreamRows — a finished step is one calm line', () => {
  beforeEach(() => {
    vi.mocked(useDeepBool).mockImplementation((key: string) => key === 'chat.show_tool_count')
    vi.mocked(useDeepSelect).mockReturnValue('expanded')
  })

  it('summarises a finished group as "Ran N tools"', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    expect(screen.getByText('Ran 3 tools')).toBeTruthy()
  })

  it('keeps the proof and the status out of the collapsed row', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    expect(screen.queryByTestId('tool-row-proof')).toBeNull()
    expect(screen.queryByTestId('tool-row-status')).toBeNull()
    expect(screen.queryByTestId('tool-duration-chip')).toBeNull()
  })

  it('shows the one measurement and the proof once the reader opens it', () => {
    render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    fireEvent.click(screen.getByText('Ran 3 tools'))
    expect(screen.getByTestId('tool-row-proof').textContent).toBe('passed · 38 ms')
    // The proof carries the number; a second duration chip would state it twice.
    expect(screen.queryByTestId('tool-duration-chip')).toBeNull()
    expect(screen.getByTestId('tool-cards')).toBeTruthy()
  })

  it('renders no template placeholder anywhere in the row', () => {
    const { container } = render(<ToolStreamRows tool_calls={calls as never} streaming={false} />)
    fireEvent.click(screen.getByText('Ran 3 tools'))
    expect(container.textContent ?? '').not.toContain('{{')
  })

  it('prints the run clock once for a block with two running families', () => {
    const running = [
      { id: 'a1', name: 'run_shell', args: { command: 'pytest -q' }, status: 'pending' },
      { id: 'a2', name: 'read_file', args: { path: 'README.md' }, status: 'pending' },
    ]
    render(<ToolStreamRows tool_calls={running as never} streaming startTs={Date.now()} />)
    expect(screen.getAllByTestId('tool-run-header')).toHaveLength(1)
    expect(screen.getAllByTestId('tool-row-spinner')).toHaveLength(2)
  })

  it('opens the running step, counts its time and keeps one live duration', () => {
    const running = [
      { id: 't1', name: 'run_shell', args: { command: 'pytest -q' }, status: 'done', duration_ms: 13 },
      { id: 't2', name: 'run_shell', args: { command: 'ruff check .' }, status: 'pending' },
    ]
    render(<ToolStreamRows tool_calls={running as never} streaming startTs={Date.now() - 245_000} />)
    // The running step shows its work without a click, and the header counts from
    // the turn's first frame (the reference block reads "Running · 245s").
    expect(screen.getByTestId('tool-run-header').textContent).toContain('Running')
    expect(screen.getByTestId('tool-run-header').textContent).toContain('4m 5s')
    expect(screen.getByTestId('tool-cards')).toBeTruthy()
    expect(screen.getByTestId('tool-row-spinner')).toBeTruthy()
    expect(screen.getByTestId('tool-row-status').textContent).toContain('Working')
    expect(screen.getByTestId('tool-duration-chip')).toBeTruthy()
    expect(screen.queryByTestId('tool-row-proof')).toBeNull()
  })
})
