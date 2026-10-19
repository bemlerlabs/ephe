// H-round H3 (2026-09-07): status display top right like the reference —
// a compact pill shows live what the agent is working on (running activity
// from the active message); the click opens a popover with activity,
// running sub-agents and open tasks. Every entry jumps per
// PREVIEW_OPEN_EVENT into the matching pane tab — everything wired smartly,
// except the steps ledger: its one surface is its page in the settings.
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, CircleDot, ChevronDown, ListTodo, Bot, ChevronRight } from 'lucide-react'
import type { ChatMessage } from '@/types'
import { getTasks, type TaskItem } from '@/lib/api'
// gitStatus straight from misc — the barrel mocking of the many status tests is
// partial; the environment check must not break it hard (fetched only
// when opening, error case => no section).
import { gitStatus } from '@/lib/api/misc'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import MetricsGauges, { useSystemMetrics } from './MetricsGauges'
import { ToolbarMeta } from './StatusMeta'
import { SkyStatusLine } from './SkyCard'
import {
  useStatusPanelData,
  TurnTimerRow,
  ProgressSection,
  QueryMapSection,
  StatusSection,
  GoalSection,
  EnvironmentSection,
  UsageSection,
} from './AgentStatusSections'

const COLLAPSED_KEY = 'ephe_status_collapsed'

interface AgentRun {
  id: string
  label: string
  status: 'running' | 'done' | 'failed'
  detail?: string
}

export default function AgentStatusButton({
  messages = [],
  sessionId,
}: {
  messages?: ChatMessage[]
  sessionId?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // Owner parity (2026-09-08): the popover collapses and expands like the
  // reference — the header stays put, the content folds away. The
  // state is persisted and survives remounts.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSED_KEY) === '1'
    } catch {
      return false
    }
  })
  const toggleCollapse = () => {
    const next = !collapsed
    setCollapsed(next)
    try {
      window.localStorage.setItem(COLLAPSED_KEY, next ? '1' : '0')
    } catch {
      /* private mode */
    }
  }
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const systemMetrics = useSystemMetrics()
  const pillRef = useRef<HTMLButtonElement>(null)
  // S3 workbench: the pill lives at the BOTTOM of the status line — top-anchored put
  // the popover below the viewport and the owner saw "nothing". When the
  // space underneath does not suffice, the panel opens UPWARDS.
  const [popPos, setPopPos] = useState<{ top?: number; bottom?: number; right: number } | null>(
    null,
  )
  const openPopover = () => {
    const el = pillRef.current
    if (el) {
      const r = el.getBoundingClientRect()
      const right = window.innerWidth - r.right
      const spaceBelow = window.innerHeight - r.bottom
      const POP_MIN = 240
      if (spaceBelow < POP_MIN && r.top > window.innerHeight / 2) {
        setPopPos({ bottom: window.innerHeight - r.top + 8, right })
      } else {
        setPopPos({ top: r.bottom + 8, right })
      }
    }
    setOpen((v) => !v)
  }

  // U1b: Escape dismisses the status popover (keyboard parity with menus).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // Light task poll (10s) — the status stays alive even when the pane is closed.
  // Finding 2026-10-02: it kept polling in a hidden tab too (CPU/battery). Gating
  // like MetricsGauges: only on a visible tab, pause on visibilitychange.
  useEffect(() => {
    let cancelled = false
    let handle: number | null = null
    const load = () =>
      getTasks()
        .then((r) => {
          if (!cancelled) setTasks(Array.isArray(r) ? r : [])
        })
        .catch(() => {})
    const start = () => {
      if (handle !== null) return
      load()
      handle = window.setInterval(load, 10_000)
    }
    const stop = () => {
      if (handle !== null) {
        window.clearInterval(handle)
        handle = null
      }
    }
    const onVisibility = () => (document.hidden ? stop() : start())
    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const runs = useMemo<AgentRun[]>(() => {
    const out: AgentRun[] = []
    for (const m of messages) {
      for (const a of m.activities ?? []) {
        if (!/agent|swarm/i.test(a.label)) continue
        out.push({ id: a.id, label: a.label, status: a.status, detail: a.detail })
      }
    }
    return out
  }, [messages])

  // [F10]/progress/[F9]: timer, plan state and query map come from the
  // shared hook (AgentStatusSections.tsx).
  const { activeTurn, plan, queries, elapsed, goal, goalRun, jumpToQuery } =
    useStatusPanelData(messages)
  const onJump = (messageId: string) => {
    jumpToQuery(messageId)
    setOpen(false)
  }

  // P6 B3 (environment): git context of the session — fetch when the popup
  // opens (not polling; branch/changes do not change every second).
  const [git, setGit] = useState<{ branch: string; changes: number } | null>(null)
  useEffect(() => {
    if (!open) return
    let cancelled = false
    gitStatus()
      .then((r) => {
        if (!cancelled && r.git) setGit({ branch: r.branch, changes: r.changes.length })
      })
      .catch(() => {
        if (!cancelled) setGit(null)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const running = runs.filter((r) => r.status === 'running')
  const runningTasks = tasks.filter((x) => x.status !== 'done')
  // "Working" is now turn-parity: a simple stream without
  // sub-agent activity counts too (the reference shows "Working for 29s" per turn).
  const working = running.length > 0 || Boolean(activeTurn)
  const current = running[0]

  const openTab = (tab: string) => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
    setOpen(false)
  }

  /** The ledger's one surface is its settings page — the two events the palette sends. */
  const openStepsPage = () => {
    window.dispatchEvent(new CustomEvent('ephe:open-settings'))
    window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'tasks' } }))
    setOpen(false)
  }

  return (
    <div className="relative flex items-center gap-1.5" data-testid="agent-status">
      <button
        type="button"
        data-testid="agent-status-expand"
        onClick={openPopover}
        title={t('agentStatus.title')}
        className="rounded-full border border-control bg-canvas px-2 py-1 text-ui-xs font-medium text-ink-soft hover:text-foreground/80 transition-colors whitespace-nowrap shrink-0"
      >
        {t('agentStatus.expandStatus')}
      </button>
      <button
        ref={pillRef}
        type="button"
        data-testid="agent-status-pill"
        aria-expanded={open}
        onClick={openPopover}
        title={t('agentStatus.title')}
        className={`flex items-center gap-1.5 pl-2 pr-1.5 py-1 rounded-full text-ui-sm font-medium transition-colors border min-h-9 max-lg:min-h-11 ${working ? 'border-brand/30 bg-brand/10 text-brand-deep' : 'border-control bg-canvas text-ink-soft hover:text-foreground/80'}`}
      >
        {working ? (
          <Loader2 className="h-3 w-3 animate-spin shrink-0" />
        ) : (
          <CircleDot className="h-3 w-3 shrink-0" />
        )}
        {working ? (
          <span data-testid="agent-status-activity" className="max-w-40 truncate">
            {current ? current.label : t('agentStatus.workingFor', { time: elapsed ?? '' })}
          </span>
        ) : (
          <span className="max-w-32 truncate">{t('agentStatus.idle')}</span>
        )}
        {runningTasks.length > 0 && (
          <span className="rounded-full bg-surface px-1.5 text-ui-xs font-mono shrink-0">
            {runningTasks.length}
          </span>
        )}
        <ChevronDown
          className={`h-3 w-3 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open &&
        popPos &&
        createPortal(
          <>
            <div
              className="fixed inset-0 z-modal"
              aria-hidden="true"
              onClick={() => setOpen(false)}
            />
            <div
              data-testid="agent-status-popover"
              style={{
                position: 'fixed',
                top: popPos.top,
                bottom: popPos.bottom,
                right: popPos.right,
              }}
              className="z-modal w-72 float-surface p-3 max-h-96 overflow-y-auto"
            >
              <div className="flex items-center justify-between mb-1">
                <p className="text-ui-xs font-semibold text-foreground/90">
                  {t('agentStatus.title')}
                </p>
                <button
                  type="button"
                  data-testid="agent-status-collapse"
                  aria-label={collapsed ? t('agentStatus.expand') : t('agentStatus.collapse')}
                  onClick={toggleCollapse}
                  className="p-1 rounded-md text-ink-faint hover:text-foreground hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                >
                  <ChevronDown
                    className={`h-3.5 w-3.5 transition-transform ${collapsed ? 'rotate-180' : ''}`}
                  />
                </button>
              </div>

              {collapsed && (
                <div
                  data-testid="agent-status-collapsed-summary"
                  className="flex items-center gap-2 px-0.5 py-1"
                >
                  {working ? (
                    <>
                      <Loader2 className="h-3 w-3 animate-spin text-brand/80 shrink-0" />
                      <span className="flex-1 min-w-0 truncate text-ui-sm text-foreground/70">
                        {current
                          ? current.label
                          : t('agentStatus.workingFor', { time: elapsed ?? '' })}
                      </span>
                    </>
                  ) : (
                    <>
                      <CircleDot className="h-3 w-3 text-ink-faint shrink-0" />
                      <span className="flex-1 text-ui-sm text-ink-faint">
                        {t('agentStatus.idle')}
                      </span>
                    </>
                  )}
                  {runningTasks.length > 0 && (
                    <span className="text-ui-xs font-mono text-ink-faint shrink-0">
                      {t('agentStatus.openCount', { count: runningTasks.length })}
                    </span>
                  )}
                </div>
              )}

              {!collapsed && (
                <div data-testid="agent-status-body">
                  {activeTurn && elapsed && <TurnTimerRow elapsed={elapsed} />}
                  {/* P6 B3: goal + environment only with data (section catalogue). */}
                  {goal && <GoalSection goal={goal} run={goalRun} />}
                  {git && <EnvironmentSection branch={git.branch} changes={git.changes} />}
                  <UsageSection />
                  {current && (
                    <section className="mb-2" data-testid="agent-status-running-section">
                      <p className="text-ui-xs uppercase tracking-wide text-ink-faint mb-1">
                        {t('agentStatus.activitySection')}
                      </p>
                      <div className="flex items-start gap-2 rounded-lg bg-brand/10 border border-brand/20 px-2.5 py-2">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand/80 shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <p className="text-ui-xs text-foreground/80 truncate">{current.label}</p>
                          {current.detail && (
                            <p className="text-ui-sm text-ink-soft line-clamp-2">
                              {current.detail}
                            </p>
                          )}
                        </div>
                      </div>
                    </section>
                  )}

                  {plan && plan.items.length > 0 && <ProgressSection plan={plan} />}

                  {queries.length > 0 && <QueryMapSection queries={queries} onJump={onJump} />}

                  {running.length > 0 && (
                    <StatusSection
                      kind="agent"
                      title={t('agentStatus.subagentsSection')}
                      testId="agent-status-agents"
                    >
                      {running.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          data-testid={`agent-status-subagent-${r.id}`}
                          onClick={() => openTab('subagents')}
                          className="w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                        >
                          <Bot className="h-3.5 w-3.5 text-brand/70 shrink-0" />
                          <span className="flex-1 min-w-0 truncate text-ui-xs text-foreground/80">
                            {r.label}
                          </span>
                          <ChevronRight className="h-3 w-3 text-ink-faint shrink-0" />
                        </button>
                      ))}
                    </StatusSection>
                  )}

                  <section>
                    <button
                      type="button"
                      data-testid="agent-status-tasks-link"
                      onClick={() => openStepsPage()}
                      className="w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                    >
                      <ListTodo className="h-3.5 w-3.5 text-ink-faint shrink-0" />
                      <span className="flex-1 text-ui-xs text-foreground/80">
                        {t('agentStatus.tasksSection')}
                      </span>
                      <span
                        data-testid="agent-status-task-count"
                        className="text-ui-xs font-mono text-ink-faint shrink-0"
                      >
                        {t('agentStatus.openCount', { count: runningTasks.length })}
                      </span>
                      <ChevronRight className="h-3 w-3 text-ink-faint shrink-0" />
                    </button>
                    {runningTasks.slice(0, 3).map((x) => (
                      <p key={x.id} className="pl-8 pr-2 py-0.5 text-ui-sm text-ink-faint truncate">
                        {x.title}
                      </p>
                    ))}
                  </section>
                  {/* E-phase UX: CPU/RAM/disk gauges + uptime/auto-read-aloud live
                in the expandable status — the visible status line stays minimal:
                one pill per fact, nothing more. */}
                  <section className="pt-1.5">
                    {/* S4 workbench parity: the ephemerides in the status too —
                        "where do I see this?" now has an answer. */}
                    <SkyStatusLine />
                    <MetricsGauges metrics={systemMetrics} />
                    <ToolbarMeta sessionId={sessionId} />
                  </section>
                </div>
              )}
            </div>
          </>,
          document.body,
        )}
    </div>
  )
}
