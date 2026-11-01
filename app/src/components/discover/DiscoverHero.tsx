/** The featured pick: the one entry the shelf argues for, at display size.
 *
 *  It carries the same facts a card carries, set as a summary column, so the
 *  large surface never claims more than the small one. The mark sits behind
 *  the column as a watermark, cropped by the card, never as an illustration.
 *  When the entry names a vendor icon the publisher's own mark takes the
 *  eyebrow slot on the card's plate; the subject glyph is the fallback, so a
 *  turn between picks of equal shape never moves the title. */
import { useTranslation } from 'react-i18next'
import { Check, Plus } from 'lucide-react'
import { CategoryGlyph } from './categoryGlyph'
import type { DiscoverItem } from './discoverModel'
import './discover.css'

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <dt className="text-ui-2xs uppercase tracking-[0.12em] text-ink-faint">{label}</dt>
      <dd className="min-w-0 truncate text-right text-ui-xs tabular-nums text-foreground/90">
        {value}
      </dd>
    </div>
  )
}

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
  const on = item.installed && item.enabled && !item.offline

  return (
    <section
      data-testid="discover-hero"
      className="relative flex h-full flex-col overflow-hidden rounded-3xl border border-hairline bg-surface/60"
    >
      <span
        aria-hidden="true"
        className="forest-glow pointer-events-none absolute inset-0 opacity-50"
      />
      <div className="relative grid flex-1 gap-8 px-6 py-7 sm:px-9 sm:py-9 lg:grid-cols-[minmax(0,1fr)_248px] lg:gap-10">
        <div className="flex min-w-0 flex-col justify-between gap-6">
          <div>
            <p className="flex items-center gap-2 font-mono text-ui-2xs uppercase tracking-[0.2em] text-ink-faint">
              <span
                data-subject={category}
                data-testid="discover-hero-plate"
                className="discover-plate grid h-9 w-9 shrink-0 place-items-center rounded-lg border"
              >
                {item.icon ? (
                  <img
                    src={item.icon}
                    alt=""
                    width={28}
                    height={28}
                    loading="lazy"
                    data-testid="discover-hero-icon"
                    className="h-7 w-7 rounded-md object-contain"
                  />
                ) : (
                  <CategoryGlyph category={category} kind={item.kind} className="h-3.5 w-3.5" />
                )}
              </span>
              {t('discover.heroEyebrow')}
            </p>
            <h2 className="mt-4 max-w-lg font-display text-4xl leading-[1.06] tracking-tight text-foreground sm:text-5xl">
              {item.title}
            </h2>
            <p className="mt-3 line-clamp-2 max-w-xl text-ui-sm leading-relaxed text-ink-soft">
              {item.summary || t('discover.noSummary')}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-3">
            <button
              type="button"
              data-testid="discover-hero-act"
              disabled={busy}
              onClick={() => (item.installed ? onToggle(item, !item.enabled) : onAdd(item))}
              className={`inline-flex min-h-10 items-center gap-1.5 rounded-full px-4 text-ui-sm font-medium transition-colors disabled:opacity-50 ${
                on
                  ? 'border border-hairline text-ink-soft hover:border-hairline-strong hover:text-foreground'
                  : 'bg-brand text-black hover:bg-brand-glow'
              }`}
            >
              {on ? (
                <Check className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Plus className="h-4 w-4" aria-hidden="true" />
              )}
              {item.installed
                ? t(item.enabled ? 'discover.actionOff' : 'discover.actionOn')
                : t('discover.actionAdd')}
            </button>
            {onDetail ? (
              <button
                type="button"
                data-testid="discover-hero-detail"
                disabled={busy}
                onClick={() => onDetail(item)}
                className="focus-ring inline-flex h-10 items-center rounded-full px-3 text-ui-sm text-ink-soft hover:text-foreground disabled:opacity-50"
              >
                {t('discover.cardDetail')}
              </button>
            ) : null}
          </div>
        </div>

        <dl className="grid content-start divide-y divide-hairline border-t border-hairline pt-1 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          {item.downloads ? (
            <Fact
              label={t('discover.detailDownloads')}
              value={t('discover.cardDownloads', { count: item.downloads })}
            />
          ) : null}
          {item.publisher ? (
            <Fact label={t('discover.detailPublisher')} value={item.publisher} />
          ) : null}
          <Fact
            label={t('discover.facetCategory')}
            value={t(`discover.category.${category}`, { defaultValue: category })}
          />
          <Fact
            label={t('discover.detailKind')}
            value={t(`discover.kind${item.kind.charAt(0).toUpperCase()}${item.kind.slice(1)}`)}
          />
          <Fact
            label={t('discover.detailSource')}
            value={t(`discover.origin.${item.origin}`, { defaultValue: item.origin })}
          />
          {item.version ? <Fact label={t('discover.detailVersion')} value={item.version} /> : null}
        </dl>
      </div>
    </section>
  )
}
