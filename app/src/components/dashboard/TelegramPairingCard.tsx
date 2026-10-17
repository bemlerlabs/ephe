import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Loader2, RefreshCw, Send, Trash2 } from 'lucide-react'
import {
  createTelegramPairing,
  deleteTelegramToken,
  getTelegramStatus,
  listTelegramDevices,
  revokeTelegramDevice,
  saveTelegramToken,
  startTelegramChannel,
  stopTelegramChannel,
  type TelegramDevice,
  type TelegramPairing,
  type TelegramStatus,
} from '@/lib/api'

/**
 * R24 Telegram channel card (Settings → Mobile):
 * bot-token setup (once) → QR pairing (t.me deep link, 10 min TTL)
 * → device list with immediate revoke. The token never leaves the server;
 * the pairing token lives only in the QR code.
 */
export function TelegramPairingCard() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<TelegramStatus | null>(null)
  const [devices, setDevices] = useState<TelegramDevice[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tokenInput, setTokenInput] = useState('')
  const [pairing, setPairing] = useState<TelegramPairing | null>(null)
  const [remaining, setRemaining] = useState(0)
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null)
  const [justPaired, setJustPaired] = useState(false)
  const baselinePairs = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([getTelegramStatus(), listTelegramDevices()])
      setStatus(s)
      setDevices(d)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Countdown while the QR is open
  useEffect(() => {
    if (!pairing) return
    const tick = () => setRemaining(Math.max(0, Math.round(pairing.expires_at - Date.now() / 1000)))
    tick()
    const iv = setInterval(tick, 1000)
    return () => clearInterval(iv)
  }, [pairing])

  // Poll the device count: above the QR baseline → pairing succeeded
  useEffect(() => {
    if (!pairing) return
    const iv = setInterval(async () => {
      try {
        const d = await listTelegramDevices()
        setDevices(d)
        if (baselinePairs.current !== null && d.length > baselinePairs.current) {
          setPairing(null)
          setJustPaired(true)
          void refresh()
        }
      } catch {
        /* swallow poll errors quietly — the QR stays open */
      }
    }, 2000)
    return () => clearInterval(iv)
  }, [pairing, refresh])

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const saveToken = () =>
    withBusy(async () => {
      if (!tokenInput.trim()) return
      await saveTelegramToken(tokenInput.trim())
      setTokenInput('')
      await refresh()
    })

  const toggleRunner = () =>
    withBusy(async () => {
      if (status?.running) await stopTelegramChannel()
      else await startTelegramChannel()
      await refresh()
    })

  const openPairing = () =>
    withBusy(async () => {
      setJustPaired(false)
      const d = await listTelegramDevices()
      baselinePairs.current = d.length
      const p = await createTelegramPairing()
      setPairing(p)
      setRemaining(p.ttl_seconds)
    })

  const revoke = (userId: number) =>
    withBusy(async () => {
      await revokeTelegramDevice(userId)
      setConfirmRevoke(null)
      await refresh()
    })

  const removeToken = () =>
    withBusy(async () => {
      await deleteTelegramToken()
      setPairing(null)
      await refresh()
    })

  const dot = status?.running
    ? 'bg-status-success'
    : status?.token_configured
      ? 'bg-status-warning'
      : 'bg-mist/30'

  return (
    <div className="mt-6 pt-5 border-t border-hairline space-y-3" data-testid="telegram-card">
      <div className="flex items-center justify-between">
        <h3 className="text-ui-sm font-medium text-foreground/70 flex items-center gap-2">
          <Send className="h-4 w-4 text-brand/80" />
          {t('settings.telegramTitle')}
        </h3>
        <span
          className={`h-2 w-2 rounded-full ${dot}`}
          data-testid="telegram-status-dot"
          title={status?.running ? t('settings.telegramRunning') : t('settings.telegramStopped')}
        />
      </div>
      <p className="text-ui-xs text-ink-faint">{t('settings.telegramHint')}</p>

      {error && (
        <div className="rounded-xl p-3 text-ui-xs bg-status-danger/10 border border-red-400/20 text-status-danger flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span data-testid="telegram-error">{error}</span>
        </div>
      )}
      {status?.last_error && !error && (
        <div className="rounded-xl p-3 text-ui-xs bg-status-warning/10 border border-amber-400/20 text-status-warning flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{status.last_error}</span>
        </div>
      )}
      {justPaired && (
        <div
          className="rounded-xl p-3 text-ui-xs bg-status-success/10 border border-status-success/20 text-status-success"
          data-testid="telegram-paired-success"
        >
          {t('settings.telegramPairedSuccess')}
        </div>
      )}

      {!status?.token_configured ? (
        <div className="space-y-2" data-testid="telegram-setup">
          <p className="text-ui-sm text-ink-faint leading-relaxed">
            {t('settings.telegramSetupHint')}
          </p>
          <input
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder={t('settings.telegramTokenPlaceholder')}
            className="w-full glass-control rounded-xl h-10 px-3 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring"
            data-testid="telegram-token-input"
            type="password"
            autoComplete="off"
          />
          <button
            onClick={() => void saveToken()}
            disabled={busy || !tokenInput.trim()}
            className="w-full glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/80 hover:text-foreground hover:bg-brand/10 transition-all disabled:opacity-40"
            data-testid="telegram-token-save"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin mx-auto" />
            ) : (
              t('settings.telegramSaveToken')
            )}
          </button>
        </div>
      ) : (
        <div className="space-y-3" data-testid="telegram-managed">
          <p className="text-ui-sm text-ink-faint font-mono break-all">
            {status.token_masked}
            {status.bot_username ? ` · @${status.bot_username}` : ''}
          </p>

          {pairing ? (
            <div className="space-y-3 rounded-xl bg-surface-raised border border-hairline p-3">
              <div className="flex justify-center rounded-xl bg-white p-3 max-w-[240px] mx-auto">
                <img
                  src={`data:image/png;base64,${pairing.qr_base64}`}
                  alt={t('settings.telegramQrAlt')}
                  className="w-full h-auto"
                  data-testid="telegram-qr"
                />
              </div>
              <p className="text-ui-sm text-ink-soft text-center leading-relaxed">
                {t('settings.telegramWaitingQr')}
              </p>
              <p className="text-ui-sm text-ink-faint text-center" data-testid="telegram-qr-expiry">
                {t('settings.telegramExpiresIn', { seconds: remaining })}
              </p>
              <div className="flex gap-2">
                <a
                  href={pairing.deep_link}
                  className="flex-1 glass-control rounded-xl h-9 text-ui-xs font-medium text-foreground/80 hover:text-foreground hover:bg-brand/10 transition-all flex items-center justify-center"
                  data-testid="telegram-open-link"
                >
                  {t('settings.telegramOpenInTelegram')}
                </a>
                <button
                  onClick={() => setPairing(null)}
                  className="flex-1 glass-control rounded-xl h-9 text-ui-xs font-medium text-foreground/60 hover:text-foreground hover:bg-brand/10 transition-all"
                  data-testid="telegram-pair-cancel"
                >
                  {t('settings.telegramCancel')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => void openPairing()}
                disabled={busy}
                className="flex-1 glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/80 hover:text-foreground hover:bg-brand/10 transition-all disabled:opacity-40"
                data-testid="telegram-pair-button"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                ) : (
                  t('settings.telegramConnect')
                )}
              </button>
              <button
                onClick={() => void toggleRunner()}
                disabled={busy}
                className={`glass-control rounded-xl h-10 px-3 text-ui-xs font-medium transition-all disabled:opacity-40 ${
                  status.running
                    ? 'text-foreground/70 hover:text-foreground'
                    : 'text-brand/80 hover:text-brand'
                }`}
                data-testid="telegram-toggle-runner"
              >
                {status.running ? t('settings.telegramStop') : t('settings.telegramStart')}
              </button>
            </div>
          )}

          {/* Device list + revoke */}
          <div className="space-y-1.5" data-testid="telegram-devices">
            <p className="text-ui-sm uppercase tracking-wide text-ink-faint pt-1">
              {t('settings.telegramDevicesTitle')}
            </p>
            {devices.length === 0 ? (
              <p className="text-ui-xs text-ink-faint">{t('settings.telegramNoDevices')}</p>
            ) : (
              devices.map((d) => (
                <div
                  key={d.user_id}
                  className="flex items-center justify-between rounded-xl bg-surface-raised border border-hairline px-3 py-2"
                  data-testid={`telegram-device-${d.user_id}`}
                >
                  <div className="min-w-0">
                    <p className="text-ui-xs text-foreground/80 truncate">
                      {d.label || `Telegram ${d.user_id}`}
                    </p>
                    <p className="text-ui-xs text-ink-faint font-mono">
                      ID {d.user_id} ·{' '}
                      {t('settings.telegramPaired', { date: d.paired_at.slice(0, 10) })}
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      confirmRevoke === d.user_id
                        ? void revoke(d.user_id)
                        : setConfirmRevoke(d.user_id)
                    }
                    onBlur={() => setConfirmRevoke(null)}
                    className={`shrink-0 ml-2 rounded-lg px-2 py-1 text-ui-sm font-medium transition-all ${
                      confirmRevoke === d.user_id
                        ? 'bg-status-danger/20 text-status-danger'
                        : 'text-ink-faint hover:text-status-danger'
                    }`}
                    data-testid={`telegram-revoke-${d.user_id}`}
                  >
                    {confirmRevoke === d.user_id ? (
                      t('settings.telegramRevokeConfirm')
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              ))
            )}
          </div>

          <button
            onClick={() => void removeToken()}
            disabled={busy}
            className="text-ui-sm text-ink-faint hover:text-status-danger transition-colors flex items-center gap-1"
            data-testid="telegram-remove-token"
          >
            <RefreshCw className="h-3 w-3" />
            {t('settings.telegramRemoveToken')}
          </button>
        </div>
      )}
    </div>
  )
}
