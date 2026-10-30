/** Where the shelf is read from: the two presets that ship, and what the user
 *  added. A preset is readable and not removable — it is the breadth the app
 *  promises out of the box. A user source is a local JSON index or an HTTPS
 *  index; both come through the same validated door and can be removed again. */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'
import { Database, Globe, HardDrive, Plus, Trash2 } from 'lucide-react'
import type { DiscoverPreset } from '@/lib/api'
import type { MarketSource } from '@/lib/api'

export interface SourcesRowProps {
  presets: DiscoverPreset[]
  sources: MarketSource[]
  busy: boolean
  onAdd: (body: { kind: 'local' | 'https'; title: string; url: string }) => Promise<unknown>
  onRemove: (id: string) => Promise<unknown>
}

export function SourcesRow({ presets, sources, busy, onAdd, onRemove }: SourcesRowProps) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<'local' | 'https'>('https')
  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')

  const submit = async () => {
    setError('')
    try {
      await onAdd({ kind, title: title.trim(), url: url.trim() })
      setTitle('')
      setUrl('')
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('discover.sourceRefused'))
    }
  }

  return (
    <section
      data-testid="discover-sources"
      className="mt-16 rounded-2xl border border-hairline bg-surface/35 p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-ui-sm font-semibold text-foreground/95">
            {t('discover.sourcesTitle')}
          </h2>
          <p className="mt-1 max-w-xl text-ui-xs leading-relaxed text-ink-faint">
            {t('discover.sourcesLede')}
          </p>
        </div>
        <button
          type="button"
          data-testid="discover-source-add"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-full border border-hairline px-3 text-ui-xs text-ink-soft transition-colors hover:border-hairline-strong hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
          {t('discover.sourceAdd')}
        </button>
      </div>

      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {presets.map((preset) => (
          <li
            key={preset.id}
            data-testid={`discover-preset-${preset.id}`}
            className="flex items-center gap-2.5 rounded-xl border border-hairline bg-surface/50 px-3 py-2.5 text-ui-xs text-ink-soft"
          >
            {preset.kind === 'mirror' ? (
              <Database className="h-4 w-4 shrink-0 text-ink-faint" strokeWidth={1.5} />
            ) : (
              <HardDrive className="h-4 w-4 shrink-0 text-ink-faint" strokeWidth={1.5} />
            )}
            <span className="min-w-0 flex-1 truncate">{t(`discover.preset.${preset.id}`)}</span>
            <span className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint">
              {formatNumber(preset.count, i18n?.language)}
            </span>
          </li>
        ))}
        {sources
          .filter((source) => source.removable)
          .map((source) => (
            <li
              key={source.id}
              data-testid={`discover-source-${source.id}`}
              className="flex items-center gap-2.5 rounded-xl border border-hairline bg-surface/50 px-3 py-2.5 text-ui-xs text-ink-soft"
            >
              <Globe className="h-4 w-4 shrink-0 text-ink-faint" strokeWidth={1.5} />
              <span className="min-w-0 flex-1 truncate">{source.title}</span>
              <button
                type="button"
                data-testid={`discover-source-remove-${source.id}`}
                disabled={busy}
                onClick={() => void onRemove(source.id)}
                className="focus-ring shrink-0 rounded-full p-1 text-ink-faint hover:text-foreground disabled:opacity-50"
                aria-label={t('discover.sourceRemove')}
              >
                <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </li>
          ))}
      </ul>

      {open ? (
        <div className="mt-3 space-y-2 rounded-xl border border-hairline bg-surface/50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            {(['https', 'local'] as const).map((option) => (
              <button
                key={option}
                type="button"
                data-testid={`discover-source-kind-${option}`}
                onClick={() => setKind(option)}
                aria-pressed={kind === option}
                className={`focus-ring rounded-full border px-2.5 py-1 text-ui-xs ${
                  kind === option
                    ? 'border-hairline-strong text-foreground'
                    : 'border-hairline text-ink-faint'
                }`}
              >
                {t(`discover.sourceKind.${option}`)}
              </button>
            ))}
          </div>
          <input
            data-testid="discover-source-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t('discover.sourceTitle')}
            className="focus-ring w-full rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-ui-xs text-foreground placeholder:text-ink-faint"
          />
          <input
            data-testid="discover-source-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder={kind === 'https' ? 'https://…/index.json' : t('discover.sourcePath')}
            className="focus-ring w-full rounded-lg border border-hairline bg-surface px-2.5 py-1.5 font-mono text-ui-xs text-foreground placeholder:text-ink-faint"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="discover-source-save"
              disabled={busy || !title.trim() || !url.trim()}
              onClick={() => void submit()}
              className="focus-ring rounded-full border border-hairline px-2.5 py-1 text-ui-xs text-ink-soft hover:border-hairline-strong hover:text-foreground disabled:opacity-50"
            >
              {t('discover.sourceSave')}
            </button>
            {error ? (
              <span data-testid="discover-source-error" className="text-ui-xs text-warning">
                {error}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
