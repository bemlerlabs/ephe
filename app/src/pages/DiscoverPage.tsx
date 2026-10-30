/**
 * `/discover` — the shelf Ephe's own abilities are browsed from, one page for
 * skills, connectors and add-ons. The bench on the right is the product's claim
 * made visible: every bar is a call count this machine wrote to its own audit log.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PageHeader from '@/components/shell/PageHeader'
import { EpheMark } from '@/components/shell/EpheMark'
import { LoadingRow } from '@/components/ui'
import { DiscoverCard } from '@/components/discover/DiscoverCard'
import { DiscoverDetail } from '@/components/discover/DiscoverDetail'
import { DiscoverHero } from '@/components/discover/DiscoverHero'
import { DiscoverFilters } from '@/components/discover/DiscoverFilters'
import { SourcesRow } from '@/components/discover/SourcesRow'
import { useIntentSearch } from '@/components/discover/useIntentSearch'
import { UsageBench } from '@/components/discover/UsageBench'
import {
  bentoOf,
  buildItems,
  countByTab,
  facetValues,
  filterItems,
  heroOf,
  rankByIntent,
  specName,
  type DiscoverItem,
  type DiscoverQuery,
  type DiscoverSources,
} from '@/components/discover/discoverModel'
import {
  addMarketSource,
  declareMcpEnv,
  disableSkill,
  enableSkill,
  getDiscoverBootstrap,
  getMcpSettings,
  installMarketPlan,
  planMarketInstall,
  probeMcpHealth,
  putMcpSettings,
  removeMarketSource,
  setPluginEnabled,
} from '@/lib/api'

/** The bootstrap frame carries everything but the slow health probes. */
async function loadSources(): Promise<{ sources: DiscoverSources; failed: string[] }> {
  const [boot, mcp, health] = await Promise.all([
    getDiscoverBootstrap().catch(() => null),
    getMcpSettings().catch(() => null),
    probeMcpHealth().catch(() => null),
  ])
  const failed: string[] = []
  const note = (key: string, ok: boolean) => {
    if (!ok) failed.push(key)
  }
  note('skills', boot !== null)
  note('connectors', boot !== null)
  note('addons', boot !== null)
  return {
    sources: {
      skills: boot?.skills ?? [],
      mcp,
      health: health?.servers ?? [],
      catalog: boot?.catalog ?? [],
      registry: boot?.curated ?? [],
      registryCount: boot?.registry_count ?? 0,
      presets: boot?.presets ?? [],
      home: boot?.home ?? null,
      index: boot?.index ?? null,
      installed: boot?.installed ?? [],
      usage: boot?.usage ?? null,
    },
    failed,
  }
}

/** A publisher launch line becomes the config spec the connector rides on. */
function registrySpec(hint: string): string | null {
  const match = hint.match(
    /^(npx|uvx|uv run|python3?|node)\s+(.+?)(?:\s+\((stdio|http|streamable-http)\))?$/,
  )
  if (!match || !match[1] || !match[2]) return null
  return `stdio:${match[1]} ${match[2].trim()}`
}

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
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [detail, setDetail] = useState<DiscoverItem | null>(null)

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
  const categories = useMemo(() => facetValues(items, (one) => one.categories), [items])
  const origins = useMemo(() => facetValues(items, (one) => [one.origin]), [items])
  const hero = useMemo(() => heroOf(shown), [shown])
  const bento = useMemo(() => bentoOf(items), [items])
  const bentoIds = useMemo(() => new Set(bento.map((one) => one.id)), [bento])

  /** On the quiet default view the shelf reads as sections, one per category. */
  const grouped = useMemo(() => {
    if (query.tab !== 'all' || query.query || query.category) return null
    const map = new Map<string, DiscoverItem[]>()
    for (const item of shown) {
      if (bentoIds.has(item.id)) continue
      const key = item.categories[0] ?? 'other'
      map.set(key, [...(map.get(key) ?? []), item])
    }
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 8)
  }, [shown, query, bentoIds])

  const run = async (item: DiscoverItem, action: () => Promise<unknown>, done: string) => {
    setBusy(item.id)
    setNotice('')
    try {
      await action()
      setNotice(t('discover.did', { name: item.title, what: t(done) }))
      await load()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t('discover.didNot', { name: item.title }))
    } finally {
      setBusy('')
    }
  }

  /** A skill switches through its own pair of routes; everything else through plugins. */
  const onToggle = (item: DiscoverItem, next: boolean) => {
    if (item.kind === 'skill') {
      return run(
        item,
        () => (next ? enableSkill(item.name) : disableSkill(item.name)),
        next ? 'discover.stateOn' : 'discover.stateOff',
      )
    }
    return run(
      item,
      () => setPluginEnabled(item.name, next),
      next ? 'discover.stateOn' : 'discover.stateOff',
    )
  }

  const onAdd = (item: DiscoverItem) => {
    if (item.kind === 'connector') {
      const spec = item.spec ?? (item.installHint ? registrySpec(item.installHint) : null)
      if (!spec) {
        setNotice(t('discover.didNot', { name: item.title }))
        return undefined
      }
      const current = sources?.mcp?.servers ?? []
      return run(
        item,
        async () => {
          await putMcpSettings(current.includes(spec) ? current : [...current, spec])
          const names = (item.requiredEnv ?? []).map((one) => one.name)
          if (names.length) await declareMcpEnv(spec, names)
        },
        'discover.added',
      )
    }
    if (item.kind === 'skill') {
      return run(item, () => enableSkill(item.name), 'discover.added')
    }
    return run(
      item,
      async () => {
        const plan = await planMarketInstall(indexSource, item.name, item.version ?? '')
        if (plan.status === 'refused')
          throw new Error(plan.error || plan.code || t('discover.refused'))
        return installMarketPlan(plan)
      },
      'discover.added',
    )
  }

  const onRemove = (item: DiscoverItem) => {
    if (item.kind === 'connector') {
      const current = sources?.mcp?.servers ?? []
      const next = item.spec ? current.filter((one) => specName(one) !== item.name) : current
      return run(item, () => putMcpSettings(next), 'discover.removed')
    }
    return run(item, () => setPluginEnabled(item.name, false), 'discover.removed')
  }

  const renderCards = (list: DiscoverItem[]) => (
    <div data-testid="discover-grid" className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {list
        .filter((item) => !bentoIds.has(item.id))
        .map((item) => (
          <DiscoverCard
            key={item.id}
            item={item}
            hero={item === hero}
            busy={busy === item.id}
            onAdd={onAdd}
            onToggle={onToggle}
            onRemove={onRemove}
            onDetail={setDetail}
          />
        ))}
    </div>
  )

  return (
    <div data-testid="discover-page" className="flex h-full min-h-0 flex-col overflow-y-auto">
      <PageHeader title={t('discover.title')} subtitle={t('discover.subtitle')} />

      <div className="mx-auto w-full max-w-6xl px-4 pb-10 sm:px-6">
        <section
          data-testid="discover-band"
          className="relative -mt-2 overflow-hidden rounded-3xl border border-hairline bg-surface/60 px-5 py-6 sm:px-8 sm:py-9"
        >
          <span
            aria-hidden="true"
            className="forest-glow pointer-events-none absolute inset-0 opacity-70"
          />
          <div className="relative flex items-start gap-4">
            <EpheMark size="2.75rem" testId="discover-mark" className="mt-1 shrink-0" />
            <div className="min-w-0">
              <p className="font-mono text-ui-xs uppercase tracking-[0.18em] text-brand">
                {t('discover.eyebrow')}
              </p>
              <h2 className="font-display mt-1.5 text-2xl leading-tight text-foreground sm:text-3xl">
                {t('discover.headline')}
              </h2>
              <p className="mt-2 max-w-prose text-ui-sm text-ink-soft">{t('discover.lede')}</p>
            </div>
          </div>
        </section>

        {bento.length ? (
          <section data-testid="discover-bento" className="mt-6">
            <p className="font-mono text-ui-xs uppercase tracking-[0.18em] text-brand">
              {t('discover.bentoEyebrow')}
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {bento.map((item) => (
                <DiscoverCard
                  key={item.id}
                  item={item}
                  busy={busy === item.id}
                  onAdd={onAdd}
                  onToggle={onToggle}
                  onRemove={onRemove}
                  onDetail={setDetail}
                />
              ))}
            </div>
          </section>
        ) : null}

        {notice ? (
          <p
            data-testid="discover-notice"
            role="status"
            className="mt-4 rounded-xl border border-hairline bg-surface-raised/60 px-3 py-2 text-ui-sm text-ink-soft"
          >
            {notice}
          </p>
        ) : null}

        {failed.length ? (
          <p data-testid="discover-failed" className="mt-4 text-ui-xs text-status-warning">
            {t('discover.partial', { areas: '' })}
            {failed.map((one) => (
              <span key={one} data-testid={`discover-fail-${one}`} className="ml-1">
                {t(`discover.fail.${one}`)}
              </span>
            ))}
          </p>
        ) : null}

        {hero && !query.query ? (
          <DiscoverHero
            item={hero}
            busy={busy === hero.id}
            onAdd={onAdd}
            onToggle={onToggle}
            onDetail={setDetail}
          />
        ) : null}

        <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
            <DiscoverFilters
              query={query}
              counts={counts}
              categories={categories}
              origins={origins}
              total={shown.length}
              onChange={setQuery}
            />

            {sources ? (
              <SourcesRow
                presets={sources.presets}
                sources={sources.home?.sources ?? []}
                busy={Boolean(busy)}
                onAdd={(body) => addMarketSource(body).then(load)}
                onRemove={(id) => removeMarketSource(id).then(load)}
              />
            ) : null}

            {sources === null ? (
              <LoadingRow label={t('discover.loading')} />
            ) : shown.length === 0 ? (
              <p data-testid="discover-empty" className="mt-8 text-center text-ui-sm text-ink-soft">
                {failed.length ? t('discover.emptyFailed') : t('discover.empty')}
              </p>
            ) : grouped ? (
              <div data-testid="discover-sections" className="mt-5 space-y-7">
                {grouped.map(([key, list]) => (
                  <section key={key} data-testid={`discover-section-${key}`}>
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="font-display text-lg text-foreground">
                        {t(`discover.category.${key}`, { defaultValue: key })}
                      </h3>
                      <button
                        type="button"
                        data-testid={`discover-see-all-${key}`}
                        onClick={() => setQuery((q) => ({ ...q, category: key }))}
                        className="text-ui-xs text-brand hover:underline"
                      >
                        {t('discover.seeAll', { count: list.length })}
                      </button>
                    </div>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {list.slice(0, 6).map((item) => (
                        <DiscoverCard
                          key={item.id}
                          item={item}
                          busy={busy === item.id}
                          onAdd={onAdd}
                          onToggle={onToggle}
                          onRemove={onRemove}
                          onDetail={setDetail}
                        />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              renderCards(shown)
            )}
          </div>

          <UsageBench view={sources?.usage ?? null} />
        </div>
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
