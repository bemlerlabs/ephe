/**
 * SubAgent parity: spawn-/agent_message calls get their own family
 * with `type · short description` in the summary line (reference pattern).
 */
import { describe, it, expect } from 'vitest'
import { classifyToolCall, type ToolCallShape } from '@/lib/toolCardModel'
import { aggregateToolCalls } from '@/lib/toolStreamModel'

const shape = (over: Partial<ToolCallShape>): ToolCallShape => ({
  id: 'c1',
  name: 'spawn_swarm',
  status: 'completed',
  ...over,
})

describe('classifyToolCall — SubAgent-Familie', () => {
  it('spawn_swarm: Rolle und erster Subtask in der Summary-Zeile', () => {
    const m = classifyToolCall(
      shape({
        args: { count: 2, role: 'general-purpose', subtasks: ['P2-Layout + P4-Doku', 'Zweit'] },
      }),
    )
    expect(m.family).toBe('subagent')
    expect(m.icon).toBe('subagent')
    expect(m.verbKey).toBe('chat.toolVerbSubagent')
    expect(m.target).toBe('general-purpose · P2-Layout + P4-Doku')
  })

  it('agent_message: Task-Typ und Nachricht als Ziel', () => {
    const m = classifyToolCall(
      shape({ name: 'agent_message', args: { task_type: 'research', message: 'Rates die Zahl' } }),
    )
    expect(m.family).toBe('subagent')
    expect(m.target).toBe('research · Rates die Zahl')
  })

  it('Aggregation nutzt das SubAgent-Gruppenlabel', () => {
    const groups = aggregateToolCalls([shape({})])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.family).toBe('subagent')
    expect(groups[0]!.summaryKey).toBe('streamGroup.subagent')
  })
})
