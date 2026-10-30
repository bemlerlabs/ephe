/** The credential fields inside one item's permission sheet (Y5).
 *
 *  A required name gets a password field; saving writes the value into the
 *  vault and the page only ever learns whether it is there and where it sits.
 *  Nothing on this surface can read a stored value back. */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getSecretStatus, putSecret, removeSecret, type SecretStatus } from '@/lib/api'

export interface CredentialFieldsProps {
  names: { name: string; secret: boolean }[]
  testId?: string
}

export function CredentialFields({ names, testId = 'discover-credentials' }: CredentialFieldsProps) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<Record<string, SecretStatus>>({})
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  const wanted = names.map((one) => one.name)

  useEffect(() => {
    if (!wanted.length) return
    let live = true
    getSecretStatus(wanted)
      .then((rows) => {
        if (!live) return
        setStatus(Object.fromEntries(rows.map((row) => [row.name, row])))
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
    // The names come from the chosen item; a different item is a different sheet.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted.join(',')])

  const save = async (name: string) => {
    const value = (drafts[name] ?? '').trim()
    if (!value) return
    setBusy(name)
    setNotice('')
    try {
      const row = await putSecret(name, value)
      setStatus((current) => ({ ...current, [name]: row }))
      setDrafts((current) => ({ ...current, [name]: '' }))
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t('discover.credentialRefused'))
    } finally {
      setBusy('')
    }
  }

  const forget = async (name: string) => {
    setBusy(name)
    setNotice('')
    try {
      const row = await removeSecret(name)
      setStatus((current) => ({ ...current, [name]: row }))
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t('discover.credentialRefused'))
    } finally {
      setBusy('')
    }
  }

  if (!names.length) return null

  return (
    <section
      data-testid={testId}
      className="space-y-2 rounded-xl border border-hairline bg-surface/40 p-4"
    >
      <h3 className="font-mono text-ui-xs uppercase tracking-[0.16em] text-ink-faint">
        {t('discover.credentialsTitle')}
      </h3>
      <p className="text-ui-xs text-ink-soft">{t('discover.credentialNote')}</p>
      {names.map((one) => {
        const row = status[one.name]
        return (
          <div key={one.name} className="space-y-1">
            <label
              className="flex flex-wrap items-center gap-2 font-mono text-ui-xs text-foreground/90"
              htmlFor={`secret-${one.name}`}
            >
              <span>{one.name}</span>
              <span
                data-testid={`discover-credential-state-${one.name}`}
                className="text-ink-faint"
              >
                {row?.present
                  ? t(`discover.credentialStored.${row.mode || 'file_0600'}`)
                  : t('discover.credentialMissing')}
              </span>
            </label>
            <div className="flex items-center gap-2">
              <input
                id={`secret-${one.name}`}
                data-testid={`discover-credential-input-${one.name}`}
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={drafts[one.name] ?? ''}
                onChange={(event) =>
                  setDrafts((current) => ({ ...current, [one.name]: event.target.value }))
                }
                placeholder={t('discover.credentialPlaceholder')}
                className="focus-ring w-full rounded-lg border border-hairline bg-surface px-2.5 py-1.5 font-mono text-ui-xs text-foreground placeholder:text-ink-faint"
              />
              <button
                type="button"
                data-testid={`discover-credential-save-${one.name}`}
                disabled={busy === one.name || !(drafts[one.name] ?? '').trim()}
                onClick={() => void save(one.name)}
                className="focus-ring rounded-lg border border-hairline px-2.5 py-1 text-ui-xs text-ink-soft hover:border-hairline-strong hover:text-foreground disabled:opacity-50"
              >
                {t('discover.credentialSave')}
              </button>
              {row?.present ? (
                <button
                  type="button"
                  data-testid={`discover-credential-forget-${one.name}`}
                  disabled={busy === one.name}
                  onClick={() => void forget(one.name)}
                  className="focus-ring rounded-lg px-2 py-1 text-ui-xs text-ink-faint hover:text-foreground disabled:opacity-50"
                >
                  {t('discover.credentialForget')}
                </button>
              ) : null}
            </div>
          </div>
        )
      })}
      {notice ? (
        <p data-testid="discover-credential-notice" className="text-ui-xs text-warning">
          {notice}
        </p>
      ) : null}
    </section>
  )
}
