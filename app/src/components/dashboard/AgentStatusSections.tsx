// P0 macro plan (2026-09-28): the three reference sections of the „Expand status“
// panel as separate building blocks — [F10] turn timer („Working for Xm Ys“),
// the progress checklist (Plan · n/m) and [F9] the query map („Jump to query N“).
// Data + logic live in the hook, the components are purely presentational.
// P6 B2/B3: each section is its own collapsible with a chevron (hover only) and its
// own scroll policy; goal/environment complete the section catalogue.
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'
import {
  Loader2,
  Check,
  ArrowRight,
  Circle,
  AlertCircle,
  Minus,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Target,
} from 'lucide-react'
import type { ChatMessage, GoalRunState } from '@/types'
import { QUERY_JUMP_EVENT } from '@/lib/panelEvents'
import { parsePlanCard, type PlanCardSpec } from '@/lib/planCardModel'
import { formatDuration } from '@/lib/duration'
import { STATUS_SECTION_SCROLL_POLICY, type StatusSectionKind } from './agent/statusSectionPolicy'

export interface StatusPanelData {
  activeTurn: ChatMessage | null
  plan: PlanCardSpec | null
  queries: ChatMessage[]
  elapsed: string | null
  goal: string | null
  /** The goal run of the newest turn that has one — the loop's own state, not a guess. */
  goalRun: GoalRunState | null
  jumpToQuery: (messageId: string) => void
}

export function useStatusPanelData(messages: ChatMessage[]): StatusPanelData {
  // [F10] turn timer: the running assistant message carries its turn start as
  // timestamp — that is what feeds „Working for Xm Ys“ (reference parity), with a
  // 1s tick only while a turn is active.
  const activeTurn = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (!m) continue
      if (m.role === 'assistant' && m.streaming) return m
    }
    return null
  }, [messages])
  const activeTurnId = activeTurn?.id
  const [nowTick, setNowTick] = useState(() => Date.now())
  useEffect(() => {
    if (!activeTurnId) return
    setNowTick(Date.now())
    const handle = setInterval(() => setNowTick(Date.now()), 1000)
    return () => clearInterval(handle)
  }, [activeTurnId])

  // Progress checklist: the plan of the newest turn that has one. The `plan` frame wins
  // where it arrived (it carries state the text cannot); the answer text is the fallback,
  // so a replayed session from before the frame still shows its plan here.
  const plan = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (!m || m.role !== 'assistant') continue
      if (m.plan) return m.plan
      const p = parsePlanCard(m.content)
      if (p) return p
    }
    return null
  }, [messages])

  // [F9] Query map: the session's user queries, numbered — a click jumps to the
  // message in the chat via QUERY_JUMP_EVENT (virtualizer scroll, pattern: handleRailSelect).
  const queries = useMemo(
    () => messages.filter((m) => m.role === 'user' && m.content.trim().length > 0),
    [messages],
  )
  const jumpToQuery = (messageId: string) => {
    window.dispatchEvent(new CustomEvent(QUERY_JUMP_EVENT, { detail: { messageId } }))
  }

  // P6 B3: the goal of the session, from the goal run's own state — the `goal_start`
  // frame carries core/goal_loop.py's goal, so the panel shows that and not a guess.
  const goalRun = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const run = messages[i]?.goal
      if (run && run.goal.trim()) return run
    }
    return null
  }, [messages])
  const goal = useMemo(() => {
    if (goalRun) return goalRun.goal.trim()
    // Fallback: the opening query's first line — all a chat without a goal run has.
    const first = messages.find((m) => m.role === 'user')
    const line = first?.content.trim().split('\n')[0]?.trim()
    return line ? line : null
  }, [messages, goalRun])

  const elapsed = activeTurn ? formatDuration(nowTick - activeTurn.timestamp) : null
  return { activeTurn, plan, queries, elapsed, goal, goalRun, jumpToQuery }
}

/** P6 B2: section as its own collapsible — chevron on hover only,
 *  body with the max-h policy from statusSectionPolicy.ts. */
export function StatusSection({
  kind,
  title,
  trailing,
  testId,
  children,
}: {
  kind: StatusSectionKind
  title: string
  trailing?: React.ReactNode
  testId?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <section className="group mb-2" data-status-section={kind} data-testid={testId}>
      <button
        type="button"
        data-testid={`status-section-head-${kind}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-full items-center gap-1.5 rounded-md px-2 pr-8 text-left hover:bg-surface transition-colors"
      >
        <span className="flex-1 min-w-0 truncate text-ui-xs uppercase tracking-wide text-ink-faint">
          {title}
        </span>
        {trailing}
        <ChevronDown
          className={`size-3.5 shrink-0 text-ink-faint transition-all ${
            open ? 'rotate-0' : '-rotate-90'
          } opacity-0 group-hover:opacity-100`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div
          data-testid={`status-section-body-${kind}`}
          className={`overflow-y-auto ${STATUS_SECTION_SCROLL_POLICY[kind] ?? ''}`}
        >
          {children}
        </div>
      )}
    </section>
  )
}

/** P6 B3: goal section — with a goal run on, the loop's own goal: the command it is
 *  judged by, the round it is in and that round's verdict; otherwise the opening line. */
export function GoalSection({ goal, run }: { goal: string; run?: GoalRunState | null }) {
  const { t } = useTranslation()
  // null = this round's check has not answered yet, and no round has run before.
  const verdict = !run || run.ok === null ? 'running' : run.ok ? 'passed' : 'failed'
  return (
    <StatusSection kind="goal" title={t('agentStatus.goalSection')} testId="agent-status-goal">
      <p
        data-testid="agent-status-goal-text"
        className="rounded-lg border border-hairline bg-canvas px-2 py-1.5 text-ui-xs leading-relaxed text-foreground/80 line-clamp-4"
      >
        <Target
          className="mr-1.5 inline h-3 w-3 text-firefly/80 align-baseline"
          aria-hidden="true"
        />
        {goal}
      </p>
      {run && (
        <p
          data-testid="agent-status-goal-check"
          data-status={verdict}
          className="mt-1 flex items-center gap-2 rounded-lg border border-hairline bg-canvas px-2 py-1.5 text-ui-xs text-foreground/80"
        >
          {verdict === 'running' ? (
            <Loader2 className="h-3 w-3 shrink-0 animate-spin text-firefly" aria-hidden="true" />
          ) : verdict === 'passed' ? (
            <Check className="h-3 w-3 shrink-0 text-status-success" aria-hidden="true" />
          ) : (
            <AlertCircle className="h-3 w-3 shrink-0 text-status-danger" aria-hidden="true" />
          )}
          <span className="font-mono truncate">{run.check}</span>
          <span
            data-testid="agent-status-goal-turn"
            className="ml-auto shrink-0 font-mono text-ink-faint"
          >
            {run.turn}/{run.maxTurns}
          </span>
        </p>
      )}
    </StatusSection>
  )
}

/** P6 B3: environment section — Git branch + change counter, only when it has data. */
export function EnvironmentSection({ branch, changes }: { branch: string; changes: number }) {
  const { t } = useTranslation()
  return (
    <StatusSection
      kind="environment"
      title={t('agentStatus.environmentSection')}
      testId="agent-status-environment"
    >
      <p
        data-testid="agent-status-environment-line"
        className="flex items-center gap-2 rounded-lg border border-hairline bg-canvas px-2 py-1.5 text-ui-xs text-foreground/80"
      >
        <GitBranch className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
        <span className="font-mono truncate">{branch}</span>
        <span className="ml-auto shrink-0 font-mono text-ink-faint">
          {t('agentStatus.environmentChanges', { count: changes })}
        </span>
      </p>
    </StatusSection>
  )
}

/** [F10] Live turn duration, the same way the reference shows it („Working for 29s“). */
export function TurnTimerRow({ elapsed }: { elapsed: string }) {
  const { t } = useTranslation()
  return (
    <p
      data-testid="agent-status-timer"
      className="flex items-center gap-1.5 px-0.5 pb-1.5 text-ui-xs text-ink-soft"
    >
      <Loader2 className="h-3 w-3 animate-spin shrink-0" />
      {t('agentStatus.workingFor', { time: elapsed })}
    </p>
  )
}

/** Progress checklist: live state of the task plan (✓ done, → active, ○ open). */
export function ProgressSection({ plan }: { plan: PlanCardSpec }) {
  const { t } = useTranslation()
  return (
    <StatusSection
      kind="plan"
      title={t('agentStatus.progressSection')}
      testId="agent-status-progress"
      trailing={
        <span
          data-testid="agent-status-progress-count"
          className="text-ui-xs font-mono text-ink-faint"
        >
          {plan.done}/{plan.total}
        </span>
      }
    >
      <ul className="rounded-lg border border-hairline bg-canvas px-2 py-1.5 space-y-1">
        {plan.items.map((item, i) => (
          <li
            key={i}
            data-testid={`agent-status-progress-item-${i}`}
            data-status={item.status}
            className="flex items-start gap-1.5 text-ui-xs"
          >
            {item.status === 'done' ? (
              <Check className="h-3 w-3 mt-0.5 text-status-success shrink-0" />
            ) : item.status === 'active' ? (
              <ArrowRight className="h-3 w-3 mt-0.5 text-firefly shrink-0" />
            ) : item.status === 'failed' ? (
              <AlertCircle className="h-3 w-3 mt-0.5 text-status-danger shrink-0" />
            ) : item.status === 'cancelled' ? (
              <Minus className="h-3 w-3 mt-0.5 text-ink-faint shrink-0" />
            ) : (
              <Circle className="h-3 w-3 mt-0.5 text-ink-faint shrink-0" />
            )}
            <span
              className={
                item.status === 'done'
                  ? 'text-ink-faint line-clamp-2 line-through'
                  : 'text-foreground/80 line-clamp-2'
              }
            >
              {item.text}
            </span>
          </li>
        ))}
      </ul>
    </StatusSection>
  )
}

/** [F9] Query map: „Jump to query N“ over every user query of the session. */
export function QueryMapSection({
  queries,
  onJump,
}: {
  queries: ChatMessage[]
  onJump: (messageId: string) => void
}) {
  const { t } = useTranslation()
  return (
    <StatusSection
      kind="queries"
      title={t('agentStatus.queryMapSection')}
      testId="agent-status-query-map"
    >
      <div className="space-y-0.5">
        {queries.map((q, i) => (
          <button
            key={q.id}
            type="button"
            data-testid={`agent-status-jump-${i}`}
            data-message-id={q.id}
            aria-label={t('agentStatus.jumpToQuery', { n: i + 1 })}
            onClick={() => onJump(q.id)}
            className="w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            <span className="w-4 shrink-0 text-right font-mono text-ui-xs text-ink-faint">
              {i + 1}
            </span>
            <span className="flex-1 min-w-0 truncate text-ui-xs text-foreground/80">
              {q.content.trim().split('\n')[0]}
            </span>
            <ChevronRight className="h-3 w-3 shrink-0 text-ink-faint" />
          </button>
        ))}
      </div>
    </StatusSection>
  )
}

// ── Wave 3: Kosten & Verbrauch (7/30 days, content-free) ── // language-gate: ignore (de.json renders this section title)

/**
 * UsageSection — the „Kosten & Verbrauch" block in the Expand-status popover. // language-gate: ignore (label de.json renders verbatim)
 * Self-fetching: /api/usage/summary (30-day window). Shows today/7/30 from the
 * content-free usage ledger; USD only while engine.json maintains pricing.
 * No data → no section (never an empty promise).
 */
export function UsageSection() {
  const { t, i18n } = useTranslation()
  const [data, setData] = useState<import('@/lib/api').UsageSummary | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    import('@/lib/api')
      .then(({ getUsageSummary }) => getUsageSummary(30))
      .then((r) => {
        if (!cancelled) setData(r)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (failed || !data || data.totals.turns === 0) return null

  const day = data.by_day[0] ?? { in: 0, out: 0, cached: 0, turns: 0 }
  const week = data.by_day
    .slice(0, 7)
    .reduce((acc, d) => ({ in: acc.in + d.in, out: acc.out + d.out }), { in: 0, out: 0 })
  const fmt = (n: number) => formatNumber(n, i18n.language)
  const usd = (i: number, o: number) => {
    const p = data.pricing
    if (!p) return null
    const v = (i / 1_000_000) * (p.in_per_m ?? 0) + (o / 1_000_000) * (p.out_per_m ?? 0)
    return v > 0 && v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`
  }

  const rows: Array<{ label: string; i: number; o: number }> = [
    { label: t('agentStatus.usageToday'), i: day.in, o: day.out },
    { label: t('agentStatus.usage7d'), i: week.in, o: week.out },
    { label: t('agentStatus.usage30d'), i: data.totals.in, o: data.totals.out },
  ]

  return (
    <StatusSection kind="usage" title={t('agentStatus.usageTitle')} testId="agent-status-usage">
      <div className="space-y-1">
        {rows.map((r) => {
          const cost = usd(r.i, r.o)
          return (
            <div
              key={r.label}
              className="flex items-center justify-between text-ui-xs text-ink-soft"
            >
              <span>{r.label}</span>
              <span className="font-mono tabular-nums">
                {fmt(r.i)} / {fmt(r.o)}
                {cost && <span className="ml-1.5 text-brand/90">{cost}</span>}
              </span>
            </div>
          )
        })}
        {data.totals.est_turns > 0 && (
          <p className="text-ui-xs text-ink-faint">
            {t('agentStatus.usageEstimated', { count: data.totals.est_turns })}
          </p>
        )}
      </div>
    </StatusSection>
  )
}
