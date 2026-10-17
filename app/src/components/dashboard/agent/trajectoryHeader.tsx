'use client'

import { useTranslation } from 'react-i18next'
import { X, Search, ListFilter, Maximize2, FolderInput, RefreshCw } from 'lucide-react'
import type { TrajTurn } from '@/lib/api'
import { fmtTokens } from '@/lib/format'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { TRAJ_ICON_BTN, MAX_TURNS_NOTICE } from './trajectoryParts'

// The header block of the trajectory pane: 6 icon buttons, a summary line, search,
// the Δ switch and the truncated notice — prop-driven from the pane body.
export function TrajectoryHeader({
  turns,
  summary,
  searchOpen,
  query,
  matchIndex,
  deltaOn,
  scrollRef,
  onToggleSearch,
  onToggleFilter,
  onToggleExpand,
  onRefresh,
  onToggleDelta,
  onQueryChange,
}: {
  turns: TrajTurn[] | null
  summary: { calls: number; tokens: number; models: string }
  searchOpen: boolean
  query: string
  matchIndex: number
  deltaOn: boolean
  scrollRef: React.RefObject<HTMLDivElement | null>
  onToggleSearch: () => void
  onToggleFilter: () => void
  onToggleExpand: () => void
  onRefresh: () => void
  onToggleDelta: () => void
  onQueryChange: (value: string) => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <>
      <div className="px-3 py-2 space-y-1.5" data-testid="trajectory-header">
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="trajectory-btn-search"
            aria-label={t('agentPanel.trajectorySearch')}
            title={t('agentPanel.trajectorySearch')}
            className={TRAJ_ICON_BTN}
            onClick={onToggleSearch}
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="trajectory-btn-filter"
            aria-label={t('agentPanel.trajectoryFilter')}
            title={t('agentPanel.trajectoryFilter')}
            className={TRAJ_ICON_BTN}
            onClick={onToggleFilter}
          >
            <ListFilter className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="trajectory-btn-expand"
            aria-label={t('agentPanel.trajectoryExpandAll')}
            title={t('agentPanel.trajectoryExpandAll')}
            className={TRAJ_ICON_BTN}
            onClick={onToggleExpand}
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="trajectory-btn-move"
            aria-label={t('agentPanel.trajectoryMove')}
            title={t('agentPanel.trajectoryMove')}
            className={TRAJ_ICON_BTN}
            onClick={() => window.dispatchEvent(new Event('ephe:panel-dock-toggle'))}
          >
            <FolderInput className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="trajectory-btn-refresh"
            aria-label={t('agentPanel.trajectoryRefresh')}
            title={t('agentPanel.trajectoryRefresh')}
            className={TRAJ_ICON_BTN}
            onClick={onRefresh}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="trajectory-btn-close"
            aria-label={t('agentPanel.collapsePane')}
            title={t('agentPanel.collapsePane')}
            className={TRAJ_ICON_BTN}
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }),
              )
            }
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        {turns && turns.length > 0 && (
          <p
            data-testid="trajectory-summary"
            className="text-ui-xs text-ink-faint font-mono truncate"
          >
            {`${summary.calls} calls · ${fmtTokens(summary.tokens, i18n.language)} tok${summary.models ? ` · ${summary.models}` : ''}`}
          </p>
        )}
        {searchOpen && (
          <input
            data-testid="trajectory-search"
            type="text"
            value={query}
            placeholder={t('agentPanel.trajectorySearchPlaceholder')}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && matchIndex >= 0) {
                scrollRef.current?.scrollTo?.({ top: matchIndex * 120 })
              }
            }}
            className="w-full rounded-md border border-hairline bg-surface px-2 py-1 text-ui-xs text-foreground/90 outline-none focus:border-hairline-strong"
          />
        )}
      </div>
      {/* N5: the Δ switch (its own row, so the six-button header stays stable) */}
      <div className="px-3 pb-1.5">
        <button
          type="button"
          data-testid="trajectory-btn-delta"
          aria-label={t('agentPanel.trajectoryDelta')}
          title={t('agentPanel.trajectoryDelta')}
          aria-pressed={deltaOn}
          onClick={onToggleDelta}
          className={`rounded-md px-1.5 font-mono text-ui-xs transition-colors ${
            deltaOn
              ? 'bg-brand/20 text-brand'
              : 'text-ink-faint hover:text-foreground hover:bg-surface'
          }`}
        >
          Δ
        </button>
      </div>
      <div className="h-px bg-border flex-shrink-0" />
      {turns && turns.length >= MAX_TURNS_NOTICE && (
        <p className="px-3 py-1 text-ui-2xs text-ink-faint" data-testid="trajectory-truncated">
          {t('agentPanel.trajectoryTruncated', { n: MAX_TURNS_NOTICE })}
        </p>
      )}
      {/* n1-memory: the 20-turn window (core/trajectory.py `MAX_TURNS_PER_SESSION`) is
          named even below the cap, so the pane never leaves how far back it reaches
          unsaid. */}
      {turns && turns.length > 0 && turns.length < MAX_TURNS_NOTICE && (
        <p className="px-3 py-1 text-ui-2xs text-ink-faint" data-testid="trajectory-window">
          {t('agentPanel.trajectoryWindow', { n: MAX_TURNS_NOTICE })}
        </p>
      )}
    </>
  )
}
