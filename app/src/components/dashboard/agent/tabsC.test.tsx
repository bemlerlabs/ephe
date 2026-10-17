/**
 * tabsC — TerminalTab (the implementation currently lives in ./terminalTab;
 * tabsC.tsx is a re-export rail — imported via './tabsC' so the rail stays
 * under test too).
 *
 * What this block pins:
 *  1 mode live/history — LiveTerminal is xterm/WebSocket-bound, so jsdom only
 *    gets a marker mock; prompt + history list exist only in history mode
 *  2 history empty state incl. the ls / git status code words
 *  3 run cards: $ + command in the head, output through the REAL renderAnsi,
 *    '…' for empty/missing output
 *  4 prompt submit: trim, clear, disabled matrix (empty input / busy)
 *  5 ↑/↓ recall: counter (pos/total), clamping, dedupe, the 30-command cap
 *
 * The DE strings below are copied from src/locales/de.json so assertions read
 * real user-facing words instead of i18n keys.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const DE: Record<string, string> = {
  'agentPanel.terminalLive': 'Live',
  'agentPanel.terminalHistory': 'History',
  'agentPanel.terminalEmptyBefore': 'No actions. Type a whitelisted command below (e.g.',
  'agentPanel.terminalEmptyAfter': '— or let the agent run one.',
  'agentPanel.terminalBusy': '… running',
  'agentPanel.terminalPlaceholder': 'Enter a command and press Enter (whitelisted)',
  'agentPanel.terminalCommandLabel': 'Shell command',
  'agentPanel.terminalRun': 'Run',
  'agentPanel.workspace': 'Workspace',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'de' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      // Like the real i18next: {{placeholders}} are filled from the options.
      const raw = DE[key] ?? (o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        o && o[name] !== undefined ? String(o[name]) : `{{${name}}}`,
      )
    },
  }),
}))

// xterm.js (fed by a PTY WebSocket) cannot run under jsdom — the live pane
// becomes a marker div.
vi.mock('./LiveTerminal', () => ({
  default: () => <div data-testid="live-terminal" />,
}))

// @/lib/api for everything the transitively loaded modules pull in:
// terminalTab via primitives (getSettings in useWorkspaceDir), plus the
// re-exported reviewTab + DiffView (loaded through './tabsC').
vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ workspace_dir: '/ws' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({})),
  updateTask: vi.fn(async () => ({})),
  deleteTask: vi.fn(async () => ({ success: true })),
  gitStatus: vi.fn(async () => ({ branch: 'main', files: [] })),
  gitDiff: vi.fn(async () => ({ diff: '' })),
  gitAdd: vi.fn(async () => ({ added: [] })),
  gitCommit: vi.fn(async () => ({ committed: true })),
  gitApplyPatch: vi.fn(async () => ({ applied: true })),
  wsUrl: vi.fn((path: string) => `ws://test${path}`),
}))

import { TerminalTab } from './tabsC'

type Run = { id: string; command: string; result?: string }

const input = () => screen.getByTestId('terminal-prompt-input') as HTMLInputElement
const runButton = () => screen.getByRole('button', { name: 'Run' })
const counter = () => screen.queryByTestId('terminal-recall-counter')

/** Renders TerminalTab and switches to history mode (where list + prompt live). */
function renderHistory(
  over: Partial<{ runs: Run[]; busy: boolean; onSubmit: (command: string) => void }> = {},
) {
  const onSubmit = over.onSubmit ?? vi.fn()
  const view = render(
    <TerminalTab runs={over.runs ?? []} busy={over.busy ?? false} onSubmit={onSubmit} />,
  )
  fireEvent.click(screen.getByTestId('terminal-mode-history'))
  return { onSubmit, ...view }
}

function submit(command: string) {
  fireEvent.change(input(), { target: { value: command } })
  fireEvent.keyDown(input(), { key: 'Enter' })
}

function arrow(key: 'ArrowUp' | 'ArrowDown') {
  fireEvent.keyDown(input(), { key })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TerminalTab — live/history mode', () => {
  it('starts in live mode (LiveTerminal visible, no prompt) with the labels', () => {
    render(<TerminalTab runs={[]} busy={false} onSubmit={vi.fn()} />)
    expect(screen.getByTestId('live-terminal')).toBeInTheDocument()
    expect(screen.queryByTestId('terminal-prompt-input')).toBeNull()
    expect(screen.getByTestId('terminal-mode-live')).toHaveTextContent('Live')
    expect(screen.getByTestId('terminal-mode-history')).toHaveTextContent('History')
  })

  it('a history click shows the list + prompt without LiveTerminal; a live click switches back', () => {
    render(<TerminalTab runs={[]} busy={false} onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByTestId('terminal-mode-history'))
    expect(screen.queryByTestId('live-terminal')).toBeNull()
    expect(input()).toBeInTheDocument()
    expect(runButton()).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('terminal-mode-live'))
    expect(screen.getByTestId('live-terminal')).toBeInTheDocument()
    expect(screen.queryByTestId('terminal-prompt-input')).toBeNull()
  })
})

describe('TerminalTab — history list', () => {
  it('an empty history shows the empty state with ls / git status as code words', () => {
    const { container } = renderHistory()
    const ls = screen.getByText('ls')
    expect(ls.tagName).toBe('CODE')
    expect(screen.getByText('git status').tagName).toBe('CODE')
    expect(ls.closest('p')).toHaveTextContent(
      'No actions. Type a whitelisted command below (e.g. ls, git status — or let the agent run one.',
    )
    expect(container.querySelectorAll('pre')).toHaveLength(0)
  })

  it('run cards: $ + command in the head, ANSI result via renderAnsi, empty output shows …', () => {
    const { container } = renderHistory({
      runs: [
        { id: 'r1', command: 'ls -la', result: 'total 2\ntotal \u001b[32mfile-a\u001b[0m\n' },
        { id: 'r2', command: 'git status', result: '' },
      ],
    })
    expect(screen.getByText('ls -la').parentElement?.textContent).toBe('$ls -la')
    expect(screen.getByText('git status').parentElement?.textContent).toBe('$git status')

    const pres = container.querySelectorAll('pre')
    expect(pres).toHaveLength(2)
    // renderAnsi is real: the SGR sequence is swallowed, the text stays visible.
    expect(pres[0]?.textContent).toBe('total 2\ntotal file-a\n')
    expect(pres[0]?.textContent).not.toContain('\u001b')
    // Falsy output ('' / missing) falls back to the literal placeholder.
    expect(pres[1]?.textContent).toBe('…')
  })
})

describe('TerminalTab — Prompt (Submit)', () => {
  it('Enter submits the trimmed command and clears the field', () => {
    const { onSubmit } = renderHistory()
    fireEvent.change(input(), { target: { value: '  ls -la  ' } })
    expect(runButton()).toBeEnabled()
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith('ls -la')
    expect(input().value).toBe('')
    expect(runButton()).toBeDisabled()
  })

  it('the Run button also submits; without text it is disabled', () => {
    const { onSubmit } = renderHistory()
    expect(runButton()).toBeDisabled()
    fireEvent.change(input(), { target: { value: 'pwd' } })
    expect(runButton()).toBeEnabled()
    fireEvent.click(runButton())
    expect(onSubmit).toHaveBeenCalledWith('pwd')
    expect(input().value).toBe('')
  })

  it('whitespace only: no submit, field keeps its content, button stays disabled', () => {
    const { onSubmit } = renderHistory()
    fireEvent.change(input(), { target: { value: '   ' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
    expect(input().value).toBe('   ')
    expect(runButton()).toBeDisabled()
  })
})

describe('TerminalTab — busy-Zustand', () => {
  it('busy: input disabled, placeholder "… running", Enter triggers no submit', () => {
    const { onSubmit } = renderHistory({ busy: true })
    expect(input()).toBeDisabled()
    expect(input()).toHaveAttribute('placeholder', '… running')
    expect(runButton()).toBeDisabled()
    fireEvent.change(input(), { target: { value: 'ls' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('idle: placeholder "Enter a command and press Enter (whitelisted)", input active', () => {
    renderHistory()
    expect(input()).toBeEnabled()
    expect(input()).toHaveAttribute('placeholder', 'Enter a command and press Enter (whitelisted)')
  })
})

describe('TerminalTab — command history (↑/↓)', () => {
  it('↑ walks backward to the oldest command (clamped), ↓ forward; counter from pos>0', () => {
    renderHistory()
    submit('alpha')
    submit('beta')
    submit('gamma')
    expect(counter()).toBeNull() // after submit: pos 0 → counter hidden

    arrow('ArrowUp')
    expect(input().value).toBe('gamma')
    expect(counter()).toHaveTextContent('↑/↓ 1/3')
    arrow('ArrowUp')
    expect(input().value).toBe('beta')
    expect(counter()).toHaveTextContent('↑/↓ 2/3')
    arrow('ArrowUp')
    expect(input().value).toBe('alpha')
    expect(counter()).toHaveTextContent('↑/↓ 3/3')
    arrow('ArrowUp') // oldest entry: stays clamped
    expect(input().value).toBe('alpha')
    expect(counter()).toHaveTextContent('↑/↓ 3/3')

    arrow('ArrowDown')
    expect(input().value).toBe('beta')
    expect(counter()).toHaveTextContent('↑/↓ 2/3')
    arrow('ArrowDown')
    expect(input().value).toBe('gamma')
    expect(counter()).toHaveTextContent('↑/↓ 1/3')
    arrow('ArrowDown') // pos 0: counter gone, the input keeps the last recalled value
    expect(counter()).toBeNull()
    expect(input().value).toBe('gamma')
  })

  it('without history the arrow keys do nothing', () => {
    renderHistory()
    arrow('ArrowUp')
    arrow('ArrowDown')
    expect(input().value).toBe('')
    expect(counter()).toBeNull()
  })

  it('dedupe: the same command counts only once', () => {
    renderHistory()
    submit('ls')
    submit('ls')
    arrow('ArrowUp')
    expect(input().value).toBe('ls')
    expect(counter()).toHaveTextContent('↑/↓ 1/1')
    arrow('ArrowUp') // no second entry in the history
    expect(input().value).toBe('ls')
    expect(counter()).toHaveTextContent('↑/↓ 1/1')
  })

  it('cap: only the last 30 commands stay in the history', () => {
    renderHistory()
    for (let i = 1; i <= 31; i++) submit(`cmd-${i}`)
    arrow('ArrowUp')
    expect(input().value).toBe('cmd-31')
    expect(counter()).toHaveTextContent('↑/↓ 1/30')
    for (let i = 0; i < 29; i++) arrow('ArrowUp')
    expect(counter()).toHaveTextContent('↑/↓ 30/30')
    expect(input().value).toBe('cmd-2') // cmd-1 fell out through the 30-entry cap
    arrow('ArrowUp')
    expect(counter()).toHaveTextContent('↑/↓ 30/30')
    expect(input().value).toBe('cmd-2')
  })

  it('submit resets the recall (counter gone, field empty, history updated)', () => {
    const { onSubmit } = renderHistory()
    submit('one')
    submit('two')
    arrow('ArrowUp')
    expect(input().value).toBe('two')
    expect(counter()).toHaveTextContent('↑/↓ 1/2')

    fireEvent.keyDown(input(), { key: 'Enter' }) // submit the recalled value
    expect(onSubmit).toHaveBeenLastCalledWith('two')
    expect(input().value).toBe('')
    expect(counter()).toBeNull()

    arrow('ArrowUp') // back to pos 1
    expect(input().value).toBe('two')
    expect(counter()).toHaveTextContent('↑/↓ 1/2')
  })
})
