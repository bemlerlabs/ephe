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
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import i18n from '@/i18n'
import MessageBubble from './MessageBubble'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
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

  it('fertige Gruppe: kein Spinner, „Completed"-Suffix in der gedämpften Rolle', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1', 'completed')], false)} />)
    expect(screen.queryByTestId('tool-row-spinner')).toBeNull()
    expect(screen.queryByTestId('tool-stream-row-active')).toBeNull()
    expect(screen.getByTestId('tool-row-status').textContent).toContain('Completed')
    // R2-B: the step used to be text-status-info/60 — 3.81:1 on paper, hence below
    // 4.5:1. Muted text now lives on its own role.
    expect(screen.getByTestId('tool-row-status').className).toContain('text-ink-faint')
  })

  it('fehlgeschlagene Gruppe: „Failed"-Suffix in Gefahren-Farbe', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1', 'failed')], false)} />)
    expect(screen.getByTestId('tool-row-status').textContent).toContain('Failed')
    expect(screen.getByTestId('tool-row-status').className).toContain('text-status-danger')
  })
})

describe('MessageBubble — Subagent-Zeilen persistieren nach Turn-Ende (P3)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  const agentActivities = [
    { id: 'sa1', label: 'SubAgent e1 (explore)', status: 'done' as const },
    { id: 'sa2', label: 'Agent a2', status: 'running' as const },
    { id: 'ph1', label: 'Analyzing request…', status: 'done' as const },
  ]

  it('nach streaming=false bleiben Agent-Zeilen sichtbar (Suffix pro Status)', () => {
    render(
      <MessageBubble
        message={{ ...toolMsg([], false), activities: agentActivities } as unknown as ChatMessage}
      />,
    )
    // Agent rows stay put below the tool groups …
    expect(screen.getByTestId('agent-activity-rows')).toBeTruthy()
    expect(screen.getByTestId('agent-activity-sa1').textContent).toContain('SubAgent e1 (explore)')
    expect(screen.getByTestId('agent-activity-sa1').textContent).toContain('· Completed')
    // … running row: spinner + „Working"
    expect(screen.getByTestId('agent-activity-sa2').querySelector('.animate-spin')).toBeTruthy()
    expect(screen.getByTestId('agent-activity-status-sa2').textContent).toContain('Working')
    // non-agent phases do NOT enter the persistence list …
    expect(screen.queryByTestId('agent-activity-ph1')).toBeNull()
    // … and the transient feed is gone once the stream ends
    expect(screen.queryByTestId('activity-ph1')).toBeNull()
  })

  it('während streaming zeigt der transiente Feed die Agent-Zeile (wie bisher)', () => {
    render(
      <MessageBubble
        message={{ ...toolMsg([], true), activities: agentActivities } as unknown as ChatMessage}
      />,
    )
    expect(screen.getByTestId('activity-sa1')).toBeTruthy()
    expect(screen.getByTestId('activity-sa1').textContent).toContain('SubAgent e1 (explore)')
  })

  it('Klick auf die persistente Agent-Zeile öffnet den Subagents-Tab', () => {
    let detail: unknown = null
    const listener = (e: Event) => {
      detail = (e as CustomEvent).detail
    }
    window.addEventListener(PREVIEW_OPEN_EVENT, listener)
    try {
      render(
        <MessageBubble
          message={
            { ...toolMsg([], false), activities: [agentActivities[0]] } as unknown as ChatMessage
          }
        />,
      )
      fireEvent.click(screen.getByTestId('agent-activity-sa1'))
      expect(detail).toEqual({ tab: 'subagents' })
    } finally {
      window.removeEventListener(PREVIEW_OPEN_EVENT, listener)
    }
  })
})
