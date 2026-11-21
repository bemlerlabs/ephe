/**
 * The shelf's toolbar. What kind to look at is a segmented control, the words
 * are a search field, and the two facets are menus — a wall of topic pills put
 * the first row of the shelf below the fold on a phone.
 */
import { useTranslation } from 'react-i18next'
import { ChevronDown, Search, X } from 'lucide-react'
import type { DiscoverQuery, DiscoverTab } from './discoverModel'
import './discover.css'

const TABS: DiscoverTab[] = ['all', 'skill', 'connector', 'plugin']

function Menu({
  testId,
  label,
  value,
  options,
  onChange,
}: {
  testId: string
  label: string
  value: string | null
  options: { value: string; label: string; id?: string }[]
  onChange: (next: string | null) => void
}) {
  return (
    <label className="relative inline-flex w-40 min-w-0 items-center">
      <span className="sr-only">{label}</span>
      <select
        data-testid={testId}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        className={`h-8 w-full min-w-0 cursor-pointer appearance-none truncate rounded-full border bg-transparent pl-3 pr-7 text-ui-xs transition-colors motion-safe:duration-fast hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
          value
            ? 'border-brand/45 text-foreground'
            : 'border-hairline text-ink-soft hover:border-hairline-strong'
        }`}
      >
        <option value="">{label}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value} data-testid={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2.5 h-3.5 w-3.5 text-ink-faint"
      />
    </label>
  )
}

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
    <div
      data-testid="discover-filters"
      className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-x-4"
    >
      <label className="relative order-first flex h-10 items-center lg:order-last lg:ml-auto lg:w-56 xl:w-72">
        <Search
          className="pointer-events-none absolute left-3 h-4 w-4 text-ink-faint"
          aria-hidden="true"
        />
        <span className="sr-only">{t('discover.searchLabel')}</span>
        <input
          value={query.query}
          data-testid="discover-search"
          onChange={(event) => set({ query: event.target.value })}
          placeholder={t('discover.searchPlaceholder')}
          className="h-10 w-full rounded-full border border-hairline bg-surface/60 pl-9 pr-3 text-ui-sm text-foreground transition-colors placeholder:text-ink-faint hover:border-hairline-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        />
      </label>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 lg:flex-nowrap">
        <div
          role="tablist"
          aria-label={t('discover.tabsLabel')}
          data-testid="discover-tabs"
          className="discover-track flex max-w-full flex-nowrap items-center gap-0.5 overflow-x-auto rounded-lg border border-hairline bg-surface/40 p-0.5"
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
                className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-ui-xs transition-colors motion-safe:duration-fast ${
                  active
                    ? 'bg-surface-interactive text-foreground'
                    : 'text-ink-soft hover:text-foreground'
                }`}
              >
                {t(`discover.tab${tab.charAt(0).toUpperCase()}${tab.slice(1)}`)}
                <span
                  className={`font-mono text-ui-2xs tabular-nums ${
                    active ? 'text-ink-soft' : 'text-ink-faint'
                  }`}
                >
                  {counts[tab]}
                </span>
              </button>
            )
          })}
        </div>

        <span aria-hidden="true" className="hidden h-5 w-px bg-hairline lg:block" />

        <div className="flex min-w-0 items-center gap-2">
          {categories.length > 1 ? (
            <Menu
              testId="discover-subject-select"
              label={t('discover.facetAll')}
              value={query.category}
              onChange={(category) => set({ category })}
              options={categories.map((value) => ({
                value,
                label: t(`discover.category.${value}`, { defaultValue: value }),
                id: `discover-chip-${value}`,
              }))}
            />
          ) : null}
          {origins.length > 1 ? (
            <Menu
              testId="discover-origin-select"
              label={t('discover.facetAnyOrigin')}
              value={query.origin}
              onChange={(origin) => set({ origin })}
              options={origins.map((value) => ({
                value,
                label: t(`discover.origin.${value}`, { defaultValue: value }),
                id: `discover-origin-${value}`,
              }))}
            />
          ) : null}
        </div>

        {filtered ? (
          <div className="ml-auto flex items-center gap-3 text-ui-xs text-ink-faint">
            <span data-testid="discover-result-count" className="tabular-nums">
              {t('discover.resultCount', { shown: total, total: counts.all })}
            </span>
            <button
              type="button"
              data-testid="discover-clear"
              onClick={() => onChange({ tab: query.tab, query: '', category: null, origin: null })}
              className="focus-ring inline-flex h-7 items-center gap-1 rounded-full px-2 text-ink-soft hover:bg-surface-interactive hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              {t('discover.clear')}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
