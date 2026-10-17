'use client'

import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import Switch from '@/components/shell/Switch'
import SearchInput from '@/components/shell/SearchInput'
import PluginIcon from '@/components/shell/PluginIcon'
import { Puzzle, Power, Store } from 'lucide-react'
import type { PluginEntry } from '@/lib/api'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function renderPlugins(model: SettingsModel) {
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

  return (
    <div className="space-y-4">
      {/* S-wave app-shell pilot (docs/BRAND.md): PageHeader + search +
              sections — the testids of the store logic stay unchanged. */}
      <PageHeader
        title={t('settings.pluginsTitle')}
        subtitle={t('settings.pluginsHint')}
        actions={
          pluginView ? (
            <span
              data-testid="plugin-count-pill"
              className="rounded-full bg-brand/15 px-2.5 py-1 text-ui-xs font-medium text-brand"
            >
              {(pluginView.public ?? []).filter((p) => p.enabled).length +
                (pluginView.personal ?? []).filter((p) => p.enabled).length}
              {' / '}
              {(pluginView.public?.length ?? 0) + (pluginView.personal?.length ?? 0)}
            </span>
          ) : undefined
        }
      />
      <SearchInput
        value={pluginQuery}
        onChange={setPluginQuery}
        placeholder={t('settings.pluginsSearch')}
        label={t('settings.pluginsSearch')}
      />
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
            const segments = (['public', 'personal'] as const)
              .map((seg) => ({
                seg,
                rows: (pluginView[seg] ?? []).filter(matches),
              }))
              .filter((s) => s.rows.length > 0)
            if (segments.length === 0) {
              return <p className="text-ui-xs text-ink-faint">{t('settings.noResults')}</p>
            }
            return segments.map(({ seg, rows }) => (
              <SettingsGroup
                key={seg}
                icon={seg === 'public' ? Store : Puzzle}
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
                              <span className="ml-1.5 font-mono text-ui-2xs text-ink-faint">
                                v{p.version}
                              </span>
                            )}
                            <span
                              data-testid={`plugin-origin-${p.id}`}
                              className={`ml-1.5 rounded-md px-1.5 py-0.5 text-ui-2xs align-middle ${p.origin === 'external' ? 'bg-surface text-ink-faint' : 'bg-brand/10 text-brand'}`}
                            >
                              {p.origin === 'external'
                                ? t('settings.pluginOriginExternal')
                                : t('settings.pluginOriginFirstParty')}
                            </span>
                          </p>
                          <p className="line-clamp-1 text-ui-xs text-ink-faint">{p.description}</p>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={p.enabled}
                          disabled={pluginView.master_enabled === false}
                          onClick={() => void handlePluginToggle(p.id, !p.enabled)}
                          data-testid={`plugin-toggle-${p.id}`}
                          className={`shrink-0 rounded-full px-2.5 py-1 text-ui-xs font-medium transition-colors max-lg:min-h-9 disabled:opacity-40 disabled:cursor-not-allowed ${p.enabled ? 'bg-brand/20 text-brand' : 'bg-surface text-ink-faint'}`}
                        >
                          {p.enabled ? t('settings.pluginOn') : t('settings.pluginOff')}
                        </button>
                      </div>
                      {p.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {p.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-2xs text-foreground/60"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {/* E4b: detail sheet — click the name to expand facts. */}
                      <button
                        type="button"
                        data-testid={`plugin-detail-toggle-${p.id}`}
                        aria-expanded={expandedPlugin === p.id}
                        onClick={() => setExpandedPlugin((prev) => (prev === p.id ? null : p.id))}
                        className="text-ui-2xs text-ink-faint hover:text-foreground transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 rounded"
                      >
                        {expandedPlugin === p.id
                          ? t('settings.pluginDetailHide')
                          : t('settings.pluginDetailShow')}
                      </button>
                      {expandedPlugin === p.id && (
                        <div
                          data-testid={`plugin-detail-${p.id}`}
                          className="space-y-1.5 rounded-lg bg-canvas p-2"
                        >
                          <div className="flex flex-wrap gap-1">
                            {p.source && (
                              <span className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-2xs text-foreground/70">
                                {t('settings.pluginDetailSource')}:{' '}
                                {t(`settings.pluginSource.${p.source}`)}
                              </span>
                            )}
                            {(p.permissions ?? []).map((fam) => (
                              <span
                                key={fam}
                                className="rounded-md bg-status-warning/10 px-1.5 py-0.5 font-mono text-ui-2xs text-status-warning"
                              >
                                {fam}
                              </span>
                            ))}
                          </div>
                          {p.sha256 && (
                            <p
                              className="truncate font-mono text-ui-2xs text-ink-faint"
                              title={p.sha256}
                            >
                              {t('settings.pluginDetailHash')}: {p.sha256.slice(0, 16)}…
                            </p>
                          )}
                          {(p.example_prompts ?? []).length > 0 && (
                            <div className="space-y-0.5">
                              <p className="text-ui-2xs font-medium text-ink-faint">
                                {t('settings.pluginDetailPrompts')}
                              </p>
                              {p.example_prompts.map((prompt, i) => (
                                <p key={i} className="text-ui-2xs text-ink-faint">
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
              <p className="text-ui-2xs text-ink-faint">{t('settings.plugins.orphansHint')}</p>
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
