/**
 * `/discover` — the shelf Ephe's own abilities are browsed from, one page for
 * skills, connectors and add-ons. The bench on the right is the product's claim
 * made visible: every bar is a call count this machine wrote to its own audit log.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Package } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { DiscoverCard } from '@/components/discover/DiscoverCard'
import { DiscoverDetail } from '@/components/discover/DiscoverDetail'
import { DiscoverHero } from '@/components/discover/DiscoverHero'
import { DiscoverFilters } from '@/components/discover/DiscoverFilters'
import { DiscoverSections } from '@/components/discover/DiscoverSections'
import { Shelf } from '@/components/discover/Shelf'
import { SourcesRow } from '@/components/discover/SourcesRow'
import { useIntentSearch } from '@/components/discover/useIntentSearch'
import { UsageBench } from '@/components/discover/UsageBench'
import {
  bentoOf,
  buildItems,
  categoryFacets,
  countByTab,
  facetValues,
  filterItems,
  rankByIntent,
  type DiscoverItem,
  type DiscoverQuery,
  type DiscoverSources,
} from '@/components/discover/discoverModel'
import { CATEGORY_ORDER } from '@/components/discover/discoverNames'
import { loadSources } from '@/components/discover/discoverSources'
import { useDiscoverActions } from '@/components/discover/useDiscoverActions'
import { browsingPicks, useFeaturedRotation } from '@/components/discover/useFeaturedRotation'
import { addMarketSource, removeMarketSource } from '@/lib/api'

export default function DiscoverPage() {
  const { t } = useTranslation()
  const [sources, setSources] = useState<DiscoverSources | null>(null)
  const [indexSource, setIndexSource] = useState<string>('')
  const [failed, setFailed] = useState<string[]>([])
  const [query, setQuery] = useState<DiscoverQuery>({
    tab: 'all',
    query: '',
    category: null,
    origin: null,
  })

  const load = useCallback(async () => {
    const next = await loadSources()
    setSources(next.sources)
    setFailed(next.failed)
    setIndexSource(next.sources.home?.sources[0]?.id ?? '')
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const items = useMemo(() => (sources ? buildItems(sources) : []), [sources])

  const needle = query.query.trim()
  const intentIds = useIntentSearch(items, needle)

  const shown = useMemo(
    () => rankByIntent(filterItems(items, query, intentIds), intentIds),
    [items, query, intentIds],
  )
  const counts = useMemo(() => countByTab(items), [items])
  const categories = useMemo(() => categoryFacets(items), [items])
  const origins = useMemo(() => facetValues(items, (one) => [one.origin]), [items])
  const { featured, hero, pick, setPick, setPaused } = useFeaturedRotation(items, query, shown)
  const bento = useMemo(() => bentoOf(items), [items])
  const bentoIds = useMemo(() => new Set(bento.map((one) => one.id)), [bento])

  /** On the quiet default view the shelf reads as sections, one per subject. */
  const grouped = useMemo(() => {
    if (query.tab !== 'all' || query.query || query.category) return null
    const map = new Map<string, DiscoverItem[]>()
    for (const item of shown) {
      if (bentoIds.has(item.id)) continue
      const key = item.categories[0] ?? 'other'
      map.set(key, [...(map.get(key) ?? []), item])
    }
    const order = new Map<string, number>(CATEGORY_ORDER.map((key, index) => [key, index]))
    return [...map.entries()]
      .sort((a, b) => (order.get(a[0]) ?? 99) - (order.get(b[0]) ?? 99))
      .slice(0, 8)
  }, [shown, query, bentoIds])

  const { busy, notice, detail, setDetail, onToggle, onAdd, onRemove } = useDiscoverActions(
    sources,
    indexSource,
    load,
  )

  const renderCards = (list: DiscoverItem[]) => (
    <div data-testid="discover-grid" className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {list
        .filter((item) => !bentoIds.has(item.id))
        .map((item) => (
          <DiscoverCard
            key={item.id}
            item={item}
            fluid
            busy={busy === item.id}
            onAdd={onAdd}
            onToggle={onToggle}
            onDetail={setDetail}
          />
        ))}
    </div>
  )

  const browsing = Boolean(query.query || query.category || query.origin || query.tab !== 'all')

  return (
    <div data-testid="discover-page" className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="relative z-20 border-b border-hairline bg-canvas/85 px-4 pb-4 pt-4 backdrop-blur-xl sm:sticky sm:top-0 sm:px-6">
        <div className="mx-auto w-full max-w-6xl">
          <div className="flex items-start gap-1">
            <button
              type="button"
              data-testid="discover-back"
              aria-label={t('a11y.navBack')}
              onClick={() => {
                window.location.hash = '#/chat'
              }}
              className="focus-ring -ml-2 mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-surface-interactive hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <div className="min-w-0 flex-1">
              <PageHeader title={t('discover.title')} subtitle={t('discover.subtitle')} />
            </div>
          </div>
          <div className="mt-4">
            <DiscoverFilters
              query={query}
              counts={counts}
              categories={categories}
              origins={origins}
              total={shown.length}
              onChange={setQuery}
            />
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-6xl px-4 pb-20 pt-7 sm:px-6">
        {notice ? (
          <p
            data-testid="discover-notice"
            role="status"
            className="mb-5 rounded-xl border border-hairline bg-surface/60 px-3 py-2 text-ui-xs text-ink-soft"
          >
            {notice}
          </p>
        ) : null}

        {failed.length ? (
          <p data-testid="discover-failed" className="mb-5 text-ui-xs text-status-warning">
            {t('discover.partial', { areas: '' })}
            {failed.map((one) => (
              <span key={one} data-testid={`discover-fail-${one}`} className="ml-1">
                {t(`discover.fail.${one}`)}
              </span>
            ))}
          </p>
        ) : null}

        {sources === null ? (
          <LoadingRow label={t('discover.loading')} />
        ) : (
          <>
            {!browsing ? (
              <div className="grid items-stretch gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
                {hero ? (
                  <div
                    className="min-w-0"
                    onMouseEnter={() => setPaused(true)}
                    onMouseLeave={() => setPaused(false)}
                    onFocusCapture={() => setPaused(true)}
                    onBlurCapture={() => setPaused(false)}
                  >
                    <div key={hero.id} className="discover-hero-turn">
                      <DiscoverHero
                        item={hero}
                        busy={busy === hero.id}
                        onAdd={onAdd}
                        onToggle={onToggle}
                        onDetail={setDetail}
                      />
                    </div>
                    {featured.length > 1 && !browsingPicks(query) ? (
                      <div
                        data-testid="discover-pick-dots"
                        className="mt-3 flex items-center gap-1.5"
                        role="tablist"
                        aria-label={t('discover.featuredEyebrow')}
                      >
                        {featured.slice(0, 3).map((entry, index) => (
                          <button
                            key={entry.id}
                            type="button"
                            role="tab"
                            aria-selected={index === pick}
                            aria-label={entry.title}
                            data-testid={`discover-pick-dot-${index}`}
                            onClick={() => setPick(index)}
                            className={`h-1.5 rounded-full transition-all motion-safe:duration-300 ${
                              index === pick
                                ? 'w-6 bg-brand'
                                : 'w-1.5 bg-ink-faint/40 hover:bg-ink-faint'
                            }`}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <UsageBench view={sources.usage} />
              </div>
            ) : null}

            {featured.length > 0 && !browsing ? (
              <Shelf
                testId="discover-featured"
                subject="code"
                title={t('discover.featuredEyebrow')}
                lede={t('discover.featuredLede')}
                className="mt-10"
              >
                {featured.map((item) => (
                  <DiscoverCard
                    key={item.id}
                    item={item}
                    busy={busy === item.id}
                    onAdd={onAdd}
                    onToggle={onToggle}
                    onDetail={setDetail}
                  />
                ))}
              </Shelf>
            ) : null}

            {bento.length > 0 && !browsing ? (
              <Shelf
                testId="discover-bento"
                subject="skills"
                title={t('discover.bentoEyebrow')}
                lede={t('discover.bentoLede')}
                className="mt-10"
              >
                {bento.map((item) => (
                  <DiscoverCard
                    key={item.id}
                    item={item}
                    busy={busy === item.id}
                    onAdd={onAdd}
                    onToggle={onToggle}
                    onDetail={setDetail}
                  />
                ))}
              </Shelf>
            ) : null}

            {shown.length === 0 ? (
              <div data-testid="discover-empty" className="mt-16 text-center">
                <Package
                  className="mx-auto h-6 w-6 text-ink-faint"
                  strokeWidth={1.5}
                  aria-hidden="true"
                />
                <p className="mt-3 text-ui-sm text-ink-soft">
                  {failed.length ? t('discover.emptyFailed') : t('discover.empty')}
                </p>
              </div>
            ) : grouped && !browsing ? (
              <DiscoverSections
                groups={grouped}
                busy={busy}
                onAdd={onAdd}
                onToggle={onToggle}
                onDetail={setDetail}
                onSeeAll={(key) => setQuery((q) => ({ ...q, category: key }))}
              />
            ) : (
              renderCards(shown)
            )}

            {sources ? (
              <SourcesRow
                presets={sources.presets}
                sources={sources.home?.sources ?? []}
                busy={Boolean(busy)}
                onAdd={(body) => addMarketSource(body).then(load)}
                onRemove={(id) => removeMarketSource(id).then(load)}
              />
            ) : null}
          </>
        )}
      </div>

      <DiscoverDetail
        item={detail}
        busy={detail ? busy === detail.id : false}
        onClose={() => setDetail(null)}
        onAdd={onAdd}
        onToggle={onToggle}
        onRemove={onRemove}
      />
    </div>
  )
}
