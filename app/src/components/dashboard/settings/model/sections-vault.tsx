'use client'

/**
 * Passwörter & Tresor — what this machine holds for connectors, never the values.
 *
 * The rows come from the declarations a connector carries (`/api/mcp/env`) and
 * the vault's own presence answer (`/api/secrets/status`). A value can be
 * forgotten here and typed in on the connector's card in the discover shelf;
 * this page has no field that could read one back.
 */
import { useEffect, useState } from 'react'
import { KeyRound, Link2, Trash2 } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { getMcpEnv, getSecretStatus, removeSecret, type SecretStatus } from '@/lib/api'
import type { SettingsModel } from './types'

export function VaultSection({ model }: { model: SettingsModel }) {
  const { t } = model
  const [declared, setDeclared] = useState<Record<string, string[]> | null>(null)
  const [status, setStatus] = useState<Record<string, SecretStatus>>({})
  const [busy, setBusy] = useState('')

  const load = async () => {
    const rows = await Promise.resolve(getMcpEnv())
      .then((payload) => payload.servers)
      .catch(() => ({}))
    setDeclared(rows)
    const names = [...new Set(Object.values(rows).flat())]
    if (!names.length) return
    const held = await getSecretStatus(names).catch(() => [])
    setStatus(Object.fromEntries(held.map((row) => [row.name, row])))
  }

  useEffect(() => {
    void load()
  }, [])

  const forget = async (name: string) => {
    setBusy(name)
    try {
      const row = await removeSecret(name)
      setStatus((current) => ({ ...current, [name]: row }))
    } catch {
      // A refused forget leaves the row as it was; the next load tells the truth.
    } finally {
      setBusy('')
    }
  }

  const specs = Object.entries(declared ?? {})

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.vault')} subtitle={t('settings.vaultHint')} />
      {declared === null ? (
        <LoadingRow label={t('settings.vaultLoading')} data-testid="vault-loading" />
      ) : specs.length === 0 ? (
        <p data-testid="vault-empty" className="text-ui-sm text-ink-soft">
          {t('settings.vaultEmpty')}
        </p>
      ) : (
        <SettingsGroup icon={KeyRound} title={t('settings.vaultGroup')} testid="vault-group">
          {specs.map(([spec, names]) => (
            <div key={spec} data-testid={`vault-spec-${spec}`}>
              <SettingsRow
                icon={Link2}
                title={spec}
                description={t('settings.vaultConnectorHint')}
                testid={`vault-spec-row-${spec}`}
              />
              {names.map((name) => {
                const row = status[name]
                return (
                  <SettingsRow
                    key={name}
                    icon={KeyRound}
                    title={name}
                    description={
                      row?.present
                        ? t(`settings.vaultStored.${row.mode || 'file_0600'}`)
                        : t('settings.vaultMissing')
                    }
                    testid={`vault-name-${name}`}
                  >
                    {row?.present ? (
                      <button
                        type="button"
                        data-testid={`vault-forget-${name}`}
                        disabled={busy === name}
                        onClick={() => void forget(name)}
                        className="focus-ring flex items-center gap-1.5 rounded-lg border border-hairline px-2.5 py-1 text-ui-xs text-ink-soft hover:border-hairline-strong hover:text-foreground disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                        {t('settings.vaultForget')}
                      </button>
                    ) : null}
                  </SettingsRow>
                )
              })}
            </div>
          ))}
        </SettingsGroup>
      )}
    </div>
  )
}
