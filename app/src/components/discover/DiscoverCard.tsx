/**
 * One card, two weights. The hero card carries the display face and the glow the
 * brand uses elsewhere; the compact card keeps the same slots so a filter change
 * never moves a value to a different place.
 */
import { useTranslation } from 'react-i18next'
import { Check, Plug, Plus, Puzzle, Sparkles, Trash2 } from 'lucide-react'
import type { DiscoverItem, DiscoverKind } from './discoverModel'

export type DiscoverAction = 'add' | 'toggle' | 'remove'

const KIND_ICON: Record<DiscoverKind, typeof Plug> = {
  skill: Sparkles,
  connector: Plug,
  plugin: Puzzle,
}

/** The four numbers a card may carry, each only when the endpoint sent it. */
function Facts({ item }: { item: DiscoverItem }) {
  const { t } = useTranslation()
  const facts: string[] = []
  if (item.version) facts.push(item.version)
  if (item.toolCount !== undefined) facts.push(t('discover.cardTools', { count: item.toolCount }))
  if (item.calls !== undefined) facts.push(t('discover.cardCalls', { count: item.calls }))
  if (item.latencyMs !== undefined) facts.push(t('discover.cardLatency', { ms: item.latencyMs }))
  if (!facts.length) return null
  return (
    <p data-testid={`discover-facts-${item.id}`} className="font-mono text-ui-xs text-ink-faint">
      {facts.join(' · ')}
    </p>
  )
}

export function DiscoverCard({
  item,
  hero = false,
  busy = false,
  onAdd,
  onToggle,
  onRemove,
}: {
  item: DiscoverItem
  hero?: boolean
  busy?: boolean
  onAdd: (item: DiscoverItem) => void
  onToggle: (item: DiscoverItem, next: boolean) => void
  onRemove: (item: DiscoverItem) => void
}) {
  const { t } = useTranslation()
  const Icon = KIND_ICON[item.kind]
  const primary = item.installed
    ? {
        label: t(item.enabled ? 'discover.actionOff' : 'discover.actionOn'),
        run: () => onToggle(item, !item.enabled),
      }
    : { label: t('discover.actionAdd'), run: () => onAdd(item) }

  return (
    <article
      data-testid={`discover-card-${item.id}`}
      data-hero={hero ? 'true' : 'false'}
      className={`group relative flex flex-col gap-2 overflow-hidden rounded-2xl border border-hairline bg-surface p-4 transition-shadow motion-safe:transition-all motion-safe:duration-base hover:shadow-elevation-2 ${
        hero ? 'sm:col-span-2 lg:col-span-3 lg:p-6' : ''
      }`}
    >
      {hero ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-20 h-52 w-52 rounded-full bg-brand/12 blur-3xl"
        />
      ) : null}

      <header className="flex items-start justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-surface-raised/60 px-2 py-0.5 font-mono text-ui-xs text-ink-soft">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {t(`discover.kind${item.kind.charAt(0).toUpperCase()}${item.kind.slice(1)}`)}
        </span>
        {item.installed ? (
          <span
            data-testid={`discover-state-${item.id}`}
            className={`inline-flex items-center gap-1 text-ui-xs ${
              item.offline
                ? 'text-status-warning'
                : item.enabled
                  ? 'text-status-success'
                  : 'text-ink-faint'
            }`}
          >
            {item.offline ? (
              t('discover.stateOffline')
            ) : item.enabled ? (
              <>
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                {t('discover.stateOn')}
              </>
            ) : (
              t('discover.stateOff')
            )}
          </span>
        ) : null}
      </header>

      <div className="relative">
        <h3
          className={
            hero
              ? 'font-display text-xl leading-snug text-foreground sm:text-2xl'
              : 'text-ui-sm font-semibold leading-snug text-foreground'
          }
        >
          {item.title}
        </h3>
        <p
          data-testid={`discover-summary-${item.id}`}
          className={`mt-1 text-ink-soft ${hero ? 'text-ui-sm' : 'line-clamp-2 text-ui-xs'}`}
        >
          {item.summary || t('discover.noSummary')}
        </p>
      </div>

      <div className="mt-auto flex items-end justify-between gap-3 pt-1">
        <div className="min-w-0">
          <p className="truncate text-ui-xs text-ink-faint">
            {t(`discover.origin.${item.origin}`)}
          </p>
          <Facts item={item} />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {item.installed && item.kind !== 'skill' ? (
            <button
              type="button"
              data-testid={`discover-remove-${item.id}`}
              disabled={busy}
              onClick={() => onRemove(item)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-hairline text-ink-faint hover:border-hairline-strong hover:text-status-danger disabled:opacity-50"
              aria-label={t('discover.actionRemove')}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : null}
          <button
            type="button"
            data-testid={`discover-act-${item.id}`}
            disabled={busy}
            onClick={primary.run}
            className="glass-control inline-flex min-h-9 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-ui-xs font-medium text-foreground hover:bg-surface-interactive disabled:opacity-50"
          >
            {item.installed ? null : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            {primary.label}
          </button>
        </div>
      </div>
    </article>
  )
}
