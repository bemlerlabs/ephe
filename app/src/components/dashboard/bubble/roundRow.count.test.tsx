/**
 * The counter behind a tool round — the whole promise of `chat.show_tool_count`.
 *
 * The register row makes four claims and all four live in one line of
 * `roundRow.tsx`: live as done/total, finished as a number, a single call left
 * without one (`total > 1`), and off hiding the counter while the row itself
 * stays. None of them had a test.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RoundRow } from './roundRow'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'
import type { RoundEvent } from './calmRounds'
import type { ToolCall } from '@/types'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}<${JSON.stringify(opts)}>` : key,
    i18n: { language: 'de' },
  }),
}))

function call(id: string, status: ToolCall['status'] = 'completed'): ToolCall {
  return {
    id,
    name: 'read_file',
    args: { path: 'notes.md' },
    status,
    duration_ms: status === 'pending' ? undefined : 120,
  }
}

function calls(count: number, pendingTail = 0): RoundEvent[] {
  const first = count - pendingTail
  return Array.from({ length: count }, (_, index) => ({
    kind: 'call' as const,
    call: call(`c${index}`, index < first ? 'completed' : 'pending'),
  }))
}

/** Seeded before the render only: the store notifies its subscribers, and a
 *  live component would take that update outside `act`. */
function counterSwitch(on: boolean) {
  seedDeepSettings([
    {
      key: 'chat',
      fields: [
        {
          key: 'chat.show_tool_count',
          type: 'bool',
          label: 'Tool count',
          labelEn: 'Tool count',
          default: true,
          value: on,
        },
      ],
    } as unknown as DeepSection,
  ])
}

beforeEach(() => seedDeepSettings(null))

describe('RoundRow tool counter (chat.show_tool_count)', () => {
  it('a finished round of several calls carries the number', () => {
    render(<RoundRow events={calls(3)} streaming={false} />)
    expect(screen.getByTestId('round-count').textContent).toBe('3×')
  })

  it('a running round counts as done over total', () => {
    render(<RoundRow events={calls(3, 1)} streaming />)
    expect(screen.getByTestId('round-count').textContent).toBe('2/3')
  })

  it('a single call is left without a counter — the name already says one', () => {
    render(<RoundRow events={calls(1)} streaming={false} />)
    expect(screen.queryByTestId('round-count')).toBeNull()
    expect(screen.getByTestId('round-tool-name').textContent).toBe('read_file')
  })

  it('off hides the counter and keeps the row', () => {
    counterSwitch(false)
    render(<RoundRow events={calls(3)} streaming={false} />)
    expect(screen.queryByTestId('round-count')).toBeNull()
    expect(screen.getByTestId('round-tool-name').textContent).toBe('read_file')
  })
})
