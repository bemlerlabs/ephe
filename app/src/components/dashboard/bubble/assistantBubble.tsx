import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useDeepBool, useDeepSelect } from '@/lib/deepSettings'
import { synthesizeSpeech } from '@/lib/api'
import { isAutospeakActive } from '@/lib/autospeak'
import { copyTypedText } from '@/lib/clipboard'
import { stripRenderedCards } from '@/lib/cardText'
import type { ToolCall } from '@/types'
import type { ChatMessage as LegacyChatMessage } from '@/store/chatStore'
import { MarkdownBody } from './messageMarkdown'
import ThinkingBlock from '../ThinkingBlock'
import ActivityFeed from '../ActivityFeed'
import ToolApprovalPrompt from '../ToolApprovalPrompt'
import { AssistantExtras } from './assistantExtras'
import { BubbleActions } from './bubbleActions'
import { TurnHeadRow } from './turnHeadRow'
import { StreamBlocks } from './streamBlocks'
import { SourcesBar } from './sourcesBar'
import { ToolStreamRows } from './toolStreamRows'
import { SwarmDeck } from './SwarmDeck'
import { ProofLedger } from './ProofLedger'
import LiveAskCard from './liveAskCard'

interface AssistantBubbleProps {
  m: LegacyChatMessage
  sessionId?: string
  prevUserContent?: string
  onRegenerate?: (id: string) => void
  onRetry?: (id: string) => void
  onPickOption?: (answer: string) => void
  onApproveSandbox?: (tool: ToolCall, remember?: boolean) => void
  onDenySandbox?: (tool: ToolCall) => void
  /** G1: the answer to the question this RUN is waiting on (token + text). */
  onAnswerAsk?: (token: string, answer: string) => void
}

/** The assistant content branch of a message bubble: turn header, stream
 *  blocks, markdown answer, extras, actions and the approval prompt. Owns
 *  the per-bubble interaction state (speech, copy, feedback, collapse). */
export function AssistantBubble({
  m,
  sessionId,
  prevUserContent = '',
  onRegenerate,
  onRetry,
  onPickOption,
  onApproveSandbox,
  onDenySandbox,
  onAnswerAsk,
}: AssistantBubbleProps) {
  const showReasoning = useDeepBool('chat.show_reasoning', true)
  const isAssistant = m.role === 'assistant'
  const detailsMode = useDeepSelect('chat.details_mode', 'expanded')
  // QD-015 W1: the card reads the raw block; the prose path must not repeat it.
  // Memoized on the source string, so a finished bubble still skips re-parsing.
  const answerText = useMemo(() => stripRenderedCards(m.content ?? ''), [m.content])
  const [copied, setCopied] = useState(false)
  const [fb, setFb] = useState<'up' | 'down' | null>(null)
  // P6 timeline (ref-01): event rows of a finished turn collapse;
  // the header shows the elapsed time live while streaming (1-s tick).
  // I3-5: chat.details_mode presets the initial state.
  const [timelineCollapsed, setTimelineCollapsed] = useState(detailsMode === 'collapsed')
  // The tick value itself is never read — it only triggers the re-render so that
  // the live header re-derives the elapsed time every second.
  const [, setNowTick] = useState(() => Date.now())
  useEffect(() => {
    if (!m.streaming) return
    setNowTick(Date.now())
    const handle = setInterval(() => setNowTick(Date.now()), 1000)
    return () => clearInterval(handle)
  }, [m.streaming])
  // G4: read the answer aloud (Edge-TTS). One <audio> per bubble, a second click cancels it.
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const handleSpeak = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
      setSpeaking(false)
      return
    }
    setSpeaking(true)
    synthesizeSpeech(m.content)
      .then((url) => {
        const a = new Audio(url)
        audioRef.current = a
        a.onended = () => {
          audioRef.current = null
          setSpeaking(false)
        }
        a.onerror = () => {
          audioRef.current = null
          setSpeaking(false)
        }
        return a.play()
      })
      .catch(() => {
        audioRef.current = null
        setSpeaking(false)
      })
  }, [m.content])
  // P4: auto read-aloud — fires only when THIS stream ended here
  // (history bubbles mount with streaming=false → they stay silent).
  const sawStreaming = useRef(!!m.streaming)
  useEffect(() => {
    if (
      !m.streaming &&
      sawStreaming.current &&
      isAssistant &&
      m.content &&
      isAutospeakActive(sessionId)
    ) {
      sawStreaming.current = false
      handleSpeak()
    }
  }, [m.streaming, isAssistant, m.content, handleSpeak, sessionId])
  // R18 barge-in: stop the running read-aloud as soon as the user records again
  // (voice input "interrupts" the output — voice-assistant pattern).
  useEffect(() => {
    const stop = () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
        setSpeaking(false)
      }
    }
    window.addEventListener('ephe:stop-speech', stop)
    return () => window.removeEventListener('ephe:stop-speech', stop)
  }, [])

  const handleCopy = useCallback(() => {
    // The answer is markdown, not HTML, so only its plain face is copied: a
    // half-rendered HTML face would be a second markdown parser at the button.
    void copyTypedText(m.content).then((ok) => {
      if (!ok) return
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [m.content])

  const waitingTool = m.tool_calls?.find((t) => t.status === 'waiting')

  return (
    <>
      {/* P6 timeline (ref-01): turn header "Working/Worked for Xm Ys ⌄" —
                  live while the stream runs; afterwards it shows the measured
                  wall time and collapses the event rows (the answer stays). */}
      <TurnHeadRow
        streaming={Boolean(m.streaming)}
        startTs={m.timestamp}
        durationMs={m.durationMs}
        failed={Boolean(m.error)}
        hasTimeline={Boolean(m.blocks?.length || m.tool_calls?.length || m.thinkingPhases?.length)}
        collapsed={timelineCollapsed}
        onToggle={() => setTimelineCollapsed((v) => !v)}
      />

      {/* 2. Activities (phase transitions inline) — transient: only
                  while streaming, otherwise "Analyzing request…" lingers in
                  finished bubbles forever (deploy polish P2-6). */}
      {m.activities && m.activities.length > 0 && (
        <SwarmDeck activities={m.activities} sessionId={sessionId} turnId={m.turnId} />
      )}
      {m.streaming && <ActivityFeed activities={m.activities} />}

      {/* R1 (reference parity): ordered chronology plan — thinking,
                  tool and text segments in event-arrival order
                  (thinking → tool → thinking → tool). Every reasoning phase sits at
                  its own position, exactly like the reference pattern.
                  Without blocks (legacy/seed messages) the old fixed sequence applies. */}
      {m.blocks && m.blocks.length > 0 ? (
        <>
          {/* E1: the proof sits above the chronology, which ends in the answer text. */}
          <ProofLedger tools={m.tool_calls ?? []} />
          <div data-testid="bubble-timeline" className={timelineCollapsed ? 'hidden' : undefined}>
            <StreamBlocks
              blocks={m.blocks}
              tool_calls={m.tool_calls ?? []}
              thinkingPhases={m.thinkingPhases ?? []}
              streaming={m.streaming}
            />
          </div>
        </>
      ) : (
        <>
          <div data-testid="bubble-timeline" className={timelineCollapsed ? 'hidden' : undefined}>
            {/* 1. Thinking (KI-client order: first thinking, then activity, then content) */}
            {showReasoning && <ThinkingBlock thinking={m.thinking ?? null} />}

            {/* I1 (reference parity): aggregated tool rows before the text */}
            {m.tool_calls && m.tool_calls.length > 0 && (
              <ToolStreamRows tool_calls={m.tool_calls} streaming={m.streaming} />
            )}
          </div>

          {/* 3. Content (+ streaming cursor) */}
          <ProofLedger tools={m.tool_calls ?? []} />
          {(m.content || m.streaming) && (
            <div
              className="chat-reading-type text-foreground/90 prose prose-invert max-w-none break-words prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground prose-em:text-foreground/90"
              aria-live={m.streaming ? 'polite' : undefined}
              aria-atomic={false}
            >
              <MarkdownBody text={answerText} highlight={!m.streaming} detectA2UI />
              {m.streaming && (
                <span className="inline-block h-3.5 w-1.5 ml-0.5 bg-brand animate-pulse align-text-bottom" />
              )}
              {/* K3 Z14: source bar directly under the answer text (1:1) */}
              {!m.streaming && <SourcesBar tool_calls={m.tool_calls} />}
            </div>
          )}
        </>
      )}

      <AssistantExtras m={m} onPickOption={onPickOption} onRetry={onRetry} />

      <BubbleActions
        m={m}
        copied={copied}
        handleCopy={handleCopy}
        speaking={speaking}
        handleSpeak={handleSpeak}
        onRegenerate={onRegenerate}
        fb={fb}
        setFb={setFb}
        prevUserContent={prevUserContent}
      />

      {/* G1 ask gate: the question the RUNNING turn is waiting on. It renders while the
                  stream is open (the options card of a FINISHED answer sits further up in
                  AssistantExtras), and the answer goes back into this same run. */}
      {m.ask && onAnswerAsk && (
        <LiveAskCard
          ask={m.ask}
          live={Boolean(m.streaming)}
          onAnswer={(answer) => onAnswerAsk(m.ask!.token, answer)}
        />
      )}

      {/* Approval prompt at the END of the bubble (parity harness): the
                  approve button sits directly above the composer, the user
                  does not have to scroll up to the button. */}
      {waitingTool && onApproveSandbox && onDenySandbox && (
        <ToolApprovalPrompt
          tool={waitingTool}
          rememberable={waitingTool.rememberable}
          onApprove={(remember?: boolean) => onApproveSandbox(waitingTool, remember)}
          onDeny={() => onDenySandbox(waitingTool)}
        />
      )}
    </>
  )
}
