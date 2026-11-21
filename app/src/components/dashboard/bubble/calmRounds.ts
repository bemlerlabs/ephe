import { classifyToolCall } from '@/lib/toolCardModel'
import type { MessageBlock, ThinkingPhase, ToolCall } from '@/types'

/**
 * UI-CHAT — the calm transcript model.
 *
 * The store delivers the turn as an ordered block list
 * (thinking → tool → thinking → tool → text). Rendering every block as its own
 * chrome line is what made a 27 ms call cost four rows. This module folds the
 * blocks into the only two things a reader needs:
 *
 *   - a ROUND: the thoughts and the tool calls of one working step, together in
 *     arrival order. It renders as ONE row (name · duration · outcome) whose
 *     body opens to show the reasons and the calls.
 *   - a TEXT segment: the answer prose, untouched.
 *
 * Consecutive thinking blocks stay in the same round (one line, summed time and
 * count). Adjacent calls of the same family join one round; a different family
 * or a text segment starts a new one. Pure function — no React, no i18n.
 */
export type RoundEvent =
  { kind: 'thought'; phase: ThinkingPhase } | { kind: 'call'; call: ToolCall }

export interface CalmRound {
  kind: 'round'
  events: RoundEvent[]
}

export interface CalmText {
  kind: 'text'
  text: string
}

export type CalmSegment = CalmRound | CalmText

function lastCall(round: CalmRound): ToolCall | null {
  for (let i = round.events.length - 1; i >= 0; i -= 1) {
    const event = round.events[i]
    if (event && event.kind === 'call') return event.call
  }
  return null
}

/**
 * Build the readable order of one turn.
 *
 * `showReasoning=false` drops the thought events entirely (the existing
 * `chat.show_reasoning` switch) but keeps the calls and the prose.
 */
export function buildCalmSegments(
  blocks: readonly MessageBlock[],
  thinkingPhases: readonly ThinkingPhase[],
  toolCalls: readonly ToolCall[],
  showReasoning = true,
): CalmSegment[] {
  const byId = new Map(toolCalls.map((call) => [call.id, call]))
  const out: CalmSegment[] = []
  /** Thoughts that arrived since the last rendered segment. */
  let pending: RoundEvent[] = []
  let current: CalmRound | null = null

  const flushThoughts = () => {
    if (pending.length === 0) return
    out.push({ kind: 'round', events: pending })
    pending = []
  }

  for (const block of blocks) {
    if (block.kind === 'text') {
      flushThoughts()
      current = null
      out.push({ kind: 'text', text: block.text })
      continue
    }

    if (block.kind === 'thinking') {
      const phase = thinkingPhases[block.index]
      if (phase && showReasoning) pending.push({ kind: 'thought', phase })
      // A thought closes the running round: the next call starts a new one and
      // carries this thought with it.
      current = null
      continue
    }

    const call = byId.get(block.callId)
    if (!call) continue

    const previous = current ? lastCall(current) : null
    const sameFamily =
      previous !== null && classifyToolCall(previous).family === classifyToolCall(call).family
    if (current && pending.length === 0 && sameFamily) {
      current.events.push({ kind: 'call', call })
      continue
    }

    const round: CalmRound = { kind: 'round', events: [...pending, { kind: 'call', call }] }
    pending = []
    out.push(round)
    current = round
  }

  flushThoughts()
  return out
}
