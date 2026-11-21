import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database } from 'lucide-react'
import {
  fetchIndexStatus,
  indexProgress,
  startIndex,
  type CodebaseIndexStatus,
} from '@/lib/codebaseIndex'

interface Props {
  open: boolean
  onClose: () => void
}

export default function CodebaseIndexDialog({ open, onClose }: Props) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<CodebaseIndexStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchIndexStatus()
      setStatus(next)
      setError(null)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }, [])

  useEffect(() => {
    if (open) void refresh()
  }, [open, refresh])

  useEffect(() => {
    if (!open || status?.state !== 'indexing') return
    const id = setInterval(() => void refresh(), 400)
    return () => clearInterval(id)
  }, [open, status?.state, refresh])

  const start = async () => {
    setBusy(true)
    try {
      setStatus(await startIndex())
      setError(null)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null
  const percent = status ? indexProgress(status) : 0
  const indexing = status?.state === 'indexing'

  return (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center bg-canvas/60 p-4"
      data-testid="codebase-dialog-backdrop"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="codebase-dialog-title"
        data-testid="codebase-dialog"
        className="w-full max-w-md rounded-xl border border-hairline bg-surface p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-status-success" />
          <h2 id="codebase-dialog-title" className="text-sm font-semibold text-ink">
            {t('codebase.title')}
          </h2>
        </div>
        <p className="mt-1 text-xs text-ink-soft">{t('codebase.body')}</p>

        {indexing && (
          <div className="mt-4">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-interactive">
              <div
                data-testid="codebase-progress"
                className="h-full bg-status-success transition-all"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="mt-1 text-ui-xs text-ink-faint">
              {t('codebase.running', {
                done: status?.indexed ?? 0,
                total: status?.total ?? 0,
              })}
            </p>
          </div>
        )}

        {status?.state === 'ready' && (
          <p data-testid="codebase-count" className="mt-3 text-ui-xs text-status-success">
            {t('codebase.done', { count: status.symbols })}
          </p>
        )}

        {error && (
          <p className="mt-3 text-ui-xs text-status-danger" data-testid="codebase-error">
            {t('codebase.error', { message: error })}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="min-h-[32px] rounded-lg px-3 text-ui-xs text-ink-soft hover:bg-surface-interactive"
          >
            {t('codebase.close')}
          </button>
          <button
            type="button"
            data-testid="codebase-start"
            onClick={() => void start()}
            disabled={busy || indexing}
            className="min-h-[32px] rounded-lg bg-brand px-3 text-ui-xs font-medium text-canvas disabled:opacity-50"
          >
            {status?.state === 'ready' ? t('codebase.retry') : t('codebase.start')}
          </button>
        </div>
      </div>
    </div>
  )
}
