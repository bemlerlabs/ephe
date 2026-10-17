'use client'

/**
 * The "brains" sub-page of the memory surface: which store answers, whether each of
 * its legs holds, and what a migration would take with it — first a dry run with
 * numbers, only then a button.
 *
 * It owns its own request state because nothing outside this panel reads the report
 * or the switching flag; the page only decides which sub-page to show.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive, Brain, Database, GitCommitHorizontal, Layers, ListChecks } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { migrateMemory, setMemoryProvider, type MemoryStats, type MigrateReport } from '@/lib/api'
import { toastBus } from '@/lib/toast'

// `id` is the stable handle the tests select on; `label` is the surface word and
// comes from the locale — a testid built from the label would change with the
// interface language.
function Leg({ ok, id, label }: { ok: boolean | undefined; id: string; label: string }) {
  const { t } = useTranslation()
  return (
    <span
      className={`font-mono text-ui-xs ${
        ok === false ? 'text-status-warn' : ok === true ? 'text-ink' : 'text-ink-faint'
      }`}
      data-testid={`memory-leg-${id}`}
    >
      {/* The wording carries the statement on its own — colour is only the hint. */}
      {label}: {ok === undefined ? '—' : ok ? t('memory.legOn') : t('memory.legOff')}
    </span>
  )
}

export function MemoryBrainsPanel({
  stats,
  onReload,
}: {
  stats: MemoryStats | null
  onReload: () => void
}) {
  const { t } = useTranslation()
  const [report, setReport] = useState<MigrateReport | null>(null)
  const [switching, setSwitching] = useState(false)
  const provider = stats?.provider ?? ''
  // The surface names its own stores, not the names behind them. The wire value
  // stays the backend contract; the word belongs to Ephe.
  const storeName = (wire: string) =>
    wire === 'kepta' ? t('memory.storeArchive') : wire === 'chroma' ? t('memory.storeIndex') : wire

  const runMigration = async (dryRun: boolean) => {
    setSwitching(true)
    try {
      const r = await migrateMemory(dryRun)
      setReport(r)
      if (!dryRun) {
        toastBus.success(t('memory.migrated', { imported: r.imported, skipped: r.skipped }))
        onReload()
      }
    } catch {
      toastBus.error(t('memory.migrateFailed'))
    } finally {
      setSwitching(false)
    }
  }

  const chooseProvider = async (next: 'kepta' | 'chroma') => {
    setSwitching(true)
    try {
      const r = await setMemoryProvider(next)
      // W4: the result was thrown away although, with no feedback, switching was
      // indistinguishable from a click. `scope` already shows the page from the
      // stats — here the switch carries its own reason.
      toastBus.success(
        t('memory.providerSwitched', { provider: r.provider }),
        r.reason || undefined,
      )
      onReload()
    } catch {
      toastBus.error(t('memory.providerFailed'))
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="space-y-4">
      <SettingsGroup
        icon={Brain}
        title={t('memory.groupBrains')}
        description={t('memory.groupBrainsHint')}
      >
        <SettingsRow
          icon={Database}
          title={t('memory.provider')}
          description={stats?.reason || t('memory.providerUnknown')}
          testid="memory-page-provider"
        >
          <span className="font-mono text-ui-xs text-foreground/80">
            {provider ? storeName(provider) : '—'}
          </span>
        </SettingsRow>
        <SettingsRow
          icon={Layers}
          title={t('memory.legs')}
          description={t('memory.legsHint')}
          testid="memory-page-legs"
        >
          <span className="flex items-center gap-3">
            <Leg id="vector" label={t('memory.legVector')} ok={stats?.vector_leg} />
            <Leg id="lexical" label={t('memory.legLexical')} ok={stats?.lexical_leg} />
          </span>
        </SettingsRow>
        <SettingsRow
          icon={ListChecks}
          title={t('memory.scope')}
          description={t('memory.scopeHint')}
          testid="memory-page-scope"
        >
          <span className="max-w-[55%] break-all text-right font-mono text-ui-2xs text-ink-faint">
            {stats?.scope || '—'}
          </span>
        </SettingsRow>
        <SettingsRow
          icon={GitCommitHorizontal}
          title={t('memory.switch')}
          description={t('memory.switchHint')}
          testid="memory-page-switch"
        >
          <span className="flex items-center gap-2">
            {(['kepta', 'chroma'] as const).map((next) => (
              <button
                key={next}
                type="button"
                disabled={switching || next === provider}
                onClick={() => void chooseProvider(next)}
                className="rounded-lg border border-hairline px-3 py-1.5 text-ui-xs font-medium text-ink-faint transition-colors hover:text-foreground disabled:opacity-40 max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                {storeName(next)}
              </button>
            ))}
          </span>
        </SettingsRow>
      </SettingsGroup>

      <SettingsGroup
        icon={Archive}
        title={t('memory.groupMigrate')}
        description={t('memory.groupMigrateHint')}
      >
        <SettingsRow
          icon={Archive}
          title={t('memory.dryRun')}
          description={t('memory.dryRunHint')}
          testid="memory-page-dryrun"
        >
          <button
            type="button"
            disabled={switching}
            onClick={() => void runMigration(true)}
            className="rounded-lg bg-brand/20 px-3 py-1.5 text-ui-xs font-medium text-brand-deep transition-colors hover:bg-brand/25 max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            {t('memory.dryRunGo')}
          </button>
        </SettingsRow>
        {report && (
          <div
            data-testid="memory-migrate-report"
            className="border-t border-hairline px-4 py-3 font-mono text-ui-xs text-ink-faint"
          >
            <p>
              {storeName(report.provider_source)} → {storeName(report.provider_target)} ·{' '}
              {/* The dry run only knows the source: it counts that and writes
                  nothing. "0 would move" would be a number the endpoint never
                  computes. */}
              {report.dry_run
                ? t('memory.reportSource', { source: report.source_total })
                : t('memory.reportCount', {
                    source: report.source_total,
                    imported: report.imported,
                    skipped: report.skipped,
                    target: report.target_total,
                  })}
            </p>
            <p>{t('memory.reportTargetHere')}</p>
            {!report.dry_run && <p className="mt-1 text-brand-deep">{t('memory.migrateDone')}</p>}
            {report.dry_run && (
              <button
                type="button"
                disabled={switching}
                onClick={() => void runMigration(false)}
                className="mt-2 rounded-lg border border-status-danger/30 bg-status-danger/15 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/25 max-lg:min-h-11"
              >
                {t('memory.migrateGo')}
              </button>
            )}
          </div>
        )}
      </SettingsGroup>
    </div>
  )
}
