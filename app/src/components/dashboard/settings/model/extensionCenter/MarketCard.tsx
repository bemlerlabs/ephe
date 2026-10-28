'use client'

import { useState } from 'react'
import {
  ChevronDown,
  Download,
  Loader2,
  MessageSquarePlus,
  RotateCcw,
  ShieldAlert,
  Trash2,
} from 'lucide-react'

import PluginIcon from '@/components/shell/PluginIcon'
import PluginSwitch from '@/components/ui/PluginSwitch'
import { startDisposableChat } from '@/lib/chatSeed'
import { examplePromptFor } from '@/lib/pluginExamples'
import {
  type MarketInstalledRow,
  type MarketPlugin,
  type MarketUpdate,
  type MarketVersion,
} from '@/lib/api'
import type { SettingsModel } from '../types'
import { trustLabel } from './marketLabels'

type T = SettingsModel['t']

function text(value: string | Record<string, string> | undefined, language: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  return value[language] || value.en || Object.values(value)[0] || ''
}

const BUTTON =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'
const PRIMARY =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg bg-brand/90 px-3 py-1 text-ui-xs font-medium text-white transition-colors hover:bg-brand disabled:opacity-40 pointer-coarse:min-h-11'

export function MarketCard({
  plugin,
  installed,
  update,
  language,
  t,
  busy,
  onInstall,
  onRemove,
  onRollback,
  onSwitch,
  switchBusy = false,
  consent,
  onConsentAllow,
  onConsentCancel,
}: {
  plugin: MarketPlugin
  installed?: MarketInstalledRow
  update?: MarketUpdate
  language: string
  t: T
  busy: boolean
  onInstall: (version: MarketVersion) => void
  onRemove: () => void
  onRollback: () => void
  onSwitch?: (enabled: boolean) => void
  switchBusy?: boolean
  consent?: { families: string[]; roots: string[] } | null
  onConsentAllow?: () => void
  onConsentCancel?: () => void
}) {
  const [open, setOpen] = useState(false)
  const version = plugin.versions[0]
  const updateVersion = update
    ? plugin.versions.find((entry) => entry.version === update.version)
    : undefined
  const quality = plugin.quality_label || 'plugin'
  // A bundled entry ships inside the app, unless it is third-party content the
  // user installs into their own profile (the Superpowers pack is one).
  const bundledInApp = plugin.trust === 'bundled' && plugin.provenance !== 'third-party'
  const notInstallable = quality === 'capability-preset' || bundledInApp
  const qualityText =
    quality === 'capability-preset'
      ? t('settings.marketQualityCapabilityPreset')
      : quality === 'bundled'
        ? t('settings.marketQualityBundled')
        : t('settings.marketQualityPlugin')
  const tiers = plugin.tiers
    ? `A ${plugin.tiers.A ?? 0} · B ${plugin.tiers.B ?? 0} · C ${plugin.tiers.C ?? 0}`
    : ''
  const measured = plugin.measurement?.model
    ? t('settings.marketMeasuredOn', {
        engine: plugin.measurement.model,
        cases: String(plugin.measurement.cases ?? 0),
        pass3: plugin.measurement.pass3 ?? '—',
      })
    : t('settings.marketMeasuredNo')
  const bundledEntry = plugin.trust === 'bundled' || installed?.origin === 'bundled'
  const signed = Boolean(version?.source.signature) && !bundledEntry
  const installedState = installed
    ? `${t('settings.marketInstalledState')} · v${installed.version}`
    : t('settings.marketBundledState')

  return (
    <div
      data-testid={`market-plugin-${plugin.name}`}
      className="glass-reading rounded-xl p-3 space-y-2"
    >
      <div className="flex items-start gap-2">
        <PluginIcon pluginId={plugin.name} name={plugin.displayName} size={36} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-ui-xs font-medium text-foreground/90">
            <span className="truncate">{plugin.displayName}</span>
            <span className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-ui-xs tabular-nums text-ink-faint">
              v{version?.version ?? '—'}
            </span>
            <span
              className={`rounded-md px-1.5 py-0.5 text-ui-xs ${
                signed ? 'bg-brand/10 text-brand-deep' : 'bg-status-warning/15 text-status-warning'
              }`}
            >
              {bundledEntry
                ? t('settings.marketBundledState')
                : signed
                  ? t('settings.marketTrustSigned')
                  : t('settings.marketUnsigned')}
            </span>
          </p>
          <p className="text-ui-xs text-ink-faint">
            {plugin.publisher?.name} · {trustLabel(plugin.trust, t)}
          </p>
          <p className="flex flex-wrap items-center gap-1.5 text-ui-xs text-ink-faint">
            <span
              className="rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-ink-soft"
              data-testid={`market-quality-${plugin.name}`}
            >
              {qualityText}
            </span>
            <span>
              {t('settings.marketProvenance')}:{' '}
              {plugin.provenance === 'first-party'
                ? t('settings.marketProvenanceFirstParty')
                : plugin.provenance || '—'}
            </span>
            {tiers && (
              <span className="tabular-nums">
                {t('settings.marketTiers')}: {tiers}
              </span>
            )}
          </p>
          <p className="text-ui-xs text-ink-faint" data-testid={`market-measured-${plugin.name}`}>
            {measured}
          </p>
          <p className="line-clamp-2 text-ui-xs text-ink-soft">
            {text(plugin.description, language)}
          </p>
        </div>
      </div>

      {consent && (
        <div
          data-testid={`market-consent-${plugin.name}`}
          className="rounded-lg border border-status-warning/40 bg-status-warning/10 p-2 space-y-1"
        >
          <p className="text-ui-xs font-medium text-foreground/85">
            {t('settings.marketConsentTitle')}
          </p>
          {(consent.families.length > 0 || consent.roots.length > 0) && (
            <p className="text-ui-xs text-ink-soft">
              {t('settings.marketConsentDelta')}: {[...consent.families, ...consent.roots].join(', ')}
            </p>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={PRIMARY}
              onClick={() => onConsentAllow?.()}
              data-testid={`market-consent-allow-${plugin.name}`}
            >
              {t('settings.marketConsentAllow')}
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={() => onConsentCancel?.()}
              data-testid={`market-consent-cancel-${plugin.name}`}
            >
              {t('settings.marketConsentCancel')}
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        {installed && onSwitch && (
          <PluginSwitch
            name={plugin.displayName}
            checked={installed.enabled}
            disabled={busy || switchBusy}
            onToggle={(next) => onSwitch(next)}
            testid={`market-switch-${plugin.name}`}
            errorTestid={`market-switch-error-${plugin.name}`}
            labels={{
              on: t('settings.marketOn'),
              off: t('settings.marketOff'),
              enabling: t('settings.pluginEnabling'),
              disabling: t('settings.pluginDisabling'),
              failed: t('settings.pluginToggleFailed'),
            }}
          />
        )}
        {update && updateVersion && !notInstallable && (
          <button
            type="button"
            className={PRIMARY}
            onClick={() => onInstall(updateVersion)}
            disabled={busy}
            data-testid={`market-update-${plugin.name}`}
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            {t('settings.marketUpdate')} → v{update.version}
          </button>
        )}
        {!installed && version && !notInstallable && (
          <button
            type="button"
            className={PRIMARY}
            onClick={() => onInstall(version)}
            disabled={busy}
            data-testid={`market-install-${plugin.name}`}
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            {t('settings.marketInstall')}
          </button>
        )}
        {installed && (
          <span className="text-ui-xs text-ink-faint">
            {installed.origin === 'bundled' ? `${t('settings.marketBundledState')} · ` : ''}
            {installedState}
          </span>
        )}
        <button
          type="button"
          className={BUTTON}
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          data-testid={`market-detail-${plugin.name}`}
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          {t('settings.marketDetail')}
        </button>
        <button
          type="button"
          className={BUTTON}
          onClick={() => startDisposableChat(examplePromptFor(plugin.name, plugin.displayName))}
          data-testid={`market-try-${plugin.name}`}
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          {t('settings.marketTryInChat')}
        </button>
        {installed?.origin === 'user' && (
          <>
            <button type="button" className={BUTTON} onClick={onRollback} disabled={busy}>
              <RotateCcw className="h-3.5 w-3.5" /> {t('settings.marketRollback')}
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={onRemove}
              disabled={busy}
              data-testid={`market-remove-${plugin.name}`}
            >
              <Trash2 className="h-3.5 w-3.5" /> {t('settings.marketRemove')}
            </button>
          </>
        )}
      </div>

      {!signed && !notInstallable && installed?.origin !== 'bundled' && (
        <p className="flex items-start gap-1.5 text-ui-xs text-status-warning">
          <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" />
          {t('settings.marketUnsignedHint')}
        </p>
      )}

      {open && version && (
        <div
          className="space-y-1.5 rounded-lg bg-canvas p-2"
          data-testid={`market-detail-body-${plugin.name}`}
        >
          <p className="text-ui-xs text-ink-soft">
            <span className="font-medium">{t('settings.marketPublisher')}:</span>{' '}
            {plugin.publisher?.name}
          </p>
          <p className="text-ui-xs text-ink-soft">
            <span className="font-medium">{t('settings.marketTrust')}:</span>{' '}
            {trustLabel(plugin.trust, t)}
          </p>
          <p className="text-ui-xs text-ink-soft">
            <span className="font-medium">{t('settings.marketQualityLabel')}:</span> {qualityText}
          </p>
          <p
            className="text-ui-xs text-ink-soft"
            data-testid={`market-detail-measured-${plugin.name}`}
          >
            {measured}
          </p>
          <p className="break-all font-mono text-ui-xs tabular-nums text-ink-faint">
            {t('settings.marketVersion')}: {version.version} · {version.source.sha256.slice(0, 16)}…
          </p>
          <p className="text-ui-xs text-ink-soft">
            <span className="font-medium">{t('settings.marketPermissions')}:</span>{' '}
            {(version.permissions?.tool_families ?? []).join(', ') || '—'}
          </p>
          <p className="text-ui-xs text-ink-soft">
            <span className="font-medium">{t('settings.marketComponents')}:</span>{' '}
            {version.components.join(', ') || '—'}
          </p>
          {plugin.versions.length > 1 && (
            <p className="text-ui-xs tabular-nums text-ink-faint">
              {plugin.versions.map((entry) => `v${entry.version}`).join(' · ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
