import { memo, useState, useCallback } from 'react'
import { useReducedMotion, m } from 'framer-motion'
import { Sparkles, Pencil, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatTime } from '@/lib/utils'
import { useDeepBool } from '@/lib/deepSettings'
import { stripFileMarkers } from '@/lib/fileMarkers'
import type { ChatMessage, ToolCall } from '@/types'
import type { ChatMessage as LegacyChatMessage } from '@/store/chatStore'
import { UserMarkdown } from './bubble/messageMarkdown'
import { AssistantBubble } from './bubble/assistantBubble'
import SystemContextBlock from './SystemContextBlock'

/**
 * Chat message (PWA-Chat-UX-Plan, task B4).
 *
 * The assistant message renders in the KI-client order:
 *   thinking block → activity feed → content (+ streaming cursor)
 *   → tool calls → tool-approval prompt (when a call is waiting)
 *
 * Backwards compatible: accepts both the full ChatMessage (with
 * thinking/activities/streaming/error) and the legacy props.
 */
interface MessageBubbleProps {
  sessionId?: string
  message?: Omit<ChatMessage, 'id'> & { id?: string }
  /** Legacy props (ignored once `message` is set) */
  role?: 'user' | 'assistant' | 'system'
  content?: string
  timestamp?: number
  tool_calls?: ToolCall[]
  /** Round 12: entrance animation only for fresh messages — virtualized
      historical rows mount instantly (otherwise every scrolled row jumps again) */
  animateEntrance?: boolean
  /** Approval callback (sandbox token from tool.description) */
  onApproveSandbox?: (tool: ToolCall, remember?: boolean) => void
  onDenySandbox?: (tool: ToolCall) => void
  /** G1: edit a user message (id + new text) */
  onEdit?: (id: string, content: string) => void
  /** G1: regenerate the assistant answer */
  onRegenerate?: (id: string) => void
  /** G1.2: try again after a stream error */
  onRetry?: (id: string) => void
  /** J6: clicking an ask option → the answer (label) is sent */
  onPickOption?: (answer: string) => void
  /** G1: the answer to the question the RUNNING turn is waiting on (token + text).
   *  It continues THAT run instead of starting a new turn. */
  onAnswerAsk?: (token: string, answer: string) => void
  /** K2 (Z13): content of the preceding user message (context for the
      feedback pair); empty when no predecessor message is known */
  prevUserContent?: string
}

function MessageBubbleInner({
  animateEntrance = true,
  sessionId,
  message,
  role,
  content,
  timestamp,
  tool_calls,
  onApproveSandbox,
  onDenySandbox,
  onEdit,
  onRegenerate,
  onRetry,
  onPickOption,
  onAnswerAsk,
  prevUserContent = '',
}: MessageBubbleProps) {
  const { t, i18n } = useTranslation()
  const showTimestamps = useDeepBool('appearance.show_timestamps', true)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  // Normalisation: message (ChatMessage) or legacy props
  const msg: LegacyChatMessage = message
    ? { id: 'x', ...message }
    : {
        id: 'legacy',
        role: role ?? 'system',
        content: content ?? '',
        timestamp: timestamp ?? 0,
        tool_calls,
      }

  const isUser = msg.role === 'user'
  const isAssistant = msg.role === 'assistant'
  // Compaction writes system rows into the same list (compact.ts, helpers.ts);
  // they are Ephe's own context and never a turn of the conversation.
  const isSystem = !isUser && !isAssistant
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState('')

  const startEditing = useCallback(() => {
    setEditDraft(msg.content)
    setEditing(true)
  }, [msg.content])

  const saveEdit = useCallback(() => {
    const trimmed = editDraft.trim()
    if (!trimmed || trimmed === msg.content) {
      setEditing(false)
      return
    }
    onEdit?.(msg.id, trimmed)
    setEditing(false)
  }, [editDraft, msg.content, msg.id, onEdit])

  const reduceMotion = useReducedMotion()

  return (
    <m.div
      initial={
        animateEntrance && !reduceMotion && animationsEnabled
          ? { opacity: 0, y: 12, scale: 0.98 }
          : false
      }
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28, mass: 0.7 }}
      // DD-27: stable anchor for E2E — specs used to guess bubbles via
      // [class*="group"] + response-text filters, which flakes whenever the
      // model words its answer without the expected token.
      data-testid="message-bubble"
      data-role={isSystem ? 'system' : isUser ? 'user' : 'assistant'}
      className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''} group`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-brand/20' : 'glass-reading forest-glow-subtle'
        }`}
      >
        {isUser ? (
          <span className="text-ui-sm font-medium text-brand">U</span>
        ) : isSystem ? (
          <Layers className="h-4 w-4 text-ink-soft" />
        ) : (
          <Sparkles className="h-4 w-4 text-brand" />
        )}
      </div>

      {/* Content — S1: wider than the old 80% cap (owner: "too small, choppy
      texts"); the reference runs at ~88% of the column. P6 (ref-01):
      the user prompt sits as a quiet card on the right, its text left-aligned
      (no text-right) — Ephe never renders prompts right-aligned. */}
      {/* Content — the user prompt sits as a quiet capsule on the right; the
      assistant answer runs the full reading width straight on the studio stage,
      with no outer card, the way a modern workspace reads an answer. */}
      <div className={isAssistant ? 'flex-1 min-w-0' : 'flex-1 max-w-[88%]'}>
        {/* The approval prompt renders at the BOTTOM of the bubble (see below), so the
            user does not have to scroll up to reach the approve button. */}
        <div
          className={
            isUser
              ? 'rounded-2xl p-4 rounded-tr-sm bg-canvas border border-hairline'
              : isAssistant
                ? 'text-foreground'
                : 'rounded-2xl p-4 bg-yellow-500/10 border border-yellow-500/20'
          }
        >
          {isAssistant ? (
            <AssistantBubble
              m={msg}
              sessionId={sessionId}
              prevUserContent={prevUserContent}
              onRegenerate={onRegenerate}
              onRetry={onRetry}
              onPickOption={onPickOption}
              onAnswerAsk={onAnswerAsk}
              onApproveSandbox={onApproveSandbox}
              onDenySandbox={onDenySandbox}
            />
          ) : isUser && editing ? (
            /* G1: inline edit editor (user bubble) */
            <div className="text-left">
              <textarea
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    saveEdit()
                  } else if (e.key === 'Escape') {
                    setEditing(false)
                  }
                }}
                rows={3}
                autoFocus
                className="w-full bg-canvas rounded-lg p-2 text-ui-sm text-foreground/90 focus-ring border border-brand/30 resize-none"
              />
              <div className="mt-1.5 flex items-center justify-end gap-2">
                <button
                  onClick={() => setEditing(false)}
                  className="rounded-md px-2 py-1 text-ui-xs text-ink-faint hover:text-foreground transition-colors"
                  aria-label={t('chat.cancel')}
                >
                  {t('chat.cancel')}
                </button>
                <button
                  onClick={saveEdit}
                  className="rounded-md bg-brand px-2.5 py-1 text-ui-xs font-medium text-black hover:bg-brand-glow transition-colors"
                  aria-label={t('chat.save')}
                >
                  {t('chat.save')}
                </button>
              </div>
            </div>
          ) : isUser ? (
            /* G1.5: user bubbles as Markdown (without syntax highlighting) —
               backticks/links/lists in user messages render cleanly. */
            <div className="text-ui-sm text-foreground/80 prose prose-invert max-w-none break-words prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground text-left">
              <UserMarkdown text={msg.content} />
            </div>
          ) : (
            <SystemContextBlock text={stripFileMarkers(msg.content)} />
          )}
        </div>

        {/* G1: user actions (edit) — hover toolbar */}
        {isUser && !editing && onEdit && (
          <div className="mt-1 flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            <button
              onClick={startEditing}
              className="flex min-h-6 max-lg:min-h-11 items-center gap-1 text-ui-xs text-ink-faint hover:text-brand transition-colors"
              aria-label={t('chat.edit')}
            >
              <Pencil className="h-3 w-3" />
              {t('chat.edit')}
            </button>
          </div>
        )}

        {/* I3-4: appearance.show_timestamps — the switch in the register really
            applies; without the register the time stays visible as before I3-4. */}
        {showTimestamps && (
          <span data-testid="message-timestamp" className="text-ui-xs text-ink-faint mt-1 block">
            {formatTime(new Date(msg.timestamp), i18n.language)}
          </span>
        )}
      </div>
    </m.div>
  )
}

/**
 * D2 performance: memoized wrapper.
 *
 * While streaming, only the ACTIVE assistant message changes per chunk
 * (updateActiveMessage → a new object per changed message). With memo + stable
 * props only the bubbles whose message object is actually new re-render — all
 * historical bubbles stay stable on a reference-identical message.
 *
 * IMPORTANT: ChatLayout MUST pass the callback props (onApproveSandbox/
 * onDenySandbox) stably (useCallback), otherwise the memo comparison breaks on
 * every ChatLayout render because of new function instances.
 */
export default memo(MessageBubbleInner)
