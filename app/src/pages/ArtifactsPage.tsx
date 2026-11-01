/**
 * Ephe — the archive page `/artifacts` (R4/A2): the workbench as a surface.
 *
 * Before this it was a portal pop-up above the chat. Since then it is a page like
 * `/memory`: its own entry in the sidebar, sub-pages in the URL, detail on the
 * right. Two views that differ by a single question — "what did Ephe born?" (the
 * shelf) against "what sits with me?" (the archive of adopted copies). A third
 * view (the chain into the replay) stays out until A3 can fill it; an empty tab
 * is not progress.
 *
 * The header count comes from `/api/artifacts/stats`, so over ALL rows — the list
 * itself is capped at 500, and reporting a number from the first slice as the
 * total was exactly the class of claim we took out of the product in W2.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Search, X } from 'lucide-react'
import { LoadingRow, Skeleton } from '@/components/ui'
import PageHeader from '@/components/shell/PageHeader'
import ArtifactExpiryNotice from '@/components/dashboard/artifacts/expiryNotice'
import ArtifactDetailPane from '@/components/dashboard/artifacts/detail'
import ArtifactShelf, { kindLabel } from '@/components/dashboard/artifacts/shelf'
import { formatBytes, formatDate, formatNumber } from '@/lib/dateLocale'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import {
  artifactExportUrl,
  artifactStats,
  listArtifacts,
  type ArtifactEntry,
  type ArtifactStats,
} from '@/lib/api'

const VIEWS = ['regal', 'ablage'] as const
type View = (typeof VIEWS)[number]

export default function ArtifactsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const params = useParams<{ view: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const turnFilter = searchParams.get('turn') ?? ''
  const sessionFilter = searchParams.get('session') ?? ''
  const view: View = (VIEWS as readonly string[]).includes(params.view ?? '')
    ? (params.view as View)
    : 'regal'

  const [rows, setRows] = useState<ArtifactEntry[] | null>(null)
  const [stats, setStats] = useState<ArtifactStats | null>(null)
  const [query, setQuery] = useState('')
  const heldQuery = useDebouncedValue(query)
  const [kind, setKind] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [failed, setFailed] = useState(false)
  const [failReason, setFailReason] = useState('')

  // Both reads key off this counter: the list and the header count fail together when
  // the server is gone, and a retry that only brought back one of them would leave
  // the reader with a number and no cards.
  const refresh = useCallback(() => setReload((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    setRows(null)
    setFailed(false)
    setFailReason('')
    listArtifacts({
      q: heldQuery,
      kind,
      turn_id: turnFilter || undefined,
      session_id: sessionFilter || undefined,
      limit: 500,
    })
      .then((r) => !cancelled && setRows(r.artifacts))
      .catch((e: unknown) => {
        if (cancelled) return
        setFailed(true)
        setFailReason(e instanceof Error ? e.message : String(e))
        setRows([])
      })
    return () => {
      cancelled = true
    }
  }, [heldQuery, kind, turnFilter, sessionFilter, reload])

  useEffect(() => {
    artifactStats()
      .then(setStats)
      .catch(() => setStats(null))
  }, [reload])

  const shown = useMemo(() => {
    const all = rows ?? []
    // Archive = the cards that hold a copy on the user's disk. The filter is a
    // view, never a second source of data.
    return view === 'ablage' ? all.filter((a) => Boolean(a.adopted_path)) : all
  }, [rows, view])

  const selected = useMemo(() => {
    if (shown.length === 0) return null
    return shown.find((a) => a.id === selectedId) ?? shown[0]
  }, [shown, selectedId])

  const kinds = useMemo(() => {
    // The chip row filters the list. If it counted its kinds from the filtered
    // result, the last kind chip would also make "All" disappear — the only way
    // out left would be the reload button. So: the inventory of the *view*, and
    // the row stays standing as long as a filter is set.
    const counts = new Map<string, number>()
    for (const a of shown) counts.set(a.kind, (counts.get(a.kind) ?? 0) + 1)
    return [...counts.entries()].sort((x, y) => y[1] - x[1])
  }, [shown])

  // A search that matches nothing has its own sentence. "Nothing in the workbench
  // yet" is false in that state — the shelf holds every card the filter hides — and
  // the header number beside it is the store total, so the count has to move into
  // the sentence that explains the empty list.
  const filtered = Boolean(query.trim() || kind || turnFilter || sessionFilter)
  const emptySentence = filtered
    ? stats
      ? t('artifacts.page.noMatchHidden', { count: formatNumber(stats.count, i18n.language) })
      : t('artifacts.page.noMatch')
    : view === 'ablage'
      ? t('artifacts.page.emptyAblage')
      : t('artifacts.page.empty')

  const clearFilters = () => {
    setQuery('')
    setKind('')
    if (turnFilter || sessionFilter) setSearchParams({}, { replace: true })
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto" data-testid="artifacts-page">
      <div className="mx-auto w-full max-w-[1400px] px-6 py-8">
        {/* The page is its own root space without a sidebar — like /memory.
            Without this way out, the browser back button would be the only exit,
            and on the desktop there is none. */}
        <button
          type="button"
          onClick={() => navigate('/chat')}
          data-testid="artifacts-back"
          className="mb-4 -ml-1.5 inline-flex min-h-7 items-center gap-1.5 rounded-md px-1.5 text-ui-xs text-ink-faint transition-colors hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          {t('artifacts.page.back')}
        </button>

        <PageHeader title={t('artifacts.page.title')} subtitle={t('artifacts.page.subtitle')} />

        <nav aria-label={t('artifacts.page.title')} className="mt-6 mb-4 flex flex-wrap gap-1">
          {VIEWS.map((key) => {
            const active = key === view
            return (
              <a
                key={key}
                href={key === 'regal' ? '#/artifacts' : `#/artifacts/${key}`}
                aria-current={active ? 'page' : undefined}
                title={key === 'ablage' ? t('artifacts.page.ablageHint') : undefined}
                className={`inline-flex min-h-7 items-center rounded-lg px-3 py-2 text-ui-xs font-medium transition-colors max-lg:min-h-11 focus-ring ${
                  active
                    ? 'bg-brand/20 text-brand-deep border border-brand/20'
                    : 'border border-control text-ink-faint hover:bg-surface hover:text-foreground'
                }`}
              >
                {t(`artifacts.page.view.${key}`)}
                {key === 'ablage' && rows && (
                  <span className="ml-1.5 text-ink-faint">
                    {rows.filter((a) => Boolean(a.adopted_path)).length}
                  </span>
                )}
              </a>
            )
          })}
        </nav>

        {/* The tab is called "Adopted" and does not say what that is. The page
            subtitle explains it once, globally — someone standing at the tab does
            not read it up there anymore. So the sentence goes where it explains
            something, and only there. */}
        {view === 'ablage' && (
          <p
            className="-mt-2 mb-4 px-1 text-ui-xs text-ink-faint"
            data-testid="artifacts-ablage-hint"
          >
            {t('artifacts.page.ablageHint')}
          </p>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-56 flex-1">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('artifacts.searchPlaceholder')}
              aria-label={t('artifacts.searchPlaceholder')}
              className="w-full rounded-lg border border-control bg-surface py-2 pl-8 pr-8 text-ui-sm text-foreground/80 placeholder:text-ink-faint focus-ring pointer-coarse:min-h-11 pointer-coarse:text-ui-input"
            />
            {/* The field sends a request per keystroke, so a mistyped word needs a
                way out shorter than backspace. The button fills the field height:
                the input itself is the smaller touch target here. */}
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                aria-label={t('artifacts.searchClear')}
                title={t('artifacts.searchClear')}
                data-testid="artifacts-search-clear"
                className="absolute inset-y-0 right-0 flex items-center rounded-r-lg px-2 text-ink-faint transition-colors hover:text-foreground focus-ring max-lg:px-3"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
          {stats && (
            <p className="text-ui-xs text-ink-faint" data-testid="artifacts-stats">
              {t('artifacts.page.stats', {
                count: formatNumber(stats.count, i18n.language),
                bytes: formatBytes(stats.bytes, i18n.language),
              })}
              {stats.expiring_count > 0 && (
                <span className="text-status-warning">
                  {' · '}
                  {t('artifacts.page.expiring', {
                    count: stats.expiring_count,
                    when: formatDate(stats.next_expiry, i18n.language),
                  })}
                </span>
              )}
            </p>
          )}
          <a
            href={artifactExportUrl({ q: query, kind })}
            download
            className="inline-flex min-h-7 items-center rounded-lg border border-control px-3 py-2 text-ui-xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
          >
            {t('artifacts.exportAll')}
          </a>
        </div>

        {(kinds.length > 1 || kind) && (
          <div
            className="mb-3 flex flex-wrap gap-1"
            role="group"
            aria-label={t('artifacts.filterGroup')}
            data-testid="artifacts-kind-filter"
          >
            <button
              onClick={() => setKind('')}
              aria-pressed={kind === ''}
              className={`inline-flex min-h-7 items-center rounded-md px-2 py-1 text-ui-xs font-medium transition-colors max-lg:min-h-11 focus-ring ${
                kind === ''
                  ? 'bg-brand/20 text-brand-deep border border-brand/20'
                  : 'text-ink-soft border border-control hover:bg-surface hover:text-foreground/80'
              }`}
            >
              {t('artifacts.filterAll')}
            </button>
            {/* The number belongs on the group heading, not on the switch: the
                heading counts what stands under it, the switch counts the list it
                has just filtered itself — and it sat 40 px above that. */}
            {kinds.map(([k]) => (
              <button
                key={k}
                onClick={() => setKind(kind === k ? '' : k)}
                aria-pressed={kind === k}
                className={`inline-flex min-h-7 items-center rounded-md px-2 py-1 text-ui-xs font-medium transition-colors max-lg:min-h-11 focus-ring ${
                  kind === k
                    ? 'bg-brand/20 text-brand-deep border border-brand/20'
                    : 'text-ink-soft border border-control hover:bg-surface hover:text-foreground/80'
                }`}
              >
                {kindLabel(k, t)}
              </button>
            ))}
          </div>
        )}

        {(turnFilter || sessionFilter) && (
          <div className="mb-3 flex flex-wrap items-center gap-2 text-ui-xs">
            <span
              className="rounded-md border border-brand/20 bg-brand/20 px-2 py-1 text-brand-deep"
              data-testid="artifacts-scope"
            >
              {turnFilter
                ? t('artifacts.page.scopeTurn', { turn: turnFilter })
                : t('artifacts.page.scopeSession', { session: sessionFilter.slice(0, 8) })}
            </span>
            <button
              onClick={() => setSearchParams({}, { replace: true })}
              className="inline-flex min-h-7 items-center rounded-md px-1 text-ink-soft transition-colors hover:text-foreground/80 max-lg:min-h-11 focus-ring"
              data-testid="artifacts-scope-clear"
            >
              {t('artifacts.page.scopeClear')}
            </button>
          </div>
        )}

        <div className="mb-4">
          <ArtifactExpiryNotice active onAnswered={refresh} />
        </div>

        {rows === null ? (
          <div className="grid min-h-[26rem] gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
            <div className="space-y-2">
              <LoadingRow label={t('artifacts.page.loading')} className="px-1" />
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex min-h-9 items-center gap-2 px-2">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-3 flex-1" />
                  <Skeleton className="h-3 w-10" />
                </div>
              ))}
            </div>
            <Skeleton className="h-full min-h-[18rem] rounded-lg" />
          </div>
        ) : failed ? (
          <div
            role="alert"
            data-testid="artifacts-error"
            className="flex flex-col items-center gap-2 py-10 text-center text-ui-xs text-status-warn"
          >
            <p>{t('artifacts.page.failed')}</p>
            {failReason && (
              <p
                data-testid="artifacts-error-reason"
                className="max-w-[52ch] break-words font-mono text-ui-2xs text-ink-faint"
              >
                {failReason}
              </p>
            )}
            <button
              type="button"
              onClick={refresh}
              data-testid="artifacts-retry"
              className="inline-flex min-h-7 items-center rounded-lg border border-control px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-surface max-lg:min-h-11 focus-ring"
            >
              {t('agentPanel.retry')}
            </button>
          </div>
        ) : (
          <div className="grid min-h-[26rem] gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
            <div className="min-w-0">
              {filtered && shown.length === 0 ? (
                <div className="py-10 text-center" data-testid="artifacts-nomatch">
                  <p className="px-2 text-ui-xs text-ink-faint">{emptySentence}</p>
                  <button
                    type="button"
                    onClick={clearFilters}
                    data-testid="artifacts-clear-filters"
                    className="mt-3 min-h-7 max-lg:min-h-11 rounded-lg border border-control px-3 text-ui-xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
                  >
                    {t('artifacts.page.scopeClear')}
                  </button>
                </div>
              ) : (
                <ArtifactShelf
                  items={shown}
                  selectedId={selected?.id ?? null}
                  onSelect={setSelectedId}
                  onChanged={refresh}
                  leerText={emptySentence}
                />
              )}
            </div>
            <div className="min-w-0 lg:sticky lg:top-6 lg:h-[calc(100vh-8rem)]">
              {selected ? (
                <ArtifactDetailPane key={selected.id} id={selected.id} onChanged={refresh} />
              ) : filtered ? (
                <p className="flex h-full min-h-[18rem] items-center justify-center rounded-lg border border-dashed border-hairline p-6 text-center text-ui-xs text-ink-faint">
                  {t('artifacts.page.noMatch')}
                </p>
              ) : shown.length > 0 ? (
                <p className="flex h-full min-h-[18rem] items-center justify-center rounded-lg border border-dashed border-hairline p-6 text-center text-ui-xs text-ink-faint">
                  {t('artifacts.page.detailHint')}
                </p>
              ) : (
                <p className="flex h-full min-h-[18rem] items-center justify-center rounded-lg border border-dashed border-hairline p-6 text-center text-ui-xs text-ink-faint">
                  {t('artifacts.page.detailEmpty')}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
