/**
 * Direct unit tests for AgentStatusSections.tsx — the building blocks of the
 * „Expand status“ popup (hook + six sections).
 *
 * Complements AgentStatusButton.statusPanel.test.tsx, which reaches timer /
 * progress / query-map / collapse only through the button. Here each piece gets
 * its own unit test — most importantly UsageSection (self-fetching, never
 * exercised by the indirect test) and the hook edge cases (plan precedence,
 * blank queries, goal, elapsed ticker).
 *
 * jsdom cannot measure layout — pinned are text, roles, aria state, data-*
 * attributes and utility classes, never pixels.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'

import {
  EnvironmentSection,
  GoalSection,
  ProgressSection,
  QueryMapSection,
  StatusSection,
  TurnTimerRow,
  UsageSection,
  useStatusPanelData,
} from './AgentStatusSections'
import {
  STATUS_SECTION_SCROLL_POLICY,
  type StatusSectionKind,
} from './agent/statusSectionPolicy'
import { QUERY_JUMP_EVENT } from '@/lib/panelEvents'
import type { ChatMessage, PlanCardSpec, PlanItemStatus } from '@/types'
import type { UsageDay, UsageSummary } from '@/lib/api'

// i18n: the agentStatus.* wording, {{x}} interpolated
const DE: Record<string, string> = {
  'agentStatus.workingFor': 'Working since {{time}}',
  'agentStatus.progressSection': 'Progress',
  'agentStatus.queryMapSection': 'Questions in this task',
  'agentStatus.goalSection': 'Goal',
  'agentStatus.environmentSection': 'Environment (Git)',
  'agentStatus.environmentChanges': '{{count}} changes',
  'agentStatus.jumpToQuery': 'Jump to question {{n}}',
  'agentStatus.usageTitle': 'Cost & usage',
  'agentStatus.usageToday': 'Today',
  'agentStatus.usage7d': 'Last 7 days',
  'agentStatus.usage30d': 'Last 30 days',
  'agentStatus.usageEstimated':
    '{{count}} turns estimated (no provider usage frame) — marked honestly.',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    // 'de' pins the number grouping: formatNumber(10499, 'de') → '10.499',
    // so a component that dropped the language would fail loudly.
    i18n: { language: 'de' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      // Like the real i18next: {{placeholders}} are filled from the options.
      const raw = DE[key] ?? (o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        o && o[name] !== undefined ? String(o[name]) : `{{${name}}}`,
      )
    },
  }),
}))

// api: UsageSection loads getUsageSummary via a dynamic import('@/lib/api');
// deepSettings (pulled in through duration.ts) statically imports getSettings.
const api = vi.hoisted(() => ({
  getUsageSummary: vi.fn<() => Promise<UsageSummary>>(),
  getSettings: vi.fn(async () => ({ workspace_dir: '/ws' })),
}))
vi.mock('@/lib/api', () => api)

// helpers
let seq = 0
const msg = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  id: `m${++seq}`,
  role: 'assistant',
  content: '',
  timestamp: Date.now(),
  ...over,
})

const flushPromises = () => act(async () => { await Promise.resolve() })

// useStatusPanelData: plan precedence (frame wins, text is the fallback)
describe('useStatusPanelData — plan precedence', () => {
  const framePlan: PlanCardSpec = {
    items: [{ status: 'done', text: 'From the frame' }],
    done: 1,
    total: 1,
  }

  it('prefers the plan frame on the message over parsing its content', () => {
    const turn = msg({
      role: 'assistant',
      plan: framePlan,
      content: '## Plan\n- [x] parsed A\n- [ ] parsed B',
    })
    const { result } = renderHook(() => useStatusPanelData([turn]))
    expect(result.current.plan).toBe(framePlan)
  })

  it('falls back to parsePlanCard(content) when no frame arrived', () => {
    const turn = msg({
      role: 'assistant',
      content: '## Plan\n- [x] Read routes\n- [ ] Add the case',
    })
    const { result } = renderHook(() => useStatusPanelData([turn]))
    expect(result.current.plan).toEqual({
      items: [
        { status: 'done', text: 'Read routes' },
        { status: 'pending', text: 'Add the case' },
      ],
      done: 1,
      total: 2,
    })
  })

  it('takes the newest assistant turn that carries a plan', () => {
    const older = msg({ role: 'assistant', plan: framePlan, content: '' })
    const newer = msg({ role: 'assistant', content: '## Plan\n- [ ] Only step\n- [ ] Second step' })
    const { result } = renderHook(() => useStatusPanelData([older, newer]))
    expect(result.current.plan?.items.map((i) => i.text)).toEqual(['Only step', 'Second step'])
  })

  it('skips plan-less assistant turns and user messages', () => {
    const withPlan = msg({ role: 'assistant', plan: framePlan, content: '' })
    const plain = msg({ role: 'assistant', content: 'Just prose, no list.' })
    const user = msg({ role: 'user', content: '## Plan\n- [x] not mine\n- [ ] not mine either' })
    const { result } = renderHook(() => useStatusPanelData([withPlan, plain, user]))
    expect(result.current.plan).toBe(framePlan)
  })

  it('returns null when no message carries a plan', () => {
    const { result } = renderHook(() =>
      useStatusPanelData([msg({ role: 'user', content: 'hi' }), msg({ content: 'hello' })]),
    )
    expect(result.current.plan).toBeNull()
  })
})

// useStatusPanelData: queries, goal, jump event
describe('useStatusPanelData — queries, goal, jump', () => {
  it('lists only non-blank user messages as queries', () => {
    const u1 = msg({ role: 'user', content: 'First question' })
    const a1 = msg({ role: 'assistant', content: 'Answer' })
    const blank = msg({ role: 'user', content: '   \n  ' })
    const u2 = msg({ role: 'user', content: 'Second question' })
    const { result } = renderHook(() => useStatusPanelData([u1, a1, blank, u2]))
    expect(result.current.queries.map((q) => q.id)).toEqual([u1.id, u2.id])
  })

  it('jumpToQuery dispatches QUERY_JUMP_EVENT with the message id', () => {
    const u1 = msg({ role: 'user', content: 'First question' })
    const { result } = renderHook(() => useStatusPanelData([u1]))
    const seen: Array<{ type: string; messageId?: string }> = []
    const listener = (e: Event) => {
      seen.push({
        type: e.type,
        messageId: (e as CustomEvent<{ messageId: string }>).detail?.messageId,
      })
    }
    window.addEventListener(QUERY_JUMP_EVENT, listener)
    try {
      result.current.jumpToQuery('m42')
    } finally {
      window.removeEventListener(QUERY_JUMP_EVENT, listener)
    }
    expect(seen).toEqual([{ type: 'ephe:query-jump', messageId: 'm42' }])
  })

  it('goal is the trimmed first line of the first user message', () => {
    const u1 = msg({ role: 'user', content: '  Fix the login bug  \nwith more detail below' })
    const { result } = renderHook(() =>
      useStatusPanelData([msg({ content: 'ok' }), u1]),
    )
    expect(result.current.goal).toBe('Fix the login bug')
  })

  it('goal stays null when a blank first user message precedes the real one (pinned edge)', () => {
    const blank = msg({ role: 'user', content: '   ' })
    const real = msg({ role: 'user', content: 'Real question' })
    const { result } = renderHook(() => useStatusPanelData([blank, real]))
    expect(result.current.goal).toBeNull()
  })

  it('goal is null without any user message', () => {
    const { result } = renderHook(() => useStatusPanelData([msg({ content: 'hello' })]))
    expect(result.current.goal).toBeNull()
  })

  it('empty transcript yields the empty contract', () => {
    const { result } = renderHook(() => useStatusPanelData([]))
    expect(result.current.activeTurn).toBeNull()
    expect(result.current.elapsed).toBeNull()
    expect(result.current.plan).toBeNull()
    expect(result.current.goal).toBeNull()
    expect(result.current.queries).toEqual([])
  })

  it('activeTurn is the newest streaming assistant message', () => {
    const early = msg({ role: 'assistant', streaming: true, content: 'a' })
    const late = msg({ role: 'assistant', streaming: true, content: 'b' })
    const { result } = renderHook(() => useStatusPanelData([early, late]))
    expect(result.current.activeTurn?.id).toBe(late.id)
    expect(typeof result.current.elapsed).toBe('string')
  })
})

// useStatusPanelData: elapsed ticker (fake timers)
describe('useStatusPanelData — elapsed ticker (fake timers)', () => {
  const T0 = new Date('2026-10-11T10:00:00.000Z').getTime()
  const toFake = ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] as const

  beforeEach(() => {
    vi.useFakeTimers({ now: T0, toFake: [...toFake] })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const streamingTurn = (ageMs: number): ChatMessage =>
    msg({ id: 'turn', role: 'assistant', streaming: true, timestamp: T0 - ageMs })

  it.each<[number, string]>([
    [0, '0s'],
    [1999, '1s'],
    [59_000, '59s'],
    [60_000, '1m'],
    [61_000, '1m 1s'],
    [125_000, '2m 5s'],
    [3_600_000, '1h'],
    [3_661_000, '1h 1m'],
  ])('formats %ims of a running turn as „%s“', (ageMs, expected) => {
    const { result } = renderHook(() => useStatusPanelData([streamingTurn(ageMs)]))
    expect(result.current.elapsed).toBe(expected)
  })

  it('ticks once per second while the turn runs', () => {
    const { result } = renderHook(() => useStatusPanelData([streamingTurn(29_000)]))
    expect(result.current.elapsed).toBe('29s')
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(result.current.elapsed).toBe('30s')
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(result.current.elapsed).toBe('31s')
  })

  it('clamps a turn timestamp in the future to „0s“', () => {
    const { result } = renderHook(() =>
      useStatusPanelData([msg({ role: 'assistant', streaming: true, timestamp: T0 + 5_000 })]),
    )
    expect(result.current.elapsed).toBe('0s')
  })

  it('runs no timer without a streaming turn', () => {
    const { result } = renderHook(() =>
      useStatusPanelData([msg({ role: 'assistant', streaming: false })]),
    )
    expect(result.current.activeTurn).toBeNull()
    expect(result.current.elapsed).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('arms exactly one interval while streaming and clears it on unmount', () => {
    const { unmount } = renderHook(() => useStatusPanelData([streamingTurn(1_000)]))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears the interval when the turn stops streaming', () => {
    const turn = msg({ id: 'turn-1', role: 'assistant', streaming: true, timestamp: T0 - 1_000 })
    const { result, rerender } = renderHook(
      ({ msgs }: { msgs: ChatMessage[] }) => useStatusPanelData(msgs),
      { initialProps: { msgs: [turn] } },
    )
    expect(vi.getTimerCount()).toBe(1)
    rerender({ msgs: [{ ...turn, streaming: false }] })
    expect(result.current.activeTurn).toBeNull()
    expect(result.current.elapsed).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })
})

// TurnTimerRow
describe('TurnTimerRow', () => {
  it.each([
    ['0s', 'Working since 0s'],
    ['59s', 'Working since 59s'],
    ['1m', 'Working since 1m'],
    ['1m 1s', 'Working since 1m 1s'],
    ['2m 5s', 'Working since 2m 5s'],
  ])('renders elapsed "%s" as "%s" with a spinning loader', (elapsed, text) => {
    render(<TurnTimerRow elapsed={elapsed} />)
    const row = screen.getByTestId('agent-status-timer')
    expect(row.textContent).toBe(text)
    const icon = row.querySelector('svg')
    expect(icon?.classList.contains('lucide-loader-circle')).toBe(true)
    expect(icon?.classList.contains('animate-spin')).toBe(true)
  })
})

// GoalSection
describe('GoalSection', () => {
  it('renders the goal text under the Goal heading', () => {
    render(<GoalSection goal="Fix the login bug" />)
    expect(screen.getByTestId('agent-status-goal').dataset.statusSection).toBe('goal')
    expect(screen.getByText('Goal')).toBeTruthy()
    expect(screen.getByTestId('agent-status-goal-text').textContent?.trim()).toBe(
      'Fix the login bug',
    )
  })

  it('does not gate on empty text — the parent hides the section (goal="" renders an empty line)', () => {
    render(<GoalSection goal="" />)
    expect(screen.getByTestId('agent-status-goal-text').textContent?.trim()).toBe('')
  })
})

// EnvironmentSection
describe('EnvironmentSection', () => {
  it('shows the branch and the change count', () => {
    render(<EnvironmentSection branch="feat/status-panel" changes={3} />)
    const line = screen.getByTestId('agent-status-environment-line')
    expect(screen.getByTestId('agent-status-environment').dataset.statusSection).toBe('environment')
    expect(line.textContent).toContain('feat/status-panel')
    expect(line.textContent).toContain('3 changes')
    expect(line.querySelector('svg')?.classList.contains('lucide-git-branch')).toBe(true)
  })

  it('prints a clean tree as "0 changes"', () => {
    render(<EnvironmentSection branch="main" changes={0} />)
    expect(screen.getByTestId('agent-status-environment-line').textContent).toContain(
      '0 changes',
    )
  })
})

// ProgressSection
describe('ProgressSection', () => {
  const plan: PlanCardSpec = {
    items: [
      { status: 'done', text: 'Read routes' },
      { status: 'active', text: 'Add the case' },
      { status: 'failed', text: 'Explode' },
      { status: 'cancelled', text: 'Skipped' },
      { status: 'pending', text: 'Next' },
      { status: 'missing' as unknown as PlanItemStatus, text: 'Unknown' },
    ],
    // Counts come from the spec, never recomputed from the items — 4/9 pins that.
    done: 4,
    total: 9,
  }

  it('shows the counter from the spec and the section title', () => {
    render(<ProgressSection plan={plan} />)
    expect(screen.getByTestId('agent-status-progress-count').textContent).toBe('4/9')
    expect(screen.getByText('Progress')).toBeTruthy()
  })

  it('keeps the raw status on data-status for every row', () => {
    render(<ProgressSection plan={plan} />)
    const statuses = [0, 1, 2, 3, 4, 5].map(
      (i) => screen.getByTestId(`agent-status-progress-item-${i}`).dataset.status,
    )
    expect(statuses).toEqual(['done', 'active', 'failed', 'cancelled', 'pending', 'missing'])
  })

  it('maps each status to its own icon, colour and done strikethrough', () => {
    render(<ProgressSection plan={plan} />)
    const icon = (i: number) =>
      screen.getByTestId(`agent-status-progress-item-${i}`).querySelector('svg')
    const text = (i: number) =>
      screen.getByTestId(`agent-status-progress-item-${i}`).querySelector('span')

    expect(icon(0)?.classList.contains('lucide-check')).toBe(true)
    expect(icon(0)?.classList.contains('text-status-success')).toBe(true)
    expect(text(0)?.classList.contains('line-through')).toBe(true)

    expect(icon(1)?.classList.contains('lucide-arrow-right')).toBe(true)
    expect(icon(1)?.classList.contains('text-firefly')).toBe(true)
    expect(text(1)?.classList.contains('line-through')).toBe(false)

    expect(icon(2)?.classList.contains('lucide-circle-alert')).toBe(true)
    expect(icon(2)?.classList.contains('text-status-danger')).toBe(true)

    expect(icon(3)?.classList.contains('lucide-minus')).toBe(true)
    expect(icon(4)?.classList.contains('lucide-circle')).toBe(true)
    // Unknown status falls into the same open-circle branch as pending.
    expect(icon(5)?.classList.contains('lucide-circle')).toBe(true)
  })
})

// QueryMapSection
describe('QueryMapSection', () => {
  const q1 = msg({ id: 'q-1', role: 'user', content: 'First question — with lots of text' })
  const q2 = msg({ id: 'q-2', role: 'user', content: 'Second question\nSecond line with details' })

  it('renders one numbered entry per query with jump aria-labels', () => {
    render(<QueryMapSection queries={[q1, q2]} onJump={() => {}} />)
    expect(screen.getByText('Questions in this task')).toBeTruthy()
    expect(screen.getByTestId('agent-status-jump-0').dataset.messageId).toBe('q-1')
    expect(screen.getByTestId('agent-status-jump-1').dataset.messageId).toBe('q-2')
    expect(screen.getByTestId('agent-status-jump-1').querySelector('span')?.textContent).toBe('2')
    expect(screen.getByTestId('agent-status-jump-1').getAttribute('aria-label')).toBe(
      'Jump to question 2',
    )
    expect(screen.queryByTestId('agent-status-jump-2')).toBeNull()
  })

  it('clicking an entry calls onJump with that message id', () => {
    const onJump = vi.fn()
    render(<QueryMapSection queries={[q1, q2]} onJump={onJump} />)
    fireEvent.click(screen.getByTestId('agent-status-jump-1'))
    expect(onJump).toHaveBeenCalledTimes(1)
    expect(onJump).toHaveBeenCalledWith('q-2')
  })

  it('cuts multi-line queries to their first line', () => {
    render(<QueryMapSection queries={[q2]} onJump={() => {}} />)
    const entry = screen.getByTestId('agent-status-jump-0')
    expect(entry.textContent).toContain('Second question')
    expect(entry.textContent).not.toContain('Second line with details')
    expect(entry.querySelector('.truncate')).toBeTruthy()
  })

  it('renders the empty section when there are no queries (the parent gates it)', () => {
    render(<QueryMapSection queries={[]} onJump={() => {}} />)
    expect(screen.getByTestId('agent-status-query-map')).toBeTruthy()
    expect(screen.queryByTestId('agent-status-jump-0')).toBeNull()
  })
})

// StatusSection (collapse + scroll policy)
describe('StatusSection', () => {
  it('starts open and toggles aria-expanded + body on header clicks', () => {
    render(
      <StatusSection kind="goal" title="Goal" testId="probe">
        <p>Body content</p>
      </StatusSection>,
    )
    const head = () => screen.getByTestId('status-section-head-goal')
    expect(head().getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByTestId('status-section-body-goal')).toBeTruthy()

    fireEvent.click(head())
    expect(head().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByTestId('status-section-body-goal')).toBeNull()

    fireEvent.click(head())
    expect(head().getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByTestId('status-section-body-goal')).toBeTruthy()
  })

  it('rotates the chevron with the open state', () => {
    render(
      <StatusSection kind="usage" title="Cost" testId="probe-chevron">
        <span>x</span>
      </StatusSection>,
    )
    const chevron = () => screen.getByTestId('status-section-head-usage').querySelector('svg')
    expect(chevron()?.classList.contains('rotate-0')).toBe(true)
    fireEvent.click(screen.getByTestId('status-section-head-usage'))
    expect(chevron()?.classList.contains('-rotate-90')).toBe(true)
  })

  it('carries data-status-section + testId on the section and the title on the head', () => {
    render(
      <StatusSection kind="queries" title="Questions in this task" testId="probe-ident">
        <span>x</span>
      </StatusSection>,
    )
    expect(screen.getByTestId('probe-ident').dataset.statusSection).toBe('queries')
    expect(screen.getByTestId('status-section-head-queries').textContent).toContain(
      'Questions in this task',
    )
  })

  it.each(Object.entries(STATUS_SECTION_SCROLL_POLICY))(
    'body of kind %s scrolls with its policy class %s',
    (kind, policy) => {
      render(
        <StatusSection kind={kind as StatusSectionKind} title="T" testId="policy-probe">
          <span>x</span>
        </StatusSection>,
      )
      const body = screen.getByTestId(`status-section-body-${kind}`)
      expect(body.classList.contains('overflow-y-auto')).toBe(true)
      expect(body.classList.contains(policy)).toBe(true)
    },
  )
})

// UsageSection (self-fetching; the big direct gap)
describe('UsageSection', () => {
  const day = (over: Partial<UsageDay> = {}): UsageDay => ({
    d: '2026-10-01',
    in: 0,
    out: 0,
    cached: 0,
    est_turns: 0,
    turns: 1,
    ...over,
  })

  const HAPPY_DAYS: UsageDay[] = [
    day({ d: '2026-10-11', in: 100, out: 10 }), // by_day[0] = today
    day({ d: '2026-10-10', in: 200, out: 20 }),
    day({ d: '2026-10-09', in: 40, out: 4 }),
    day({ d: '2026-10-08', in: 40, out: 4 }),
    day({ d: '2026-10-07', in: 40, out: 4 }),
    day({ d: '2026-10-06', in: 40, out: 4 }),
    day({ d: '2026-10-05', in: 40, out: 4 }), // 7th entry: still in the 7-day window
    day({ d: '2026-10-04', in: 9999, out: 999 }), // 8th entry: 30-day view only
  ]

  const summary = (over: Partial<UsageSummary> = {}): UsageSummary => ({
    days: 30,
    totals: { in: 10499, out: 1049, cached: 0, est_turns: 0, turns: 30 },
    by_day: HAPPY_DAYS,
    pricing: null,
    cost: null,
    ...over,
  })

  beforeEach(() => {
    api.getUsageSummary.mockReset()
  })

  it('renders nothing while the fetch is pending', async () => {
    api.getUsageSummary.mockImplementation(() => new Promise<UsageSummary>(() => {}))
    render(<UsageSection />)
    expect(screen.queryByTestId('agent-status-usage')).toBeNull()
    await waitFor(() => expect(api.getUsageSummary).toHaveBeenCalledWith(30))
    expect(screen.queryByTestId('agent-status-usage')).toBeNull()
  })

  it('renders nothing when totals.turns is 0', async () => {
    api.getUsageSummary.mockResolvedValue(
      summary({ totals: { in: 5, out: 5, cached: 0, est_turns: 0, turns: 0 } }),
    )
    render(<UsageSection />)
    await waitFor(() => expect(api.getUsageSummary).toHaveBeenCalledTimes(1))
    await flushPromises()
    await flushPromises()
    expect(screen.queryByTestId('agent-status-usage')).toBeNull()
  })

  it('renders nothing when the fetch rejects (no crash)', async () => {
    api.getUsageSummary.mockRejectedValue(new Error('offline'))
    render(<UsageSection />)
    await waitFor(() => expect(api.getUsageSummary).toHaveBeenCalledTimes(1))
    await flushPromises()
    await flushPromises()
    expect(screen.queryByTestId('agent-status-usage')).toBeNull()
  })

  it('aggregates today / 7-day / 30-day rows from by_day and totals', async () => {
    api.getUsageSummary.mockResolvedValue(summary())
    render(<UsageSection />)
    const section = await screen.findByTestId('agent-status-usage')
    expect(section.dataset.statusSection).toBe('usage')
    expect(screen.getByText('Cost & usage')).toBeTruthy()
    expect(screen.getByText('Today')).toBeTruthy()
    expect(screen.getByText('Last 7 days')).toBeTruthy()
    expect(screen.getByText('Last 30 days')).toBeTruthy()
    expect(screen.getByText('100 / 10')).toBeTruthy() // today = by_day[0]
    expect(screen.getByText('500 / 50')).toBeTruthy() // 7-day slice of the first 7 entries
    expect(screen.getByText('10.499 / 1.049')).toBeTruthy() // totals, German grouping
    expect(api.getUsageSummary).toHaveBeenCalledWith(30)
    // No pricing → no cost column at all.
    expect(document.body.textContent).not.toContain('$')
    // No pending estimate → no estimated-turns line.
    expect(screen.queryByText(/estimated/)).toBeNull()
  })

  it('formats cost below one cent with 4 decimals and from one cent with 2', async () => {
    api.getUsageSummary.mockResolvedValue(summary({ pricing: { in_per_m: 42, out_per_m: 0 } }))
    render(<UsageSection />)
    await screen.findByTestId('agent-status-usage')
    expect(screen.getByText('$0.0042')).toBeTruthy() // 100 tok → 0.0042 (sub-cent → 4 decimals)
    expect(screen.getByText('$0.02')).toBeTruthy() // 500 tok → 0.021 (≥ 1 cent → 2 decimals)
    expect(screen.getByText('$0.44')).toBeTruthy() // 10499 tok → 0.440958 → 2 decimals
  })

  it('prints exactly one cent with 2 decimals and defaults a missing out price to 0', async () => {
    api.getUsageSummary.mockResolvedValue(
      summary({
        totals: { in: 3000, out: 555, cached: 0, est_turns: 0, turns: 3 },
        by_day: [day({ d: '2026-10-11', in: 1000, out: 555 })],
        pricing: { in_per_m: 10 }, // out_per_m missing → ?? 0 (out tokens add nothing)
      }),
    )
    render(<UsageSection />)
    await screen.findByTestId('agent-status-usage')
    // today and 7-day rows: (1000 / 1e6) * 10 = 0.01 exactly → $0.01, not $0.0100.
    expect(screen.getAllByText('$0.01')).toHaveLength(2)
    expect(screen.getByText('$0.03')).toBeTruthy()
  })

  it('shows the estimated-turns note and falls back to zero rows when by_day is empty', async () => {
    api.getUsageSummary.mockResolvedValue(
      summary({
        totals: { in: 5, out: 1, cached: 0, est_turns: 7, turns: 2 },
        by_day: [],
      }),
    )
    render(<UsageSection />)
    await screen.findByTestId('agent-status-usage')
    expect(screen.getAllByText('0 / 0')).toHaveLength(2) // today + 7-day fall back to zero
    expect(screen.getByText('5 / 1')).toBeTruthy() // 30-day row keeps the totals
    expect(
      screen.getByText(
        '7 turns estimated (no provider usage frame) — marked honestly.',
      ),
    ).toBeTruthy()
  })

  it('prints $0.00 for a row without usage while pricing is configured (pinned quirk)', async () => {
    api.getUsageSummary.mockResolvedValue(
      summary({
        totals: { in: 0, out: 0, cached: 0, est_turns: 0, turns: 1 },
        by_day: [],
        pricing: { in_per_m: 42 },
      }),
    )
    render(<UsageSection />)
    await screen.findByTestId('agent-status-usage')
    // v === 0 skips the sub-cent branch and formats as $0.00 — the row renders,
    // because the string '0.00' is truthy in the component's {cost && …} guard.
    expect(screen.getAllByText('$0.00')).toHaveLength(3)
  })
})
