'use client'

/**
 * The "brains" sub-page of the memory surface: which store answers, whether each of
 * its legs holds, and what a migration would take with it — first a dry run with
 * numbers, only then a button.
 *
 * It owns its own request state because nothing outside this panel reads the report
 * or the switching flag; the page only decides which sub-page to show.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive, Brain, Database, GitCommitHorizontal, Layers, ListChecks } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import {
  listMemoryProviders,
  migrateMemory,
  setMemoryProvider,
  type MemoryStats,
  type MigrateReport,
} from '@/lib/api'
import {
  readEmbeddingModel,
  startEmbeddingReembed,
  type EmbeddingReembed,
} from '@/lib/embeddingModel'
import { toastBus } from '@/lib/toast'

const REEMBED_POLL_MS = 1500

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
  const [providers, setProviders] = useState<string[]>([])
  const [reembed, setReembed] = useState<EmbeddingReembed | null>(null)
  const [reembedding, setReembedding] = useState(false)
  const [reembedStartFailed, setReembedStartFailed] = useState(false)
  const reembedTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const provider = stats?.provider ?? ''
  const chunks = stats?.chunks ?? 0
  const embedded = stats?.chunks_embedded ?? 0
  // A pass can only help when the vector arm loads; coverage is honest even when it
  // cannot (0 of N stays visible, the action waits for a model).
  const coverageIncomplete = chunks > 0 && embedded < chunks
  const canReembed = coverageIncomplete && stats?.vector_leg === true

  useEffect(
    () => () => {
      if (reembedTimer.current) clearInterval(reembedTimer.current)
    },
    [],
  )

  const followReembed = () => {
    if (reembedTimer.current) clearInterval(reembedTimer.current)
    reembedTimer.current = setInterval(async () => {
      const status = await readEmbeddingModel()
      const pass = status?.reembed ?? null
      setReembed(pass)
      if (pass?.running) return
      if (reembedTimer.current) clearInterval(reembedTimer.current)
      reembedTimer.current = null
      setReembedding(false)
      onReload()
    }, REEMBED_POLL_MS)
  }

  const startReembed = async () => {
    setReembedStartFailed(false)
    setReembedding(true)
    const started = await startEmbeddingReembed()
    if (started) {
      followReembed()
      return
    }
    // `started: false` also means "a pass is already running": follow that one
    // instead of claiming a failure the store does not have.
    const status = await readEmbeddingModel()
    setReembed(status?.reembed ?? null)
    if (status?.reembed.running) {
      followReembed()
      return
    }
    setReembedding(false)
    setReembedStartFailed(true)
  }

  // The fetch starts the pass by itself. A Brains page opened while it runs shows
  // the progress instead of a button whose click would return "already running".
  useEffect(() => {
    if (!canReembed) return
    let alive = true
    void readEmbeddingModel().then((status) => {
      if (!alive || !status?.reembed.running) return
      setReembed(status.reembed)
      setReembedding(true)
      followReembed()
    })
    return () => {
      alive = false
    }
  }, [canReembed])
  // The surface names its own stores, not the names behind them. The wire value
  // stays the backend contract; the word belongs to Ephe.
  const storeName = (wire: string) =>
    wire === 'kepta'
      ? t('memory.storeArchive')
      : wire === 'kepta-bridge'
        ? t('memory.storeBridge')
        : wire

  // The list comes from the backend for the same reason the switch validates
  // against it: a hardcoded pair offers a store the route would refuse.
  useEffect(() => {
    let alive = true
    void listMemoryProviders()
      .then((answer) => {
        if (alive) setProviders(answer.providers ?? [])
      })
      .catch(() => {
        if (alive && stats?.provider) setProviders([stats.provider])
      })
    return () => {
      alive = false
    }
  }, [stats?.provider])

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

  const chooseProvider = async (next: string) => {
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
          <span className="flex flex-col items-end gap-0.5">
            <span className="flex items-center gap-3">
              <Leg id="vector" label={t('memory.legVector')} ok={stats?.vector_leg} />
              <Leg id="lexical" label={t('memory.legLexical')} ok={stats?.lexical_leg} />
            </span>
            {chunks > 0 && (
              <span
                data-testid="memory-vector-coverage"
                className={`font-mono text-ui-2xs ${
                  embedded === 0 ? 'text-status-warn' : 'text-ink-faint'
                }`}
              >
                {t('memory.vectorCoverage', { embedded, chunks })}
              </span>
            )}
            {canReembed && (
              <span className="flex flex-col items-end gap-0.5">
                {reembedding ? (
                  <span
                    data-testid="memory-reembed-progress"
                    className="font-mono text-ui-2xs text-ink-faint"
                  >
                    {t('memory.vectorReembedRunning', {
                      embedded: reembed?.embedded ?? 0,
                      total: reembed?.total ?? chunks,
                    })}
                  </span>
                ) : (
                  <button
                    type="button"
                    data-testid="memory-reembed-start"
                    onClick={() => void startReembed()}
                    className="rounded-lg border border-control px-2 py-1 text-ui-2xs font-medium text-ink-faint transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                  >
                    {t('memory.vectorReembed')}
                  </button>
                )}
                {reembedStartFailed && (
                  <span
                    data-testid="memory-reembed-error"
                    className="text-ui-2xs text-status-danger"
                  >
                    {t('memory.vectorReembedStartFailed')}
                  </span>
                )}
                {!reembedding && reembed?.error && (
                  <span
                    data-testid="memory-reembed-error"
                    className="text-ui-2xs text-status-danger"
                  >
                    {t('memory.vectorReembedFailed', { reason: reembed.error })}
                  </span>
                )}
              </span>
            )}
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
            {providers.map((next) => (
              <button
                key={next}
                type="button"
                disabled={switching || next === provider}
                onClick={() => void chooseProvider(next)}
                className="rounded-lg border border-control px-3 py-1.5 text-ui-xs font-medium text-ink-faint transition-colors hover:text-foreground disabled:opacity-40 max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
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
