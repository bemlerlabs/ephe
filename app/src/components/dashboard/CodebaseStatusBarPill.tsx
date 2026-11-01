import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, Loader2, AlertCircle } from 'lucide-react'
import { fetchIndexStatus, type CodebaseIndexStatus } from '@/lib/codebaseIndex'

interface Props {
  onOpen?: () => void
}

/** What the pill reads when the status route gave no answer: the idle word, and no claim. */
const IDLE_READ: CodebaseIndexStatus = { state: 'idle', files: 0, symbols: 0, indexed: 0, total: 0 }

export default function CodebaseStatusBarPill({ onOpen }: Props) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<CodebaseIndexStatus | null>(null)

  useEffect(() => {
    let alive = true
    fetchIndexStatus()
      .then((next) => {
        if (alive) setStatus(next)
      })
      .catch(() => {
        // A read that never answered is not a failed index. The route names a real
        // failure in its own body (`state: "error"`, from a job that stopped), and only
        // that path may paint the danger tone here; a refused request falls back to the
        // idle word, and the dialog the pill opens reports the status code it saw.
        if (alive) setStatus({ ...IDLE_READ })
      })
    return () => {
      alive = false
    }
  }, [])

  if (!status) return null

  const label =
    status.state === 'ready'
      ? t('codebase.pillReady', { count: status.symbols })
      : status.state === 'indexing'
        ? t('codebase.pillIndexing', { done: status.indexed, total: status.total })
        : status.state === 'error'
          ? t('codebase.pillError')
          : t('codebase.pillIdle')

  const Icon =
    status.state === 'ready' ? Database : status.state === 'indexing' ? Loader2 : AlertCircle
  const tone =
    status.state === 'ready'
      ? 'text-status-success'
      : status.state === 'error'
        ? 'text-status-danger'
        : 'text-ink-faint'

  return (
    <button
      type="button"
      data-testid="codebase-pill"
      data-state={status.state}
      onClick={onOpen}
      className={`flex min-w-0 max-w-full items-center gap-1.5 rounded-full px-2 py-0.5 text-ui-xs font-medium hover:bg-surface-interactive ${tone}`}
      aria-label={label}
    >
      <Icon className={`h-3.5 w-3.5 ${status.state === 'indexing' ? 'animate-spin' : ''}`} />
      <span className="truncate">{label}</span>
    </button>
  )
}
