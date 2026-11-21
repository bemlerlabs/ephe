'use client'

import { useTranslation } from 'react-i18next'
import { Archive, Search, Database } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import { useMemoryActions, useMemoryFacts } from '@/lib/useMemoryFacts'
import { MemoryRowCard, type MemoryRow, type WriteKind } from './memoryRowCard'
import { MemoryStoreUnavailable, trashEmptySentence } from './memoryStoreState'

/**
 * M8 (memory graph panel): the agent's facts as a list — semantic search, single
 * deletion, inline editing.
 *
 *  * R40: a search hit carries its real document id — before this the list
 *    invented indexes/scores that produced a 404 at DELETE /api/memory/{id}.
 *  * D5: the ways the store (wave D) can actually write are also the ones the UI
 *    offers. A correction is its own action, not "edit": it supersedes the old
 *    fact, which then stays visible as history. And a deleted fact is not gone
 *    from the archive — it lies in the trash, where it can be seen and restored.
 *    The row and its chips live in `memoryRowCard.tsx`, because what an entry
 *    *is* and what one *does* with it are two responsibilities.
 *
 * The provider pill belongs in the surface: two brains behind one API are only
 * trustworthy when the interface can say which one is speaking right now.
 */

export function MemoryTab() {
  const { t } = useTranslation()
  // R2-A: the same data path as the "What remains" page. Before, the tab had its
  // own chain — two opinions about search, trash and stats.
  const facts = useMemoryFacts(100)
  const actions = useMemoryActions(facts.reload)
  const { rows, stats, state, reason } = facts
  const trash = facts.view === 'trash'
  const q = facts.query

  const setQ = (next: string) => facts.setQuery(next)
  const setTrash = (on: boolean) => facts.setView(on ? 'trash' : 'live')

  const commit = (row: MemoryRow, kind: WriteKind) => void actions.commit(row, kind)
  const remove = (row: MemoryRow) => void actions.remove(row)
  const restore = (row: MemoryRow) => void actions.restore(row)

  const closeEdit = () => actions.closeEdit()

  const deletedCount = stats?.deleted ?? 0

  return (
    <div className="flex-1 min-h-0 flex flex-col" data-testid="memory-view">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-hairline shrink-0">
        <Search className="h-3.5 w-3.5 text-ink-faint shrink-0" aria-hidden="true" />
        <input
          data-testid="memory-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('agentPanel.memorySearch')}
          aria-label={t('agentPanel.memorySearch')}
          className="flex-1 min-w-0 bg-transparent text-ui-xs text-foreground placeholder:text-ink-faint outline-none"
        />
        {stats?.provider && (
          <span
            data-testid="memory-provider"
            title={t('agentPanel.memoryProviderHint', { provider: stats.provider })}
            className="shrink-0 rounded-full border border-hairline px-1.5 text-ui-2xs text-ink-faint"
          >
            {stats.provider}
          </span>
        )}
        {(deletedCount > 0 || trash) && (
          <button
            type="button"
            data-testid="memory-trash-toggle"
            aria-pressed={trash}
            title={t('agentPanel.memoryTrash')}
            onClick={() => setTrash(!trash)}
            className={`shrink-0 flex items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-2xs ${
              trash ? 'bg-status-info/15 text-foreground' : 'text-ink-faint hover:bg-surface'
            }`}
          >
            <Archive className="h-3 w-3" aria-hidden="true" />
            <span className="tabular-nums">{deletedCount}</span>
            <span className="sr-only">{t('agentPanel.memoryTrash')}</span>
          </button>
        )}
        <span
          data-testid="memory-count"
          className="text-ui-xs text-ink-faint shrink-0 tabular-nums"
        >
          {state === 'unreachable' ? '—' : rows.length}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-1.5">
        {state === 'loading' ? (
          <LoadingRow label={t('agentPanel.memoryLoading')} className="p-2" />
        ) : state === 'unreachable' ? (
          <MemoryStoreUnavailable reason={reason} onRetry={facts.reload} />
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center">
            <Database className="h-10 w-10 opacity-40" />
            <p>
              {trash
                ? q.trim()
                  ? t('agentPanel.memoryTrashNoMatch')
                  : trashEmptySentence(
                      t('agentPanel.memoryTrashEmpty'),
                      facts.restoreSupported,
                      facts.restoreDetail,
                    )
                : t('agentPanel.memoryEmpty')}
            </p>
          </div>
        ) : (
          rows.map((row, i) => (
            <MemoryRowCard
              key={row.id}
              row={row}
              index={i}
              trash={trash}
              restoreSupported={facts.restoreSupported}
              sources={stats?.sources}
              isEditing={actions.editingId === row.id}
              editLocked={actions.editingId !== null}
              draft={actions.draft}
              saving={actions.saving}
              onDraft={actions.setDraft}
              onStartEdit={() => actions.startEdit(row)}
              onCancelEdit={closeEdit}
              onCommit={(kind) => commit(row, kind)}
              onRemove={() => remove(row)}
              onRestore={() => restore(row)}
            />
          ))
        )}
      </div>
    </div>
  )
}
