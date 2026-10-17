import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MessagesSquare, RefreshCw } from 'lucide-react'
import {
  deleteDiscordToken,
  getDiscordStatus,
  saveDiscordToken,
  startDiscordChannel,
  stopDiscordChannel,
  type DiscordStatus,
} from '@/lib/api'

/**
 * W3d Discord channel card (Settings → Mobile):
 * status row, token setup, runner start/stop. Without a token it says
 * 'not configured' honestly — no automatic network access.
 */
export function DiscordChannelCard() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<DiscordStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tokenInput, setTokenInput] = useState('')

  const refresh = useCallback(async () => {
    try {
      setStatus(await getDiscordStatus())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

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
      await saveDiscordToken(tokenInput.trim())
      setTokenInput('')
      await refresh()
    })

  const toggleRunner = () =>
    withBusy(async () => {
      if (status?.running) await stopDiscordChannel()
      else await startDiscordChannel()
      await refresh()
    })

  const removeToken = () =>
    withBusy(async () => {
      await deleteDiscordToken()
      await refresh()
    })

  const dot = status?.running
    ? 'bg-status-success'
    : status?.configured
      ? 'bg-status-warning'
      : 'bg-mist/30'

  return (
    <div className="mt-6 pt-5 border-t border-hairline space-y-3" data-testid="discord-card">
      <div className="flex items-center justify-between">
        <h3 className="text-ui-sm font-medium text-foreground/70 flex items-center gap-2">
          <MessagesSquare className="h-4 w-4 text-brand/80" />
          {t('settings.discordTitle')}
        </h3>
        <span
          className={`h-2 w-2 rounded-full ${dot}`}
          data-testid="discord-status-dot"
          title={status?.running ? t('settings.telegramRunning') : t('settings.telegramStopped')}
        />
      </div>
      <p className="text-ui-xs text-ink-faint">{t('settings.discordHint')}</p>

      {error && (
        <p className="text-ui-xs text-status-danger" data-testid="discord-error">
          {error}
        </p>
      )}
      {status?.last_error && !error && (
        <p
          className="text-ui-xs text-status-warning/90 font-mono break-all"
          data-testid="discord-last-error"
        >
          {status.last_error}
        </p>
      )}

      {!status?.configured ? (
        <div className="space-y-2" data-testid="discord-setup">
          <p className="text-ui-sm text-ink-faint leading-relaxed">
            {t('settings.discordSetupHint')}
          </p>
          <input
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder={t('settings.discordTokenPlaceholder')}
            className="w-full glass-control rounded-xl h-10 px-3 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring max-lg:min-h-11"
            data-testid="discord-token-input"
            type="password"
            autoComplete="off"
          />
          <button
            onClick={() => void saveToken()}
            disabled={busy || !tokenInput.trim()}
            className="w-full glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/80 hover:text-foreground hover:bg-brand/10 transition-all disabled:opacity-40 max-lg:min-h-11"
            data-testid="discord-token-save"
          >
            {busy ? '…' : t('settings.telegramSaveToken')}
          </button>
        </div>
      ) : (
        <div className="space-y-3" data-testid="discord-managed">
          <p
            className="text-ui-sm text-ink-faint font-mono break-all"
            data-testid="discord-token-masked"
          >
            {status.token_masked}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => void toggleRunner()}
              disabled={busy}
              className={`flex-1 glass-control rounded-xl h-10 text-ui-sm font-medium transition-all disabled:opacity-40 max-lg:min-h-11 ${
                status.running
                  ? 'text-foreground/70 hover:text-foreground'
                  : 'text-brand/80 hover:text-brand'
              }`}
              data-testid="discord-toggle-runner"
            >
              {status.running ? t('settings.telegramStop') : t('settings.telegramStart')}
            </button>
            <button
              onClick={() => void refresh()}
              disabled={busy}
              className="glass-control rounded-xl h-10 px-3 text-ui-xs font-medium text-foreground/60 hover:text-foreground transition-all disabled:opacity-40 max-lg:min-h-11"
              data-testid="discord-refresh"
              aria-label={t('settings.discordRefresh')}
            >
              <RefreshCw className="h-3.5 w-3.5 mx-auto" />
            </button>
          </div>
          <button
            onClick={() => void removeToken()}
            disabled={busy}
            className="text-ui-sm text-ink-faint hover:text-status-danger transition-colors flex items-center gap-1"
            data-testid="discord-remove-token"
          >
            <RefreshCw className="h-3 w-3" />
            {t('settings.telegramRemoveToken')}
          </button>
        </div>
      )}
    </div>
  )
}
