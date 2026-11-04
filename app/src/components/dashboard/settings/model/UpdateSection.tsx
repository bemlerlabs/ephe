/**
 * Version & Updates on the About page: the answer the app already has, the one
 * button that asks again, the action that takes the update when the answer says
 * it can be taken, and the three facts that make the answer checkable.
 *
 * Its own module because `sections-misc.tsx` sits close to the 400-line wall and
 * this block reads its state from the update machine on `@/lib/useUpdateCheck`,
 * the one the header's sheet reads too, so the two surfaces cannot reach the
 * same answer by two different routes.
 */
import { useTranslation } from 'react-i18next'
import { UpdateDialog } from '@/components/dashboard/UpdateDialog'
import { updateActionOf, updateNoticeOf, useUpdateCheck } from '@/lib/useUpdateCheck'

export function UpdateSection() {
  const { t } = useTranslation()
  const update = useUpdateCheck()
  const { state } = update

  /** Every phase has its word here: a surface that goes quiet while the machine
   *  is running is the no-op this page was reported for. */
  const status = {
    idle: t('update.checking'),
    checking: t('update.checking'),
    current: t('update.titleCurrent'),
    available:
      state.channel === 'main'
        ? t('update.mainChannel', { count: state.commitsBehind ?? 0 })
        : t('update.titleAvailable'),
    downloading: t('update.titleDownloading'),
    installing: t('update.titleInstalling'),
    ready: t('update.titleReady'),
    applying: t('update.titleApplying'),
    applied: t('update.titleApplied'),
    failed: t('update.titleFailed'),
    unsupported: t('update.title'),
  }[state.phase]

  const action = updateActionOf(state)
  const notice = updateNoticeOf(state)

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
      {notice ? (
        <p data-testid="settings-updates-notice" className="text-ui-xs text-ink-soft">
          {t(notice)}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {action?.takesEffect ? (
          <button
            type="button"
            data-testid="settings-updates-apply"
            onClick={() => void (action.run === 'apply' ? update.apply() : update.install())}
            className="focus-ring rounded-md bg-brand px-2.5 py-1 text-ui-xs font-medium text-white hover:bg-brand-glow"
          >
            {t(action.labelKey)}
          </button>
        ) : null}
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
        {/* The sheet the header opens, on the page that names the version. It sits
            inside the button's row so the dialog returns focus to the control that
            opened it; the portal paints it over the page either way. */}
        <UpdateDialog
          state={state}
          open={update.open}
          onOpenChange={update.setOpen}
          onCheck={() => void update.check()}
          onInstall={() => void update.install()}
          onApply={() => void update.apply()}
          onRelaunch={() => void update.relaunch()}
          releasesUrl={state.url}
          restartBlocked={update.restartBlocked}
        />
      </div>
    </div>
  )
}
