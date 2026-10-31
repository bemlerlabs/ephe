/** The centred detail surface for one shelf item (S3): provenance, launch
 *  line, version and the actions — the card stays a card. */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui'
import { Button } from '@/components/ui'
import { dryRunEntry, type DryRunResult } from '@/lib/api'
import { CredentialFields } from './CredentialFields'
import { CategoryGlyph } from './categoryGlyph'
import './discover.css'
import type { DiscoverItem } from './discoverModel'

export interface DiscoverDetailProps {
  item: DiscoverItem | null
  busy: boolean
  onClose: () => void
  onAdd: (item: DiscoverItem) => Promise<void> | undefined
  onToggle: (item: DiscoverItem, next: boolean) => Promise<void> | undefined
  onRemove: (item: DiscoverItem) => Promise<void> | undefined
}

/** One labelled fact. The value keeps its own line when it is a command. */
function Row({
  label,
  children,
  mono = false,
  testId,
}: {
  label: string
  children: React.ReactNode
  mono?: boolean
  testId?: string
}) {
  return (
    <div className="flex items-start justify-between gap-6 px-4 py-3">
      <dt className="shrink-0 text-ui-xs text-ink-faint">{label}</dt>
      <dd
        data-testid={testId}
        className={`min-w-0 text-right text-ui-xs text-foreground/90 ${
          mono ? 'break-all font-mono text-ui-2xs' : ''
        }`}
      >
        {children}
      </dd>
    </div>
  )
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
      <DialogContent className="max-w-xl">
        {item ? (
          <div data-subject={item.categories[0] ?? 'other'}>
            <DialogHeader className="text-left">
              <div className="flex items-start gap-4">
                <span
                  aria-hidden="true"
                  className="discover-plate grid h-12 w-12 shrink-0 place-items-center rounded-xl border"
                >
                  {item.icon ? (
                    <img
                      src={item.icon}
                      alt=""
                      width={40}
                      height={40}
                      className="h-10 w-10 rounded-lg object-contain"
                    />
                  ) : item.kind === 'skill' ? (
                    <span className="font-display text-xl leading-none">
                      {(item.title.trim()[0] ?? '?').toUpperCase()}
                    </span>
                  ) : (
                    <CategoryGlyph
                      category={item.categories[0]}
                      kind={item.kind}
                      className="h-5 w-5"
                    />
                  )}
                </span>
                <div className="min-w-0">
                  <p
                    data-testid="discover-detail-origin"
                    className="font-mono text-ui-2xs uppercase tracking-[0.18em] text-ink-faint"
                  >
                    {t(`discover.kind${item.kind.charAt(0).toUpperCase()}${item.kind.slice(1)}`)} ·{' '}
                    {t(`discover.origin.${item.origin}`, { defaultValue: item.origin })}
                  </p>
                  <DialogTitle className="mt-1.5 font-display text-[1.7rem] leading-tight">
                    {item.title}
                  </DialogTitle>
                </div>
              </div>
            </DialogHeader>

            <p
              data-testid="discover-detail-summary"
              className="mt-4 text-ui-sm leading-relaxed text-ink-soft"
            >
              {item.summary}
            </p>

            {item.why ? (
              <div data-testid="discover-detail-why" className="mt-3">
                <p className="font-mono text-ui-2xs uppercase tracking-[0.16em] text-ink-faint">
                  {t('discover.whyFeatured')}
                </p>
                <p className="mt-1 text-ui-xs leading-relaxed text-ink-soft">{item.why}</p>
              </div>
            ) : null}

            {item.badge && item.badge !== 'pick' ? (
              <p
                data-testid="discover-detail-badge"
                className="mt-2 font-mono text-ui-2xs uppercase tracking-wide text-ink-faint"
              >
                {t(`discover.badge.${item.badge}`)}
              </p>
            ) : null}

            <dl className="mt-5 divide-y divide-hairline overflow-hidden rounded-2xl border border-hairline bg-surface/40">
              {item.publisher ? (
                <Row label={t('discover.detailPublisher')}>{item.publisher}</Row>
              ) : null}
              {item.downloads ? (
                <Row label={t('discover.detailDownloads')}>
                  {t('discover.cardDownloads', { count: item.downloads })}
                </Row>
              ) : null}
              {item.toolCount !== undefined ? (
                <Row label={t('discover.detailTools')}>
                  {t('discover.cardTools', { count: item.toolCount })}
                </Row>
              ) : null}
              {item.version ? <Row label={t('discover.detailVersion')}>{item.version}</Row> : null}
              {item.docs ? (
                <Row label={t('discover.detailDocs')} testId="discover-detail-docs">
                  <a
                    href={item.docs}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="focus-ring break-all text-brand hover:underline"
                  >
                    {item.docs}
                  </a>
                </Row>
              ) : null}
              {item.sources?.length ? (
                <Row label={t('discover.detailSources')} testId="discover-detail-sources">
                  <span className="flex flex-col gap-0.5">
                    {item.sources.map((one) => (
                      <a
                        key={one}
                        href={one}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="focus-ring break-all text-brand hover:underline"
                      >
                        {one.replace(/^https?:\/\//, '')}
                      </a>
                    ))}
                  </span>
                </Row>
              ) : null}
              {item.installHint ? (
                <Row label={t('discover.detailInstall')} mono testId="discover-detail-install">
                  {item.installHint}
                </Row>
              ) : item.spec ? (
                <Row label={t('discover.detailAttached')} mono>
                  {item.spec}
                </Row>
              ) : null}
              <div className="px-4 py-3">
                <dt className="text-ui-xs text-ink-faint">{t('discover.detailPermissions')}</dt>
                <dd
                  data-testid="discover-detail-permissions"
                  className="mt-1 text-ui-xs leading-relaxed text-foreground/90"
                >
                  {item.installed
                    ? t('discover.detailPermissionsInstalled')
                    : t('discover.detailPermissionsReview')}
                </dd>
              </div>
            </dl>

            {item.kind === 'connector' && !item.installed ? (
              <div className="mt-3 space-y-1">
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
                  <p
                    data-testid="discover-detail-verdict"
                    className="font-mono text-ui-xs text-ink-soft"
                  >
                    {t(`discover.verdict.${rehearsal.verdict}`)}
                    {rehearsal.findings.length
                      ? ` · ${t('discover.verdictFindings', { count: rehearsal.findings.length })}`
                      : ''}
                  </p>
                ) : null}
              </div>
            ) : null}

            {item.requiredEnv?.length ? <CredentialFields names={item.requiredEnv} /> : null}

            <div className="mt-6 flex items-center gap-2 border-t border-hairline pt-4">
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
                    className="text-ink-faint hover:text-status-danger"
                  >
                    {t('discover.detailRemove')}
                  </Button>
                </>
              ) : (
                <Button
                  data-testid="discover-detail-add"
                  disabled={busy}
                  onClick={() => void onAdd(item)}
                  className="ml-auto h-10 px-5"
                >
                  {t('discover.detailAdd')}
                </Button>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
