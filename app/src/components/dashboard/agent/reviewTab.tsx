'use client'

// ReviewTab — split out of tabsC 1:1 (the architecture boundary maxFileLines=400).

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RotateCw, Check, GitBranch, ChevronRight } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import SmartTip from '../SmartTip'
import DiffView from '../DiffView'
import { gitStatus, gitDiff, gitAdd, gitCommit, GitFileChange, GitDiffResponse } from '@/lib/api'
import { useWorkspaceDir, WorkspaceBadge } from './primitives'

// Round G (2026-09-07): Review tab — the file list of workspace changes,
// as in the reference: status short code, +N/−M chips, expandable patches
// (DiffView coloring), refresh, working-copy/staged toggle. Read-only
// routes /api/git/status + /api/git/diff; the agent's git runs stay on
// view in the Terminal tab.
export function ReviewTab() {
  const { t } = useTranslation()
  const workspace = useWorkspaceDir()
  const [staged, setStaged] = useState(false)
  const [changes, setChanges] = useState<GitFileChange[] | null>(null)
  const [isRepo, setIsRepo] = useState(true)
  const [branch, setBranch] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [patches, setPatches] = useState<Record<string, GitDiffResponse>>({})
  const [gitBusy, setGitBusy] = useState(false)
  const [gitMsg, setGitMsg] = useState<string | null>(null)
  const [commitDraft, setCommitDraft] = useState('')

  const load = useCallback(async (stagedView: boolean) => {
    try {
      const res = await gitStatus(stagedView)
      setIsRepo(res.git)
      setBranch(res.branch)
      setChanges(res.changes)
    } catch {
      setIsRepo(false)
      setChanges([])
    }
  }, [])

  useEffect(() => {
    void load(staged)
  }, [staged, load])

  async function handleStageAll() {
    setGitBusy(true)
    setGitMsg(null)
    try {
      const r = await gitAdd()
      setGitMsg(t('agentPanel.gitStaged', { n: r.staged }))
      void load(staged)
    } catch (e) {
      setGitMsg(e instanceof Error ? e.message : 'git add failed')
    } finally {
      setGitBusy(false)
    }
  }

  async function handleCommit() {
    const message = commitDraft.trim()
    if (!message) return
    setGitBusy(true)
    setGitMsg(null)
    try {
      const r = await gitCommit(message)
      setGitMsg(t('agentPanel.gitCommitted', { hash: r.hash.slice(0, 7) }))
      setCommitDraft('')
      void load(staged)
    } catch (e) {
      setGitMsg(e instanceof Error ? e.message : 'git commit failed')
    } finally {
      setGitBusy(false)
    }
  }

  const toggleRow = async (path: string) => {
    if (expanded === path) {
      setExpanded(null)
      return
    }
    setExpanded(path)
    if (!patches[path]) {
      try {
        const res = await gitDiff(path, staged)
        setPatches((prev) => ({ ...prev, [path]: res }))
      } catch {
        setPatches((prev) => ({ ...prev, [path]: { path, diff: '', binary: false } }))
      }
    }
  }

  const reviewTip: Record<string, { title: string; body: string }> = {
    M: { title: t('chat.reviewTipM.title'), body: t('chat.reviewTipM.body') },
    '?': { title: t('chat.reviewTipQ.title'), body: t('chat.reviewTipQ.body') },
    D: { title: t('chat.reviewTipD.title'), body: t('chat.reviewTipD.body') },
  }
  // WP2b keep: the Git status letter in the trio D=danger / ?=info / the rest=success.
  const statusTone = (code: string) =>
    code === 'D'
      ? 'text-status-danger/90'
      : code === '?'
        ? 'text-ink-soft'
        : 'text-status-success/90'

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <WorkspaceBadge dir={workspace} />
      <div className="flex items-center gap-2 px-3 py-2 border-b border-hairline flex-shrink-0">
        <div className="flex items-center rounded-lg border border-hairline overflow-hidden text-ui-sm">
          <button
            type="button"
            data-testid="review-worktree-toggle"
            aria-pressed={!staged}
            onClick={() => setStaged(false)}
            className={`px-2.5 py-1 transition-colors ${!staged ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
          >
            {t('agentPanel.reviewWorktree')}
          </button>
          <button
            type="button"
            data-testid="review-staged-toggle"
            aria-pressed={staged}
            onClick={() => setStaged(true)}
            className={`px-2.5 py-1 transition-colors ${staged ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
          >
            {t('agentPanel.reviewStaged')}
          </button>
        </div>
        {branch && <span className="text-ui-sm text-ink-faint font-mono truncate">{branch}</span>}
        <div className="flex-1" />
        <button
          type="button"
          data-testid="review-refresh"
          aria-label={t('agentPanel.reviewRefresh')}
          title={t('agentPanel.reviewRefresh')}
          onClick={() => void load(staged)}
          className="p-1.5 rounded-md text-ink-soft hover:text-foreground hover:bg-surface transition-colors"
        >
          <RotateCw className="h-3.5 w-3.5" />
        </button>
      </div>
      {/* W3c: stage + commit directly in the git tab (argument-list routes, no shell) */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-hairline flex-shrink-0">
        <button
          type="button"
          disabled={gitBusy}
          onClick={() => void handleStageAll()}
          data-testid="git-stage-all"
          className="rounded-lg bg-brand/20 text-brand hover:bg-brand/20 px-2.5 py-1.5 text-ui-sm font-medium transition-colors disabled:opacity-50 max-lg:min-h-11"
        >
          {t('agentPanel.gitStageAll')}
        </button>
        <input
          type="text"
          value={commitDraft}
          onChange={(e) => setCommitDraft(e.target.value)}
          placeholder={t('agentPanel.gitCommitMsgPh')}
          aria-label={t('agentPanel.gitCommitMsgPh')}
          data-testid="git-commit-msg"
          className="min-w-0 flex-1 rounded-lg bg-surface px-2 py-1.5 text-ui-sm text-foreground/80 placeholder:text-ink-faint outline-none focus:bg-surface transition-colors max-lg:min-h-11"
        />
        <button
          type="button"
          disabled={gitBusy || !commitDraft.trim()}
          onClick={() => void handleCommit()}
          data-testid="git-commit"
          className="shrink-0 rounded-lg bg-brand/20 text-brand hover:bg-brand/20 px-2.5 py-1.5 text-ui-sm font-medium transition-colors disabled:opacity-50 max-lg:min-h-11"
        >
          {t('agentPanel.gitCommitBtn')}
        </button>
      </div>
      {gitMsg && (
        <p className="px-3 py-1.5 text-ui-sm font-mono text-brand/80 break-all border-b border-hairline">
          {gitMsg}
        </p>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto" data-testid="review-file-list">
        {!isRepo ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center">
            <GitBranch className="h-10 w-10 opacity-40" />
            <p>{t('agentPanel.gitEmpty')}</p>
          </div>
        ) : changes !== null && changes.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center">
            {/* WP2b keep: a clean working tree is a real status, not a selection accent. */}
            <Check className="h-10 w-10 text-status-success/40" />
            <p>{t('agentPanel.reviewClean')}</p>
          </div>
        ) : (
          <div className="p-2 space-y-1.5">
            {(changes ?? []).map((c) => (
              <div
                key={c.path}
                className="rounded-lg border border-hairline bg-canvas overflow-hidden"
              >
                <button
                  type="button"
                  data-testid={`review-row-${c.path}`}
                  onClick={() => void toggleRow(c.path)}
                  aria-expanded={expanded === c.path}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface transition-colors"
                >
                  <ChevronRight
                    className={`h-3.5 w-3.5 text-ink-faint shrink-0 transition-transform ${expanded === c.path ? 'rotate-90' : ''}`}
                  />
                  <SmartTip
                    testId={`review-chip-tip-${c.path}`}
                    tip={reviewTip[c.status] ?? { title: c.status, body: '' }}
                    side="bottom"
                  >
                    <span
                      data-testid={`review-status-chip-${c.path}`}
                      className={`w-4 text-center text-ui-sm font-mono font-bold shrink-0 ${statusTone(c.status)}`}
                    >
                      {c.status}
                    </span>
                  </SmartTip>
                  <span
                    className="flex-1 min-w-0 truncate font-mono text-ui-xs text-foreground/80"
                    title={c.path}
                  >
                    {c.path}
                  </span>
                  {c.additions > 0 && (
                    <span className="text-ui-sm font-mono text-status-success/90 shrink-0">
                      +{c.additions}
                    </span>
                  )}
                  {c.deletions > 0 && (
                    <span className="text-ui-sm font-mono text-status-danger/90 shrink-0">
                      −{c.deletions}
                    </span>
                  )}
                </button>
                {expanded === c.path && (
                  <div className="border-t border-hairline p-2 max-h-80 overflow-auto">
                    {patches[c.path]?.binary ? (
                      <p className="text-ui-sm text-ink-faint font-mono px-1">
                        {t('agentPanel.reviewBinary')}
                      </p>
                    ) : patches[c.path] ? (
                      <DiffView
                        diff={(patches[c.path] as GitDiffResponse).diff}
                        filePath={(patches[c.path] as GitDiffResponse).path}
                        onApplied={() => {
                          // Drop the cached patch + collapse so the next expand
                          // re-fetches fresh content, and reload the change list
                          // so the hunk action is visibly acknowledged.
                          setPatches((prev) => {
                            const next = { ...prev }
                            delete next[c.path]
                            return next
                          })
                          setExpanded(null)
                          void load(staged)
                        }}
                      />
                    ) : (
                      <LoadingRow label={t('agentPanel.loading')} className="px-1 py-2" />
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
