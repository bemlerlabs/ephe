'use client'

/**
 * R2-A — "What remains": the agent's own page for what it has stored.
 *
 * Before this it was a strip to the right of the chat: one list, one search, one
 * trash switch. The same inventory sat a second time in the settings, there
 * without correction and without history. This page is the one place; the panel
 * tab stays the quick look at it from inside the chat.
 *
 * Four sub-pages, and each shows only what the API really delivers:
 *   inventory · corrections · trash · brains
 * "Brains" is the diagnosis page: which of the two stores answers and why,
 * whether its vector and its lexical leg hold, and what a migration would take
 * with it — first as a dry run with numbers, only then as a button.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Search } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import SearchInput from '@/components/shell/SearchInput'
import { MemoryBrainsPanel } from '@/components/dashboard/agent/memoryBrainsPanel'
import { MemoryRowCard } from '@/components/dashboard/agent/memoryRowCard'
import {
  MemoryStoreUnavailable,
  trashEmptySentence,
} from '@/components/dashboard/agent/memoryStoreState'
import {
  memoryCountLine,
  memoryIsCorrection,
  memoryTypeOf,
  useMemoryActions,
  useMemoryFacts,
  type MemoryView,
} from '@/lib/useMemoryFacts'

const VIEWS = ['bestand', 'korrekturen', 'papierkorb', 'gehirne'] as const
type ViewKey = (typeof VIEWS)[number]

const VIEW_DATA: Record<ViewKey, MemoryView> = {
  bestand: 'live',
  korrekturen: 'live',
  papierkorb: 'trash',
  gehirne: 'live',
}

export default function MemoryPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const params = useParams<{ view?: string }>()
  const view: ViewKey = (VIEWS as readonly string[]).includes(params.view ?? '')
    ? (params.view as ViewKey)
    : 'bestand'
  const facts = useMemoryFacts(200)
  const actions = useMemoryActions(facts.reload)
  const wanted = VIEW_DATA[view]
  useEffect(() => {
    // A link to /memory/papierkorb must load the trash itself, not only a click on
    // it: the data path follows the URL, not the click history.
    if (facts.view !== wanted) facts.setView(wanted)
  }, [wanted, facts])
  const [typeFilter, setTypeFilter] = useState('')

  const types = useMemo(() => {
    const seen = new Set<string>()
    for (const row of facts.rows) {
      const kind = memoryTypeOf(row)
      if (kind) seen.add(kind)
    }
    return [...seen].sort()
  }, [facts.rows])

  const rows = useMemo(() => {
    if (view !== 'korrekturen') return facts.rows
    return facts.rows.filter(memoryIsCorrection)
  }, [facts.rows, view])

  // The count and the list below have to answer for the same set.
  const visible = rows.filter((r) => !typeFilter || memoryTypeOf(r) === typeFilter)
  const searching = facts.query.trim() !== ''

  const stats = facts.stats
  const corrected = useMemo(() => facts.rows.filter(memoryIsCorrection).length, [facts.rows])

  return (
    <div className="h-dvh overflow-y-auto" data-testid="memory-page">
      <div className="mx-auto w-full max-w-3xl px-6 py-8">
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="mb-4 inline-flex items-center gap-1.5 text-ui-xs text-ink-faint transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 pointer-coarse:min-h-11"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          {t('memory.back')}
        </button>

        <PageHeader title={t('memory.title')} subtitle={t('memory.subtitle')} />

        {/* These are sub-pages with their own address, not tabs: a tab list
            without a panel relationship would be the very semantics gap that was
            only just closed in the agent panel. */}
        <nav aria-label={t('memory.title')} className="mb-6 flex flex-wrap gap-1">
          {VIEWS.map((key) => {
            const active = key === view
            return (
              <a
                key={key}
                href={key === 'bestand' ? '#/memory' : `#/memory/${key}`}
                aria-current={active ? 'page' : undefined}
                className={`rounded-lg px-3 py-2 text-ui-xs font-medium transition-colors min-h-7 inline-flex items-center max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${
                  active
                    ? 'bg-brand/20 text-brand-deep border border-brand/20'
                    : 'border border-hairline text-ink-faint hover:bg-surface hover:text-foreground'
                }`}
              >
                {t(`memory.view.${key}`)}
              </a>
            )
          })}
        </nav>

        {view === 'gehirne' ? (
          <MemoryBrainsPanel stats={stats} onReload={facts.reload} />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="min-w-56 flex-1">
                <SearchInput
                  value={facts.query}
                  onChange={facts.setQuery}
                  placeholder={t('memory.search')}
                  label={t('memory.search')}
                  testid="memory-page-search"
                />
              </div>
              {view === 'bestand' && types.length > 0 && (
                <div
                  className="flex items-center gap-1.5"
                  role="group"
                  aria-label={t('memory.filter')}
                >
                  {types.map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      aria-pressed={typeFilter === kind}
                      onClick={() => setTypeFilter((v) => (v === kind ? '' : kind))}
                      className={`rounded-md px-2 py-1 text-ui-xs font-medium transition-colors max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${
                        typeFilter === kind
                          ? 'bg-brand/20 text-brand-deep border border-brand/20'
                          : 'border border-hairline text-ink-faint hover:bg-surface hover:text-foreground'
                      }`}
                    >
                      {kind}
                    </button>
                  ))}
                </div>
              )}
              <span
                className={`${searching ? '' : 'font-mono '}text-ui-xs text-ink-faint`}
                data-testid="memory-page-count"
              >
                {facts.state === 'unreachable'
                  ? '—'
                  : memoryCountLine(facts.query, visible.length, facts.stats, t, i18n.language)}
              </span>
            </div>

            {facts.pending || facts.state === 'loading' ? (
              <LoadingRow label={t('memory.loading')} className="py-8" />
            ) : facts.state === 'unreachable' ? (
              <MemoryStoreUnavailable reason={facts.reason} onRetry={facts.reload} />
            ) : rows.length === 0 ? (
              <p
                data-testid="memory-page-empty"
                className="py-10 text-center text-ui-xs text-ink-faint"
              >
                {searching
                  ? t('memory.noMatch')
                  : view === 'papierkorb'
                    ? trashEmptySentence(
                        t('memory.emptyTrash'),
                        facts.restoreSupported,
                        facts.restoreDetail,
                      )
                    : view === 'korrekturen'
                      ? t('memory.emptyCorrections')
                      : t('memory.empty')}
              </p>
            ) : (
              <div className="space-y-1.5">
                {visible.map((row, i) => (
                  <MemoryRowCard
                    key={row.id}
                    row={row}
                    index={i}
                    trash={view === 'papierkorb'}
                    restoreSupported={facts.restoreSupported}
                    sources={facts.stats?.sources}
                    isEditing={actions.editingId === row.id}
                    editLocked={actions.editingId !== null}
                    draft={actions.draft}
                    saving={actions.saving}
                    onDraft={actions.setDraft}
                    onStartEdit={() => actions.startEdit(row)}
                    onCancelEdit={actions.closeEdit}
                    onCommit={(kind) => void actions.commit(row, kind)}
                    onRemove={() => void actions.remove(row)}
                    onRestore={() => void actions.restore(row)}
                  />
                ))}
              </div>
            )}

            {view === 'bestand' && corrected > 0 && (
              <p className="pt-2 text-ui-xs text-ink-faint">
                <Search className="mr-1 inline h-3 w-3" aria-hidden="true" />
                {t('memory.correctedCount', { count: corrected })}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
