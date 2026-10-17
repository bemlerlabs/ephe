'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, XCircle, Bot, Loader2 } from 'lucide-react'
import { ChatMessage } from '@/types'
import { getSubagent, listSubagents } from '@/lib/api'
import type { SubagentDetail, SubagentSummary } from '@/lib/api'
import { fmtMs } from '@/lib/format'
import { OpenHelperChatButton } from './primitives'
import { SubagentDetailBlock } from './subagentsDetail'
import { useChatStore } from '@/store/chatStore'

/** Backend agent_id taken from the activity label ("SubAgent subagent-1 (role)"). */
function backendAgentId(label: string): string | null {
  if (!label.startsWith('SubAgent ')) return null
  const core = label.replace(/^SubAgent\s+/, '').replace(/\s*\([^)]*\)\s*$/, '')
  return core || null
}

export function SubagentsTab({ messages }: { messages: ChatMessage[] }) {
  const { t } = useTranslation()
  const agents = useMemo(() => {
    const out: {
      id: string
      label: string
      status: 'running' | 'done' | 'failed'
      detail?: string
      at: number
    }[] = []
    for (const m of messages) {
      for (const a of m.activities ?? []) {
        if (!/agent/i.test(a.label) && !/swarm/i.test(a.label)) continue
        out.push({ id: a.id, label: a.label, status: a.status, detail: a.detail, at: m.timestamp })
      }
    }
    return out
  }, [messages])

  // P6 B1 (ref-02): directory history from the subagent API, cursor-paginated.
  // The conversation activities stay the live axis; the REST pages extend the
  // history below the Ended section ("Show more" only while a nextCursor keeps
  // arriving). A failed fetch shows an alert row.
  const [dirPage, setDirPage] = useState<SubagentSummary[] | null>(null)
  const [dirCursor, setDirCursor] = useState<string | null>(null)
  const [dirError, setDirError] = useState<string | null>(null)
  const loadDir = useCallback(async (cursor?: string | null, append = false) => {
    try {
      const page = await Promise.resolve(listSubagents(cursor))
      const list: SubagentSummary[] = page?.agents ?? []
      setDirPage((prev) => (append ? [...(prev ?? []), ...list] : list))
      setDirCursor(page?.nextCursor ?? null)
      setDirError(null)
    } catch (e) {
      setDirError(e instanceof Error ? e.message : String(e))
    }
  }, [])
  useEffect(() => {
    void loadDir()
  }, [loadDir])

  // P4-D: a row expands — detail via the REST endpoint (report/steps/ms).
  const [openId, setOpenId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SubagentDetail | null>(null)
  useEffect(() => {
    if (!openId) return
    let cancelled = false
    setDetail(null)
    getSubagent(openId)
      .then((r) => {
        if (!cancelled) setDetail(r)
      })
      .catch(() => {
        if (!cancelled) setDetail(null)
      })
    return () => {
      cancelled = true
    }
  }, [openId])

  // Visibility wave: the row is the entrance to the helper's own chat. If it is
  // already running (live events created the session) the click switches at once;
  // otherwise the ledger builds it — the same chat, the same way back to the
  // mother task.
  const openHelper = useCallback((agentId: string, chatSessionId?: string) => {
    void useChatStore.getState().openHelperChat({ agentId, chatSessionId })
  }, [])

  // Live in an open turn: the ticker refreshes the duration (started_ts) and polls
  // the record — new steps/report appear without a click. Identity check: an
  // unchanged answer does not replace the object, otherwise the 500 ms ticker
  // would hang itself on every detail reference.
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!openId) return
    const id = setInterval(() => {
      setTick((v) => v + 1)
      getSubagent(openId)
        .then((r) =>
          setDetail((prev) =>
            prev &&
            r.status === prev.status &&
            r.tool_calls.length === prev.tool_calls.length &&
            r.report === prev.report
              ? prev
              : r,
          ),
        )
        .catch(() => {})
    }, 600)
    return () => clearInterval(id)
  }, [openId])
  void tick
  const liveDur =
    detail?.duration_ms != null
      ? detail.duration_ms
      : detail?.started_ts
        ? Math.max(0, Math.round(Date.now() - detail.started_ts * 1000))
        : null

  const running = agents.filter((a) => a.status === 'running')
  const ended = agents.filter((a) => a.status !== 'running')
  const relTime = (ts: number) => {
    const m = Math.max(0, Math.round((Date.now() - ts) / 60000))
    if (m < 60) return t('agentPanel.minAgo', { count: m })
    const h = Math.round(m / 60)
    if (h < 48) return t('agentPanel.hoursAgo', { count: h })
    // N1: this register stopped converting at hours, so a helper from a fortnight
    // ago read "289h ago" — the arithmetic, not the age. `relTime` in
    // primitives.tsx, one directory over, already steps to days; so does this one.
    return t('agentPanel.daysAgo', { count: Math.round(h / 24) })
  }

  // Directory pages minus the rows the conversation already shows live.
  const backendIds = useMemo(
    () => new Set(agents.map((a) => backendAgentId(a.label)).filter(Boolean) as string[]),
    [agents],
  )
  const dirAgents = useMemo(
    () => (dirPage ?? []).filter((d) => !backendIds.has(d.agent_id)),
    [dirPage, backendIds],
  )

  const detailBlock = (backendId: string) =>
    openId === backendId && (
      <SubagentDetailBlock backendId={backendId} detail={detail} liveDur={liveDur} />
    )

  // M2 (visible planning): row = numbered step (#n) + icon + name + status word +
  // the time on the right; the detail as its own truncated row underneath.
  const Row = ({ a, n }: { a: (typeof agents)[number]; n: number }) => {
    const backendId = backendAgentId(a.label)
    return (
      <div
        data-testid={`subagent-row-${a.id}`}
        onClick={backendId ? () => setOpenId(openId === backendId ? null : backendId) : undefined}
        className={`w-full text-left rounded-lg border border-hairline bg-canvas px-3 py-2.5 ${
          backendId ? 'cursor-pointer' : ''
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-ui-xs font-mono text-ink-faint shrink-0 tabular-nums">#{n}</span>
          {a.status === 'running' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-brand/80 shrink-0" />
          ) : a.status === 'failed' ? (
            <XCircle className="h-3.5 w-3.5 text-status-danger/80 shrink-0" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-status-success/60 shrink-0" />
          )}
          <span className="flex-1 min-w-0 truncate text-ui-xs text-foreground/80">{a.label}</span>
          <span
            data-testid={`subagent-state-${a.id}`}
            className={`text-ui-xs shrink-0 ${a.status === 'failed' ? 'text-status-danger/80' : 'text-ink-faint'}`}
          >
            {a.status === 'running'
              ? t('agentPanel.subagentRunning')
              : a.status === 'failed'
                ? t('agentPanel.subagentFailed')
                : t('agentPanel.subagentCompleted')}
          </span>
          {a.status !== 'running' && (
            <span
              data-testid={`subagent-time-${a.id}`}
              className="text-ui-xs text-ink-faint shrink-0 min-w-8 text-right"
            >
              {relTime(a.at)}
            </span>
          )}
          {backendId && <OpenHelperChatButton agentId={backendId} onOpen={openHelper} />}
        </div>
        {a.detail && (
          <p
            data-testid={`subagent-detail-${a.id}`}
            className="mt-1.5 pl-6 text-ui-sm leading-relaxed text-ink-soft truncate"
          >
            {a.detail}
          </p>
        )}
        {backendId && detailBlock(backendId)}
      </div>
    )
  }

  // P6 B1 (ref-02): a history row from the REST directory — same row anatomy, the
  // detail runs through the very same openId/getSubagent polling.
  const DirectoryRow = ({ d, n }: { d: SubagentSummary; n: number }) => (
    <div
      data-testid={`subagent-directory-row-${d.agent_id}`}
      onClick={() => setOpenId(openId === d.agent_id ? null : d.agent_id)}
      className="w-full cursor-pointer text-left rounded-lg border border-hairline bg-canvas px-3 py-2.5"
    >
      <div className="flex items-center gap-2">
        <span className="text-ui-xs font-mono text-ink-faint shrink-0 tabular-nums">#{n}</span>
        {d.status === 'running' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-brand/80 shrink-0" />
        ) : d.status === 'error' || d.status === 'failed' ? (
          <XCircle className="h-3.5 w-3.5 text-status-danger/80 shrink-0" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 text-status-success/60 shrink-0" />
        )}
        <span className="flex-1 min-w-0 truncate text-ui-xs text-foreground/80">
          {d.description || d.task || d.agent_id}
        </span>
        <span className="text-ui-xs text-ink-faint shrink-0">
          {d.status === 'running'
            ? t('agentPanel.subagentRunning')
            : d.status === 'error' || d.status === 'failed'
              ? t('agentPanel.subagentFailed')
              : t('agentPanel.subagentCompleted')}
        </span>
        {d.duration_ms != null && (
          <span className="text-ui-xs font-mono text-ink-faint shrink-0 tabular-nums">
            {fmtMs(d.duration_ms)}
          </span>
        )}
        {d.started_ts != null && (
          <span className="text-ui-xs text-ink-faint shrink-0 min-w-8 text-right">
            {relTime(d.started_ts * 1000)}
          </span>
        )}
        <OpenHelperChatButton
          agentId={d.agent_id}
          chatSessionId={d.chat_session_id}
          onOpen={openHelper}
        />
      </div>
      {detailBlock(d.agent_id)}
    </div>
  )

  const endedCount = ended.length + dirAgents.length
  const emptyAll =
    agents.length === 0 && (dirPage === null || (dirAgents.length === 0 && !dirError))

  return (
    <div className="flex-1 min-h-0 flex flex-col" data-testid="subagents-view">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-hairline shrink-0">
        <Bot className="h-3.5 w-3.5 text-brand/60 shrink-0" aria-hidden="true" />
        <h2 className="text-ui-sm font-semibold text-foreground/90">
          {t('agentPanel.tabSubagents')}
        </h2>
      </div>
      {dirError && (
        <div className="flex items-center gap-2 px-3 py-1.5 shrink-0">
          <p role="alert" className="min-w-0 flex-1 truncate text-ui-xs text-destructive font-mono">
            {t('agentPanel.error')}
            {dirError ? `: ${dirError}` : ''}
          </p>
          <button
            type="button"
            data-testid="subagents-dir-retry"
            onClick={() => void loadDir()}
            className="shrink-0 rounded-md border border-hairline px-2 py-1 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors"
          >
            {t('agentPanel.retry')}
          </button>
        </div>
      )}
      {emptyAll ? (
        <div
          className="flex-1 flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center"
          data-testid="subagents-empty"
        >
          <Bot className="h-10 w-10 opacity-40" />
          <p>{t('agentPanel.subagentsEmpty')}</p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-4">
          {/* M1 (ref-02): both sections are always present — 'Running · 0' with an empty
              row, 'Ended · 0' with an empty row, the header never disappears. */}
          <section data-testid="subagents-running-section">
            <p className="py-1 px-1 text-ui-xs font-medium text-ink-faint uppercase tracking-wider">
              {t('agentPanel.subagentsRunning', { count: running.length })}
            </p>
            {running.length === 0 ? (
              <p data-testid="subagents-none-row" className="pl-1 py-1 text-ui-xs text-ink-faint">
                {t('agentPanel.noRunningAgents')}
              </p>
            ) : (
              <div className="space-y-1.5 mt-1">
                {running.map((a, i) => (
                  <Row key={a.id} a={a} n={i + 1} />
                ))}
              </div>
            )}
          </section>
          <section data-testid="subagents-ended-section">
            <p className="py-1 px-1 text-ui-xs font-medium text-ink-faint uppercase tracking-wider">
              {t('agentPanel.subagentsEnded', { count: endedCount })}
            </p>
            {endedCount === 0 ? (
              <p
                data-testid="subagents-ended-none-row"
                className="pl-1 py-1 text-ui-xs text-ink-faint"
              >
                {t('agentPanel.subagentsNoneEnded')}
              </p>
            ) : (
              <div className="space-y-1.5 mt-1">
                {ended.map((a, i) => (
                  <Row key={a.id} a={a} n={i + 1} />
                ))}
                {dirAgents.map((d, i) => (
                  <DirectoryRow key={d.agent_id} d={d} n={ended.length + i + 1} />
                ))}
              </div>
            )}
            {dirCursor && (
              <button
                type="button"
                data-testid="subagents-show-more"
                onClick={() => void loadDir(dirCursor, true)}
                className="mt-2 w-full rounded-lg border border-hairline px-3 py-2 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors"
              >
                {t('agentPanel.showMore')}
              </button>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
