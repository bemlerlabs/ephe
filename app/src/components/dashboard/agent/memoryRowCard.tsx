'use client'

import { useTranslation } from 'react-i18next'
import { Check, Pencil, RotateCcw, X } from 'lucide-react'
import { formatDuration } from '@/lib/duration'

/**
 * D5: a memory row shows what the store knows about the fact.
 *
 * Split out of `tabsMemory.tsx` because the list has two things to say and both
 * belong here: the way it was written (type, tags, supersession) and its state
 * (leading, superseded, in the trash). The data comes from the columns wave D
 * maintains in the archive — they are missing from the index, and then the chip
 * field stays empty rather than guessing a riddle.
 */
export interface MemoryRow {
  id: string
  text: string
  metadata: Record<string, unknown>
}

/** source → label key. Unknown sources fall back to the backend vocabulary. */
const SOURCE_KEYS: Record<string, string> = {
  auto_memory: 'agentPanel.memorySourceAuto',
  compaction: 'agentPanel.memorySourceCompaction',
}

/**
 * The label for a row's origin.
 *
 * Wave 10: the vocabulary is the backend's (`stats.sources`), not the page's own
 * map — that map knew only `auto_memory` and `compaction`, so the tool-written
 * rows (`agent`) rendered with no origin at all (walkthrough 2026-10-12: 32 rows,
 * 29 chips). A source the UI can localise uses its own key; every other value the
 * store holds falls back to the backend's label, so no row stays unlabelled.
 */
export function memorySourceLabel(
  source: string,
  sources: Record<string, string> | undefined,
  t: (key: string) => string,
): string {
  if (!source) return ''
  const key = SOURCE_KEYS[source]
  if (key) return t(key)
  return sources?.[source] ?? ''
}

/** memory_type → label key. If the type is missing (Chroma does not know it) there is no chip. */
const TYPE_KEYS: Record<string, string> = {
  semantic: 'agentPanel.memoryTypeSemantic',
  episodic: 'agentPanel.memoryTypeEpisodic',
  procedural: 'agentPanel.memoryTypeProcedural',
}

function num(meta: Record<string, unknown>, key: string): number | null {
  const v = meta[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function str(meta: Record<string, unknown>, key: string): string {
  const v = meta[key]
  return typeof v === 'string' ? v : ''
}

/**
 * The two ways of writing — offering them separately is the point: "the address
 * changed" is not "I made a typo". `supersede` writes a correction and leaves the
 * old fact standing as descent; `rewrite` overwrites the text at the same ID.
 */
export type WriteKind = 'supersede' | 'rewrite'

export interface MemoryRowCardProps {
  row: MemoryRow
  index: number
  /** Trash rows behave differently: no editing, only restoring. */
  trash: boolean
  /**
   * Wave 10: what the backend says about restore for the active store. `false`
   * means the store deletes finally — the row must not offer a restore it cannot
   * perform. Absent/`true` keeps the control (a backend without the field).
   */
  restoreSupported?: boolean
  /** Wave 10: the store's origin vocabulary (`stats.sources`), label fallback. */
  sources?: Record<string, string>
  isEditing: boolean
  /** An open edit form blocks the other rows (only one draft can exist). */
  editLocked: boolean
  draft: string
  saving: boolean
  onDraft: (value: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onCommit: (kind: WriteKind) => void
  onRemove: () => void
  onRestore: () => void
}

export function MemoryRowCard({
  row,
  index,
  trash,
  restoreSupported = true,
  sources,
  isEditing,
  editLocked,
  draft,
  saving,
  onDraft,
  onStartEdit,
  onCancelEdit,
  onCommit,
  onRemove,
  onRestore,
}: MemoryRowCardProps) {
  const { t } = useTranslation()
  const sourceLabel = memorySourceLabel(str(row.metadata, 'source'), sources, t)
  const typeKey = TYPE_KEYS[str(row.metadata, 'type')]
  const hits = num(row.metadata, 'hits')
  // Trash rows age from deleted_at; live rows from timestamp.
  const stamp = num(row.metadata, trash ? 'deleted_at' : 'timestamp')
  const age = stamp === null ? null : formatDuration(Date.now() - stamp * 1000)
  const tags = Array.isArray(row.metadata.tags) ? (row.metadata.tags as unknown[]) : []
  const lineage = row.metadata.superseded_by
    ? { key: 'agentPanel.memorySuperseded', title: str(row.metadata, 'superseded_by') }
    : row.metadata.supersedes
      ? { key: 'agentPanel.memorySupersedes', title: str(row.metadata, 'supersedes') }
      : null
  // Only the superseded fact steps back — the correction leads and is not an
  // excerpt from history.
  const replaced = Boolean(row.metadata.superseded_by)
  const showMeta =
    !isEditing &&
    (sourceLabel || typeKey || age || lineage || tags.length > 0 || (hits && hits > 1))

  return (
    <div
      data-testid={`memory-row-${index}`}
      className={`rounded-lg border px-3 py-2 ${
        trash ? 'border-dashed border-hairline bg-surface' : 'border-hairline bg-surface'
      } ${replaced && !trash ? 'opacity-70' : ''}`}
    >
      <div className="flex items-start gap-2">
        <span className="text-ui-xs font-mono text-ink-faint shrink-0 tabular-nums mt-0.5">
          #{index + 1}
        </span>
        {isEditing ? (
          <textarea
            data-testid="memory-edit-input"
            value={draft}
            autoFocus
            rows={3}
            onChange={(e) => onDraft(e.target.value)}
            aria-label={t('agentPanel.memoryEdit')}
            className="flex-1 min-w-0 resize-y rounded-md bg-canvas border border-brand/30 px-2 py-1 text-ui-xs text-foreground outline-none focus-ring"
          />
        ) : (
          <p
            className={`flex-1 min-w-0 text-ui-xs leading-relaxed break-words ${
              trash
                ? 'text-foreground/60 line-through decoration-status-info/30'
                : 'text-foreground/80'
            }`}
          >
            {row.text}
          </p>
        )}
        {isEditing ? (
          <>
            <button
              type="button"
              data-testid="memory-edit-supersede"
              aria-label={t('agentPanel.memorySupersedeAction')}
              title={t('agentPanel.memorySupersedeHint')}
              disabled={saving || !draft.trim()}
              onClick={() => onCommit('supersede')}
              className="shrink-0 rounded-md px-1.5 py-1 min-h-7 max-lg:min-h-11 text-ui-2xs bg-brand/15 text-brand hover:bg-brand/25 disabled:opacity-40"
            >
              {t('agentPanel.memorySupersedeAction')}
            </button>
            <button
              type="button"
              data-testid="memory-edit-rewrite"
              aria-label={t('agentPanel.memoryRewriteAction')}
              title={t('agentPanel.memoryRewriteHint')}
              disabled={saving || !draft.trim()}
              onClick={() => onCommit('rewrite')}
              className="shrink-0 rounded-md px-1.5 py-1 min-h-7 max-lg:min-h-11 text-ui-2xs text-ink-faint hover:text-foreground hover:bg-surface disabled:opacity-40"
            >
              {t('agentPanel.memoryRewriteAction')}
            </button>
            <button
              type="button"
              data-testid="memory-edit-cancel"
              aria-label={t('common.cancel')}
              title={t('common.cancel')}
              onClick={onCancelEdit}
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 rounded-md text-ink-faint hover:text-foreground hover:bg-surface shrink-0"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </>
        ) : trash ? (
          // Wave 10: under a store that deletes finally there is nothing to bring
          // back — no restore control rather than one that answers 409.
          restoreSupported && (
            <button
              type="button"
              data-testid={`memory-restore-${index}`}
              aria-label={t('agentPanel.memoryRestore')}
              title={t('agentPanel.memoryRestore')}
              onClick={onRestore}
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 rounded-md text-ink-faint hover:text-foreground hover:bg-surface shrink-0"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          )
        ) : (
          <>
            <button
              type="button"
              data-testid={`memory-edit-${index}`}
              aria-label={t('agentPanel.memoryEdit')}
              title={t('agentPanel.memoryEdit')}
              disabled={editLocked}
              onClick={onStartEdit}
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 rounded-md text-ink-faint hover:text-foreground hover:bg-surface shrink-0 disabled:opacity-30"
            >
              <Pencil className="h-3 w-3" />
            </button>
            <button
              type="button"
              data-testid={`memory-delete-${index}`}
              aria-label={t('agentPanel.memoryDelete')}
              title={t('agentPanel.memoryDelete')}
              onClick={onRemove}
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 rounded-md text-ink-faint hover:text-foreground hover:bg-surface shrink-0"
            >
              <X className="h-3 w-3" />
            </button>
          </>
        )}
      </div>
      {showMeta && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1 pl-6 text-ui-2xs text-ink-faint">
          {sourceLabel && (
            <span data-testid={`memory-source-${index}`} className="truncate">
              {sourceLabel}
            </span>
          )}
          {typeKey && (
            <span
              data-testid={`memory-type-${index}`}
              className="rounded-full border border-hairline px-1.5"
            >
              {t(typeKey)}
            </span>
          )}
          {tags.length > 0 && (
            <span data-testid={`memory-tags-${index}`} className="truncate">
              {tags
                .slice(0, 3)
                .map((v) => `#${String(v)}`)
                .join(' ')}
            </span>
          )}
          {age && (
            <span data-testid={`memory-age-${index}`}>
              {t('agentPanel.memoryAge', { duration: age })}
            </span>
          )}
          {hits !== null && hits > 1 && (
            <span data-testid={`memory-hits-${index}`}>
              {t('agentPanel.memoryHits', { n: hits })}
            </span>
          )}
          {row.metadata.priority === 'high' && (
            <span data-testid={`memory-priority-${index}`} className="text-brand/80">
              <Check className="inline h-3 w-3" aria-hidden="true" />
              {t('agentPanel.memoryPriorityHigh')}
            </span>
          )}
          {lineage && (
            <span
              data-testid={`memory-lineage-${index}`}
              title={lineage.title}
              className="text-status-warning/80"
            >
              {t(lineage.key)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
