import { useMemo } from 'react'
import { useDeepBool } from '@/lib/deepSettings'
import { stripRenderedCards } from '@/lib/cardText'
import type { MessageBlock, ThinkingPhase, ToolCall } from '@/types'
import { MarkdownBody } from './messageMarkdown'
import { SourcesBar } from './sourcesBar'
import { RoundRow } from './roundRow'
import { buildCalmSegments } from './calmRounds'

/**
 * R1 (2026-09-09): markdown segment from the chronology list (identical
 * markup shape as the previous content block, so pins/styling stay the same).
 */
function TextBlockView({ text, streaming }: { text: string; streaming?: boolean }) {
  // QD-015 W1: a card block arriving inside a text segment is the card's source,
  // not prose — cut it here so the live stream does not type the JSON out.
  const prose = useMemo(() => stripRenderedCards(text), [text])
  return (
    <div
      className="text-ui-sm text-foreground/90 prose prose-invert max-w-none prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground prose-em:text-foreground/90"
      data-testid="stream-text-block"
      style={{ contentVisibility: 'auto' }}
    >
      {/* P1-6: memoized — finished text segments do not re-parse on stream ticks;
          highlighting arrives once, at finalize. */}
      <MarkdownBody text={prose} highlight={!streaming} />
    </div>
  )
}

/**
 * R1 (reference parity) + UI-CHAT: the chat stream renders at the pace of the
 * events, but a working step is ONE row. The store's ordered blocks fold into
 * rounds (thoughts + tool calls, in arrival order) and text segments; the
 * thought of a round lives inside that round's expandable body, never as a
 * separate line above it.
 */
export function StreamBlocks({
  blocks,
  tool_calls,
  thinkingPhases,
  streaming,
  startTs,
}: {
  blocks: MessageBlock[]
  tool_calls: ToolCall[]
  thinkingPhases: ThinkingPhase[]
  streaming?: boolean
  /** The turn's first frame (kept in the signature for the callers). */
  startTs?: number
}) {
  void startTs
  const showReasoning = useDeepBool('chat.show_reasoning', true)

  const segments = useMemo(
    () => buildCalmSegments(blocks, thinkingPhases, tool_calls, showReasoning),
    [blocks, thinkingPhases, tool_calls, showReasoning],
  )

  return (
    <>
      {segments.map((segment, index) => {
        if (segment.kind === 'text') {
          return <TextBlockView key={`t-${index}`} text={segment.text} streaming={streaming} />
        }
        const row = <RoundRow events={segment.events} streaming={streaming} defaultOpen={false} />
        // The legacy path (bubble/toolStreamRows.tsx) names its group container
        // `tool-stream-rows`; automation must reach a tool round by one name whichever
        // renderer drew it, so a round carrying a call is wrapped in that name with the
        // legacy group's classes. A round of thoughts alone stays a plain thought row.
        if (!segment.events.some((event) => event.kind === 'call')) {
          return <div key={`r-${index}`}>{row}</div>
        }
        return (
          <div
            key={`r-${index}`}
            data-testid="tool-stream-rows"
            className="mt-1 inline-flex max-w-full flex-col items-start gap-0"
          >
            {row}
          </div>
        )
      })}
      {streaming && (
        <span className="inline-block h-3.5 w-1.5 ml-0.5 bg-brand animate-pulse align-text-bottom" />
      )}
      {/* K3 Z14: source bar closing the answer (after the last segment) */}
      {!streaming && <SourcesBar tool_calls={tool_calls} />}
    </>
  )
}
