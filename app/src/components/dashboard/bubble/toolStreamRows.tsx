import { useMemo } from 'react'
import { useDeepBool } from '@/lib/deepSettings'
import { aggregateToolCalls } from '@/lib/toolStreamModel'
import type { ToolCallShape } from '@/lib/toolStreamModel'
import type { ThinkingPhase } from '@/types'
import { RoundRow } from './roundRow'
import type { RoundEvent } from './calmRounds'

/**
 * I1 (2026-09-07): reference-B style aggregated activity rows.
 *
 * UI-CHAT: one row per working round. Consecutive calls of the same family stay
 * one row (icon + tool name + count + duration + outcome); the chevron opens the
 * detail body. Thoughts that arrived before the calls fold into the first row,
 * so a round is never introduced by a second chrome line.
 */
function toEvents(calls: ToolCallShape[], thoughts: ThinkingPhase[]): RoundEvent[] {
  const events: RoundEvent[] = thoughts.map((phase) => ({ kind: 'thought', phase }))
  for (const call of calls) events.push({ kind: 'call', call: call as never })
  return events
}

export function ToolStreamRows({
  tool_calls,
  thoughts = [],
  streaming,
}: {
  tool_calls: ToolCallShape[]
  /** Reasoning that belongs to this run (folded into the first round row). */
  thoughts?: ThinkingPhase[]
  streaming?: boolean
  /** Wall clock of the turn's first frame (kept in the signature for callers). */
  startTs?: number
}) {
  const expandFirst = useDeepBool('chat.expand_tool_calls', false)
  const groups = useMemo(() => aggregateToolCalls(tool_calls), [tool_calls])

  if (groups.length === 0) return null

  return (
    <div
      data-testid="tool-stream-rows"
      className="mt-1 inline-flex max-w-full flex-col items-start gap-0"
    >
      {groups.map((group, index) => (
        <RoundRow
          key={`${group.family}-${index}`}
          events={toEvents(group.calls, index === 0 ? thoughts : [])}
          streaming={streaming}
          defaultOpen={expandFirst && index === 0}
        />
      ))}
    </div>
  )
}
