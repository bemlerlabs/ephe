import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import AskUserQuestionCard from '../AskUserQuestionCard'
import type { AskMessageState } from '@/types'

interface LiveAskCardProps {
  ask: AskMessageState
  /** The turn behind this card is still streaming — i.e. the server is still holding
   *  it open on this token. A restored transcript carries the same card with `live`
   *  false: the question and its answer stay readable, the buttons do not. */
  live: boolean
  onAnswer: (answer: string) => void
}

/**
 * G1: the ask gate's card — the question a RUNNING turn is waiting on.
 *
 * It is the sibling of the answer-text card (`assistantExtras.tsx`), with the one
 * difference that matters: this question is still open. The run holds on the server
 * until the answer arrives through `POST /api/ask/answer`, and the tool call that
 * asked receives it as its result — so the same turn goes on with the answer in
 * context. Picking an option of a FINISHED answer starts a new turn instead; this
 * card never sends a message.
 */
export default function LiveAskCard({ ask, live, onAnswer }: LiveAskCardProps) {
  const { t } = useTranslation()
  const [own, setOwn] = useState('')
  // Picking is possible while the run waits: 'waiting' plus a live stream. Everything
  // else (answered, timeout, expired, restored history) shows the question read-only.
  const open = ask.status === 'waiting' && live
  const freeText = open && ask.options.length === 0

  const sendOwn = () => {
    const value = own.trim()
    if (!value) return
    setOwn('')
    onAnswer(value)
  }

  return (
    <div className="mt-2" data-testid="live-ask">
      <p
        role="status"
        aria-live="polite"
        className="text-ui-2xs mb-1 text-ink-soft"
        data-testid="live-ask-status"
      >
        {open && (
          <>
            <span className="text-brand/90">{t('chat.askLive')}</span>
            {ask.timeoutS ? ` · ${Math.round(ask.timeoutS)}s` : ''}
          </>
        )}
        {ask.status === 'answered' && (
          <span>
            {t('chat.askAnswered')}
            {ask.answer ? `: ${ask.answer}` : ''}
          </span>
        )}
        {ask.status === 'timeout' && (
          <span>{t('chat.askTimedOut', { seconds: Math.round(ask.timeoutS ?? 0) })}</span>
        )}
        {ask.status === 'expired' && <span>{t('chat.askExpired')}</span>}
        {ask.defaultAnswer && ask.status !== 'answered' && (
          <span className="block text-ink-faint">
            {t('chat.askDefault', { value: ask.defaultAnswer })}
          </span>
        )}
      </p>

      <AskUserQuestionCard
        spec={{
          question: ask.question,
          options: ask.options,
          ...(ask.recommendation ? { recommendation: ask.recommendation } : {}),
          ...(ask.multiSelect ? { multiSelect: true } : {}),
        }}
        onPick={onAnswer}
        disabled={!open}
      />

      {freeText && (
        <div className="mt-1.5 flex items-center gap-2" data-testid="live-ask-freetext">
          <input
            value={own}
            onChange={(e) => setOwn(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                sendOwn()
              }
            }}
            aria-label={t('chat.askOwn')}
            placeholder={t('chat.askOwn')}
            className="flex-1 bg-canvas rounded-lg px-2 py-1 text-ui-xs text-foreground/90 focus-ring border border-brand/30"
          />
          <button
            onClick={sendOwn}
            disabled={!own.trim()}
            data-testid="live-ask-send"
            className="px-3 py-1 rounded-lg text-ui-xs bg-brand text-black hover:bg-brand disabled:opacity-30 transition-colors"
          >
            {t('chat.send')}
          </button>
        </div>
      )}
    </div>
  )
}
