import { Wifi, WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Status row (W17/DD-22): connection + engine state as one quiet pill
 *  group; hidden entirely while `backendOnline` is undefined. */
export function ConnectionPill({
  backendOnline,
  engineOnline,
}: {
  backendOnline?: boolean | null
  engineOnline?: boolean | null
}) {
  const { t } = useTranslation()
  if (backendOnline === undefined) return null
  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label={
        backendOnline === null
          ? t('chat.connecting')
          : !backendOnline
            ? t('chat.disconnected')
            : engineOnline === false
              ? t('chat.engineOffline')
              : t('chat.connected')
      }
    >
      {backendOnline === null ? (
        <>
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-warning opacity-40" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-status-warning" />
          </span>
          <span className="text-ui-xs text-ink-faint font-medium min-h-[19px] min-w-[19px]">
            {t('chat.connecting')}
          </span>
        </>
      ) : !backendOnline ? (
        <span className="flex items-center gap-1.5">
          <WifiOff className="h-3.5 w-3.5 text-status-danger" />
          <span className="text-ui-xs text-ink-faint font-medium min-h-[19px] min-w-[19px]">
            {t('chat.disconnected')}
          </span>
        </span>
      ) : engineOnline === false ? (
        <span className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-warning opacity-40" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-status-warning" />
          </span>
          <span className="text-ui-xs text-ink-faint font-medium min-h-[19px] min-w-[19px]">
            {t('chat.engineOffline')}
          </span>
        </span>
      ) : (
        <span className="flex items-center gap-1.5">
          <Wifi className="h-3.5 w-3.5 text-status-success" />
          <span className="text-ui-xs text-ink-faint font-medium min-h-[19px] min-w-[19px]">
            {t('chat.connected')}
          </span>
        </span>
      )}
    </div>
  )
}
