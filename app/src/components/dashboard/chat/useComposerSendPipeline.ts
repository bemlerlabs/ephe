import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import type { ChatAttachment } from '@/lib/attachments'
import { ComposerHistory } from '@/lib/composerHistory'
import { annotateWithOcr } from '@/lib/ocrAnnotation'

/**
 * G1.3/DD-01 + queue editing: the composer send pipeline — draft history and
 * recall ring, the Alt+Enter queue, the stream-settle auto-flush and handleSend
 * (slash handoff, queue editing, normal send). Extracted from ChatInput.tsx;
 * `attachments` stay owned by the caller and are only read/cleared here.
 */
export function useComposerSendPipeline({
  disabled,
  streaming,
  allowInputWhileStreaming,
  message,
  setMessage,
  attachments,
  setAttachments,
  onSend,
  onSlashCommand,
}: {
  disabled: boolean
  streaming: boolean
  allowInputWhileStreaming: boolean
  message: string
  setMessage: Dispatch<SetStateAction<string>>
  attachments: ChatAttachment[]
  setAttachments: Dispatch<SetStateAction<ChatAttachment[]>>
  onSend: (message: string, attachments?: ChatAttachment[]) => void
  onSlashCommand?: (raw: string) => void
}) {
  const historyRef = useRef<ComposerHistory | null>(null)
  if (!historyRef.current) historyRef.current = new ComposerHistory()
  const history = historyRef.current
  const [, force] = useState(0)
  const [recall, setRecall] = useState<{ pos: number; total: number }>({ pos: 0, total: 0 })
  const [queueCount, setQueueCount] = useState(0)

  const refreshUi = useCallback(() => {
    setRecall(history.index())
    setQueueCount(history.queueCount())
    force((v) => v + 1)
  }, [history])

  const handleSend = () => {
    if (disabled) return
    // G1.3: while streaming, Enter queues instead of starting a parallel turn —
    // the composer stays usable (typing, autocompletion), sending goes
    // through the "N in Queue" indicator.
    if (streaming) {
      if (!allowInputWhileStreaming) return
      if (message.trim()) {
        history.enqueue(annotateWithOcr(message.trim(), attachments), attachments.length > 0 ? attachments : undefined)
        setMessage('')
        setAttachments([])
        refreshUi()
      }
      return
    }
    // Phase F: slash command → parent (compact/new/clear/help), no model call.
    // W3-50: a slash command is a control action, not a message — it must NOT
    // discard the composer's attachments. Before, a screenshot attached while the
    // user ran «/help» (or a passthrough like «/swarm» that DOES want the file)
    // was silently wiped. The draft text belongs to the command and is cleared;
    // the chips stay until a real model send consumes them.
    const trimmed = message.trim()
    if (onSlashCommand && trimmed.startsWith('/')) {
      onSlashCommand(trimmed)
      setMessage('')
      refreshUi()
      return
    }
    // Queue editing: composer empty and queue non-empty → send the next queued message
    if (!message.trim() && history.queueCount() > 0 && sendNextQueued()) {
      return
    }
    if (message.trim()) {
      onSend(annotateWithOcr(message.trim(), attachments), attachments.length > 0 ? attachments : undefined)
      history.add(message.trim())
      setMessage('')
      setAttachments([])
      refreshUi()
    }
  }

  // Sends the oldest queued message (slash items keep the slash path — deploy
  // polish P2-9). Returns false when the queue was already empty.
  //
  // W4-28: a queue flush hands off the queued item and the attachments it was
  // enqueued with. It leaves the composer's live chips alone, the same call the
  // W3-50 slash fix made: whatever the user attached since belongs to the next
  // draft. Clearing here wiped a file dropped mid-answer (the stream-settle
  // auto-flush) or behind an empty-composer Enter.
  const sendNextQueued = useCallback((): boolean => {
    const next = history.dequeue()
    if (!next) return false
    if (onSlashCommand && next.text.startsWith('/')) {
      onSlashCommand(next.text)
    } else {
      onSend(next.text, next.attachments as ChatAttachment[] | undefined)
    }
    refreshUi()
    return true
  }, [onSend, onSlashCommand, history, refreshUi])

  // DD-01: when the stream settles the queue must flush on its own — the old
  // behavior left queued text invisible until an empty-composer Enter. One
  // item per stream end: the flush starts the next stream, whose own settle
  // flushes the next item (FIFO chain). An untouched live draft stays put.
  const prevStreamingRef = useRef(streaming)
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current
    prevStreamingRef.current = streaming
    if (!wasStreaming || streaming || disabled) return
    if (message.trim() || history.queueCount() === 0) return
    sendNextQueued()
  }, [streaming, disabled, message, sendNextQueued, history])

  /** ↑ — recall an older message (only without Shift). */
  const recallPrev = (current: string) => {
    if (current.trim() && history.index().total > 0 && history.index().pos === 0) {
      history.setDraft(current)
    }
    const recalled = history.prev()
    if (recalled) {
      setMessage(recalled)
      refreshUi()
    }
  }

  /** ↓ — recall a newer message. */
  const recallNext = () => {
    const newer = history.next()
    if (newer !== null) {
      setMessage(newer)
      refreshUi()
    } else {
      // at the end → back to the draft
      refreshUi()
    }
  }

  /** Escape with no open popup: reset the recall ring back to the draft. */
  const resetRecall = () => {
    history.reset()
    refreshUi()
  }

  /** Alt+Enter — put it in the queue instead of sending. */
  const enqueueCurrent = () => {
    if (message.trim()) {
      history.enqueue(message.trim(), attachments.length > 0 ? attachments : undefined)
      setMessage('')
      setAttachments([])
      refreshUi()
    }
  }

  return { handleSend, queueCount, recall, recallPrev, recallNext, resetRecall, enqueueCurrent }
}
