'use client'

import { useState } from 'react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import Switch from '@/components/shell/Switch'
import SearchInput from '@/components/shell/SearchInput'
import PluginIcon from '@/components/shell/PluginIcon'
import PluginSwitch from '@/components/ui/PluginSwitch'
import { Puzzle, Power, Store, MessageSquarePlus, Compass, MonitorPlay } from 'lucide-react'
import type { PluginEntry, PluginStateReport, PluginStateUsage, PluginView } from '@/lib/api'
import { ApiError, getPluginState, removePluginStateFile } from '@/lib/api'
import { startDisposableChat } from '@/lib/chatSeed'
import { examplePromptFor } from '@/lib/pluginExamples'
import { hidePluginSurface, isPluginSurfaceOpen, showPluginSurface } from '@/lib/pluginDisplay'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function renderPlugins(model: SettingsModel) {
  return <PluginsSection model={model} />
}

/** How many tools the rail itself names: the entries a worker runs, or the kernel tools a
 *  bundle switches on. Zero is shown, because "this bundle contributes no tool of its own"
 *  is the sentence a reader needs on a `kernel` row before the migration moves it. */
function storedSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** The number on the row, and the list that removes one stored file. */
function PluginStoredFiles({
  id,
  usage,
  t,
}: {
  id: string
  usage: PluginStateUsage
  t: SettingsModel['t']
}) {
  const [open, setOpen] = useState(false)
  const [report, setReport] = useState<PluginStateReport | null>(null)
  const [armed, setArmed] = useState<string | null>(null)
  const [problem, setProblem] = useState<'read' | 'remove' | null>(null)

  const used = report?.used_mb ?? usage.used_mb
  const cap = report?.cap_mb ?? usage.cap_mb

  async function toggle() {
    if (open) {
      setOpen(false)
      setArmed(null)
      return
    }
    setProblem(null)
    setOpen(true)
    try {
      setReport(await getPluginState(id))
    } catch {
      setProblem('read')
    }
  }

  async function remove(name: string) {
    if (armed !== name) {
      setArmed(name)
      setProblem(null)
      return
    }
    setProblem(null)
    try {
      setReport(await removePluginStateFile(id, name))
      setArmed(null)
    } catch {
      setProblem('remove')
    }
  }

  return (
    <div className="space-y-1.5" data-testid={`plugin-state-${id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span data-testid={`plugin-state-usage-${id}`} className="text-ui-xs text-ink-faint">
          {t('settings.pluginStateUsage', { used, cap })}
        </span>
        <button
          type="button"
          data-testid={`plugin-state-files-${id}`}
          aria-expanded={open}
          onClick={() => void toggle()}
          className="focus-ring inline-flex items-center rounded-lg px-2.5 text-ui-xs text-brand-deep hover:text-brand max-lg:min-h-11"
        >
          {open ? t('settings.pluginStateHide') : t('settings.pluginStateFiles')}
        </button>
      </div>
      {open && problem === 'read' && (
        <p className="text-ui-xs text-status-warning">{t('settings.pluginStateUnavailable')}</p>
      )}
      {open && report && (
        <div data-testid={`plugin-state-list-${id}`} className="space-y-1 rounded-lg bg-canvas p-2">
          {report.truncated && (
            <p className="text-ui-xs text-ink-faint">
              {t('settings.pluginStateListed', {
                listed: report.entries.length,
                count: report.file_count,
              })}
            </p>
          )}
          {report.entries.length === 0 && (
            <p className="text-ui-xs text-ink-faint">{t('settings.pluginStateEmpty')}</p>
          )}
          {report.entries.map((entry, index) => (
            <div key={entry.name} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-mono text-ui-xs text-foreground/70">
                {entry.name}
                <span className="ml-1.5 text-ink-faint">{storedSize(entry.bytes)}</span>
              </span>
              <button
                type="button"
                data-testid={`plugin-state-remove-${id}-${index}`}
                onClick={() => void remove(entry.name)}
                className="focus-ring inline-flex shrink-0 items-center rounded-lg border border-hairline-strong px-2.5 text-ui-xs text-ink-soft max-lg:min-h-11"
              >
                {armed === entry.name
                  ? t('settings.pluginStateRemoveConfirm')
                  : t('settings.pluginStateRemove')}
              </button>
            </div>
          ))}
          {problem === 'remove' && (
            <p className="text-ui-xs text-status-warning">
              {t('settings.pluginStateRemoveFailed')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

const SCOPE_MODES = ['analyst', 'architect', 'operator', 'creator'] as const

function scopeLists(view: PluginView): { global: PluginEntry[]; session: PluginEntry[] } {
  if (view.global !== undefined || view.session !== undefined) {
    return { global: view.global ?? [], session: view.session ?? [] }
  }
  const pool = [...(view.public ?? []), ...(view.personal ?? [])]
  return {
    global: pool.filter((row) => row.scope !== 'session'),
    session: pool.filter((row) => row.scope === 'session'),
  }
}

function viaPreset(row: PluginEntry, view: PluginView): boolean {
  return (
    row.enabled === false &&
    view.master_enabled !== false &&
    view.unproven !== true &&
    (row.provided_by_modes?.length ?? 0) > 0
  )
}

function railToolCount(p: PluginEntry): number | null {
  if (p.rail === 'worker') return p.contributed_tools ?? null
  if (p.rail === 'kernel') return p.activated_tools ?? null
  return null
}

function PluginsSection({ model }: { model: SettingsModel }) {
  const {
    expandedPlugin,
    handlePluginMasterToggle,
    handlePluginToggle,
    pluginQuery,
    pluginView,
    setExpandedPlugin,
    setPluginQuery,
    t,
  } = model

  // W1-7: the row that switches a plugin also shows its surface. One busy id keeps
  // two mounts apart, and the label is read from the display module's ledger on
  // every render, so a surface closed from its own title bar flips the row back.
  const [busySurface, setBusySurface] = useState<string | null>(null)

  async function toggleSurface(p: PluginEntry) {
    if (!p.surface || busySurface) return
    setBusySurface(p.id)
    try {
      if (isPluginSurfaceOpen(p.id)) await hidePluginSurface(p.id, t)
      else await showPluginSurface({ pluginId: p.id, descriptor: p.surface }, t)
    } finally {
      setBusySurface(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* S-wave app-shell pilot (docs/BRAND.md): PageHeader + search +
              sections — the testids of the store logic stay unchanged. */}
      <PageHeader
        title={t('settings.pluginsTitle')}
        subtitle={t('settings.pluginsHint')}
        actions={
          <>
            {pluginView ? (
              <span
                data-testid="plugin-count-pill"
                className="rounded-full bg-brand/15 px-2.5 py-1 text-ui-xs font-medium text-brand-deep"
              >
                {(pluginView.public ?? []).filter((p) => p.enabled).length +
                  (pluginView.personal ?? []).filter((p) => p.enabled).length}
                {' / '}
                {(pluginView.public?.length ?? 0) + (pluginView.personal?.length ?? 0)}
              </span>
            ) : null}
            {/* The catalog lives in /discover; this area only switches what is here. */}
            <button
              type="button"
              data-testid="plugins-open-discover"
              onClick={() => {
                // HashRouter: the address is the route, and this block also renders
                // outside a router.
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
      {pluginView === null ? (
        <LoadingRow label={t('settings.loading')} />
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
            const grouped = scopeLists(pluginView)
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
                    <div
                      key={p.id}
                      data-testid={`plugin-row-${seg}-${p.id}`}
                      className="glass-reading rounded-xl p-3 space-y-1.5"
                    >
                      <div className="flex items-center gap-2">
                        <PluginIcon pluginId={p.id} name={p.name} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-ui-xs font-medium text-foreground/90">
                            {p.name}
                            {p.version && (
                              <span className="ml-1.5 font-mono text-ui-xs text-ink-faint">
                                v{p.version}
                              </span>
                            )}
                            <span
                              data-testid={`plugin-origin-${p.id}`}
                              className={`ml-1.5 rounded-md px-1.5 py-0.5 text-ui-xs align-middle ${p.origin === 'external' ? 'bg-surface text-ink-faint' : 'bg-brand/10 text-brand-deep'}`}
                            >
                              {p.origin === 'external'
                                ? t('settings.pluginOriginExternal')
                                : t('settings.pluginOriginFirstParty')}
                            </span>
                            {viaPreset(p, pluginView) && (
                              <span
                                data-testid={`plugin-scope-badge-${p.id}`}
                                className="ml-1.5 rounded-md bg-status-warning/10 px-1.5 py-0.5 text-ui-xs align-middle text-status-warning"
                              >
                                {t('settings.pluginScopeBadge')}
                              </span>
                            )}
                          </p>
                          <p className="line-clamp-1 text-ui-xs text-ink-faint">{p.description}</p>
                        </div>
                        <PluginSwitch
                          name={p.name}
                          checked={p.enabled}
                          disabled={
                            pluginView.master_enabled === false ||
                            pluginView.read_only === true ||
                            pluginView.unproven === true
                          }
                          onToggle={(next) => handlePluginToggle(p.id, next)}
                          testid={`plugin-toggle-${p.id}`}
                          errorTestid={`plugin-toggle-error-${p.id}`}
                          labels={{
                            on: t('settings.pluginOn'),
                            off: t('settings.pluginOff'),
                            enabling: t('settings.pluginEnabling'),
                            disabling: t('settings.pluginDisabling'),
                            failed: t('settings.pluginToggleFailed'),
                          }}
                          describeError={(reason, fallback) => {
                            if (reason instanceof ApiError) {
                              if (reason.reasonCode === 'dependency_blocked') {
                                return t('settings.pluginErrorDependency', {
                                  name: reason.message,
                                })
                              }
                              if (reason.reasonCode === 'dependents_enabled') {
                                return t('settings.pluginErrorDependents', {
                                  name: reason.message,
                                })
                              }
                              if (reason.reasonCode === 'stale_state') {
                                return t('settings.pluginErrorStale')
                              }
                              if (reason.reasonCode === 'not_cancellable') {
                                return t('settings.pluginErrorNotCancellable')
                              }
                              if (reason.reasonCode === 'plugin_lifecycle_read_only') {
                                return t('settings.pluginErrorReadOnly')
                              }
                            }
                            return reason instanceof Error && reason.message
                              ? reason.message
                              : fallback
                          }}
                        />
                      </div>
                      {p.state_usage && <PluginStoredFiles id={p.id} usage={p.state_usage} t={t} />}
                      {p.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {p.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs text-foreground/60"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {/* E4b: detail sheet — click the name to expand facts. */}
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          data-testid={`plugin-detail-toggle-${p.id}`}
                          aria-expanded={expandedPlugin === p.id}
                          onClick={() => setExpandedPlugin((prev) => (prev === p.id ? null : p.id))}
                          className="text-ui-xs text-ink-faint hover:text-foreground transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 rounded"
                        >
                          {expandedPlugin === p.id
                            ? t('settings.pluginDetailHide')
                            : t('settings.pluginDetailShow')}
                        </button>
                        <button
                          type="button"
                          data-testid={`plugin-try-${p.id}`}
                          onClick={() =>
                            startDisposableChat(
                              p.example_prompts?.[0] || examplePromptFor(p.id, p.name),
                            )
                          }
                          className="flex items-center gap-1 text-ui-xs text-brand-deep hover:text-brand transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 rounded"
                        >
                          <MessageSquarePlus className="h-3.5 w-3.5" strokeWidth={1.5} />
                          {t('settings.marketTryInChat')}
                        </button>
                        {p.surface && (
                          <button
                            type="button"
                            data-testid={`plugin-surface-${p.id}`}
                            disabled={busySurface !== null}
                            onClick={() => void toggleSurface(p)}
                            className="flex items-center gap-1 text-ui-xs text-brand-deep hover:text-brand transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 rounded"
                          >
                            <MonitorPlay className="h-3.5 w-3.5" strokeWidth={1.5} />
                            {isPluginSurfaceOpen(p.id)
                              ? t('settings.pluginSurfaceHide')
                              : t('settings.pluginSurfaceShow')}
                          </button>
                        )}
                      </div>
                      {expandedPlugin === p.id && (
                        <div
                          data-testid={`plugin-detail-${p.id}`}
                          className="space-y-1.5 rounded-lg bg-canvas p-2"
                        >
                          <div className="flex flex-wrap gap-1">
                            {p.source && (
                              <span className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs text-foreground/70">
                                {t('settings.pluginDetailSource')}:{' '}
                                {t(`settings.pluginSource.${p.source}`)}
                              </span>
                            )}
                            {/* #96: the rail this bundle runs on, read from its own manifest by
                                `core/plugin_rail.py`. A switch row says that a plugin is on; this
                                says what kind of on it is, and the two facts come apart — a
                                version 1 bundle turns Ephe's tools on, while a version 2 bundle
                                carries entries the confined worker runs. Absent when no manifest
                                behind the entry could be read, because the rail of a bundle
                                nobody read is not a fact this surface may state. */}
                            {p.rail && (
                              <span
                                data-testid={`plugin-rail-${p.id}`}
                                className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs text-foreground/70"
                              >
                                {t('settings.pluginRail')}: {t(`settings.pluginRail.${p.rail}`)}
                                {railToolCount(p) !== null && (
                                  <>
                                    {' · '}
                                    {t('settings.pluginRailTools', {
                                      count: railToolCount(p) ?? 0,
                                    })}
                                  </>
                                )}
                              </span>
                            )}
                            {(p.permissions ?? []).map((fam) => (
                              <span
                                key={fam}
                                className="rounded-md bg-status-warning/10 px-1.5 py-0.5 font-mono text-ui-xs text-status-warning"
                              >
                                {fam}
                              </span>
                            ))}
                          </div>
                          <p
                            data-testid={`plugin-detail-module-${p.id}`}
                            className="truncate font-mono text-ui-xs text-ink-faint"
                          >
                            {t('settings.pluginDetailModule')}:{' '}
                            {p.module ? p.module : t('settings.pluginDetailNone')}
                          </p>
                          <p
                            data-testid={`plugin-detail-configuration-${p.id}`}
                            className="text-ui-xs text-ink-faint"
                          >
                            {t('settings.pluginDetailConfiguration')}:{' '}
                            {p.configuration ? p.configuration : t('settings.pluginDetailNone')}
                          </p>
                          <fieldset
                            data-testid={`plugin-scope-include-${p.id}`}
                            disabled
                            className="space-y-1 border-0 p-0"
                          >
                            <legend className="text-ui-xs font-medium text-ink-faint">
                              {t('settings.pluginDetailEnabledIn')}
                            </legend>
                            <div className="flex flex-wrap gap-2">
                              {SCOPE_MODES.map((mode) => (
                                <label
                                  key={mode}
                                  className="inline-flex items-center gap-1 font-mono text-ui-xs text-foreground/70"
                                >
                                  <input
                                    type="checkbox"
                                    value={mode}
                                    defaultChecked={(p.provided_by_modes ?? []).includes(mode)}
                                    disabled
                                  />
                                  {mode}
                                </label>
                              ))}
                            </div>
                          </fieldset>
                          {p.sha256 && (
                            <p
                              className="truncate font-mono text-ui-xs text-ink-faint"
                              title={p.sha256}
                            >
                              {t('settings.pluginDetailHash')}: {p.sha256.slice(0, 16)}…
                            </p>
                          )}
                          {(p.example_prompts ?? []).length > 0 && (
                            <div className="space-y-0.5">
                              <p className="text-ui-xs font-medium text-ink-faint">
                                {t('settings.pluginDetailPrompts')}
                              </p>
                              {p.example_prompts.map((prompt, i) => (
                                <p key={i} className="text-ui-xs text-ink-faint">
                                  — {prompt}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </SettingsGroup>
            ))
          })()}
          {(pluginView.orphans ?? []).length > 0 && (
            <div className="space-y-1">
              <p className="text-ui-xs font-medium text-ink-soft">
                {t('settings.plugins.orphans')}
              </p>
              <p className="text-ui-xs text-ink-faint">{t('settings.plugins.orphansHint')}</p>
              {pluginView.orphans!.map((id) => (
                <p key={id} className="font-mono text-ui-xs text-ink-soft">
                  {id}
                </p>
              ))}
            </div>
          )}
        </>
      )}
      {/* I3-V5: catalog policy belongs with the plugins, not in an expert box. */}
      <DeepFields model={model} prefixes={['plugins.']} />
    </div>
  )
}
