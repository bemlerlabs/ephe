/**
 * Version & Updates on the About page: the answer the app already has, the one
 * button that asks again, and the three facts that make the answer checkable.
 *
 * Its own module because `sections-misc.tsx` sits close to the 400-line wall and
 * this block owns its own state (the update hook), so it leaves without touching
 * the page's.
 */
import { useTranslation } from 'react-i18next'
import { useUpdateCheck } from '@/lib/useUpdateCheck'

export function UpdateSection() {
  const { t } = useTranslation()
  const update = useUpdateCheck()
  const { state } = update

  const status =
    state.phase === 'current'
      ? t('update.titleCurrent')
      : state.phase === 'available'
        ? state.channel === 'main'
          ? t('update.mainChannel', { count: state.commitsBehind ?? 0 })
          : t('update.titleAvailable')
        : state.phase === 'failed'
          ? t('update.titleFailed')
          : t('update.title')

  const facts: [string, string | undefined][] = [
    [t('update.detailsVersion'), state.current],
    [t('update.detailsCommit'), state.commit],
    [t('update.detailsChannel'), state.channel],
  ]

  return (
    <div className="glass-reading rounded-xl p-4 space-y-3" data-testid="settings-updates">
      <div className="flex items-center justify-between gap-3">
        <p className="text-scale-ui text-foreground/80">{t('settings.aboutUpdates')}</p>
        <span data-testid="settings-updates-status" className="text-ui-xs text-ink-soft">
          {status}
        </span>
      </div>
      <div className="space-y-2 text-ui-xs">
        {facts
          .filter(([, value]) => !!value)
          .map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-ink-soft">{label}</span>
              <span className="font-mono text-foreground/80">{value}</span>
            </div>
          ))}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="settings-updates-check"
          onClick={() => void update.check()}
          className="focus-ring rounded-md glass-control px-2.5 py-1 text-ui-xs text-ink-soft hover:bg-brand/10 hover:text-ink"
        >
          {t('settings.aboutUpdatesCheck')}
        </button>
        <button
          type="button"
          data-testid="settings-updates-details"
          onClick={() => update.setOpen(true)}
          className="focus-ring rounded-md px-2 py-1 text-ui-xs text-ink-faint hover:text-ink"
        >
          {t('update.details')}
        </button>
      </div>
    </div>
  )
}
