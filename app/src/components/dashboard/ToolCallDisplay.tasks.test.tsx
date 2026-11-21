/**
 * P1-11: TaskBody must not drive its own 2.5s interval on the global task list
 * per card. GIVEN several task cards in the stream, WHEN they are live,
 * THEN they share ONE poller (1 fetch per tick, not N), and the
 * last unmount stops the interval. Tasks are global (no session reference),
 * so this is about dedup + error cache, not about scoping.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, cleanup, act } from '@testing-library/react'
import i18n from '@/i18n'
import ToolCallDisplay from './ToolCallDisplay'
import { getTasks } from '@/lib/api'
import { __resetTasksStoreForTests } from '@/hooks/useTasks'
import type { ToolCall } from '@/store/chatStore'

const taskList = [
  { id: 't1', title: 'Readme schreiben', status: 'done', project: null },
  { id: 't2', title: 'Tests gruen', status: 'pending', project: null },
]
vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => taskList),
}))

const getTasksMock = vi.mocked(getTasks)

function taskCall(id: string, status: 'pending' | 'completed'): ToolCall {
  return { id, name: 'manage_tasks', args: { action: 'add', title: 'x' }, status }
}

function taskCards(n: number, status: 'pending' | 'completed' = 'pending'): ToolCall[] {
  return Array.from({ length: n }, (_, i) => taskCall(`tc${i}`, status))
}

/** Flush microtasks (the fetch promise) without advancing the fake timers. */
async function flush(): Promise<void> {
  await act(async () => {})
}

async function tick(times = 1): Promise<void> {
  for (let i = 0; i < times; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })
  }
}

beforeEach(async () => {
  await i18n.changeLanguage('en')
  vi.useFakeTimers()
  __resetTasksStoreForTests()
  getTasksMock.mockClear()
  getTasksMock.mockImplementation(async () => taskList)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('TaskBody: one shared poller over N intervals (P1-11)', () => {
  it('3 live cards: one fetch at mount, one fetch per 2.5s tick', async () => {
    render(<ToolCallDisplay tool_calls={taskCards(3)} />)
    await flush()
    expect(getTasksMock).toHaveBeenCalledTimes(1)
    // Every card reads the same cache.
    expect(screen.getAllByTestId('tool-task-row')).toHaveLength(6) // 3 cards × 2 tasks

    await tick(3)
    expect(getTasksMock).toHaveBeenCalledTimes(4) // 1 + 3 ticks — not 3×4
  })

  it('the last unmount stops the interval and leaks nothing', async () => {
    const view = render(<ToolCallDisplay tool_calls={taskCards(2)} />)
    await flush()
    expect(getTasksMock).toHaveBeenCalledTimes(1)

    view.unmount()
    getTasksMock.mockClear()
    await tick(4)
    expect(getTasksMock).not.toHaveBeenCalled()
  })

  it('completed cards do not poll; only live cards keep the interval', async () => {
    render(<ToolCallDisplay tool_calls={taskCards(2, 'completed')} />)
    await flush()
    expect(getTasksMock).toHaveBeenCalledTimes(1) // one-off read
    await tick(3)
    expect(getTasksMock).toHaveBeenCalledTimes(1)
  })
})

describe('TaskBody: error handling on the shared cache', () => {
  it('a failed poll keeps the last good cache, without flicker or crash', async () => {
    render(<ToolCallDisplay tool_calls={taskCards(1)} />)
    await flush()
    expect(screen.getAllByTestId('tool-task-row')).toHaveLength(2)

    getTasksMock.mockRejectedValue(new Error('network down'))
    await tick(2)
    expect(screen.getAllByTestId('tool-task-row')).toHaveLength(2) // the last good list
  })

  it('an error with no cache shows the dash state and recovers on the next tick', async () => {
    getTasksMock.mockRejectedValue(new Error('offline'))
    render(<ToolCallDisplay tool_calls={taskCards(1)} />)
    await flush()
    expect(screen.getByTestId('tool-task-state').textContent).toBe('—')

    getTasksMock.mockImplementation(async () => taskList)
    await tick(1)
    expect(screen.getAllByTestId('tool-task-row')).toHaveLength(2)
  })
})
