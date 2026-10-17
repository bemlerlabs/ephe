import {
  Check,
  Copy,
  RefreshCw,
  Volume2,
  VolumeX,
  ThumbsUp,
  ThumbsDown,
  GitBranch,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { feedbackThumbsUp, feedbackThumbsDown } from '@/lib/api'
import { toastBus } from '@/lib/toast'
import type { ChatMessage as LegacyChatMessage } from '@/store/chatStore'
import { useChatStore } from '@/store/chatStore'

interface BubbleActionsProps {
  m: LegacyChatMessage
  copied: boolean
  handleCopy: () => void
  speaking: boolean
  handleSpeak: () => void
  onRegenerate?: (id: string) => void
  fb: 'up' | 'down' | null
  setFb: (v: 'up' | 'down' | null) => void
  prevUserContent?: string
}

/** Copy/speak/regenerate/branch row and the feedback thumbs of a finished
 *  assistant answer (state lives in AssistantBubble, this file renders it). */
export function BubbleActions({
  m,
  copied,
  handleCopy,
  speaking,
  handleSpeak,
  onRegenerate,
  fb,
  setFb,
  prevUserContent = '',
}: BubbleActionsProps) {
  const { t } = useTranslation()
  return (
    <>
      {/* 5. Copy Button */}
      {!m.streaming && m.content && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 min-h-6 max-lg:min-h-11 text-ui-xs text-ink-faint hover:text-brand transition-colors"
            aria-label={copied ? t('chat.copied') : t('chat.copy')}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-status-success" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
            {copied ? t('chat.copied') : t('chat.copy')}
          </button>
          {/* G4: read aloud (Edge-TTS) */}
          <button
            onClick={handleSpeak}
            className="flex items-center gap-1.5 min-h-6 max-lg:min-h-11 text-ui-xs text-ink-faint hover:text-brand transition-colors"
            aria-label={speaking ? t('chat.stopSpeaking') : t('chat.speak')}
          >
            {speaking ? (
              <VolumeX className="h-3.5 w-3.5 text-brand" />
            ) : (
              <Volume2 className="h-3.5 w-3.5" />
            )}
            {speaking ? t('chat.stopSpeaking') : t('chat.speak')}
          </button>
          {/* G1: regenerate (not while streaming) */}
          {!m.streaming && onRegenerate && (
            <button
              onClick={() => onRegenerate(m.id)}
              className="flex items-center gap-1.5 min-h-6 max-lg:min-h-11 text-ui-xs text-ink-faint hover:text-brand transition-colors"
              aria-label={t('chat.regenerate')}
            >
              <RefreshCw className="h-3 w-3" />
              {t('chat.regenerate')}
            </button>
          )}
          {/* W15-P5: turn-level branch — the prefix up to this message as a
                      new session (parentId = active session, Z37 primitive) */}
          {!m.streaming && (
            <button
              onClick={() => useChatStore.getState().branchSession(m.id)}
              className="flex items-center gap-1.5 min-h-6 max-lg:min-h-11 text-ui-xs text-ink-faint hover:text-brand transition-colors"
              aria-label={t('chat.branchFromHere')}
              data-testid="message-branch"
            >
              <GitBranch className="h-3 w-3" />
              {t('chat.branchFromHere')}
            </button>
          )}
        </div>
      )}
      {/* K2 (Z13): thumbs up/down — POST to the existing
                  feedback routes; the selection stays visible as an accent */}
      {!m.streaming && m.content && (
        <div className="mt-1.5 flex items-center gap-2" data-testid="thumbs-row">
          <button
            type="button"
            onClick={() => {
              // F-8: the accent reflects the stored feedback, not the
              // click — failures surface as a toast.
              void feedbackThumbsUp(prevUserContent, m.content ?? '')
                .then((r) => {
                  if (!r.saved) throw new Error('feedback not saved')
                  setFb('up')
                })
                .catch(() => toastBus.error(t('common.changeFailed')))
            }}
            aria-label={t('chat.thumbsUp')}
            data-testid="msg-thumbs-up"
            className={`flex items-center justify-center p-1 min-h-6 max-lg:min-h-11 min-w-6 max-lg:min-w-11 rounded-md transition-colors ${fb === 'up' ? 'text-brand bg-brand/10' : 'text-ink-faint hover:text-brand hover:bg-surface-interactive'}`}
          >
            <ThumbsUp className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={() => {
              void feedbackThumbsDown(prevUserContent, m.content ?? '')
                .then((r) => {
                  if (!r.saved) throw new Error('feedback not saved')
                  setFb('down')
                })
                .catch(() => toastBus.error(t('common.changeFailed')))
            }}
            aria-label={t('chat.thumbsDown')}
            data-testid="msg-thumbs-down"
            className={`flex items-center justify-center p-1 min-h-6 max-lg:min-h-11 min-w-6 max-lg:min-w-11 rounded-md transition-colors ${fb === 'down' ? 'text-brand bg-brand/10' : 'text-ink-faint hover:text-brand hover:bg-surface-interactive'}`}
          >
            <ThumbsDown className="h-3 w-3" />
          </button>
        </div>
      )}
    </>
  )
}
