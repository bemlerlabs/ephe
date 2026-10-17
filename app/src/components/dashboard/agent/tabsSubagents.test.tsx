import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { SubagentsTab } from './tabsSubagents'
import type { Activity, ChatMessage } from '@/types'
import type { SubagentDetail, SubagentSummary } from '@/lib/api'

// Unit contract of the subagents tab with its own props (messages).
// The AgentPanel-level suites (AgentPanel.subagents{,.b1,.chat}.test.tsx) cover
// the pane wiring, the plus menu, the panel-level detail paths and the
// helper-session build; this file pins the tab's direct contract: activities
// filter, running/ended split with counters, backendAgentId edges, directory
// dedupe, cursor pagination append, error/empty states, direct detail fetch,
// the helper-chat call shape and the 600 ms live ticker.

const api = vi.hoisted(() => ({
  listSubagents: vi.fn(),
  getSubagent: vi.fn(),
  getSettings: vi.fn(),
}))
vi.mock('@/lib/api', () => ({
  listSubagents: api.listSubagents,
  getSubagent: api.getSubagent,
  getSettings: api.getSettings,
}))

const store = vi.hoisted(() => ({ openHelperChat: vi.fn() }))
vi.mock('@/store/chatStore', () => ({
  useChatStore: { getState: () => ({ openHelperChat: store.openHelperChat }) },
}))

// Readable strings with {{x}} interpolation — assertions stay on visible text.
vi.mock('react-i18next', () => {
  const de: Record<string, string> = {
    'agentPanel.tabSubagents': 'Helpers',
    'agentPanel.error': 'Error',
    'agentPanel.retry': 'Try again',
    'agentPanel.openHelperChat': 'Open chat',
    'agentPanel.subagentsEmpty':
      'No helper activity in this task — several running helpers also appear here.',
    'agentPanel.subagentsRunning': 'Running · {{count}}',
    'agentPanel.subagentsEnded': 'Ended · {{count}}',
    'agentPanel.subagentRunning': 'running…',
    'agentPanel.subagentFailed': 'failed',
    'agentPanel.subagentCompleted': 'Completed',
    'agentPanel.noRunningAgents': 'No running helpers',
    'agentPanel.subagentsNoneEnded': 'No finished helpers',
    'agentPanel.minAgo': '{{count}} min ago',
    'agentPanel.hoursAgo': '{{count}} h ago',
    'agentPanel.showMore': 'Show more',
    'agentPanel.subagentLoading': 'Loading…',
    'agentPanel.subagentPrompt': 'Prompt:',
    'agentPanel.subagentWorked': 'Worked {{time}}',
    'agentPanel.subagentReport': 'Report',
  }
  return {
    initReactI18next: { type: '9', init: () => Promise.resolve() },
    useTranslation: () => ({
      t: (key: string, vars?: Record<string, unknown>) => {
        let s = de[key] ?? key
        for (const [k, v] of Object.entries(vars ?? {})) {
          s = s.replace(new RegExp(`{{${k}}}`, 'g'), String(v))
        }
        return s
      },
    }),
  }
})

const NOW_MS = Date.UTC(2026, 5, 1, 12, 0, 0)

const activity = (
  id: string,
  label: string,
  status: Activity['status'],
  detail?: string,
): Activity => ({ id, label, status, ...(detail ? { detail } : {}) })

const msg = (id: string, activities: Activity[], minAgo = 5): ChatMessage => ({
  id,
  role: 'assistant',
  content: 'x',
  timestamp: NOW_MS - minAgo * 60_000,
  activities,
})

const summary = (agentId: string, over: Partial<SubagentSummary> = {}): SubagentSummary => ({
  agent_id: agentId,
  role: 'scout',
  description: `Run ${agentId}`,
  task: 'T',
  status: 'ok',
  started_ts: NOW_MS / 1000 - 120,
  duration_ms: 1500,
  tool_count: 1,
  ...over,
})

const detail = (agentId: string, over: Partial<SubagentDetail> = {}): SubagentDetail => ({
  agent_id: agentId,
  role: 'scout',
  description: 'Research HTTP timeouts',
  task: 'Find timeouts',
  model: 'm1',
  status: 'ok',
  started_ts: NOW_MS / 1000 - 30,
  finished_ts: NOW_MS / 1000,
  duration_ms: 7234,
  report: 'Report: timeout at 30s.',
  tool_calls: [
    { tool: 'read_file', args_preview: '{"path":"a.ts"}', ms: 2500 },
    { tool: 'web_search', args_preview: '', ms: 850 },
  ],
  transcript: [],
  ...over,
})

const renderTab = (messages: ChatMessage[]) => render(<SubagentsTab messages={messages} />)

beforeEach(() => {
  vi.clearAllMocks()
  vi.setSystemTime(new Date(NOW_MS))
  api.listSubagents.mockResolvedValue({ agents: [], nextCursor: null })
  api.getSubagent.mockResolvedValue(detail('subagent-1'))
  api.getSettings.mockResolvedValue({ workspace_dir: null })
  store.openHelperChat.mockResolvedValue(true)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('SubagentsTab (unit contract)', () => {
  it('splits into running/ended with counters, status words, and time only on ended rows', async () => {
    renderTab([
      msg('m1', [
        activity('a1', 'Agent researcher', 'running'),
        activity('a2', 'Agent writer', 'done', 'Summary finished'),
        activity('a3', 'Agent critic', 'failed'),
      ]),
      msg('m2', [activity('b1', 'Agent scout', 'done')], 180),
    ])
    const running = await screen.findByTestId('subagents-running-section')
    const ended = screen.getByTestId('subagents-ended-section')
    expect(screen.getByRole('heading', { name: 'Helpers' })).toBeTruthy()
    // Counters from both axes (activities + directory = empty)
    expect(running.textContent).toContain('Running · 1')
    expect(ended.textContent).toContain('Ended · 3')
    // Split: only the running run sits at the top
    expect(within(running).getByTestId('subagent-row-a1')).toBeTruthy()
    expect(within(running).queryByTestId('subagent-row-a2')).toBeNull()
    expect(within(ended).getByTestId('subagent-row-a2')).toBeTruthy()
    expect(within(ended).getByTestId('subagent-row-a3')).toBeTruthy()
    expect(within(ended).getByTestId('subagent-row-b1')).toBeTruthy()
    // Status words
    expect(screen.getByTestId('subagent-state-a1').textContent).toBe('running…')
    expect(screen.getByTestId('subagent-state-a2').textContent).toBe('Completed')
    expect(screen.getByTestId('subagent-state-a3').textContent).toBe('failed')
    // Time: ended rows carry it, running rows do not
    expect(screen.getByTestId('subagent-time-a2').textContent).toBe('5 min ago')
    expect(screen.getByTestId('subagent-time-b1').textContent).toBe('3 h ago')
    expect(screen.queryByTestId('subagent-time-a1')).toBeNull()
    // Excerpt + numbering (#n) of the section
    expect(screen.getByTestId('subagent-detail-a2').textContent).toBe('Summary finished')
    expect(within(screen.getByTestId('subagent-row-a2')).getByText('#1')).toBeTruthy()
    expect(within(screen.getByTestId('subagent-row-b1')).getByText('#3')).toBeTruthy()
  })

  it('filters activities: only agent/swarm rows are listed', async () => {
    renderTab([
      msg('m1', [
        activity('a1', 'Agent researcher', 'running'),
        activity('a2', 'Shell command finished', 'done'),
        activity('a3', 'SWARM wave 2', 'done'),
        activity('a4', 'File written', 'done'),
      ]),
    ])
    await screen.findByTestId('subagents-running-section')
    expect(screen.getByTestId('subagent-row-a1')).toBeTruthy()
    expect(screen.getByTestId('subagent-row-a3')).toBeTruthy()
    expect(screen.queryByTestId('subagent-row-a2')).toBeNull()
    expect(screen.queryByTestId('subagent-row-a4')).toBeNull()
    expect(screen.getByTestId('subagents-ended-section').textContent).toContain('Ended · 1')
  })

  it('only ended runs: Running · 0 with the no-running-helpers row', async () => {
    renderTab([msg('m1', [activity('a1', 'Agent writer', 'done')])])
    const running = await screen.findByTestId('subagents-running-section')
    expect(running.textContent).toContain('Running · 0')
    expect(screen.getByTestId('subagents-none-row').textContent).toBe('No running helpers')
    expect(screen.getByTestId('subagents-ended-section').textContent).toContain('Ended · 1')
  })

  it('only running runs: Ended · 0 with the no-finished-helpers row', async () => {
    renderTab([msg('m1', [activity('a1', 'Agent researcher', 'running')])])
    const ended = await screen.findByTestId('subagents-ended-section')
    expect(ended.textContent).toContain('Ended · 0')
    expect(screen.getByTestId('subagents-ended-none-row').textContent).toBe('No finished helpers')
    expect(screen.getByTestId('subagents-running-section').textContent).toContain('Running · 1')
  })

  it('backend id from the label: "SubAgent subagent-2" without suffix is clickable, whitespace-/SubAgentX labels are not', async () => {
    api.getSubagent.mockResolvedValue(detail('subagent-2'))
    renderTab([
      msg('m1', [
        activity('a1', 'SubAgent subagent-2', 'done'),
        activity('a2', 'SubAgent    ', 'done'),
        activity('a3', 'SubAgentX foo', 'done'),
      ]),
    ])
    await screen.findByTestId('subagents-ended-section')

    // Without role suffix: backend id is derived → chat button + clickability
    const rowA1 = screen.getByTestId('subagent-row-a1')
    expect(rowA1.className).toContain('cursor-pointer')
    expect(screen.getByTestId('subagent-open-chat-subagent-2')).toBeTruthy()

    // Whitespace-only rest and 'SubAgentX' have NO backend id
    const rowA2 = screen.getByTestId('subagent-row-a2')
    const rowA3 = screen.getByTestId('subagent-row-a3')
    expect(rowA2.className).not.toContain('cursor-pointer')
    expect(rowA3.className).not.toContain('cursor-pointer')
    expect(within(rowA2).queryByRole('button')).toBeNull()
    expect(within(rowA3).queryByRole('button')).toBeNull()

    fireEvent.click(rowA2)
    fireEvent.click(rowA3)
    expect(screen.queryAllByTestId(/^subagent-expanded-/)).toHaveLength(0)
    expect(api.getSubagent).not.toHaveBeenCalled()

    // The one without a suffix is clickable and loads the detail for the derived id
    fireEvent.click(rowA1)
    await screen.findByTestId('subagent-expanded-subagent-2')
    expect(api.getSubagent).toHaveBeenCalledWith('subagent-2')
  })

  it('dedupe: a directory row with the same backend id does not appear twice', async () => {
    api.listSubagents.mockResolvedValue({
      agents: [summary('subagent-1'), summary('subagent-9')],
      nextCursor: null,
    })
    renderTab([msg('m1', [activity('a1', 'SubAgent subagent-1 (scout)', 'done')])])
    await screen.findByTestId('subagent-directory-row-subagent-9')

    // Live row present, duplicate NOT (neither row nor a second chat button)
    expect(screen.getByTestId('subagent-row-a1')).toBeTruthy()
    expect(screen.queryByTestId('subagent-directory-row-subagent-1')).toBeNull()
    expect(screen.getAllByTestId('subagent-open-chat-subagent-1')).toHaveLength(1)
    expect(screen.getAllByTestId(/^subagent-directory-row-/)).toHaveLength(1)
    // Counter = 1 live end + 1 directory rest; numbering continues
    expect(screen.getByTestId('subagents-ended-section').textContent).toContain('Ended · 2')
    expect(
      within(screen.getByTestId('subagent-directory-row-subagent-9')).getByText('#2'),
    ).toBeTruthy()
  })

  it('pagination: "Show more" loads with the cursor and appends page 2 (both pages visible)', async () => {
    api.listSubagents
      .mockResolvedValueOnce({ agents: [summary('subagent-10')], nextCursor: 'c2' })
      .mockResolvedValueOnce({ agents: [summary('subagent-11')], nextCursor: null })
    renderTab([msg('m1', [activity('a1', 'Agent researcher', 'done')])])
    await screen.findByTestId('subagent-directory-row-subagent-10')
    const btn = screen.getByTestId('subagents-show-more')
    expect(btn.textContent).toBe('Show more')
    expect(api.listSubagents.mock.calls[0]![0]).toBeUndefined()
    expect(screen.getByTestId('subagents-ended-section').textContent).toContain('Ended · 2')

    fireEvent.click(btn)
    await vi.waitFor(() => expect(api.listSubagents).toHaveBeenCalledTimes(2))
    expect(api.listSubagents.mock.calls[1]![0]).toBe('c2')

    // Page 2 appended: page 1 stays visible, counter grows, cursor gone → no show more
    await screen.findByTestId('subagent-directory-row-subagent-11')
    expect(screen.getByTestId('subagent-directory-row-subagent-10')).toBeTruthy()
    expect(screen.getByTestId('subagents-ended-section').textContent).toContain('Ended · 3')
    expect(screen.queryByTestId('subagents-show-more')).toBeNull()
  })

  it('directory error: role=alert with the message — live rows stay, no auto-retry', async () => {
    api.listSubagents.mockRejectedValueOnce(new Error('boom'))
    renderTab([msg('m1', [activity('a1', 'Agent researcher', 'running')])])
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Error: boom')
    // The live axis survives the directory error
    expect(screen.getByTestId('subagents-running-section').textContent).toContain('Running · 1')
    expect(screen.getByTestId('subagent-row-a1')).toBeTruthy()
    expect(screen.queryByTestId('subagents-empty')).toBeNull()
    expect(screen.queryByTestId('subagents-show-more')).toBeNull()
    // no auto-retry: the fetch stayed at exactly one attempt
    expect(api.listSubagents).toHaveBeenCalledTimes(1)
  })

  it('directory error without live rows: alert and empty state coexist', async () => {
    api.listSubagents.mockRejectedValueOnce(new Error('boom'))
    renderTab([msg('m1', [activity('a1', 'Shell command finished', 'done')])])
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Error: boom')
    expect(screen.getByTestId('subagents-empty')).toBeTruthy()
    expect(screen.queryByTestId('subagents-running-section')).toBeNull()
  })

  it('directory error names the next step: the retry button reloads and clears the alert', async () => {
    api.listSubagents
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce({ agents: [summary('subagent-9')], nextCursor: null })
    renderTab([msg('m1', [activity('a1', 'Shell command finished', 'done')])])
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Error: boom')
    const retry = screen.getByTestId('subagents-dir-retry')
    expect(retry.textContent).toBe('Try again')

    fireEvent.click(retry)
    await screen.findByTestId('subagent-directory-row-subagent-9')
    expect(screen.queryByRole('alert')).toBeNull()
    // The retry starts a fresh first page, not an append
    expect(api.listSubagents).toHaveBeenCalledTimes(2)
    expect(api.listSubagents.mock.calls[1]![0]).toBeUndefined()
  })

  it('empty state: no agent activities and an empty directory → empty message without sections', async () => {
    renderTab([msg('m1', [activity('a1', 'Shell command finished', 'done')])])
    const empty = await screen.findByTestId('subagents-empty')
    expect(empty.textContent).toContain('No helper activity')
    expect(screen.queryByTestId('subagents-running-section')).toBeNull()
    expect(screen.queryByTestId('subagents-ended-section')).toBeNull()
    expect(screen.queryByTestId('subagents-show-more')).toBeNull()
  })

  it('no loading state: while the directory hangs, the empty state is already there', () => {
    // dirPage === null counts as empty in emptyAll — the component has no loading state.
    api.listSubagents.mockImplementation(() => new Promise(() => {}))
    renderTab([msg('m1', [])])
    expect(screen.getByTestId('subagents-empty')).toBeTruthy()
    expect(screen.queryByTestId('subagents-running-section')).toBeNull()
  })

  it('row click opens the REST detail: prompt, numbered steps, formatted durations, report; a second click closes', async () => {
    let resolveDetail!: (d: SubagentDetail) => void
    const pending = new Promise<SubagentDetail>((res) => {
      resolveDetail = res
    })
    api.getSubagent.mockReturnValue(pending)
    renderTab([msg('m1', [activity('a1', 'SubAgent subagent-1 (scout)', 'done')])])
    await screen.findByTestId('subagent-row-a1')

    fireEvent.click(screen.getByTestId('subagent-row-a1'))
    expect(screen.getByTestId('subagent-expanded-subagent-1')).toBeTruthy()
    expect(screen.getByText('Loading…')).toBeTruthy()
    expect(api.getSubagent).toHaveBeenCalledWith('subagent-1')

    await act(async () => {
      resolveDetail(detail('subagent-1'))
    })
    const panel = await screen.findByTestId('subagent-expanded-subagent-1')
    await screen.findByTestId('subagent-report-subagent-1')

    // Prompt row
    const prompt = within(panel).getByTestId('subagent-prompt-subagent-1')
    expect(prompt.textContent).toContain('Prompt:')
    expect(prompt.textContent).toContain('Find timeouts')
    // Numbered steps with tool + argument preview + formatted duration
    const step0 = within(panel).getByTestId('subagent-step-0')
    expect(within(step0).getByText('01')).toBeTruthy()
    expect(step0.textContent).toContain('read_file')
    expect(step0.textContent).toContain('{"path":"a.ts"}')
    expect(within(panel).getByTestId('subagent-step-duration-0').textContent).toBe('2.50s')
    expect(within(panel).getByTestId('subagent-step-1').textContent).toContain('web_search')
    expect(within(panel).getByTestId('subagent-step-duration-1').textContent).toBe('850ms')
    // Duration from duration_ms (not from the clock)
    expect(within(panel).getByTestId('subagent-worked-subagent-1').textContent).toBe('Worked 7.23s')
    // Report section
    expect(within(panel).getByText('Report')).toBeTruthy()
    expect(within(panel).getByTestId('subagent-report-subagent-1').textContent).toBe(
      'Report: timeout at 30s.',
    )

    // a second click collapses the row again
    fireEvent.click(screen.getByTestId('subagent-row-a1'))
    expect(screen.queryByTestId('subagent-expanded-subagent-1')).toBeNull()
  })

  it('the helper-chat button calls openHelperChat with agentId/chatSessionId — without expanding the row', async () => {
    api.listSubagents.mockResolvedValue({
      agents: [summary('subagent-9', { chat_session_id: 'helper-ab12' }), summary('subagent-10')],
      nextCursor: null,
    })
    renderTab([msg('m1', [activity('a1', 'SubAgent subagent-1 (scout)', 'done')])])
    // The row components live in the render scope of the tab component: a
    // directory re-render remounts them (DOM nodes are replaced). So always
    // query freshly via screen.getByTestId before each click, never click the
    // node captured by findByTestId — it may already be detached.
    expect((await screen.findByTestId('subagent-open-chat-subagent-1')).getAttribute('title')).toBe(
      'Open chat',
    )

    fireEvent.click(screen.getByTestId('subagent-open-chat-subagent-1'))
    const first = store.openHelperChat.mock.calls[0]![0] as {
      agentId: string
      chatSessionId?: string
    }
    expect(first.agentId).toBe('subagent-1')
    expect(first.chatSessionId).toBeUndefined()

    // Directory row: the row's chat_session_id travels along
    await screen.findByTestId('subagent-open-chat-subagent-9')
    fireEvent.click(screen.getByTestId('subagent-open-chat-subagent-9'))
    const second = store.openHelperChat.mock.calls[1]![0] as {
      agentId: string
      chatSessionId?: string
    }
    expect(second.agentId).toBe('subagent-9')
    expect(second.chatSessionId).toBe('helper-ab12')

    fireEvent.click(screen.getByTestId('subagent-open-chat-subagent-10'))
    const third = store.openHelperChat.mock.calls[2]![0] as { chatSessionId?: string }
    expect(third.chatSessionId).toBeUndefined()

    // stopPropagation: no click on the row, no detail fetch, nothing expanded
    expect(store.openHelperChat).toHaveBeenCalledTimes(3)
    expect(api.getSubagent).not.toHaveBeenCalled()
    expect(screen.queryAllByTestId(/^subagent-expanded-/)).toHaveLength(0)
  })

  it('live ticker (600ms): the duration ticks with the clock and a new report appears without a click', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date(NOW_MS))
    const running = detail('subagent-1', {
      status: 'running',
      duration_ms: null,
      finished_ts: null,
      report: '',
      tool_calls: [],
      started_ts: NOW_MS / 1000 - 5,
    })
    api.getSubagent.mockResolvedValue(running)
    renderTab([msg('m1', [activity('a1', 'SubAgent subagent-1 (scout)', 'running')])])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    fireEvent.click(screen.getByTestId('subagent-row-a1'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    // duration_ms missing → duration comes from started_ts against Date.now()
    expect(screen.getByTestId('subagent-worked-subagent-1').textContent).toBe('Worked 5.00s')

    // A 600ms tick advances the fake clock by 600ms at the same time: the
    // unchanged record stays (identity check), only the duration ticks on.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })
    expect(screen.getByTestId('subagent-worked-subagent-1').textContent).toBe('Worked 5.60s')

    // The poll delivers a changed record → a new report appears without a click
    api.getSubagent.mockResolvedValue(
      detail('subagent-1', {
        status: 'done',
        duration_ms: 8000,
        report: 'Finished after eight seconds.',
      }),
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })
    expect(screen.getByTestId('subagent-report-subagent-1').textContent).toBe(
      'Finished after eight seconds.',
    )
    expect(screen.getByTestId('subagent-worked-subagent-1').textContent).toBe('Worked 8.00s')
    // 1 initial fetch + 2 polls
    expect(api.getSubagent.mock.calls.length).toBeGreaterThanOrEqual(3)
  })
})
