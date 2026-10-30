/**
 * One entry on the shelf. The whole card opens the detail surface; the one
 * round control in the corner is the only verb it carries, and it says what
 * this machine already decided: add, or on and ready to turn off.
 */
import { useTranslation } from 'react-i18next'
import { Check, Plus } from 'lucide-react'
import { CategoryGlyph } from './categoryGlyph'
import './discover.css'
import type { DiscoverItem } from './discoverModel'

export type DiscoverAction = 'add' | 'toggle' | 'remove'

/** The numbers a card may carry, each only when the endpoint sent it. */
function Facts({ item }: { item: DiscoverItem }) {
  const { t } = useTranslation()
  const facts: string[] = []
  if (item.downloads) facts.push(t('discover.cardDownloads', { count: item.downloads }))
  if (item.toolCount !== undefined) facts.push(t('discover.cardTools', { count: item.toolCount }))
  if (item.calls !== undefined) facts.push(t('discover.cardCalls', { count: item.calls }))
  if (!facts.length) return null
  return (
    <p
      data-testid={`discover-facts-${item.id}`}
      className="truncate font-mono text-ui-2xs tabular-nums tracking-wide text-ink-faint"
    >
      {facts.join(' · ')}
    </p>
  )
}

function Badge({ item }: { item: DiscoverItem }) {
  const { t } = useTranslation()
  // Nearly every registry row is a curated pick; the badge earns its place only
  // when it says something the row does not already say.
  if (!item.badge || item.badge === 'pick') return null
  return (
    <span data-testid={`discover-badge-${item.id}`} className="shrink-0 text-ui-2xs text-brand">
      · {t(`discover.badge.${item.badge}`)}
    </span>
  )
}

export function DiscoverCard({
  item,
  fluid = false,
  busy = false,
  onAdd,
  onToggle,
  onDetail,
}: {
  item: DiscoverItem
  /** A shelf sets its own card width; a filtered grid lets the column decide. */
  fluid?: boolean
  busy?: boolean
  onAdd: (item: DiscoverItem) => void
  onToggle: (item: DiscoverItem, next: boolean) => void
  onDetail?: (item: DiscoverItem) => void
}) {
  const { t } = useTranslation()
  const provenance =
    item.publisher ?? t(`discover.origin.${item.origin}`, { defaultValue: item.origin })
  const on = item.installed && item.enabled && !item.offline

  return (
    <article
      data-testid={`discover-card-${item.id}`}
      data-subject={item.categories[0] ?? 'other'}
      className={`group relative flex flex-col overflow-hidden rounded-2xl border border-hairline bg-surface/75 p-4 transition-colors motion-safe:duration-base hover:border-hairline-strong hover:bg-surface ${
        fluid ? 'w-full' : 'w-[17rem] shrink-0'
      }`}
    >
      {onDetail ? (
        <button
          type="button"
          data-testid={`discover-detail-open-${item.id}`}
          aria-label={`${t('discover.cardDetail')}: ${item.title}`}
          onClick={() => onDetail(item)}
          className="focus-ring absolute inset-0 z-0 rounded-2xl"
        />
      ) : null}

      <div className="pointer-events-none relative z-10 flex items-start gap-3">
        <span
          aria-hidden="true"
          className="discover-plate grid h-9 w-9 shrink-0 place-items-center rounded-lg border transition-colors motion-safe:duration-base"
        >
          {item.kind === 'skill' ? (
            <span className="font-display text-ui-base leading-none text-foreground/85">
              {(item.title.trim()[0] ?? '?').toUpperCase()}
            </span>
          ) : (
            <CategoryGlyph category={item.categories[0]} kind={item.kind} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-ui-sm font-semibold leading-snug tracking-[-0.01em] text-foreground">
            {item.title}
          </h3>
          <p className="mt-0.5 flex min-w-0 items-center text-ui-2xs text-ink-faint">
            <span className="truncate">{provenance}</span>
            <Badge item={item} />
          </p>
        </div>
      </div>

      <p
        data-testid={`discover-summary-${item.id}`}
        className="pointer-events-none relative z-10 mt-3 line-clamp-2 text-ui-xs leading-relaxed text-ink-soft"
      >
        {item.summary || t('discover.noSummary')}
      </p>

      <div className="mt-auto flex items-center justify-between gap-3 pt-4">
        <div className="pointer-events-none relative z-10 min-w-0">
          <Facts item={item} />
        </div>
        {item.offline ? (
          <span
            data-testid={`discover-state-${item.id}`}
            className="shrink-0 text-ui-2xs uppercase tracking-wide text-status-warning"
          >
            {t('discover.stateOffline')}
          </span>
        ) : null}
        <button
          type="button"
          data-testid={`discover-act-${item.id}`}
          disabled={busy}
          onClick={() => (item.installed ? onToggle(item, !item.enabled) : onAdd(item))}
          aria-label={
            item.installed
              ? t(item.enabled ? 'discover.actionOff' : 'discover.actionOn')
              : t('discover.actionAddNamed', { name: item.title })
          }
          data-on={on ? 'true' : 'false'}
          className={`relative z-10 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-50 ${
            on
              ? 'border-status-success/40 bg-status-success/12 text-status-success'
              : 'border-hairline text-ink-soft hover:border-brand hover:text-brand'
          }`}
        >
          {on ? (
            <Check data-testid={`discover-state-${item.id}`} className="h-3.5 w-3.5" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
    </article>
  )
}
