/**
 * RoundRow — the counter the register switch promises, and the one case it withholds.
 *
 * `chat.show_tool_count` tells the reader how often a tool group ran: live as
 * done/total, finished as a number, and off hides the counter while the line stays.
 * A single call shows no number at all (`roundRow.tsx:160` requires `total > 1`),
 * which the field's own hint now states. These cases hold both halves of that
 * sentence, because the row had no unit spec before and the switch is only half of
 * it: a counter that never appears for the most common round shape would read as a
 * control that does nothing.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'
import type { RoundEvent } from './calmRounds'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}:${opts.count}` : key,
  }),
}))

vi.mock('../ToolCallDisplay', () => ({
  ToolCallDetails: () => <div data-testid="tool-details" />,
  TaskBody: () => null,
  default: () => <div data-testid="tool-card" />,
}))

import { RoundRow } from './roundRow'

type Field = DeepSection['fields'][number]

function field(key: string, type: Field['type'], value: string | number | boolean | null): Field {
  return { key, type, label: key, labelEn: key, default: value, value }
}

function showCount(on: boolean): void {
  act(() =>
    seedDeepSettings([
      {
        key: 'chat',
        fields: [
          field('chat.show_tool_count', 'bool', on),
          field('chat.details_mode', 'select', 'collapsed'),
        ],
      },
    ]),
  )
}

function call(id: string, name: string, status: 'completed' | 'pending'): RoundEvent {
  return { kind: 'call', call: { id, name, args: {}, status, duration_ms: 900 } }
}

afterEach(() => act(() => seedDeepSettings(null)))

describe('the tool counter of a round', () => {
  it('names a single call without a number', () => {
    showCount(true)
    render(<RoundRow events={[call('t1', 'read_file', 'completed')]} streaming={false} />)
    expect(screen.getByTestId('round-tool-name').textContent).toBe('read_file')
    expect(screen.queryByTestId('round-count')).toBeNull()
  })

  it('counts a finished group of two', () => {
    showCount(true)
    render(
      <RoundRow
        events={[call('t1', 'read_file', 'completed'), call('t2', 'run_shell', 'completed')]}
        streaming={false}
      />,
    )
    expect(screen.getByTestId('round-count').textContent).toBe('2×')
  })

  it('counts a running group as done of total', () => {
    showCount(true)
    render(
      <RoundRow
        events={[call('t1', 'read_file', 'completed'), call('t2', 'run_shell', 'pending')]}
        streaming
      />,
    )
    expect(screen.getByTestId('round-count').textContent).toBe('1/2')
  })

  it('hides the counter and keeps the line when the switch is off', () => {
    showCount(false)
    render(
      <RoundRow
        events={[call('t1', 'read_file', 'completed'), call('t2', 'run_shell', 'completed')]}
        streaming={false}
      />,
    )
    expect(screen.queryByTestId('round-count')).toBeNull()
    expect(screen.getByTestId('round-tool-name').textContent).toBe('read_file')
  })
})
