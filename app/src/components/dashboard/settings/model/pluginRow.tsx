'use client'

/**
 * The store row: status, provenance, abilities, actions and the removal question.
 *
 * These parts paint one bundle and know nothing about loading the store or grouping
 * rows; `sections-plugins.tsx` owns that. The split keeps the row readable and the
 * section's answer to "which rows exist" in one place.
 */
import { useEffect, useRef, useState } from 'react'
import { Compass, MessageSquarePlus, MonitorPlay, Puzzle } from 'lucide-react'
import PluginIcon from '@/components/shell/PluginIcon'
import PluginSwitch from '@/components/ui/PluginSwitch'
import type {
  PluginCommandInfo,
  PluginEntry,
  PluginStateReport,
  PluginStateUsage,
  PluginView,
} from '@/lib/api'
import { getPluginState, removePluginStateFile } from '@/lib/api'
import { startDisposableChat } from '@/lib/chatSeed'
import { examplePromptFor } from '@/lib/pluginExamples'
import { hidePluginSurface, isPluginSurfaceOpen, showPluginSurface } from '@/lib/pluginDisplay'
import {
  canRemove,
  commandsFor,
  pluginErrorText,
  pluginSource,
  pluginStatus,
  sourceKey,
  statusKey,
  surfaceTitle,
  toolCount,
  toolExample,
  trustKey,
} from './pluginRowModel'
import type { SettingsModel } from './types'

const SCOPE_MODES = ['analyst', 'architect', 'operator', 'creator'] as const

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

const STATUS_STYLE: Record<string, string> = {
  active: 'bg-status-success/10 text-status-success',
  inactive: 'bg-surface text-ink-faint',
  faulty: 'bg-status-warning/15 text-status-warning',
}

/** One word for the state of the bundle, where the switch is the control. */
function PluginStatusBadge({ p, t }: { p: PluginEntry; t: SettingsModel['t'] }) {
  const status = pluginStatus(p)
  return (
    <span
      data-testid={`plugin-status-${p.id}`}
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-xs font-medium ${STATUS_STYLE[status]}`}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: 'currentColor' }}
      />
      {t(statusKey(status))}
    </span>
  )
}

/** Where the bundle comes from, and what that provenance is worth trusting. */
function PluginProvenance({ p, t }: { p: PluginEntry; t: SettingsModel['t'] }) {
  const source = pluginSource(p)
  const trust = trustKey(p)
  if (!source && !trust) return null
  return (
    <p className="text-ui-xs text-ink-faint">
      <span data-testid={`plugin-source-${p.id}`}>
        {source && t('settings.pluginSourceLabel', { source: t(sourceKey(source)) })}
      </span>
      {source && trust ? ' · ' : ''}
      <span data-testid={`plugin-origin-${p.id}`}>
        {trust && t('settings.pluginTrustLabel', { trust: t(trust) })}
      </span>
    </p>
  )
}

/** What the bundle can do, readable without opening the detail sheet. */
function PluginCapabilities({
  p,
  commands,
  declaresCommands,
  t,
}: {
  p: PluginEntry
  commands: PluginCommandInfo[] | null
  /** The manifest lists a command component: an off bundle still has one, the
   *  command route only reports the active set. */
  declaresCommands: boolean
  t: SettingsModel['t']
}) {
  const count = toolCount(p)
  const example = toolExample(p)
  const names = commandsFor(p, commands)
  const surface = surfaceTitle(p)
  const components = p.components ?? []
  return (
    <div
      data-testid={`plugin-capabilities-${p.id}`}
      className="flex flex-wrap items-center gap-1.5"
    >
      {count !== null && (
        <span
          title={p.module || undefined}
          className="inline-flex min-w-0 items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-foreground/70"
        >
          {count === 0 ? t('settings.pluginCapNoTools') : t('settings.pluginCapTools', { count })}
          {count > 0 && example && (
            <span className="truncate font-mono text-ink-faint">· {example}</span>
          )}
        </span>
      )}
      {surface && (
        <span className="inline-flex min-w-0 items-center gap-1 rounded-md bg-brand/10 px-1.5 py-0.5 text-ui-xs text-brand-deep">
          <MonitorPlay className="h-3 w-3 shrink-0" strokeWidth={1.5} aria-hidden="true" />
          <span className="truncate">{t('settings.pluginCapSurface', { title: surface })}</span>
        </span>
      )}
      {names.length > 0 ? (
        <span className="inline-flex min-w-0 items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-foreground/70">
          <span className="shrink-0">{t('settings.pluginCapCommands')}:</span>
          <span className="truncate font-mono text-ink-faint">
            {names.slice(0, 3).join(' ')}
            {names.length > 3 ? ` +${names.length - 3}` : ''}
          </span>
        </span>
      ) : declaresCommands && !p.enabled ? (
        <span className="inline-flex min-w-0 items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-ink-faint">
          <span className="truncate">{t('settings.pluginCapCommandsOff')}</span>
        </span>
      ) : null}
      {count === null && components.length > 0 && (
        <span className="inline-flex min-w-0 items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-foreground/70">
          <Puzzle className="h-3 w-3 shrink-0" strokeWidth={1.5} aria-hidden="true" />
          <span className="truncate font-mono text-ink-faint">
            {t('settings.pluginCapComponents', { list: components.join(', ') })}
          </span>
        </span>
      )}
    </div>
  )
}

/**
 * Removal asks in the row it removes, with the name and the consequence in the
 * question. The sheet is `role="alertdialog"`, focus lands on the refusal, and the
 * confirm button carries the verb. Only a bundle installed on this device is
 * offered this action: a bundled one ships with the app and has no directory the
 * remove route owns.
 */
function PluginRemove({
  p,
  onRemove,
  t,
}: {
  p: PluginEntry
  onRemove: (id: string) => Promise<void>
  t: SettingsModel['t']
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (armed) cancelRef.current?.focus()
  }, [armed])

  async function confirm() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await onRemove(p.id)
      setArmed(false)
    } catch (reason) {
      setError(pluginErrorText(reason, t, t('settings.pluginRemoveFailed')))
    } finally {
      setBusy(false)
    }
  }

  if (!armed) {
    return (
      <button
        type="button"
        data-testid={`plugin-remove-${p.id}`}
        onClick={() => {
          setError('')
          setArmed(true)
        }}
        className="focus-ring ml-auto inline-flex items-center gap-1 rounded-lg px-2 text-ui-xs text-ink-faint transition-colors hover:text-status-danger max-lg:min-h-11"
      >
        {t('settings.pluginRemove')}
      </button>
    )
  }

  return (
    <div
      role="alertdialog"
      aria-labelledby={`plugin-remove-title-${p.id}`}
      data-testid={`plugin-remove-confirm-${p.id}`}
      className="w-full space-y-1.5 rounded-lg border border-status-danger/30 bg-canvas p-2"
    >
      <p id={`plugin-remove-title-${p.id}`} className="text-ui-xs font-medium text-status-danger">
        {t('settings.pluginRemoveConfirm')}
      </p>
      <p className="text-ui-xs text-ink-soft">
        {t('settings.pluginRemoveConfirmHint', { name: p.name })}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          ref={cancelRef}
          data-testid={`plugin-remove-cancel-${p.id}`}
          onClick={() => setArmed(false)}
          className="focus-ring inline-flex items-center rounded-lg border border-hairline-strong px-2.5 text-ui-xs text-ink-soft max-lg:min-h-11"
        >
          {t('settings.pluginRemoveCancel')}
        </button>
        <button
          type="button"
          data-testid={`plugin-remove-confirm-yes-${p.id}`}
          disabled={busy}
          onClick={() => void confirm()}
          className="focus-ring inline-flex items-center rounded-lg bg-status-danger/10 px-2.5 text-ui-xs font-medium text-status-danger disabled:opacity-50 max-lg:min-h-11"
        >
          {busy ? t('settings.pluginRemoveBusy') : t('settings.pluginRemoveConfirmYes')}
        </button>
      </div>
      {error && (
        <p
          role="alert"
          data-testid={`plugin-remove-error-${p.id}`}
          className="text-ui-xs text-status-danger"
        >
          {error}
        </p>
      )}
    </div>
  )
}

export function PluginCard({
  p,
  segment,
  view,
  model,
  switchesDisabled,
  declaresCommands,
}: {
  p: PluginEntry
  segment: 'global' | 'session' | 'orphan'
  view: PluginView
  model: SettingsModel
  switchesDisabled: boolean
  declaresCommands: boolean
}) {
  const {
    expandedPlugin,
    handlePluginRemove,
    handlePluginToggle,
    pluginCommands,
    setExpandedPlugin,
    t,
  } = model
  const [busySurface, setBusySurface] = useState(false)
  const status = pluginStatus(p)

  // The display module reports a refusal itself (toast + outcome). The row only keeps
  // one request in flight, so a second click cannot mount two surfaces.
  async function toggleSurface() {
    if (!p.surface || busySurface) return
    setBusySurface(true)
    try {
      if (isPluginSurfaceOpen(p.id)) await hidePluginSurface(p.id, t)
      else await showPluginSurface({ pluginId: p.id, descriptor: p.surface }, t)
    } finally {
      setBusySurface(false)
    }
  }

  return (
    <div
      data-testid={`plugin-row-${segment}-${p.id}`}
      className="glass-reading space-y-2 rounded-xl p-3"
    >
      <div className="flex items-start gap-2">
        <PluginIcon pluginId={p.id} name={p.name} hasIcon={p.has_icon} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="min-w-0 truncate text-ui-xs font-medium text-foreground/90">
              {p.name}
              {p.version && (
                <span className="ml-1.5 font-mono text-ui-xs text-ink-faint">v{p.version}</span>
              )}
            </p>
            <PluginStatusBadge p={p} t={t} />
            {viaPreset(p, view) && (
              <span
                data-testid={`plugin-scope-badge-${p.id}`}
                className="rounded-md bg-status-warning/10 px-1.5 py-0.5 text-ui-xs text-status-warning"
              >
                {t('settings.pluginScopeBadge')}
              </span>
            )}
          </div>
          <p className="line-clamp-1 text-ui-xs text-ink-faint">{p.description}</p>
        </div>
        <PluginSwitch
          name={p.name}
          checked={p.enabled}
          showState={false}
          disabled={switchesDisabled}
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
          describeError={(reason, fallback) => pluginErrorText(reason, t, fallback)}
        />
      </div>
      <PluginProvenance p={p} t={t} />
      <PluginCapabilities
        p={p}
        commands={pluginCommands ?? null}
        declaresCommands={declaresCommands}
        t={t}
      />
      {status === 'faulty' && (
        <p
          data-testid={`plugin-faulty-hint-${p.id}`}
          className="rounded-lg bg-status-warning/10 px-2 py-1.5 text-ui-xs text-status-warning"
        >
          {t('settings.pluginStatusFaultyHint')}
        </p>
      )}
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
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid={`plugin-detail-toggle-${p.id}`}
          aria-expanded={expandedPlugin === p.id}
          onClick={() => setExpandedPlugin((prev) => (prev === p.id ? null : p.id))}
          className="focus-ring rounded text-ui-xs text-ink-faint transition-colors hover:text-foreground"
        >
          {expandedPlugin === p.id
            ? t('settings.pluginDetailHide')
            : t('settings.pluginDetailShow')}
        </button>
        <button
          type="button"
          data-testid={`plugin-try-${p.id}`}
          onClick={() =>
            startDisposableChat(p.example_prompts?.[0] || examplePromptFor(p.id, p.name))
          }
          className="focus-ring flex items-center gap-1 rounded text-ui-xs text-brand-deep transition-colors hover:text-brand"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
          {t('settings.marketTryInChat')}
        </button>
        {p.surface && (
          <button
            type="button"
            data-testid={`plugin-surface-${p.id}`}
            disabled={busySurface}
            onClick={() => void toggleSurface()}
            className="focus-ring flex items-center gap-1 rounded text-ui-xs font-medium text-brand-deep transition-colors hover:text-brand disabled:opacity-50"
          >
            <MonitorPlay className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
            {isPluginSurfaceOpen(p.id)
              ? t('settings.pluginSurfaceHide')
              : t('settings.pluginSurfaceShow')}
          </button>
        )}
        {canRemove(p) && <PluginRemove p={p} onRemove={handlePluginRemove} t={t} />}
      </div>
      {expandedPlugin === p.id && (
        <div data-testid={`plugin-detail-${p.id}`} className="space-y-1.5 rounded-lg bg-canvas p-2">
          <div className="flex flex-wrap gap-1">
            {p.source && (
              <span className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs text-foreground/70">
                {t('settings.pluginDetailSource')}: {t(`settings.pluginSource.${p.source}`)}
              </span>
            )}
            {p.rail && (
              <span
                data-testid={`plugin-rail-${p.id}`}
                className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs text-foreground/70"
              >
                {t('settings.pluginRail')}: {t(`settings.pluginRail.${p.rail}`)}
                {railToolCount(p) !== null && (
                  <>
                    {' · '}
                    {t('settings.pluginRailTools', { count: railToolCount(p) ?? 0 })}
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
            <p className="truncate font-mono text-ui-xs text-ink-faint" title={p.sha256}>
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
  )
}

/** The sentence a reader needs before there is anything to switch. */
export function PluginEmpty({ t }: { t: SettingsModel['t'] }) {
  return (
    <div
      data-testid="plugins-empty"
      className="glass-reading mx-auto max-w-lg space-y-2 rounded-xl p-6 text-center"
    >
      <Puzzle className="mx-auto h-8 w-8 text-brand/70" strokeWidth={1.25} aria-hidden="true" />
      <p className="text-ui-sm font-medium text-foreground/90">{t('settings.pluginEmptyTitle')}</p>
      <p className="text-ui-xs leading-relaxed text-ink-soft">{t('settings.pluginEmptyBody')}</p>
      <button
        type="button"
        data-testid="plugins-empty-discover"
        onClick={() => {
          window.location.hash = '#/discover'
        }}
        className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-brand/40 bg-brand/10 px-3 py-1.5 text-ui-xs font-medium text-brand-deep hover:bg-brand/10 max-lg:min-h-11"
      >
        <Compass className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
        {t('settings.pluginEmptyDiscover')}
      </button>
    </div>
  )
}
