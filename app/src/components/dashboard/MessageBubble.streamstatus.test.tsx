/**
 * P3: tool stream rows with a spinner and a status suffix, plus
 * persistent subagent rows after the turn ends.
 *
 * GIVEN  MessageBubble with tool calls or agent activities
 * WHEN   a group is running / done / failed, or the turn ends
 * THEN   spinner on the running row (tool-stream-row-active), the
 *        „Working"/„Completed"/„Failed" suffix, and the agent rows stay visible
 *        (click → Subagents tab).
 *
 * i18n: a real i18n instance — the new keys (chat.rowWorking/rowCompleted/
 * rowFailed) are not yet maintained in locales/*.json and fall back to the
 * component's defaultValue (the de/en texts are identical).
 */
import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import i18n from '@/i18n'
import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/types'

afterEach(cleanup)

function toolMsg(calls: unknown[], streaming = true): ChatMessage {
  return {
    id: 'sm1',
    role: 'assistant',
    content: 'x',
    timestamp: 0,
    streaming,
    tool_calls: calls,
  } as unknown as ChatMessage
}

const shellCall = (id: string, status: string) => ({
  id,
  name: 'run_shell',
  args: { command: 'ls' },
  status,
})

describe('MessageBubble — Tool-Zeilen Spinner + Status-Suffix (P3 Ephe-Norm)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('laufende Gruppe: Spinner + tool-stream-row-active + „Working"-Suffix', () => {
    render(
      <MessageBubble
        message={toolMsg([shellCall('s1', 'completed'), shellCall('s2', 'pending')])}
      />,
    )
    // The spinner replaces the family icon BEFORE the label (lean anatomy)
    const spinner = screen.getByTestId('tool-row-spinner')
    expect(spinner.getAttribute('class')).toContain('animate-spin')
    // The running row carries the active testid
    expect(screen.getByTestId('tool-stream-row-active')).toBeTruthy()
    // done/total keeps counting + status suffix
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.textContent).toContain('1/2')
    expect(row.textContent).toContain('· Working')
    expect(screen.getByTestId('tool-row-status').className).toContain('text-status-info')
  })

  it('fertige Gruppe: kein Spinner und kein Status-Suffix in der Zeile', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1', 'completed')], false)} />)
    expect(screen.queryByTestId('tool-row-spinner')).toBeNull()
    expect(screen.queryByTestId('tool-stream-row-active')).toBeNull()
    // One line per finished step: the status lives in the proof line the reader
    // opens, not as a permanent suffix beside the label.
    expect(screen.queryByTestId('tool-row-status')).toBeNull()
  })

  it('fehlgeschlagene Gruppe: „Failed"-Suffix in Gefahren-Farbe', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1', 'failed')], false)} />)
    expect(screen.getByTestId('tool-row-status').textContent).toContain('Failed')
    expect(screen.getByTestId('tool-row-status').className).toContain('text-status-danger')
  })
})

describe('MessageBubble — a finished turn keeps one run line (PAKET X)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  const agentActivities = [
    { id: 'sa1', label: 'SubAgent e1 (explore)', status: 'done' as const },
    { id: 'sa2', label: 'Agent a2', status: 'running' as const },
    { id: 'ph1', label: 'Analyzing request…', status: 'done' as const },
  ]

  it('the finished bubble repeats no subagent rows — they live in the subagents tab', () => {
    render(
      <MessageBubble
        message={{ ...toolMsg([], false), activities: agentActivities } as unknown as ChatMessage}
      />,
    )
    expect(screen.queryByTestId('agent-activity-rows')).toBeNull()
    expect(screen.queryByTestId('agent-activity-sa1')).toBeNull()
    expect(screen.queryByTestId('activity-ph1')).toBeNull()
  })

  it('while streaming the transient feed still shows the agent line', () => {
    render(
      <MessageBubble
        message={{ ...toolMsg([], true), activities: agentActivities } as unknown as ChatMessage}
      />,
    )
    expect(screen.getByTestId('activity-sa1')).toBeTruthy()
    expect(screen.getByTestId('activity-sa1').textContent).toContain('SubAgent e1 (explore)')
  })
})
