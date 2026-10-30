/**
 * The three controls above the grid: where to look (tabs, each carrying the count
 * of its own kind), what to look for (search), and what to narrow by (the facets
 * the loaded items actually offer). A facet with one value is a useless choice, so
 * a strip disappears when the items carry nothing to choose between.
 */
import { useTranslation } from 'react-i18next'
import { Search, X } from 'lucide-react'
import type { DiscoverQuery, DiscoverTab } from './discoverModel'

const TABS: DiscoverTab[] = ['all', 'skill', 'connector', 'plugin']

export function DiscoverFilters({
  query,
  counts,
  categories,
  origins,
  total,
  onChange,
}: {
  query: DiscoverQuery
  counts: Record<DiscoverTab, number>
  categories: string[]
  origins: string[]
  total: number
  onChange: (next: DiscoverQuery) => void
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<DiscoverQuery>) => onChange({ ...query, ...patch })
  const filtered = Boolean(query.category || query.origin || query.query.trim())

  return (
    <div data-testid="discover-filters" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div
          role="tablist"
          aria-label={t('discover.tabsLabel')}
          data-testid="discover-tabs"
          className="flex flex-wrap items-center gap-1 rounded-full border border-hairline bg-surface/70 p-1"
        >
          {TABS.map((tab) => {
            const active = query.tab === tab
            return (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`discover-tab-${tab}`}
                onClick={() => set({ tab })}
                className={`inline-flex min-h-9 items-center gap-1.5 rounded-full px-3 text-ui-sm transition-colors motion-safe:duration-fast ${
                  active ? 'bg-brand/18 text-foreground' : 'text-ink-soft hover:text-foreground'
                }`}
              >
                {t(`discover.tab${tab.charAt(0).toUpperCase()}${tab.slice(1)}`)}
                <span className="font-mono text-ui-xs tabular-nums text-ink-faint">{counts[tab]}</span>
              </button>
            )
          })}
        </div>

        <label className="relative flex min-w-0 flex-1 items-center md:max-w-sm">
          <Search className="pointer-events-none absolute left-3 h-4 w-4 text-ink-faint" aria-hidden="true" />
          <span className="sr-only">{t('discover.searchLabel')}</span>
          <input
            value={query.query}
            data-testid="discover-search"
            onChange={(event) => set({ query: event.target.value })}
            placeholder={t('discover.searchPlaceholder')}
            className="h-10 w-full rounded-full border border-hairline bg-surface-raised/60 pl-9 pr-3 text-ui-sm text-foreground placeholder:text-ink-faint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          />
        </label>
      </div>

      {categories.length > 1 ? (
        <ChipRow
          label={t('discover.facetCategory')}
          values={categories}
          selected={query.category}
          onPick={(value) => set({ category: value })}
        />
      ) : null}

      {origins.length > 1 ? (
        <ChipRow
          label={t('discover.facetOrigin')}
          values={origins}
          selected={query.origin}
          onPick={(value) => set({ origin: value })}
          translate
        />
      ) : null}

      {filtered ? (
        <div className="flex items-center justify-between gap-3 text-ui-xs text-ink-faint">
          <span data-testid="discover-result-count">
            {t('discover.resultCount', { shown: total, total: counts.all })}
          </span>
          <button
            type="button"
            data-testid="discover-clear"
            onClick={() => onChange({ tab: query.tab, query: '', category: null, origin: null })}
            className="inline-flex min-h-9 items-center gap-1 rounded-full border border-hairline px-2.5 text-ink-soft hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            {t('discover.clear')}
          </button>
        </div>
      ) : null}
    </div>
  )
}

function ChipRow({
  label,
  values,
  selected,
  onPick,
  translate = false,
}: {
  label: string
  values: string[]
  selected: string | null
  onPick: (value: string | null) => void
  translate?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      <span className="mr-1 font-mono text-ui-xs uppercase tracking-wide text-ink-faint">{label}</span>
      {values.map((value) => {
        const active = selected === value
        return (
          <button
            key={value}
            type="button"
            data-testid={`discover-chip-${value}`}
            aria-pressed={active}
            onClick={() => onPick(active ? null : value)}
            className={`min-h-8 rounded-full border px-2.5 text-ui-xs transition-colors motion-safe:duration-fast ${
              active
                ? 'border-brand/50 bg-brand/15 text-foreground'
                : 'border-hairline text-ink-soft hover:border-hairline-strong hover:text-foreground'
            }`}
          >
            {translate ? t(`discover.origin.${value}`) : value}
          </button>
        )
      })}
    </div>
  )
}
