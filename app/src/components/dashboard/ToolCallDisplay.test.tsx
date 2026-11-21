/**
 * Ephe — round E (reference-B parity Z01–Z06): ToolCallDisplay cards.
 *
 * GIVEN  tool calls of the shell/edit/write/task/generic families
 * WHEN   rendered (unclosed as well as collapsed)
 * THEN   summary line with icon+verb+target, family details (terminal block,
 *        diff+stats, CodeBlock, checklist), exit chip, open-in-preview.
 */
import { describe, it, expect, beforeAll, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import i18n from '@/i18n'
import ToolCallDisplay from './ToolCallDisplay'
import type { ToolCall } from '@/store/chatStore'

const taskList = [
  { id: 't1', title: 'Readme schreiben', status: 'done', project: null },
  { id: 't2', title: 'Tests gruen', status: 'pending', project: null },
]
const researchApi = vi.hoisted(() => ({
  getResearchEvidence: vi.fn(
    async (): Promise<{
      ok: boolean
      runs: unknown[]
      sources: unknown[]
      workspace: unknown[]
      total: number
    }> => ({
      ok: true,
      runs: [],
      sources: [],
      workspace: [],
      total: 0,
    }),
  ),
}))

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => taskList),
  getResearchEvidence: researchApi.getResearchEvidence,
}))

function tc(partial: Partial<ToolCall> & { id: string }): ToolCall {
  return { name: 'run_shell', args: {}, status: 'completed', ...partial }
}

const SAMPLE_DIFF = [
  '--- a/README.md',
  '+++ b/README.md',
  '@@ -1,2 +1,3 @@',
  ' # Titel',
  '+## Neu',
  '-alt',
].join('\n')

afterEach(cleanup)

describe('ToolCallDisplay: the summary line (Z01)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders a badge with the tool name', () => {
    render(
      <ToolCallDisplay tool_calls={[tc({ id: '1', name: 'read_file', args: { path: '/a' } })]} />,
    )
    expect(screen.getByText('read_file')).toBeInTheDocument()
  })

  it('shows the human target in the summary without a click (shell: the command)', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'run_shell',
            args: { command: 'npm test' },
            result: 'ok',
            status: 'completed',
          }),
        ]}
      />,
    )
    // UI-CHAT: the row is name · duration · outcome; the human target is one
    // level down, in the body the chevron opens.
    fireEvent.click(screen.getByRole('button', { name: 'run_shell Details' }))
    expect(screen.getByTestId('tool-target').textContent).toBe('npm test')
    expect(screen.queryByText(/"command"/)).not.toBeInTheDocument()
  })

  it('is not expandable without args and without a result', () => {
    render(<ToolCallDisplay tool_calls={[tc({ id: '1', name: 'noop' })]} />)
    expect(screen.getByText('noop')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'noop Details' })).not.toBeInTheDocument()
  })

  it('shows the approval label at status waiting', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({ id: '1', name: 'run_shell', args: { command: 'rm -rf x' }, status: 'waiting' }),
        ]}
      />,
    )
    // I6 P2c: no raw enum in the UI any more — the waiting label comes translated from i18n.
    expect(screen.getByTestId('tool-outcome').textContent).toContain('Waiting for approval')
  })
})

describe('ToolCallDisplay: the shell terminal block (Z02)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('expands to a dollar command line with a copy button and the output', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'run_shell',
            args: { command: 'ls -la' },
            result: 'total 3',
            status: 'completed',
          }),
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'run_shell Details' }))
    expect(screen.getByTestId('tool-cmdline').textContent).toContain('ls -la')
    expect(screen.getByTestId('tool-copy-cmd')).toBeTruthy()
    expect(screen.getByText('total 3')).toBeInTheDocument()
  })

  it('an exit chip on failure with a Paris body (the suffix appears once)', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'run_shell',
            args: { command: 'pnpm test' },
            result: 'fail out\n[exit 1] boom',
            status: 'completed',
          }),
        ]}
      />,
    )
    // Failure opens the card automatically — the output is visible at once.
    expect(screen.getByTestId('tool-exit-chip').textContent).toBe('exit 1')
    expect(screen.getByText('fail out')).toBeInTheDocument()
    // The stderr remainder behind the exit marker stays visible (red), not lost.
    expect(screen.getByText('boom')).toBeInTheDocument()
    expect(screen.queryByText(/\[exit 1\]/)).not.toBeInTheDocument()
  })
})

describe('ToolCallDisplay: the file cards (Z03 to Z05)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('edit_file: path base name, stats chips and the diff opened automatically', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'edit_file',
            args: { path: '/tmp/proj/README.md' },
            result: SAMPLE_DIFF,
            status: 'completed',
          }),
        ]}
      />,
    )
    expect(screen.getByTestId('tool-target').textContent).toBe('README.md')
    const stats = screen.getByTestId('tool-stats').textContent ?? ''
    expect(stats).toContain('+1')
    expect(stats).toContain('−1')
    expect(screen.getByText(/\+## Neu/)).toBeInTheDocument() // diff line visible without a click
  })

  it('edit_file: opening the preview dispatches the panel event with the file endpoint', () => {
    const seen: unknown[] = []
    const listener = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener('ephe:preview-open', listener)
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'edit_file',
            args: { path: '/tmp/proj/README.md' },
            result: SAMPLE_DIFF,
            status: 'completed',
          }),
        ]}
      />,
    )
    fireEvent.click(screen.getByTestId('tool-open-preview'))
    window.removeEventListener('ephe:preview-open', listener)
    expect(seen).toHaveLength(1)
    expect((seen[0] as { tab: string; url: string }).tab).toBe('preview')
    expect((seen[0] as { url: string }).url).toBe(
      `/api/file?path=${encodeURIComponent('/tmp/proj/README.md')}`,
    )
  })

  it('write_file: completed with content opens the syntax block without a click', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'write_file',
            args: { path: '/tmp/a/app.py', content: 'print("hi")' },
            result: 'created',
            status: 'completed',
          }),
        ]}
      />,
    )
    // Z04 parity: a created document shows its content in the chat without manual
    // expanding (judge-gate round finding: collapse gets in the way).
    expect(screen.getByText(/print\("hi"\)/)).toBeInTheDocument()
    expect(screen.queryByText(/"content"/)).not.toBeInTheDocument()
  })
})

describe('ToolCallDisplay: the task checklist in the stream (Z06)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('manage_tasks renders the real list with a ticked status', async () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'manage_tasks',
            args: { action: 'add', title: 'Tests gruen' },
            result: 'ok',
            status: 'completed',
          }),
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'manage_tasks Details' }))
    const rows = await screen.findAllByTestId('tool-task-row', {}, { timeout: 2000 })
    expect(rows).toHaveLength(2)
    expect(rows[0]?.textContent).toContain('Readme schreiben')
    // "Tests gruen" also shows up in the summary line — what counts here is the list entry
    expect(rows[1]?.textContent).toContain('Tests gruen')
    expect(rows[0]?.getAttribute('data-status')).toBe('done')
    expect(rows[1]?.getAttribute('data-status')).toBe('pending')
  })

  it('done rows carry a clearly visible strike-through (judge gate readability)', async () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'manage_tasks',
            args: { action: 'add', title: 'Tests gruen' },
            result: 'ok',
            status: 'completed',
          }),
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'manage_tasks Details' }))
    const rows = await screen.findAllByTestId('tool-task-row', {}, { timeout: 2000 })
    const doneSpan = rows[0]?.querySelector('span')
    const openSpan = rows[1]?.querySelector('span')
    expect(doneSpan?.className).toContain('line-through')
    // 2px thickness + own decoration colour — a 1px/45%-line vanishes at normal
    // display scale and read as "not struck through" (visual-gate finding).
    expect(doneSpan?.className).toContain('decoration-2')
    expect(doneSpan?.className).toContain('decoration-mist/80')
    expect(openSpan?.className).not.toContain('line-through')
  })
})

describe('ToolCallDisplay: generic details remain (B2 contract)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('expands the args JSON on a click for unknown tools', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({ id: '1', name: 'analyze_chart', args: { kind: 'bar' }, status: 'completed' }),
        ]}
      />,
    )
    expect(screen.queryByText(/"kind"/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'analyze_chart Details' }))
    expect(screen.getByText(/"kind": "bar"/)).toBeInTheDocument()
    expect(screen.getByText('Arguments')).toBeInTheDocument()
  })

  it('shows the result block when a result exists', () => {
    render(
      <ToolCallDisplay
        tool_calls={[
          tc({
            id: '1',
            name: 'read_file',
            args: { path: '/a' },
            result: 'OK',
            status: 'completed',
          }),
        ]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'read_file Details' }))
    expect(screen.getByText('Result')).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
  })
})

// ── I6 P2c: status labels have to be translated (no DE/EN mix) ─────────────
// Deep-test finding: after approval/denial the card showed the raw
// enum ('approved'/'denied'/'waiting') from the store instead of a label.
describe('ToolCallDisplay: status labels through i18n (I6 P2c)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('de')
  })

  it('approved shows the translated approval label over the raw word', () => {
    render(
      <ToolCallDisplay
        tool_calls={[tc({ id: 'ap1', name: 'run_shell', status: 'approved', result: 'ok' })]}
      />,
    )
    expect(screen.queryByText('approved')).not.toBeInTheDocument()
    // one name, one outcome word — never the name again inside the status
    expect(screen.getAllByText('run_shell')).toHaveLength(1)
    expect(screen.getByTestId('tool-outcome').textContent).toContain('ok')
  })

  it('denied shows the translated rejection label over the raw word', () => {
    render(
      <ToolCallDisplay tool_calls={[tc({ id: 'dn1', name: 'write_file', status: 'denied' })]} />,
    )
    expect(screen.queryByText('denied')).not.toBeInTheDocument()
    expect(screen.getAllByText('write_file')).toHaveLength(1)
    expect(screen.getByTestId('tool-outcome').textContent).toContain('Fehlgeschlagen')
  })

  it('waiting shows a translated waiting label over the raw word', () => {
    render(
      <ToolCallDisplay tool_calls={[tc({ id: 'wt1', name: 'run_shell', status: 'waiting' })]} />,
    )
    expect(screen.queryByText('waiting')).not.toBeInTheDocument()
    expect(screen.getAllByText('run_shell')).toHaveLength(1)
    expect(screen.getByTestId('tool-outcome').textContent).toContain('Wartet auf Freigabe')
  })
})

describe('ToolCallDisplay — research evidence entry', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('opens the source cards of a finished web_research call', async () => {
    researchApi.getResearchEvidence.mockResolvedValueOnce({
      ok: true,
      total: 1,
      runs: [],
      sources: [
        {
          source_id: 's_a66928a39d45',
          url: 'https://example.org/moon',
          title: 'Moon drift',
          fetched_at: '2026-11-12T00:00:00Z',
          sha256: 'a'.repeat(64),
          excerpt: 'The moon drifts away from Earth at about 3.8 cm per year.',
          query: 'moon drift',
          run_id: 'r_1',
        },
      ],
      workspace: [],
    })
    render(
      <ToolCallDisplay
        live={false}
        tool_calls={[
          tc({
            id: 'research-1',
            name: 'web_research',
            args: { query: 'moon drift' },
            result: '[web_research] query="moon drift"',
          }),
        ]}
      />,
    )
    expect(await screen.findByTestId('research-evidence')).toBeInTheDocument()
    expect(screen.getByTestId('research-source-card')).toBeInTheDocument()
    expect(screen.getByText('Raw tool output')).toBeInTheDocument()
  })
})
