'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  FolderOpen,
  Folder,
  File as FileIcon,
  ChevronRight,
  FileDiff,
  Undo2,
  RefreshCw,
} from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import { listFs, gitStatus, gitDiff, gitApplyPatch, listChangeSets } from '@/lib/api'
import type { GitDiffResponse, GitFileChange, GitStatusResponse } from '@/lib/api'
import { toastBus } from '@/lib/toast'
import DiffView from '../DiffView'
import { useWorkspaceDir, WorkspaceBadge } from './primitives'
import {
  changeState,
  hasPatch,
  indexChanges,
  indexOrigins,
  markHintKey,
  markKey,
  relFromRoot,
  sameDir,
} from './fileStatus'
import type { OriginMark } from './fileStatus'

// ── F round 4: file explorer (tree + click → preview via /api/file) ────────

export function joinPath(dir: string, name: string): string {
  return `${dir.replace(/\/$/, '')}/${name}`
}

export function FilesTab({ onOpenFile }: { onOpenFile: (fileUrl: string) => void }) {
  const { t } = useTranslation()
  const workspace = useWorkspaceDir()
  const [root, setRoot] = useState<{ path: string; entries: import('@/lib/api').FsEntry[] } | null>(
    null,
  )
  // path → child entries (loaded lazily); undefined = not expanded
  const [children, setChildren] = useState<
    Record<string, import('@/lib/api').FsEntry[] | 'loading'>
  >({})
  // The marks derived from the git workspace. Both stay empty unless the tree root turns
  // out to be the very directory git read.
  const [changes, setChanges] = useState<Record<string, GitFileChange>>({})
  const [origins, setOrigins] = useState<Record<string, OriginMark>>({})
  const [patches, setPatches] = useState<Record<string, GitDiffResponse>>({})
  const [diffFor, setDiffFor] = useState('')
  const [busy, setBusy] = useState('')
  // N1: the tree has three states, not two. `!root` used to stand for
  // "still reading", "the read failed" AND "no workspace set" at once, so the
  // surface could tell a person "No workspace set — pick one in settings" while
  // the badge above it named the workspace. Read, unread and empty are now named
  // apart — the same reason memoryStoreState.tsx exists for the knowledge store.
  const [read, setRead] = useState<'loading' | 'ready' | 'failed'>('loading')

  const loadRoot = useCallback(() => {
    setRead('loading')
    listFs(workspace || undefined)
      .then((r) => {
        setRoot({ path: r.path, entries: r.entries })
        setRead('ready')
      })
      .catch(() => {
        setRoot(null)
        setRead('failed')
      })
  }, [workspace])
  useEffect(() => {
    loadRoot()
  }, [loadRoot])

  const loadMarks = useCallback(async () => {
    if (!root) {
      setChanges({})
      setOrigins({})
      return
    }
    let status: GitStatusResponse | null = null
    try {
      status = await gitStatus(false)
    } catch {
      status = null
    }
    // The mark may only come from the tree git actually read: its paths are relative to
    // that root, so joining them under another tree spells a different file there — and
    // the revert would then act on the wrong repository.
    if (!sameDir(root.path, status?.root ?? null)) {
      setChanges({})
      setOrigins({})
      return
    }
    setChanges(indexChanges(status?.changes ?? []))
    try {
      setOrigins(indexOrigins((await listChangeSets(root.path)).change_sets))
    } catch {
      setOrigins({})
    }
  }, [root])
  useEffect(() => {
    void loadMarks()
  }, [loadMarks])

  const toggleDiff = useCallback(
    async (rel: string) => {
      if (diffFor === rel) {
        setDiffFor('')
        return
      }
      setDiffFor(rel)
      if (patches[rel]) return
      try {
        const patch = await gitDiff(rel)
        setPatches((prev) => ({ ...prev, [rel]: patch }))
      } catch {
        setDiffFor('')
        toastBus.error(t('agentPanel.diffFailed'))
      }
    },
    [diffFor, patches, t],
  )

  // Reversing the file's own patch is the working-tree revert, and it is the endpoint
  // DiffView already discards hunks through, so no second write path appears here.
  const revertFile = useCallback(
    async (rel: string) => {
      if (!window.confirm(t('agentPanel.revertConfirm'))) return
      setBusy(rel)
      try {
        const patch = patches[rel] ?? (await gitDiff(rel))
        if (patch.binary || !patch.diff) {
          toastBus.error(t('agentPanel.revertFailed'))
          return
        }
        await gitApplyPatch(patch.diff, { reverse: true })
        toastBus.success(t('agentPanel.revertDone', { path: rel }))
        setPatches((prev) => {
          const next = { ...prev }
          delete next[rel]
          return next
        })
        setDiffFor('')
        await loadMarks()
      } catch {
        toastBus.error(t('agentPanel.revertFailed'))
      } finally {
        setBusy('')
      }
    },
    [patches, loadMarks, t],
  )

  const expand = useCallback((dir: string) => {
    setChildren((prev) => {
      const cur = prev[dir]
      if (cur === 'loading') return prev
      if (cur) {
        const next = { ...prev }
        delete next[dir]
        return next
      } // toggle zu
      return { ...prev, [dir]: 'loading' }
    })
    listFs(dir)
      .then((r) => setChildren((prev) => ({ ...prev, [dir]: r.entries })))
      .catch(() =>
        setChildren((prev) => {
          const n = { ...prev }
          delete n[dir]
          return n
        }),
      )
  }, [])

  const renderRows = (
    entries: import('@/lib/api').FsEntry[],
    dir: string,
    depth: number,
  ): React.ReactNode =>
    entries.map((e) => {
      if (e.type === 'info') {
        return (
          <div
            key={`i-${dir}-${e.name}`}
            className="px-3 py-1 text-ui-xs text-ink-faint"
            style={{ paddingLeft: 12 + depth * 14 }}
          >
            {e.name}
          </div>
        )
      }
      const full = joinPath(dir, e.name)
      // The index key and the tree path must agree exactly: git and a change set both
      // spell paths from the repository root, the tree spells them from the workspace, and
      // only under a repo-rooted workspace do the two produce the same string.
      const rel = root ? (relFromRoot(root.path, full) ?? '') : ''
      const change = rel ? changes[rel] : undefined
      const origin = rel ? origins[rel] : undefined
      const state = change ? changeState(change.status) : null
      const patchable = change ? hasPatch(change.status) : false
      if (e.type === 'dir') {
        const kids = children[full]
        const isOpen = !!kids
        return (
          <div key={full}>
            <button
              type="button"
              onClick={() => expand(full)}
              aria-expanded={isOpen}
              className="w-full flex items-center gap-1.5 px-3 py-1 text-left text-ui-xs text-foreground/80 hover:bg-surface transition-colors"
              style={{ paddingLeft: 12 + depth * 14 }}
            >
              <ChevronRight
                className={`h-3 w-3 text-ink-faint transition-transform ${isOpen ? 'rotate-90' : ''}`}
              />
              {isOpen ? (
                <FolderOpen className="h-3.5 w-3.5 text-brand/70" />
              ) : (
                <Folder className="h-3.5 w-3.5 text-ink-faint" />
              )}
              <span className="truncate">{e.name}</span>
            </button>
            {kids === 'loading' && (
              <LoadingRow
                label={t('agentPanel.loading')}
                className="px-3 py-1"
                style={{ paddingLeft: 12 + (depth + 1) * 14 }}
              />
            )}
            {Array.isArray(kids) && renderRows(kids, full, depth + 1)}
          </div>
        )
      }
      const markLabel = state ? t(markKey(state, origin)) : ''
      const markHint = state && !patchable ? t(markHintKey(state)) : ''
      const markTip = [markLabel, origin?.why, markHint].filter(Boolean).join(' — ')
      const markTone =
        state === 'new'
          ? 'bg-status-success/15 text-status-success'
          : 'bg-status-warning/15 text-status-warning'
      return (
        <div key={full}>
          <div
            className="group flex items-center gap-1.5 px-3 py-1 text-ui-xs text-ink-faint hover:bg-surface transition-colors"
            style={{ paddingLeft: 12 + (depth + 1) * 14 }}
          >
            <button
              type="button"
              onClick={() => onOpenFile(`/api/file?path=${encodeURIComponent(full)}`)}
              title={t('agentPanel.openInPreview')}
              className="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:text-foreground transition-colors"
            >
              <FileIcon className="h-3.5 w-3.5 flex-shrink-0 opacity-50" />
              <span className="truncate">{e.name}</span>
            </button>
            {state && (
              <span
                data-testid={`file-mark-${rel}`}
                title={markTip}
                className={`shrink-0 rounded px-1 text-ui-xs font-medium ${markTone}`}
              >
                {markLabel}
              </span>
            )}
            {change && change.additions > 0 && (
              <span className="shrink-0 text-ui-xs font-mono text-status-success/90">
                +{change.additions}
              </span>
            )}
            {change && change.deletions > 0 && (
              <span className="shrink-0 text-ui-xs font-mono text-status-danger/90">
                −{change.deletions}
              </span>
            )}
            {patchable && (
              <>
                <button
                  type="button"
                  data-testid={`file-diff-${rel}`}
                  onClick={() => void toggleDiff(rel)}
                  aria-expanded={diffFor === rel}
                  aria-label={
                    diffFor === rel ? t('agentPanel.closeDiff') : t('agentPanel.openDiff')
                  }
                  title={diffFor === rel ? t('agentPanel.closeDiff') : t('agentPanel.openDiff')}
                  className="shrink-0 rounded p-0.5 text-ink-faint hover:text-foreground hover:bg-surface transition-colors"
                >
                  <FileDiff className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  data-testid={`file-revert-${rel}`}
                  onClick={() => void revertFile(rel)}
                  disabled={busy === rel}
                  aria-label={t('agentPanel.revertFile')}
                  title={t('agentPanel.revertFile')}
                  className="shrink-0 rounded p-0.5 text-ink-faint hover:text-status-danger disabled:opacity-40 transition-colors"
                >
                  <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </>
            )}
          </div>
          {diffFor === rel && (
            <div className="border-t border-hairline px-3 py-2">
              {patches[rel]?.binary ? (
                <p className="text-ui-xs text-ink-faint font-mono">
                  {t('agentPanel.reviewBinary')}
                </p>
              ) : patches[rel] ? (
                <DiffView
                  diff={patches[rel].diff}
                  filePath={patches[rel].path}
                  onApplied={() => void loadMarks()}
                />
              ) : (
                <LoadingRow label={t('agentPanel.loading')} className="px-1 py-1" />
              )}
            </div>
          )}
        </div>
      )
    })

  // N1: what the surface is looking at, in numbers — the read's own result.
  const changedCount = Object.keys(changes).length

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <WorkspaceBadge dir={workspace} />
      {/* N1: the status line the tab was missing. Every other pane in this
          directory says what it holds (Evidence: "80 of 54,024 records"; Changes:
          the branch and the pending count); the file tree said nothing, so a
          person could not tell a read of 44 entries from a read of 4. */}
      {read === 'ready' && root && (
        <div
          data-testid="files-status"
          className="flex items-center gap-2 px-3 py-1 border-b border-hairline bg-surface text-ui-xs text-ink-faint shrink-0"
        >
          <span className="tabular-nums">
            {t('agentPanel.filesCount', { count: root.entries.length })}
          </span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {changedCount
              ? t('agentPanel.diffFiles', { count: changedCount })
              : t('agentPanel.filesUnchanged')}
          </span>
          <button
            type="button"
            data-testid="files-refresh"
            onClick={loadRoot}
            aria-label={t('agentPanel.filesRefresh')}
            title={t('agentPanel.filesRefresh')}
            className="ml-auto shrink-0 rounded p-0.5 text-ink-faint hover:text-foreground hover:bg-surface-raised transition-colors min-h-6 min-w-6 inline-flex items-center justify-center"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
          </button>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto py-2">
        {read === 'loading' ? (
          <LoadingRow label={t('agentPanel.filesReading')} className="px-3 py-3" />
        ) : read === 'failed' ? (
          <div
            data-testid="files-unread"
            role="alert"
            className="h-full flex flex-col items-center justify-center gap-2 text-ui-sm p-6 text-center"
          >
            <Folder className="h-10 w-10 opacity-40 text-ink-faint" aria-hidden="true" />
            <p className="text-status-warning max-w-80">{t('agentPanel.filesUnread')}</p>
            <button
              type="button"
              onClick={loadRoot}
              className="mt-1 px-3 py-1.5 rounded-lg text-ui-xs font-medium border border-hairline text-foreground/80 hover:bg-surface transition-colors"
            >
              {t('agentPanel.retry')}
            </button>
          </div>
        ) : !root ? (
          <p className="text-ui-xs text-ink-faint px-3 py-3">{t('agentPanel.filesEmpty')}</p>
        ) : (
          renderRows(root.entries, root.path, 0)
        )}
      </div>
    </div>
  )
}
