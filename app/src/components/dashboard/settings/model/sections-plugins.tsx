'use client'

import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import Switch from '@/components/shell/Switch'
import SearchInput from '@/components/shell/SearchInput'
import { Puzzle, Power, Store, Compass } from 'lucide-react'
import type { MarketInstalledRow, PluginEntry, PluginView } from '@/lib/api'
import { DeepFields } from './deepFields'
import { installedEntry, pluginSegments } from './pluginRowModel'
import { PluginCard, PluginEmpty } from './pluginRow'
import type { SettingsModel } from './types'

export function renderPlugins(model: SettingsModel) {
  return <PluginsSection model={model} />
}

function PluginsSection({ model }: { model: SettingsModel }) {
  const {
    handlePluginMasterToggle,
    installedPlugins,
    pluginLoadError,
    pluginQuery,
    pluginView,
    reloadPluginStore,
    setPluginQuery,
    t,
  } = model

  // The installed inventory lists the components a manifest declares, including the
  // ones a switched-off bundle contributes to nothing. That is how a row can say
  // "commands, once enabled" without guessing or calling a route for it.
  const installedByName = new Map(
    (installedPlugins ?? []).map((row: MarketInstalledRow) => [row.name, row]),
  )
  const declaresCommands = (p: PluginEntry) =>
    (installedByName.get(p.id)?.components?.includes('commands') ??
      p.components?.includes('commands')) === true

  const switchesDisabled =
    pluginView?.master_enabled === false ||
    pluginView?.read_only === true ||
    pluginView?.unproven === true

  // Count the rows the section paints, not one of the two payload shapes: the view
  // carries `public`/`personal` and, since scope annotation, `global`/`session`.
  // Reading the painted buckets keeps the pill and the empty state true to the list.
  const grouped = pluginSegments(pluginView)
  const allRows = [...grouped.global, ...grouped.session]
  const total = allRows.length
  const activeCount = allRows.filter((p) => p.enabled).length
  const orphans = pluginView?.orphans ?? []
  const empty = pluginView !== null && total === 0 && orphans.length === 0

  return (
    <div className="space-y-4">
      <PageHeader
        title={t('settings.pluginsTitle')}
        subtitle={t('settings.pluginsHint')}
        actions={
          <>
            {pluginView && total > 0 ? (
              <span
                data-testid="plugin-count-pill"
                className="rounded-full bg-brand/15 px-2.5 py-1 text-ui-xs font-medium text-brand-deep"
              >
                {activeCount}
                {' / '}
                {total}
              </span>
            ) : null}
            <button
              type="button"
              data-testid="plugins-open-discover"
              onClick={() => {
                window.location.hash = '#/discover'
              }}
              className="focus-ring flex items-center gap-1.5 rounded-lg border border-hairline-strong px-2.5 py-1 text-ui-xs text-ink-soft hover:border-control hover:text-foreground"
            >
              <Compass className="h-3.5 w-3.5" strokeWidth={1.5} />
              {t('settings.pluginsDiscover')}
            </button>
          </>
        }
      />
      <SearchInput
        value={pluginQuery}
        onChange={setPluginQuery}
        placeholder={t('settings.pluginsSearch')}
        label={t('settings.pluginsSearch')}
      />
      {pluginView?.notices?.some((notice) => notice.code === 'legacy_master_bypass_retired') && (
        <p
          data-testid="plugin-legacy-master-notice"
          className="rounded-xl border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-ui-xs text-status-warning"
        >
          {t('settings.pluginLegacyMasterRetired')}
        </p>
      )}
      {pluginView?.read_only && (
        <p
          data-testid="plugin-read-only-notice"
          className="rounded-xl border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-ui-xs text-status-warning"
        >
          {t('settings.pluginReadOnly')}
        </p>
      )}
      {pluginView?.unproven && (
        <p
          data-testid="plugin-state-unproven-notice"
          className="rounded-xl border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-ui-xs text-status-warning"
        >
          {t('settings.pluginStateUnproven')}
        </p>
      )}
      {pluginView === null && pluginLoadError ? (
        <div
          data-testid="plugins-load-error"
          role="alert"
          className="glass-reading space-y-2 rounded-xl p-4"
        >
          <p className="text-ui-xs font-medium text-status-warning">
            {t('settings.pluginLoadError')}
          </p>
          <p className="text-ui-xs text-ink-soft">{t('settings.pluginLoadErrorHint')}</p>
          <button
            type="button"
            data-testid="plugins-load-retry"
            onClick={() => void reloadPluginStore?.()}
            className="focus-ring inline-flex items-center rounded-lg border border-hairline-strong px-2.5 py-1 text-ui-xs text-ink-soft hover:border-control hover:text-foreground max-lg:min-h-11"
          >
            {t('settings.pluginLoadRetry')}
          </button>
        </div>
      ) : pluginView === null ? (
        <LoadingRow label={t('settings.loading')} />
      ) : empty ? (
        <PluginEmpty t={t} />
      ) : (
        <>
          {/* E1: master kill switch — off = stock Ephe, toggles disabled. */}
          <SettingsGroup
            icon={Store}
            title={t('settings.pluginsGroupMaster')}
            testid="plugins-master"
          >
            <SettingsRow
              icon={Power}
              title={t('settings.pluginsMaster')}
              description={t('settings.pluginsMasterHint')}
              testid="plugins-master-row"
            >
              <Switch
                checked={pluginView.master_enabled !== false}
                label={t('settings.pluginsMaster')}
                testid="plugins-master-toggle"
                disabled={
                  pluginView.master_enabled === false ||
                  pluginView.read_only === true ||
                  pluginView.unproven === true
                }
                onChange={(next) => void handlePluginMasterToggle(next)}
              />
            </SettingsRow>
          </SettingsGroup>
          {(() => {
            // I7-4: filter first, then build the groups. Before this every
            // empty section stood there as an empty card with a dash in it —
            // "Personal" is always empty in the shipped catalog, so that
            // was a box that never had anything to say.
            const q = pluginQuery.trim().toLowerCase()
            const matches = (p: PluginEntry) =>
              !q ||
              p.name.toLowerCase().includes(q) ||
              p.description.toLowerCase().includes(q) ||
              p.tags.some((tg) => tg.toLowerCase().includes(q))
            const segments = (['global', 'session'] as const)
              .map((seg) => ({
                seg,
                rows: grouped[seg].filter(matches),
              }))
              .filter((s) => s.rows.length > 0)
            if (segments.length === 0) {
              return <p className="text-ui-xs text-ink-faint">{t('settings.noResults')}</p>
            }
            return segments.map(({ seg, rows }) => (
              <SettingsGroup
                key={seg}
                icon={seg === 'global' ? Store : Puzzle}
                title={t(`settings.plugins.${seg}`)}
                description={t('settings.pluginsGroupToggleHint')}
                testid={`plugins-section-${seg}`}
              >
                <div className="grid gap-2.5 lg:grid-cols-2">
                  {rows.map((p) => (
                    <PluginCard
                      key={p.id}
                      p={p}
                      segment={seg}
                      view={pluginView}
                      model={model}
                      switchesDisabled={switchesDisabled}
                      declaresCommands={declaresCommands(p)}
                    />
                  ))}
                </div>
              </SettingsGroup>
            ))
          })()}
          {orphans.length > 0 && (
            <SettingsGroup
              icon={Puzzle}
              title={t('settings.plugins.orphans')}
              description={t('settings.plugins.orphansHint')}
              testid="plugins-section-orphans"
            >
              <OrphanRows
                ids={orphans}
                view={pluginView}
                model={model}
                switchesDisabled={switchesDisabled}
              />
            </SettingsGroup>
          )}
        </>
      )}
      {/* I3-V5: the catalog policy sits with the plugins. */}
      <DeepFields model={model} prefixes={['plugins.']} />
    </div>
  )
}

/** Installed bundles without a catalog entry: rows when the inventory answers,
 *  their names when it does not, so an unreachable route never hides an install. */
function OrphanRows({
  ids,
  view,
  model,
  switchesDisabled,
}: {
  ids: string[]
  view: PluginView
  model: SettingsModel
  switchesDisabled: boolean
}) {
  const { installedPlugins, pluginQuery } = model
  const known = new Map((installedPlugins ?? []).map((row: MarketInstalledRow) => [row.name, row]))
  const q = pluginQuery.trim().toLowerCase()
  const matches = (row: PluginEntry) =>
    !q ||
    row.name.toLowerCase().includes(q) ||
    row.description.toLowerCase().includes(q) ||
    row.tags.some((tag) => tag.toLowerCase().includes(q))
  const rows = ids
    .flatMap((id) => {
      const row = known.get(id)
      return row ? [installedEntry(row)] : []
    })
    .filter(matches)
  const unknown = ids.filter((id) => !known.has(id))
  return (
    <div className="space-y-2">
      {rows.length > 0 && (
        <div className="grid gap-2.5 lg:grid-cols-2">
          {rows.map((p) => (
            <PluginCard
              key={p.id}
              p={p}
              segment="orphan"
              view={view}
              model={model}
              switchesDisabled={switchesDisabled}
              declaresCommands={(p.components ?? []).includes('commands')}
            />
          ))}
        </div>
      )}
      {unknown.map((id) => (
        <p
          key={id}
          data-testid={`plugin-orphan-${id}`}
          className="font-mono text-ui-xs text-ink-soft"
        >
          {id}
        </p>
      ))}
    </div>
  )
}
