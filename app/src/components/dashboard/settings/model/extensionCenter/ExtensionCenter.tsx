'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2, Search } from 'lucide-react'

import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { toastBus } from '@/lib/toast'
import {
  ApiError,
  getMarketHome,
  getMarketIndex,
  getMarketInstalled,
  getMarketUpdates,
  installMarketPlan,
  planMarketInstall,
  switchMarketPlugin,
  removeMarketPlugin,
  rollbackMarketPlugin,
} from '@/lib/api'
import type {
  MarketHome,
  MarketIndexBody,
  MarketInstalledRow,
  MarketPlan,
  MarketPlugin,
  MarketUpdate,
  MarketVersion,
} from '@/lib/api'
import { MarketCard } from './MarketCard'
import { MarketReview, type PendingInstall } from './MarketReview'
import { MarketSources } from './MarketSources'
import { MarketUpdates } from './MarketUpdates'
import type { SettingsModel } from '../types'

const FIELD =
  'w-full rounded-lg border border-control bg-background/60 px-2.5 py-2 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring focus:border-brand/50 focus:outline-none pointer-coarse:min-h-11'
const BUTTON =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'

function detailOf(err: unknown): Record<string, unknown> {
  if (err instanceof ApiError && err.payload && typeof err.payload === 'object') {
    return err.payload as Record<string, unknown>
  }
  return {}
}

export function ExtensionCenter({
  model,
  view,
}: {
  model: SettingsModel
  view: 'discover' | 'updates'
}) {
  const { t, i18n } = model
  const language = (i18n?.language || 'en').startsWith('de') ? 'de' : 'en'
  const [home, setHome] = useState<MarketHome | null>(null)
  const [index, setIndex] = useState<MarketIndexBody | null>(null)
  const [indexError, setIndexError] = useState('')
  const [installed, setInstalled] = useState<MarketInstalledRow[]>([])
  const [updates, setUpdates] = useState<MarketUpdate[]>([])
  const [updateErrors, setUpdateErrors] = useState<{ source: string; error: string }[]>([])
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [busy, setBusy] = useState('')
  const [pending, setPending] = useState<PendingInstall | null>(null)
  // The switch's inline consent: exactly one block for the card that asked.
  const [consent, setConsent] = useState<{
    plugin: MarketPlugin
    enabled: boolean
    families: string[]
    roots: string[]
  } | null>(null)

  const load = useCallback(async () => {
    try {
      const [homeData, installedData, indexData, updateData] = await Promise.all([
        getMarketHome(),
        getMarketInstalled(),
        getMarketIndex(),
        getMarketUpdates(),
      ])
      setHome(homeData)
      setInstalled(installedData.plugins)
      setIndex(indexData.index)
      setIndexError(indexData.error)
      setUpdates(updateData.updates)
      setUpdateErrors(updateData.errors)
    } catch (err) {
      toastBus.error(t('settings.marketLoadFailed'), err instanceof Error ? err.message : undefined)
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const installedByName = useMemo(
    () => new Map(installed.map((row) => [row.name, row])),
    [installed],
  )
  const updateByName = useMemo(() => new Map(updates.map((row) => [row.name, row])), [updates])
  const categories = useMemo(
    () => Array.from(new Set((index?.plugins ?? []).flatMap((plugin) => plugin.categories))).sort(),
    [index],
  )
  const plugins = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (index?.plugins ?? []).filter((plugin) => {
      if (category && !plugin.categories.includes(category)) return false
      if (!q) return true
      const description =
        typeof plugin.description === 'string'
          ? plugin.description
          : Object.values(plugin.description).join(' ')
      return (
        plugin.name.toLowerCase().includes(q) ||
        plugin.displayName.toLowerCase().includes(q) ||
        description.toLowerCase().includes(q)
      )
    })
  }, [index, query, category])

  const commit = async (plan: MarketPlan) => {
    try {
      const result = await installMarketPlan(plan)
      if (result.status === 'extracted') {
        if (result.enabled === false && result.activation_error) {
          toastBus.error(t('settings.marketInstallNotEnabled', { reason: result.activation_error }))
        } else {
          toastBus.success(t('settings.marketInstalledState'), `${plan.name} v${plan.version}`)
        }
        await load()
        return
      }
      toastBus.error(t('settings.marketInstallFailed'), result.error)
    } catch (err) {
      toastBus.error(
        t('settings.marketInstallFailed'),
        err instanceof Error ? err.message : undefined,
      )
    }
  }

  const startInstall = async (
    sourceId: string,
    plugin: MarketPlugin,
    version: MarketVersion,
    approve: boolean,
  ) => {
    const unsigned = !version.source.signature
    if (!approve && unsigned) {
      setPending({ sourceId, plugin, version, unsigned })
      return
    }
    setBusy(plugin.name)
    try {
      const plan = await planMarketInstall(sourceId, plugin.name, version.version, {
        approvePermissions: approve,
        allowLocalTrust: unsigned,
      })
      if (plan.status === 'permission_review' && plan.delta) {
        setPending({ sourceId, plugin, version, unsigned, delta: plan.delta })
        return
      }
      if (plan.status === 'ready') {
        await commit(plan)
      } else {
        toastBus.error(t('settings.marketPlanFailed'), plan.error)
      }
    } catch (err) {
      const detail = detailOf(err)
      if (detail.delta && typeof detail.delta === 'object') {
        setPending({
          sourceId,
          plugin,
          version,
          unsigned,
          delta: detail.delta as PendingInstall['delta'],
        })
      } else {
        toastBus.error(
          t('settings.marketPlanFailed'),
          err instanceof Error ? err.message : undefined,
        )
      }
    } finally {
      setBusy('')
    }
  }

  const installUpdate = async (update: MarketUpdate) => {
    setBusy(update.name)
    try {
      const response = await getMarketIndex()
      const plugin = response.index?.plugins.find((item) => item.name === update.name)
      const version = plugin?.versions.find((item) => item.version === update.version)
      if (!plugin || !version) {
        toastBus.error(t('settings.marketPlanFailed'), update.name)
        return
      }
      await startInstall(update.source_id, plugin, version, false)
    } catch (err) {
      toastBus.error(t('settings.marketPlanFailed'), err instanceof Error ? err.message : undefined)
    } finally {
      setBusy('')
    }
  }

  const confirmPending = async () => {
    if (!pending) return
    const current = pending
    setPending(null)
    await startInstall(current.sourceId, current.plugin, current.version, true)
  }

  const toggle = async (plugin: MarketPlugin, enabled: boolean, approve = false) => {
    setBusy(plugin.name)
    try {
      const version = plugin.versions[0]
      const result = await switchMarketPlugin({
        name: plugin.name,
        enabled,
        version: version?.version,
        approvePermissions: approve,
        allowLocalTrust: approve || !version?.source.signature,
      })
      if (result.status === 'installed_disabled') {
        toastBus.error(t('settings.marketInstallNotEnabled'), result.activation_error)
      } else {
        toastBus.success(
          enabled ? t('settings.marketSwitchedOn') : t('settings.marketSwitchedOff'),
          plugin.displayName,
        )
      }
      setConsent(null)
      await load()
    } catch (err) {
      const detail = detailOf(err)
      if (detail.code === 'permission_review' || detail.code === 'local_trust_required') {
        const delta = (detail.delta ?? {}) as {
          tool_families_added?: string[]
          data_roots_added?: string[]
        }
        setConsent({
          plugin,
          enabled,
          families: delta.tool_families_added ?? [],
          roots: delta.data_roots_added ?? [],
        })
      } else {
        toastBus.error(
          t('settings.marketSwitchFailed'),
          err instanceof Error ? err.message : undefined,
        )
      }
    } finally {
      setBusy('')
    }
  }

  const remove = async (name: string) => {
    setBusy(name)
    try {
      const result = await removeMarketPlugin(name)
      if (result.status === 'removed') await load()
    } catch (err) {
      const detail = detailOf(err)
      const message =
        detail.code === 'dependents_enabled'
          ? t('settings.marketDependents')
          : err instanceof Error
            ? err.message
            : undefined
      toastBus.error(t('settings.marketRemoveFailed'), message)
    } finally {
      setBusy('')
    }
  }

  const rollback = async (name: string) => {
    setBusy(name)
    try {
      const result = await rollbackMarketPlugin(name)
      if (result.status === 'rolled_back') await load()
    } catch (err) {
      toastBus.error(
        t('settings.marketRollbackFailed'),
        err instanceof Error ? err.message : undefined,
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-4" data-testid={`market-${view}`}>
      <PageHeader
        title={view === 'discover' ? t('settings.marketDiscover') : t('settings.marketUpdates')}
        actions={
          <button
            type="button"
            className={BUTTON}
            onClick={() => void load()}
            disabled={Boolean(busy)}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {t('settings.marketReload')}
          </button>
        }
      />

      {view === 'discover' ? (
        <>
          <MarketSources home={home} t={t} />
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
              <input
                className={`${FIELD} pl-9`}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('settings.marketSearch')}
                aria-label={t('settings.marketSearch')}
                data-testid="market-search"
              />
            </div>
            <select
              className={`${FIELD} sm:w-56`}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              aria-label={t('settings.marketCategory')}
            >
              <option value="">—</option>
              {categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          {indexError && <p className="text-ui-2xs text-status-warning">{indexError}</p>}
          {!index ? (
            <LoadingRow label={t('settings.loading')} />
          ) : plugins.length === 0 ? (
            <p className="text-ui-xs text-ink-faint" data-testid="market-empty">
              {t('settings.marketEmpty')}
            </p>
          ) : (
            <div className="grid gap-2.5 lg:grid-cols-2">
              {plugins.map((plugin) => (
                <MarketCard
                  key={plugin.name}
                  plugin={plugin}
                  installed={installedByName.get(plugin.name)}
                  update={updateByName.get(plugin.name)}
                  language={language}
                  t={t}
                  busy={busy === plugin.name}
                  onInstall={(version) => void startInstall('bundled', plugin, version, false)}
                  onRemove={() => void remove(plugin.name)}
                  onRollback={() => void rollback(plugin.name)}
                  onSwitch={(enabled) => void toggle(plugin, enabled)}
                  switchBusy={busy === plugin.name}
                  consent={
                    consent?.plugin.name === plugin.name
                      ? { families: consent.families, roots: consent.roots }
                      : null
                  }
                  onConsentAllow={() => void toggle(consent!.plugin, consent!.enabled, true)}
                  onConsentCancel={() => setConsent(null)}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <MarketUpdates
          updates={updates}
          errors={updateErrors}
          busy={busy}
          t={t}
          onUpdate={(update) => void installUpdate(update)}
        />
      )}

      {pending && (
        <MarketReview
          pending={pending}
          t={t}
          onApprove={() => void confirmPending()}
          onCancel={() => setPending(null)}
        />
      )}
    </div>
  )
}
