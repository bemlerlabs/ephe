/**
 * UI-CHAT — one calm row per tool round.
 *
 * GIVEN  a finished turn with 3 tool rounds and 2 thought pauses
 * WHEN   the transcript renders
 * THEN   the message stream reads as at most FOUR rows (one per round; the two
 *        thoughts fold into the round they belong to). One row = tool name ·
 *        duration · outcome, with the name exactly once and no "completed"
 *        suffix. Expanding a row gives back every detail that used to be
 *        visible: arguments, output, digest and the reasoning text.
 */
import { beforeAll, describe, expect, it } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import i18n from '@/i18n'
import MessageBubble from '@/components/dashboard/MessageBubble'
import type { ChatMessage, MessageBlock, ThinkingPhase, ToolCall } from '@/types'

const NOW = Date.now()

const CALLS: ToolCall[] = [
  {
    id: 't1',
    name: 'skill_manage',
    args: { skill: 'pdf' },
    result: 'listed 12 skills',
    status: 'completed',
    duration_ms: 27,
    sha256: '30d7e434a1b2c3d4',
  },
  {
    id: 't2',
    name: 'run_shell',
    args: { command: 'pytest -q' },
    result: '12 passed',
    status: 'completed',
    duration_ms: 1200,
  },
  {
    id: 't3',
    name: 'read_file',
    args: { path: '/tmp/report.md' },
    result: '[fetch failed] HTTP 404',
    status: 'failed',
    reason_code: 'fetch_http_error',
    reason_params: { status: '404', url: '/tmp/report.md' },
    duration_ms: 30,
  },
]

const THOUGHTS: ThinkingPhase[] = [
  { start: NOW - 20_000, end: NOW - 14_000, text: 'Check first, then write.' },
  { start: NOW - 13_000, end: NOW - 9_000, text: 'Zweite Überlegung.' },
]

const BLOCKS: MessageBlock[] = [
  { kind: 'thinking', index: 0 },
  { kind: 'tool', callId: 't1' },
  { kind: 'thinking', index: 1 },
  { kind: 'tool', callId: 't2' },
  { kind: 'tool', callId: 't3' },
  { kind: 'text', text: 'Die Antwort steht.' },
]

function turn(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'calm-1',
    role: 'assistant',
    content: '',
    timestamp: NOW - 30_000,
    durationMs: 30_000,
    streaming: false,
    blocks: BLOCKS,
    thinkingPhases: THOUGHTS,
    tool_calls: CALLS,
    ...overrides,
  } as ChatMessage
}

/** Every calm stream line carries this marker — one per round, tool or thought. */
function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-calm-row]'))
}

beforeAll(async () => {
  await i18n.changeLanguage('en')
})

describe('calm rounds (UI-CHAT)', () => {
  it('renders 3 tool rounds + 2 thought pauses as at most 4 rows', () => {
    render(<MessageBubble message={turn()} />)
    // The bound the promise holds: 4 rows. Three rounds and two thoughts may
    // never produce more than one row per round plus one spare.
    expect(rows().length).toBeLessThanOrEqual(4)
    expect(rows()).toHaveLength(3)
  })

  it('names the tool once, with duration and outcome — no verb, no "completed"', () => {
    render(<MessageBubble message={turn()} />)
    const row = rows()[0]!
    const text = row.textContent ?? ''
    expect(text.match(/skill_manage/g)).toHaveLength(1)
    expect(text).toContain('27ms')
    expect(text).toContain('ok')
    expect(text).not.toMatch(/completed/i)
    expect(text).not.toMatch(/\bUses\b/)
    // the thought that belongs to this round is folded in, not a row of its own
    expect(document.querySelector('[data-testid="thinking-block"]')).toBeNull()
    expect(within(row).getByTestId('round-thought').textContent).toBe('6s')
  })

  it('gives every detail back when the row is opened', () => {
    render(<MessageBubble message={turn()} />)
    const row = rows()[0]!
    fireEvent.click(within(row).getByRole('button'))

    expect(within(row).getByTestId('tool-args').textContent).toContain('"skill": "pdf"')
    expect(within(row).getByTestId('tool-result').textContent).toContain('listed 12 skills')
    expect(within(row).getByTestId('tool-digest').textContent).toContain('sha256:30d7e434')
    expect(within(row).getByTestId('round-thought-text').textContent).toContain(
      'Check first, then write.',
    )
  })

  it('folds a thought that directly follows its round into the same row', () => {
    render(<MessageBubble message={turn()} />)
    // round two starts after thought #2 — the shell row carries its own 4s.
    const shell = screen.getByTestId('tool-stream-row-shell')
    expect(shell.textContent).toContain('run_shell')
    expect(within(shell).getByTestId('round-thought').textContent).toBe('4s')
  })

  it('keeps a failed round one line; the reason lives in the opened body', () => {
    render(<MessageBubble message={turn()} />)
    const failed = screen.getByTestId('tool-stream-row-read')
    const summary = within(failed).getByRole('button')
    const summaryText = summary.textContent ?? ''
    expect(summaryText).toContain('read_file')
    expect(summaryText.toLowerCase()).toContain('failed')
    expect(summaryText).not.toContain('fetch failed')
    // a failure opens itself, so the reader sees why without a click
    expect(within(failed).getByTestId('tool-failure-reason').textContent).toContain('HTTP 404')
    expect(screen.queryByTestId('proof-ledger')).toBeNull()
  })

  it('merges consecutive thoughts into one line: summed time + count', () => {
    const pauses = turn({
      blocks: [
        { kind: 'thinking', index: 0 },
        { kind: 'thinking', index: 1 },
        { kind: 'text', text: 'Fertig.' },
      ],
      tool_calls: [],
    })
    render(<MessageBubble message={pauses} />)
    expect(rows()).toHaveLength(1)
    expect(rows()[0]!.textContent).toContain('Thought for 10s')
    expect(rows()[0]!.textContent).toContain('2 pauses')
    fireEvent.click(within(rows()[0]!).getByRole('button'))
    expect(rows()[0]!.textContent).toContain('Check first, then write.')
    expect(rows()[0]!.textContent).toContain('Zweite Überlegung.')
  })
})
