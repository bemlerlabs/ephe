/** The centred detail surface for one shelf item (S3): provenance, launch
 *  line, version and the actions — the card stays a card. */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui'
import { Button } from '@/components/ui'
import { dryRunEntry, type DryRunResult } from '@/lib/api'
import type { DiscoverItem } from './discoverModel'

export interface DiscoverDetailProps {
  item: DiscoverItem | null
  busy: boolean
  onClose: () => void
  onAdd: (item: DiscoverItem) => Promise<void> | undefined
  onToggle: (item: DiscoverItem, next: boolean) => Promise<void> | undefined
  onRemove: (item: DiscoverItem) => Promise<void> | undefined
}

export function DiscoverDetail({
  item,
  busy,
  onClose,
  onAdd,
  onToggle,
  onRemove,
}: DiscoverDetailProps) {
  const { t } = useTranslation()
  const [rehearsal, setRehearsal] = useState<DryRunResult | null>(null)

  const rehearse = async (target: DiscoverItem) => {
    setRehearsal(null)
    try {
      setRehearsal(
        await dryRunEntry({
          name: target.name,
          description: target.summary,
          install_hint: target.installHint,
          spec: target.spec,
        }),
      )
    } catch {
      setRehearsal({ verdict: 'checked', findings: [], mode: 'static' })
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        {item ? (
          <>
            <DialogHeader>
              <p
                data-testid="discover-detail-origin"
                className="font-mono text-ui-xs uppercase tracking-[0.16em] text-brand"
              >
                {item.origin}
              </p>
              <DialogTitle className="text-left font-display text-xl">{item.title}</DialogTitle>
            </DialogHeader>
            <div className="mt-4 space-y-4 text-ui-sm">
              <p data-testid="discover-detail-summary" className="text-ink-soft">
                {item.summary}
              </p>
              {item.badge ? (
                <span
                  data-testid="discover-detail-badge"
                  className="inline-flex rounded-full bg-brand/15 px-2.5 py-0.5 font-mono text-ui-xs text-brand-deep"
                >
                  {t(`discover.badge.${item.badge}`)}
                </span>
              ) : null}
              <dl className="grid gap-2 rounded-xl border border-hairline bg-surface/40 p-4 font-mono text-ui-xs text-ink-soft">
                {item.installHint ? (
                  <>
                    <dt className="text-ink-faint">{t('discover.detailInstall')}</dt>
                    <dd
                      data-testid="discover-detail-install"
                      className="break-all text-foreground/90"
                    >
                      {item.installHint}
                    </dd>
                  </>
                ) : item.spec ? (
                  <>
                    <dt className="text-ink-faint">{t('discover.detailAttached')}</dt>
                    <dd className="break-all text-foreground/90">{item.spec}</dd>
                  </>
                ) : null}
                {item.version ? (
                  <>
                    <dt className="text-ink-faint">{t('discover.detailVersion')}</dt>
                    <dd>{item.version}</dd>
                  </>
                ) : null}
                <dt className="text-ink-faint">{t('discover.detailPermissions')}</dt>
                <dd data-testid="discover-detail-permissions">
                  {item.installed
                    ? t('discover.detailPermissionsInstalled')
                    : t('discover.detailPermissionsReview')}
                </dd>
              </dl>
              {item.kind === 'connector' && !item.installed ? (
                <div className="space-y-1">
                  <button
                    type="button"
                    data-testid="discover-detail-rehearse"
                    disabled={busy}
                    onClick={() => void rehearse(item)}
                    className="focus-ring rounded-lg border border-hairline px-2.5 py-1 text-ui-xs text-ink-soft hover:border-hairline-strong hover:text-foreground disabled:opacity-50"
                  >
                    {t('discover.dryRun')}
                  </button>
                  {rehearsal ? (
                    <p data-testid="discover-detail-verdict" className="font-mono text-ui-xs text-ink-soft">
                      {t(`discover.verdict.${rehearsal.verdict}`)}
                      {rehearsal.findings.length
                        ? ` · ${t('discover.verdictFindings', { count: rehearsal.findings.length })}`
                        : ''}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {item.docs ? (
                <a
                  data-testid="discover-detail-docs"
                  className="inline-block text-brand hover:underline"
                  href={item.docs}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t('discover.detailDocs')}
                </a>
              ) : null}
              <div className="flex items-center gap-2 pt-1">
                {item.installed ? (
                  <>
                    <Button
                      data-testid="discover-detail-toggle"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void onToggle(item, !item.enabled)}
                    >
                      {item.enabled ? t('discover.stateOffAction') : t('discover.stateOnAction')}
                    </Button>
                    <Button
                      data-testid="discover-detail-remove"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void onRemove(item)}
                    >
                      {t('discover.detailRemove')}
                    </Button>
                  </>
                ) : (
                  <Button
                    data-testid="discover-detail-add"
                    disabled={busy}
                    onClick={() => void onAdd(item)}
                  >
                    {t('discover.detailAdd')}
                  </Button>
                )}
              </div>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
