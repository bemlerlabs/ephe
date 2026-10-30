/** The featured pick: the one entry the shelf argues for, at display size.
 *
 *  The reference draws one calm banner before its sections; the banner is the same
 *  item model as a card, so nothing here can say something a card would not. */
import { useTranslation } from 'react-i18next'
import { Check, Plus } from 'lucide-react'
import type { DiscoverItem } from './discoverModel'

export function DiscoverHero({
  item,
  busy,
  onAdd,
  onToggle,
  onDetail,
}: {
  item: DiscoverItem
  busy: boolean
  onAdd: (item: DiscoverItem) => void
  onToggle: (item: DiscoverItem, next: boolean) => void
  onDetail?: (item: DiscoverItem) => void
}) {
  const { t } = useTranslation()
  const category = item.categories[0] ?? 'other'
  const primary = item.installed
    ? { label: t(item.enabled ? 'discover.actionOff' : 'discover.actionOn'), run: () => onToggle(item, !item.enabled) }
    : { label: t('discover.actionAdd'), run: () => onAdd(item) }

  return (
    <section
      data-testid="discover-hero"
      className="relative mt-6 overflow-hidden rounded-3xl border border-hairline bg-surface p-6 sm:p-8"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 -top-28 h-64 w-64 rounded-full bg-brand/10 blur-3xl"
      />
      <div className="relative max-w-2xl">
        <p className="font-mono text-ui-xs uppercase tracking-[0.16em] text-brand">
          {t('discover.heroEyebrow')} · {t(`discover.category.${category}`, { defaultValue: category })}
        </p>
        <h2 className="mt-3 font-display text-2xl leading-tight text-foreground sm:text-3xl">
          {item.title}
        </h2>
        <p className="mt-2 line-clamp-2 text-ui-sm text-ink-soft">
          {item.summary || t('discover.noSummary')}
        </p>
      </div>
      <div className="relative mt-6 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 font-mono text-ui-xs text-ink-faint">
          {t(`discover.origin.${item.origin}`)}
        </span>
        {item.installed && item.enabled ? (
          <span className="inline-flex items-center gap-1 text-ui-xs text-status-success">
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
            {t('discover.stateOn')}
          </span>
        ) : null}
        <span className="ml-auto flex items-center gap-2">
          {onDetail ? (
            <button
              type="button"
              data-testid="discover-hero-detail"
              disabled={busy}
              onClick={() => onDetail(item)}
              className="focus-ring inline-flex h-9 items-center rounded-full px-3 text-ui-xs text-ink-soft hover:text-foreground disabled:opacity-50"
            >
              {t('discover.cardDetail')}
            </button>
          ) : null}
          <button
            type="button"
            data-testid="discover-hero-act"
            disabled={busy}
            onClick={primary.run}
            className="glass-control inline-flex min-h-9 items-center gap-1.5 rounded-full px-4 py-1.5 text-ui-xs font-medium text-foreground hover:bg-surface-interactive disabled:opacity-50"
          >
            {item.installed ? null : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            {primary.label}
          </button>
        </span>
      </div>
    </section>
  )
}
