import { useTranslation } from 'react-i18next'
import { Camera, History, X } from 'lucide-react'
import type { ChatCheckpoint } from '@/lib/checkpoints'

interface CheckpointControlsProps {
  checkpoints: ChatCheckpoint[]
  onCreate: () => void
  onRollback: (id: string) => void
  onDelete: (id: string) => void
}

/**
 * Checkpoint & Rollback (P2-7) — compact control bar.
 * One button stores a snapshot of the current session messages;
 * below it sit the stored checkpoints with rollback/delete actions.
 */
export default function CheckpointControls({
  checkpoints,
  onCreate,
  onRollback,
  onDelete,
}: CheckpointControlsProps) {
  const { t } = useTranslation()
  return (
    <div
      role="group"
      aria-label={t('a11y.checkpoints')}
      className="flex items-center gap-2 shrink-0"
    >
      <button
        onClick={onCreate}
        title={t('checkpoints.create')}
        aria-label={t('checkpoints.create')}
        className="p-1.5 rounded-lg hover:bg-brand/5 text-ink-soft hover:text-brand transition-colors"
      >
        <Camera className="h-4 w-4" aria-hidden="true" />
      </button>
      {checkpoints.length > 0 && (
        <div className="flex items-center gap-1.5">
          {checkpoints.map((cp) => (
            <span
              key={cp.id}
              className="flex items-center gap-1 text-ui-xs text-ink-soft font-mono px-1.5 py-0.5 rounded bg-surface"
            >
              <button
                onClick={() => {
                  if (window.confirm(t('checkpoints.rollbackConfirm', { label: cp.label })))
                    onRollback(cp.id)
                }}
                title={t('checkpoints.rollback')}
                aria-label={`${t('checkpoints.rollback')}: ${cp.label}`}
                className="hover:text-brand transition-colors"
              >
                <History className="h-3 w-3" aria-hidden="true" />
              </button>
              <span className="max-w-24 truncate">{cp.label}</span>
              <button
                onClick={() => {
                  if (window.confirm(t('checkpoints.deleteConfirm', { label: cp.label })))
                    onDelete(cp.id)
                }}
                title={t('checkpoints.delete')}
                aria-label={`${t('checkpoints.delete')}: ${cp.label}`}
                className="hover:text-status-danger transition-colors"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
