'use client'

import { useTranslation } from 'react-i18next'
import type { TrajMemory } from '@/lib/api'
import { useMemoryActions } from '@/lib/useMemoryFacts'
import type { MemoryRow } from './memoryRowCard'

/** A chip stays one line; the full fact lives in the tooltip and the editor. */
const CHIP_MAX = 64

/** One shape for the new field and the write path that already knows a row. */
function rowOf(m: TrajMemory): MemoryRow {
  return { id: m.id, text: m.text, metadata: { source: m.source } }
}

function clip(text: string): string {
  return text.length > CHIP_MAX ? `${text.slice(0, CHIP_MAX - 1).trimEnd()}…` : text
}

/**
 * G7 provenance: the stored facts a past turn's prompt carried.
 *
 * The block draws nothing without `memories` — an absent field means the turn
 * injected none, and a chip there would name a provenance the backend never
 * recorded. With facts it is a caption plus one tappable chip each; a chip is a
 * real button, and tapping it opens the same three write paths the knowledge
 * inventory uses (correct = supersede, rewrite = overwrite in place, retract =
 * delete) through `useMemoryActions`, so the trajectory is a second way into the
 * one data path, not a second path of its own.
 */
export function TurnMemories({
  ti,
  memories,
  reload,
}: {
  ti: number
  memories: TrajMemory[] | undefined
  reload: () => void
}) {
  const { t } = useTranslation()
  const { editingId, draft, saving, setDraft, startEdit, closeEdit, commit, remove } =
    useMemoryActions(reload)

  if (!memories || memories.length === 0) return null

  const openMemory = memories.find((m) => m.id === editingId)
  const open = openMemory ? rowOf(openMemory) : null

  return (
    <div
      data-testid={`trajectory-turn-facts-${ti}`}
      className="col-span-full border-b border-border/40 bg-surface/40 px-3 py-1.5"
    >
      <p className="flex flex-wrap items-baseline gap-x-2 font-mono text-ui-2xs text-ink-faint">
        <span>{t('agentPanel.trajectoryFacts', { n: memories.length })}</span>
        <span className="text-foreground-subtlest">{t('agentPanel.trajectoryFactsHint')}</span>
      </p>
      <div className="mt-1 flex flex-wrap gap-1">
        {memories.map((m, i) => {
          const isOpen = editingId === m.id
          return (
            <button
              key={m.id}
              type="button"
              data-testid={`turn-fact-${ti}-${i}`}
              title={m.text}
              aria-label={t('agentPanel.trajectoryFactEditorLabel', { text: m.text })}
              aria-expanded={isOpen}
              onClick={() => (isOpen ? closeEdit() : startEdit(rowOf(m)))}
              className={`max-w-full truncate rounded-full border px-2 py-0.5 text-ui-2xs min-h-7 max-lg:min-h-11 transition-colors ${
                isOpen
                  ? 'border-brand/50 bg-brand/15 text-brand'
                  : 'border-hairline text-ink-soft hover:border-brand/40 hover:text-foreground'
              }`}
            >
              {clip(m.text)}
            </button>
          )
        })}
      </div>
      {open && (
        <div
          data-testid={`turn-fact-editor-${ti}`}
          className="mt-1.5 rounded-md border border-hairline bg-canvas p-2"
        >
          <textarea
            data-testid={`turn-fact-input-${ti}`}
            value={draft}
            autoFocus
            rows={3}
            onChange={(e) => setDraft(e.target.value)}
            aria-label={t('agentPanel.trajectoryFactEditorLabel', { text: open.text })}
            className="w-full resize-y rounded-md bg-canvas border border-brand/30 px-2 py-1 text-ui-xs text-foreground outline-none focus-ring"
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              data-testid={`turn-fact-correct-${ti}`}
              aria-label={t('agentPanel.memorySupersedeAction')}
              title={t('agentPanel.memorySupersedeHint')}
              disabled={saving || !draft.trim()}
              onClick={() => void commit(open, 'supersede')}
              className="rounded-md bg-brand/15 px-2 py-1 text-ui-2xs text-brand hover:bg-brand/25 disabled:opacity-40 min-h-7 max-lg:min-h-11"
            >
              {t('agentPanel.trajectoryFactCorrect')}
            </button>
            <button
              type="button"
              data-testid={`turn-fact-rewrite-${ti}`}
              aria-label={t('agentPanel.memoryRewriteAction')}
              title={t('agentPanel.memoryRewriteHint')}
              disabled={saving || !draft.trim()}
              onClick={() => void commit(open, 'rewrite')}
              className="rounded-md px-2 py-1 text-ui-2xs text-ink-soft hover:text-foreground hover:bg-surface disabled:opacity-40 min-h-7 max-lg:min-h-11"
            >
              {t('agentPanel.memoryRewriteAction')}
            </button>
            <button
              type="button"
              data-testid={`turn-fact-retract-${ti}`}
              aria-label={t('agentPanel.memoryDelete')}
              title={t('agentPanel.memoryDelete')}
              disabled={saving}
              onClick={() => void remove(open)}
              className="rounded-md px-2 py-1 text-ui-2xs text-ink-soft hover:text-destructive hover:bg-surface disabled:opacity-40 min-h-7 max-lg:min-h-11"
            >
              {t('agentPanel.trajectoryFactRetract')}
            </button>
            <button
              type="button"
              data-testid={`turn-fact-cancel-${ti}`}
              aria-label={t('common.cancel')}
              title={t('common.cancel')}
              onClick={closeEdit}
              className="rounded-md px-2 py-1 text-ui-2xs text-ink-faint hover:text-foreground hover:bg-surface min-h-7 max-lg:min-h-11"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
