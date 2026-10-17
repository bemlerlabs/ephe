import { useMemo } from 'react'
import { useDeepBool } from '@/lib/deepSettings'
import type { MessageBlock, ThinkingPhase, ToolCall } from '@/types'
import { MarkdownBody } from './messageMarkdown'
import ThinkingBlock from '../ThinkingBlock'
import { ToolStreamRows } from './toolStreamRows'
import { SourcesBar } from './sourcesBar'

/**
 * R1 (2026-09-09): markdown segment from the chronology list (identical
 * markup shape as the previous content block, so pins/styling stay the same).
 */
function TextBlockView({ text, streaming }: { text: string; streaming?: boolean }) {
  return (
    <div
      className="text-ui-sm text-foreground/90 prose prose-invert max-w-none prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground prose-em:text-foreground/90"
      data-testid="stream-text-block"
      style={{ contentVisibility: 'auto' }}
    >
      {/* P1-6: memoized — finished text segments do not re-parse on stream ticks;
          highlighting arrives once, at finalize. */}
      <MarkdownBody text={text} highlight={!streaming} />
    </div>
  )
}

/**
 * R1 (reference parity): the chat stream renders at the pace of the events.
 * The store's ordered blocks fold into segments: consecutive tool blocks form ONE
 * ToolStreamRows run (family group), text in between keeps its position —
 * 1:1 as in the reference harness.
 */
export function StreamBlocks({
  blocks,
  tool_calls,
  thinkingPhases,
  streaming,
}: {
  blocks: MessageBlock[]
  tool_calls: ToolCall[]
  thinkingPhases: ThinkingPhase[]
  streaming?: boolean
}) {
  const byId = useMemo(() => {
    const map = new Map<string, ToolCall>()
    for (const c of tool_calls) map.set(c.id, c)
    return map
  }, [tool_calls])

  const showReasoning = useDeepBool('chat.show_reasoning', true)

  const segments = useMemo(() => {
    const out: Array<
      | { kind: 'text'; text: string }
      | { kind: 'tools'; calls: ToolCall[] }
      | { kind: 'thinking'; phase: ThinkingPhase }
    > = []
    for (const b of blocks) {
      if (b.kind === 'text') {
        out.push({ kind: 'text', text: b.text })
        continue
      }
      if (b.kind === 'thinking') {
        const phase = thinkingPhases[b.index]
        // I3-5: chat.show_reasoning — without permission there is no thinking phase,
        // not even at its chronology position.
        if (phase && showReasoning) out.push({ kind: 'thinking', phase })
        continue
      }
      const call = byId.get(b.callId)
      if (!call) continue
      const last = out[out.length - 1]
      if (last && last.kind === 'tools') last.calls.push(call)
      else out.push({ kind: 'tools', calls: [call] })
    }
    return out
  }, [blocks, byId, thinkingPhases, showReasoning])

  return (
    <>
      {segments.map((seg, i) =>
        seg.kind === 'text' ? (
          <TextBlockView key={`t-${i}`} text={seg.text} streaming={streaming} />
        ) : seg.kind === 'thinking' ? (
          <ThinkingBlock key={`h-${i}`} thinking={seg.phase} />
        ) : (
          <ToolStreamRows key={`g-${i}`} tool_calls={seg.calls} streaming={streaming} />
        ),
      )}
      {streaming && (
        <span className="inline-block h-3.5 w-1.5 ml-0.5 bg-brand animate-pulse align-text-bottom" />
      )}
      {/* K3 Z14: source bar closing the answer (after the last segment) */}
      {!streaming && <SourcesBar tool_calls={tool_calls} />}
    </>
  )
}
