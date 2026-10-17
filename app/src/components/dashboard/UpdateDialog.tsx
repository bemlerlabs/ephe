'use client'

/**
 * R2-U: the update path. A dialog that reports the actual state — including
 * the one where nothing could be checked at all. The header button is always
 * present; it used to be a banner that only existed when an update was
 * available, so anyone who just wanted to look had nothing to operate.
 *
 * U-2: the two running phases are drawn as what they are. The download has a
 * measured percentage, or the indeterminate sweep when the source reports no
 * total; the installation is a step without a percentage of its own; the
 * finished state confirms itself.
 *
 * U-4: the dialog follows the sheet's reading direction. Structure comes from
 * rules and indents, columns from one mono axis, and the single accent marks
 * what is running now: no box, no radius, no shadow. The Details section names
 * the package, the two versions, the size the transfer reported and the notes
 * the feed carried — the release's own words, readable while the download runs
 * and after it lands.
 */
import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Download,
  Loader2,
  RotateCw,
} from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/Dialog'
import { Rule } from '@/components/ui/Rule'
import { isDesktopShell, type UpdateState } from '@/lib/useUpdateCheck'
import type { RestartBlock } from '@/lib/restartGuard'
import { formatBytes } from '@/lib/updateDetails'

interface Props {
  state: UpdateState
  open: boolean
  onOpenChange: (open: boolean) => void
  onCheck: () => void
  onInstall: () => void
  onRelaunch: () => void
  releasesUrl?: string
  /** Why a restart is held back right now — undefined when nothing holds it. */
  restartBlocked?: RestartBlock | null
}

/** Inline code spans in the release notes, rendered in the mono face. */
function inline(text: string): ReactNode {
  return text.split('`').map((part, index) =>
    index % 2 === 1 ? (
      <code key={index} className="bg-surface px-1 font-mono text-ui-2xs text-ink">
        {part}
      </code>
    ) : (
      part
    ),
  )
}

/** The release notes as the feed wrote them: headings, bullets, paragraphs.
 *  No markdown dependency — the release feed has carried exactly these three
 *  shapes since the first release. */
function NotesBody({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  text.split('\n').forEach((raw, index) => {
    const line = raw.trim()
    if (!line) return
    if (line.startsWith('### ')) {
      blocks.push(
        <h4 key={index} className="mt-3 text-scale-ui font-semibold text-foreground first:mt-0">
          {line.slice(4)}
        </h4>,
      )
      return
    }
    if (line.startsWith('- ')) {
      blocks.push(
        <p key={index} className="flex gap-2 py-0.5 text-scale-ui text-ink-soft">
          <span className="mt-[0.65em] h-1 w-1 shrink-0 rounded-full bg-brand" aria-hidden="true" />
          <span className="min-w-0">{inline(line.slice(2))}</span>
        </p>,
      )
      return
    }
    blocks.push(
      <p key={index} className="py-0.5 text-scale-ui text-ink-soft">
        {inline(line)}
      </p>,
    )
  })
  return <>{blocks}</>
}

/** One line of the Details block: a rule, a label at 13px, a value on the
 *  right edge of the mono axis. */
function DetailRow({
  label,
  value,
  mono = false,
  testId,
}: {
  label: string
  value: string
  mono?: boolean
  testId?: string
}) {
  return (
    <>
      <Rule />
      <div className="flex items-baseline gap-3 py-1.5">
        <span className="text-scale-ui text-ink-faint">{label}</span>
        <span
          data-testid={testId}
          className={`ml-auto text-right ${mono ? 'font-mono tabular-nums text-scale-data' : 'text-scale-ui'} text-ink-faint`}
        >
          {value}
        </span>
      </div>
    </>
  )
}

export function UpdateDialog({
  state,
  open,
  onOpenChange,
  onCheck,
  onInstall,
  onRelaunch,
  releasesUrl,
  restartBlocked = null,
}: Props) {
  const { t } = useTranslation()
  const desktop = isDesktopShell()
  const pct = state.progress === null ? null : Math.round(state.progress * 100)
  const downloading = state.phase === 'downloading'
  const installing = state.phase === 'installing'
  /** The bar reports the download: during the installation it stands at the
   *  value the download ended with, which is 100 %. */
  const barValue = installing ? 100 : downloading ? pct : null
  const running = downloading || installing
  const size = formatBytes(state.sizeBytes)
  const notReported = t('update.detailsUnknown')
  /** The Details block is worth opening wherever the release carries facts —
   *  not only in the desktop build: the browser can read the versions and the
   *  notes just as well. */
  const hasFacts =
    state.phase === 'available' || downloading || installing || state.phase === 'ready'

  const title = {
    idle: t('update.title'),
    checking: t('update.title'),
    current: t('update.titleCurrent'),
    failed: state.failedAt === 'install' ? t('update.titleInstallFailed') : t('update.titleFailed'),
    available: t('update.titleAvailable'),
    downloading: t('update.titleDownloading'),
    installing: t('update.titleInstalling'),
    ready: t('update.titleReady'),
    unsupported: t('update.title'),
  }[state.phase]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="update-dialog"
        data-phase={state.phase}
        className="update-dialog-panel max-w-md"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-scale-title">
            {(state.phase === 'checking' || installing) && (
              <Loader2 className="h-4 w-4 animate-spin text-brand" />
            )}
            {state.phase === 'current' && <CheckCircle2 className="h-4 w-4 text-status-success" />}
            {state.phase === 'failed' && <AlertTriangle className="h-4 w-4 text-status-warning" />}
            {(state.phase === 'available' || downloading) && (
              <Download className="h-4 w-4 text-brand" />
            )}
            {state.phase === 'ready' && (
              <CheckCircle2 className="update-confirm h-4 w-4 text-status-success" />
            )}
            {title}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-1">
          <p data-testid="update-state" className="text-scale-ui text-ink-faint">
            {state.phase === 'checking' && t('update.checking')}
            {state.phase === 'current' && t('update.isCurrent', { version: state.current ?? '' })}
            {state.phase === 'failed' && (
              <>
                {state.failedAt === 'install' ? t('update.installFailed') : t('update.checkFailed')}
                {state.reason && (
                  <span className="mt-1 block font-mono text-ui-2xs" data-testid="update-reason">
                    {state.reason}
                  </span>
                )}
              </>
            )}
            {state.phase === 'unsupported' && t('update.disabledHint')}
            {downloading && t('update.downloading', { version: state.latest ?? '' })}
            {installing && t('update.installing', { version: state.latest ?? '' })}
            {state.phase === 'ready' && t('update.ready')}
          </p>

          {hasFacts && (
            <div
              className={`update-stage mt-3${running ? ' is-running' : ''}`}
              data-testid="update-stage"
              data-running={running ? 'true' : undefined}
            >
              <span className="update-orb" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="font-mono text-scale-data tabular-nums text-ink-soft">
                  <span>{state.current ?? '—'}</span>
                  <span className="px-2 text-brand" aria-hidden="true">
                    →
                  </span>
                  <span>{state.latest ?? '—'}</span>
                </p>
                <p className="mt-0.5 text-scale-ui text-ink-faint">{t('update.stageHint')}</p>
              </div>
            </div>
          )}

          {running && (
            <div className="mt-3">
              <div
                role="progressbar"
                aria-label={t('update.titleDownloading')}
                aria-valuenow={barValue === null ? undefined : barValue}
                aria-valuemin={0}
                aria-valuemax={100}
                data-testid="update-progress"
                data-indeterminate={downloading && pct === null ? 'true' : undefined}
                className="h-0.5 w-full overflow-hidden bg-hairline"
              >
                <div
                  data-testid="update-progress-fill"
                  className={
                    // Determinate: the width follows the reported percentage, one
                    // 180 ms ease-settle step at a time. Indeterminate: a 40 %
                    // band crosses the track in 1.4 s, and no number is claimed
                    // (aria-valuenow stays off). Installed: the track stands full.
                    installing || (downloading && pct === 100)
                      ? 'h-full w-full bg-brand'
                      : pct === null
                        ? 'update-progress-sweep h-full bg-brand'
                        : 'h-full bg-brand transition-[width] duration-base ease-settle'
                  }
                  style={downloading && pct !== null ? { width: `${pct}%` } : undefined}
                />
              </div>
              {(installing || pct !== null) && (
                <p
                  data-testid="update-percent"
                  className="mt-1.5 text-right font-mono text-scale-data tabular-nums text-ink-faint"
                >
                  {t('update.percent', { pct: installing ? 100 : pct })}
                </p>
              )}
            </div>
          )}

          {!desktop && state.phase === 'available' && (
            <p data-testid="update-browser-note" className="mt-3 text-scale-ui text-ink-soft">
              {t('update.browserNote')}
            </p>
          )}

          {hasFacts && (
            <section className="mt-4" data-testid="update-notes">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-scale-ui text-ink-faint">{t('update.notesTitle')}</p>
                {state.date && (
                  <p className="font-mono text-ui-2xs text-ink-faint">{state.date.slice(0, 10)}</p>
                )}
              </div>
              <div
                className="update-notes mt-2 max-h-56 overflow-y-auto pr-2"
                data-testid="update-details-notes"
              >
                <NotesBody text={state.notes ?? t('update.detailsNoNotes')} />
              </div>
            </section>
          )}

          {hasFacts && (
            <details className="update-details mt-3" data-testid="update-details">
              <summary className="update-details-summary flex items-center gap-1.5 text-scale-ui text-ink-soft">
                <ChevronRight className="update-caret h-3.5 w-3.5" aria-hidden="true" />
                {t('update.details')}
              </summary>
              <div className="update-details-body mt-1 pl-6">
                <DetailRow
                  label={t('update.detailsVersion')}
                  value={`${state.current ?? '—'} → ${state.latest ?? '—'}`}
                  mono
                  testId="update-details-version"
                />
                <DetailRow
                  label={t('update.detailsSize')}
                  value={size ?? notReported}
                  mono={!!size}
                  testId="update-details-size"
                />
                <DetailRow
                  label={t('update.detailsPlatform')}
                  value={state.platform ?? notReported}
                  testId="update-details-platform"
                />
                <DetailRow
                  label={t('update.detailsAsset')}
                  value={state.asset ?? notReported}
                  testId="update-details-asset"
                />
                {state.date && (
                  <DetailRow
                    label={t('update.detailsDate')}
                    value={state.date.slice(0, 10)}
                    mono
                    testId="update-details-date"
                  />
                )}
              </div>
            </details>
          )}

          <Rule className="mt-3" tone={running ? 'now' : 'rule'} />

          <div className="flex items-center gap-2 pt-3">
            {state.phase === 'available' && (
              <button
                type="button"
                data-testid="update-install"
                onClick={onInstall}
                className="flex-1 bg-brand px-3 py-2 text-scale-ui font-medium text-white transition-[background-color] duration-base ease-settle hover:bg-brand-glow"
              >
                {desktop ? t('update.installAndRestart') : t('update.viewReleases')}
              </button>
            )}
            {state.phase === 'available' && (
              <button
                type="button"
                data-testid="update-later"
                onClick={() => onOpenChange(false)}
                className="px-3 py-2 text-scale-ui text-ink-faint transition-colors duration-base ease-settle hover:text-foreground"
              >
                {t('update.later')}
              </button>
            )}
            {state.phase === 'ready' && desktop && (
              <button
                type="button"
                data-testid="update-relaunch"
                onClick={onRelaunch}
                disabled={restartBlocked !== null}
                className="flex-1 bg-brand px-3 py-2 text-scale-ui font-medium text-white transition-[background-color] duration-base ease-settle hover:bg-brand-glow disabled:opacity-40"
              >
                {t('update.relaunchNow')}
              </button>
            )}
            {!desktop && state.phase === 'available' && releasesUrl && (
              <a
                href={releasesUrl}
                target="_blank"
                rel="noreferrer"
                data-testid="update-releases-link"
                className="min-w-0 truncate text-scale-ui text-brand-deep underline-offset-2 hover:underline"
              >
                {releasesUrl.replace(/^https:\/\/(github\.com\/)?/, '')}
              </a>
            )}
            {(state.phase === 'failed' || state.phase === 'current' || state.phase === 'idle') && (
              <button
                type="button"
                data-testid="update-recheck"
                onClick={onCheck}
                className="inline-flex items-center gap-1.5 border border-hairline px-3 py-2 text-scale-ui text-ink-faint transition-colors duration-base ease-settle hover:text-foreground"
              >
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                {t('update.recheck')}
              </button>
            )}
          </div>

          {state.phase === 'ready' && desktop && restartBlocked && (
            <p data-testid="update-restart-blocked" className="pt-2 text-scale-ui text-ink-soft">
              {restartBlocked === 'running'
                ? t('update.restartBlockedRunning')
                : t('update.restartBlockedDraft')}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
