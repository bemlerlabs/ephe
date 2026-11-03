'use client'

/**
 * F2: the device folder on the settings surface — what Ephe keeps on this
 * machine, how much room it takes, and the one gesture that clears it.
 *
 * The card reads `GET /api/device`, which is `core/persistence.py` answered
 * against this folder; the clear runs `POST /api/device/forget` only after a
 * second click, and that click states the numbers it will act on. The rows the
 * declaration keeps stand with their reason beside them, and the entries no row
 * names are counted and left alone — the same promise `ephe device` keeps in the
 * terminal.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eraser, HardDrive, Loader2, ShieldCheck } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { forgetDevice, getDeviceState, type DeviceState } from '@/lib/api'
import { formatBytes, formatNumber } from '@/lib/dateLocale'

type Phase = 'loading' | 'failed' | 'ready'

export function DeviceStateCard() {
  const { t, i18n } = useTranslation()
  const [phase, setPhase] = useState<Phase>('loading')
  const [state, setState] = useState<DeviceState | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setPhase('loading')
    try {
      const view = await getDeviceState()
      setState(view)
      setPhase('ready')
    } catch {
      // A failed read is not an empty folder; the card says which one it is.
      setPhase('failed')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const lang = i18n.language
  const here = state?.entries ?? []
  const protectedHere = here.filter((entry) => !entry.forgettable)
  const forgetHere = here.filter((entry) => entry.forgettable)
  const forgetBytes = forgetHere.reduce((sum, entry) => sum + entry.bytes, 0)

  /** The confirmed run: this is the call that unlinks, and the only one that may. */
  async function clearNow() {
    if (!state) return
    setBusy(true)
    setOutcome(null)
    try {
      const answer = await forgetDevice({ dry_run: false })
      const gone = here.filter((entry) => answer.removed.includes(entry.name))
      const freed = gone.reduce((sum, entry) => sum + entry.bytes, 0)
      setOutcome(
        t('settings.deviceStateDone', {
          count: formatNumber(answer.removed.length, lang),
          size: formatBytes(freed, lang),
          kept: formatNumber(answer.kept.length, lang),
          unnamed: formatNumber(answer.unnamed.length, lang),
        }),
      )
      setConfirming(false)
      await refresh()
    } catch {
      setOutcome(t('settings.deviceStateFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (phase === 'failed') {
    return (
      <SettingsGroup
        icon={HardDrive}
        title={t('settings.deviceStateGroup')}
        testid="device-state-group"
      >
        <SettingsRow
          icon={HardDrive}
          title={t('settings.deviceStateRow')}
          description={t('settings.deviceStateFailed')}
          testid="device-state-failed"
        >
          <button
            type="button"
            data-testid="device-state-retry"
            onClick={() => void refresh()}
            className="rounded-lg glass-control px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors hover:text-foreground max-lg:min-h-11"
          >
            {t('settings.deviceStateRetry')}
          </button>
        </SettingsRow>
      </SettingsGroup>
    )
  }

  if (phase === 'loading' || !state) {
    return (
      <SettingsGroup
        icon={HardDrive}
        title={t('settings.deviceStateGroup')}
        testid="device-state-group"
      >
        <SettingsRow
          icon={HardDrive}
          title={t('settings.deviceStateRow')}
          description={t('settings.deviceStateLoading')}
          testid="device-state-loading"
        >
          <Loader2 className="h-4 w-4 animate-spin text-brand/50" aria-hidden="true" />
        </SettingsRow>
      </SettingsGroup>
    )
  }

  return (
    <SettingsGroup
      icon={HardDrive}
      title={t('settings.deviceStateGroup')}
      testid="device-state-group"
    >
      <SettingsRow
        icon={HardDrive}
        title={t('settings.deviceStateRow')}
        testid="device-state-row"
        description={
          here.length === 0
            ? t('settings.deviceStateEmpty')
            : t('settings.deviceStateHint', {
                present: formatNumber(state.present, lang),
                declared: formatNumber(state.declared, lang),
                size: formatBytes(state.total_bytes, lang),
                forgettable: formatNumber(state.forgettable, lang),
              })
        }
      >
        <span data-testid="device-state-total" className="font-mono text-ui-xs text-brand/90">
          {formatBytes(state.total_bytes, lang)}
        </span>
      </SettingsRow>

      {here.length > 0 && (
        <>
          {here.map((entry) => (
            <SettingsRow
              key={entry.name}
              icon={entry.forgettable ? HardDrive : ShieldCheck}
              title={entry.name}
              description={entry.holds}
              testid={`device-entry-${entry.name}`}
            >
              <span
                data-testid={`device-entry-size-${entry.name}`}
                className="font-mono text-ui-2xs text-ink-faint"
              >
                {entry.forgettable
                  ? formatBytes(entry.bytes, lang)
                  : t('settings.deviceStateProtected')}
              </span>
            </SettingsRow>
          ))}

          {protectedHere.length > 0 && (
            <p
              data-testid="device-state-protected-note"
              className="px-3 py-2 text-ui-xs text-ink-soft"
            >
              {t('settings.deviceStateProtectedHint')}
            </p>
          )}

          {state.unnamed.length > 0 && (
            <p data-testid="device-state-unnamed" className="px-3 py-2 text-ui-xs text-ink-faint">
              {t('settings.deviceStateUnnamed', { count: state.unnamed.length })}
            </p>
          )}

          <SettingsRow
            icon={Eraser}
            title={t('settings.deviceStateClear')}
            description={t('settings.deviceStateWillForget', {
              count: formatNumber(forgetHere.length, lang),
              size: formatBytes(forgetBytes, lang),
            })}
            testid="device-state-clear-row"
          >
            {!confirming ? (
              <button
                type="button"
                data-testid="device-state-clear"
                disabled={busy || forgetHere.length === 0}
                onClick={() => setConfirming(true)}
                className="rounded-lg border border-status-danger/30 bg-status-danger/15 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/25 disabled:opacity-50 max-lg:min-h-11"
              >
                {t('settings.deviceStateClear')}
              </button>
            ) : (
              <span className="flex flex-col items-end gap-2">
                <span className="text-ui-xs text-ink-soft text-right">
                  {t('settings.deviceStateWillStay', {
                    kept: formatNumber(protectedHere.length, lang),
                    unnamed: formatNumber(state.unnamed.length, lang),
                  })}
                </span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    data-testid="device-state-confirm"
                    disabled={busy}
                    onClick={() => void clearNow()}
                    className="flex items-center gap-1.5 rounded-lg border border-status-danger/30 bg-status-danger/20 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/30 disabled:opacity-50 max-lg:min-h-11"
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : null}
                    {t('settings.deviceStateConfirm')}
                  </button>
                  <button
                    type="button"
                    data-testid="device-state-cancel"
                    onClick={() => setConfirming(false)}
                    className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/60 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
                  >
                    {t('settings.cancel')}
                  </button>
                </span>
              </span>
            )}
          </SettingsRow>

          {outcome ? (
            <p
              data-testid="device-state-outcome"
              role="status"
              className="px-3 pb-2 pt-1 text-ui-xs text-ink-soft"
            >
              {outcome}
            </p>
          ) : null}
        </>
      )}
    </SettingsGroup>
  )
}
