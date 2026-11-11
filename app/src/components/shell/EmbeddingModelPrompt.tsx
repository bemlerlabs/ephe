/**
 * An offer, not a download: the memory's embedding model is missing and the install
 * does not carry its ~542 MB of weights.
 *
 * The card appears above the composer, never over it, and only while the model is
 * genuinely missing and the offer was not declined in the last month. "Not now"
 * dismisses it; "Download" starts one fetch in the backend and the card turns into a
 * progress line. A first start never waits on a download and never starts one.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  dismissOffer,
  readEmbeddingModel,
  recentlyDismissed,
  startEmbeddingDownload,
  type EmbeddingModelStatus,
} from '@/lib/embeddingModel'

const POLL_MS = 4000

export default function EmbeddingModelPrompt() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<EmbeddingModelStatus | null>(null)
  const [asking, setAsking] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const read = useCallback(async () => {
    const next = await readEmbeddingModel()
    setStatus(next)
    return next
  }, [])

  useEffect(() => {
    if (recentlyDismissed()) return
    void read()
  }, [read])

  // While a fetch runs, the card follows it to the end; before one, nothing polls.
  useEffect(() => {
    if (!status?.downloading) return
    timer.current = setInterval(() => void read(), POLL_MS)
    return () => {
      if (timer.current) clearInterval(timer.current)
      timer.current = null
    }
  }, [status?.downloading, read])

  const offerVisible = status !== null && !status.present && !status.error
  if (!offerVisible) return null
  if (!status.downloading && !asking && recentlyDismissed()) return null

  const size = status.sizeMb > 0 ? `${status.sizeMb} MB` : t('chat.model.embeddingSizeUnknown')

  return (
    <div
      data-testid="embedding-model-prompt"
      role="status"
      aria-live="polite"
      className="mx-2 mb-2 flex flex-wrap items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-ui-xs text-ink-soft sm:mx-4"
    >
      <div className="min-w-0 flex-1 basis-full sm:basis-auto">
        <p className="font-medium text-foreground">{t('chat.model.embeddingPromptTitle')}</p>
        <p className="mt-0.5 text-ink-faint">
          {status.downloading
            ? t('chat.model.embeddingDownloading', { size })
            : t('chat.model.embeddingPromptBody', { size })}
        </p>
        {status.missing.length > 0 && !status.downloading && (
          <p className="mt-0.5 text-ink-faint">
            {t('chat.model.embeddingMissing', { files: status.missing.join(', ') })}
          </p>
        )}
      </div>
      {status.downloading ? (
        <span className="shrink-0 text-ink-faint">{t('chat.model.embeddingInProgress')}</span>
      ) : (
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            data-testid="embedding-model-download"
            className="rounded-md bg-brand px-2 py-1 font-medium text-canvas"
            onClick={async () => {
              setAsking(true)
              const started = await startEmbeddingDownload()
              setAsking(false)
              if (started) {
                await read()
              } else {
                // The route refused (offline, older build): keep the offer, say nothing new.
                dismissOffer()
                setStatus(null)
              }
            }}
          >
            {t('chat.model.embeddingDownload')}
          </button>
          <button
            type="button"
            data-testid="embedding-model-dismiss"
            className="rounded-md px-2 py-1 text-ink-faint"
            onClick={() => {
              dismissOffer()
              setStatus(null)
            }}
          >
            {t('chat.model.embeddingNotNow')}
          </button>
        </div>
      )}
    </div>
  )
}
