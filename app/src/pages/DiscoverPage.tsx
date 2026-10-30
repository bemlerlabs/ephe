/**
 * `/discover` — the shelf Ephe's own abilities are browsed from, one page for
 * skills, connectors and add-ons. The bench on the right is the product's claim
 * made visible: every bar is a call count this machine wrote to its own audit log.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PageHeader from '@/components/shell/PageHeader'
import { EpheMark } from '@/components/shell/EpheMark'
import { DiscoverCard } from '@/components/discover/DiscoverCard'
import { DiscoverFilters } from '@/components/discover/DiscoverFilters'
import { UsageBench } from '@/components/discover/UsageBench'
import {
  buildItems,
  countByTab,
  facetValues,
  filterItems,
  heroOf,
  specName,
  type DiscoverItem,
  type DiscoverQuery,
  type DiscoverSources,
} from '@/components/discover/discoverModel'
import {
  disableSkill,
  enableSkill,
  getMarketHome,
  getMarketIndex,
  getMarketInstalled,
  getMcpCatalog,
  getMcpSettings,
  getToolUsage,
  installMarketPlan,
  listSkills,
  planMarketInstall,
  probeMcpHealth,
  putMcpSettings,
  setPluginEnabled,
  type MarketIndexResponse,
} from '@/lib/api'

/** `getMcpCatalog` and `probeMcpHealth` answer for the connector tabs. */
async function loadSources(): Promise<{ sources: DiscoverSources; failed: string[] }> {
  const [skills, mcp, health, catalog, home, index, installed, usage] = await Promise.all([
    listSkills().catch(() => null),
    getMcpSettings().catch(() => null),
    probeMcpHealth().catch(() => null),
    getMcpCatalog().catch(() => null),
    getMarketHome().catch(() => null),
    getMarketIndex().catch(() => null),
    getMarketInstalled().catch(() => null),
    getToolUsage().catch(() => null),
  ])
  const failed: string[] = []
  const note = (key: string, ok: boolean) => {
    if (!ok) failed.push(key)
  }
  note('skills', skills !== null)
  note('connectors', health !== null && catalog !== null)
  note('addons', (index as MarketIndexResponse | null)?.status === 'ok')
  return {
    sources: {
      skills: skills?.skills ?? [],
      mcp,
      health: health?.servers ?? [],
      catalog: catalog?.entries ?? [],
      home,
      index: index?.index ?? null,
      installed: installed?.plugins ?? [],
      usage,
    },
    failed,
  }
}

export default function DiscoverPage() {
  const { t } = useTranslation()
  const [sources, setSources] = useState<DiscoverSources | null>(null)
  const [indexSource, setIndexSource] = useState<string>('')
  const [failed, setFailed] = useState<string[]>([])
  const [query, setQuery] = useState<DiscoverQuery>({ tab: 'all', query: '', category: null, origin: null })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

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
  const shown = useMemo(() => filterItems(items, query), [items, query])
  const counts = useMemo(() => countByTab(items), [items])
  const categories = useMemo(() => facetValues(items, (one) => one.categories), [items])
  const origins = useMemo(() => facetValues(items, (one) => [one.origin]), [items])
  const hero = useMemo(() => heroOf(shown), [shown])

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
    return run(item, () => setPluginEnabled(item.name, next), next ? 'discover.stateOn' : 'discover.stateOff')
  }

  const onAdd = (item: DiscoverItem) => {
    if (item.kind === 'connector') {
      const spec = item.spec
      if (!spec) return undefined
      const current = sources?.mcp?.servers ?? []
      return run(
        item,
        () => putMcpSettings(current.includes(spec) ? current : [...current, spec]),
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
        if (plan.status === 'refused') throw new Error(plan.error || plan.code || t('discover.refused'))
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

  return (
    <div data-testid="discover-page" className="flex h-full min-h-0 flex-col overflow-y-auto">
      <PageHeader title={t('discover.title')} subtitle={t('discover.subtitle')} />

      <div className="mx-auto w-full max-w-6xl px-4 pb-10 sm:px-6">
        <section
          data-testid="discover-band"
          className="relative -mt-2 overflow-hidden rounded-3xl border border-hairline bg-surface/60 px-5 py-6 sm:px-8 sm:py-9"
        >
          <span aria-hidden="true" className="forest-glow pointer-events-none absolute inset-0 opacity-70" />
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

            {shown.length === 0 ? (
              <p data-testid="discover-empty" className="mt-8 text-center text-ui-sm text-ink-soft">
                {sources ? t('discover.empty') : t('discover.loading')}
              </p>
            ) : (
              <div data-testid="discover-grid" className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {shown.map((item) => (
                  <DiscoverCard
                    key={item.id}
                    item={item}
                    hero={item === hero}
                    busy={busy === item.id}
                    onAdd={onAdd}
                    onToggle={onToggle}
                    onRemove={onRemove}
                  />
                ))}
              </div>
            )}
          </div>

          <UsageBench view={sources?.usage ?? null} />
        </div>
      </div>
    </div>
  )
}
