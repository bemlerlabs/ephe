/**
 * Shared task poller (P1-11): /api/tasks is global (no session or turn scope), so
 * ONE interval plus cache serves every TaskBody card instead of N own pollers.
 * useSyncExternalStore: the snapshot reference stays stable as long as the data
 * does not change — that avoids render churn on a 2.5 s beat.
 */
import { useCallback, useSyncExternalStore } from 'react'
import { getTasks, type TaskItem } from '@/lib/api'

export interface TasksSnapshot {
  /** null = no successful fetch yet (loader). */
  tasks: TaskItem[] | null
  /** true only when no cached state is available — otherwise the last good cache stays. */
  failed: boolean
}

const POLL_MS = 2500

let snapshot: TasksSnapshot = { tasks: null, failed: false }
const listeners = new Set<() => void>()
let liveCount = 0
let timer: ReturnType<typeof setInterval> | null = null
let inflight = false

function emit(): void {
  for (const l of listeners) l()
}

function sameTasks(a: TaskItem[], b: TaskItem[]): boolean {
  return (
    a.length === b.length &&
    a.every((t, i) => {
      const o = b[i]
      return (
        o !== undefined &&
        t.id === o.id &&
        t.title === o.title &&
        t.status === o.status &&
        t.project === o.project
      )
    })
  )
}

async function poll(): Promise<void> {
  if (inflight) return
  inflight = true
  try {
    const list = await getTasks()
    if (snapshot.tasks === null || snapshot.failed || !sameTasks(list, snapshot.tasks)) {
      snapshot = { tasks: list, failed: false }
      emit()
    }
  } catch {
    // a failed poll keeps the last good cache; "—" only shows with no cache at all.
    if (snapshot.tasks === null && !snapshot.failed) {
      snapshot = { tasks: null, failed: true }
      emit()
    }
  } finally {
    inflight = false
  }
}

function startInterval(): void {
  if (timer === null) timer = setInterval(() => void poll(), POLL_MS)
}

function stopInterval(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

/** live subscribers keep the interval alive; finished cards only read the cache. */
function subscribe(live: boolean, listener: () => void): () => void {
  listeners.add(listener)
  if (live) {
    liveCount += 1
    startInterval()
  }
  if (snapshot.tasks === null) void poll()
  return () => {
    listeners.delete(listener)
    if (live) {
      liveCount -= 1
      if (liveCount === 0) stopInterval()
    }
  }
}

function getSnapshot(): TasksSnapshot {
  return snapshot
}

export function useTasks(live: boolean): TasksSnapshot {
  const sub = useCallback((cb: () => void) => subscribe(live, cb), [live])
  return useSyncExternalStore(sub, getSnapshot)
}

/** For tests only: reset the module state (cache/interval) between cases. */
export function __resetTasksStoreForTests(): void {
  stopInterval()
  listeners.clear()
  liveCount = 0
  inflight = false
  snapshot = { tasks: null, failed: false }
}
