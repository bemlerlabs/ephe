/**
 * Ephe — the fleet poller (G2): `/api/workspaces` on a beat, for the board and the register.
 *
 * One read answers both halves — the checkouts and the runs behind them (`core/fleet.py`) —
 * so the whole board is one poll and there is no second endpoint to keep in step. Polling,
 * not SSE, is what this surface's route style is: `/api/tasks` is read on a beat
 * (`hooks/useTasks.ts`), the four workspaces routes are plain request and response, and a
 * page that has to survive a dropped connection does not need a reconnect dance to do it.
 *
 * `useSyncExternalStore` like `useTasks`: the snapshot keeps its identity between answers,
 * so a poll that changed nothing does not re-render the page — and a page whose rows tick
 * with the clock does re-render, which is why the interval is the only timer here.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { listWorkspaces, type FleetRun, type Workspace } from '@/lib/api'
import { refusalSentence } from '@/components/dashboard/workspaces/labels'

export interface FleetSnapshot {
  /** The register as the last poll read it. */
  workspaces: Workspace[]
  /** The board: every run, the ones that need a person first. */
  runs: FleetRun[]
  /** True when the last poll failed. What it read before that failure is still here, so a
   * dropped request does not blank a board that was right a moment ago. */
  failed: boolean
  reason: string
}

const POLL_MS = 3000

let snapshot: FleetSnapshot | null = null
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setInterval> | null = null
let watchers = 0
let inflight = false

function emit(): void {
  for (const listener of listeners) listener()
}

/** One poll. A failure keeps the last good answer and says so beside it. */
async function poll(): Promise<void> {
  if (inflight) return
  inflight = true
  try {
    const answer = await listWorkspaces()
    snapshot = {
      workspaces: answer.workspaces ?? [],
      runs: answer.runs ?? [],
      failed: false,
      reason: '',
    }
  } catch (error: unknown) {
    const reason = refusalSentence(error)
    snapshot = snapshot
      ? { ...snapshot, failed: true, reason }
      : { workspaces: [], runs: [], failed: true, reason }
  } finally {
    inflight = false
    emit()
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): FleetSnapshot | null {
  return snapshot
}

/**
 * The last answer, for a reader that is not a React dependency.
 *
 * The change-set reads hang on the register's *fingerprint*, not on the snapshot: a poll that
 * only moved an age must not send twenty requests again. That reader cannot name the snapshot
 * in its dependency list without re-running on every tick, so it asks for it here.
 */
export function currentFleet(): FleetSnapshot | null {
  return snapshot
}

/** Poll now, outside the beat — the retry a failure face offers. */
export function pollFleetNow(): void {
  void poll()
}

export function useFleet(): { fleet: FleetSnapshot | null; refresh: () => void } {
  const fleet = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  useEffect(() => {
    watchers += 1
    if (timer === null) {
      void poll()
      timer = setInterval(() => {
        if (!document.hidden) void poll()
      }, POLL_MS)
    }
    // A tab that comes back is on screen again: read at once rather than up to a beat late.
    const onVisibility = () => {
      if (!document.hidden) void poll()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      watchers -= 1
      if (watchers <= 0 && timer !== null) {
        clearInterval(timer)
        timer = null
        watchers = 0
        // The answer below was read for a surface that is gone: a fresh mount reads again
        // rather than starting from another page's register, and a failure there has to be
        // a failure on its own terms instead of one hidden behind a stale good answer.
        snapshot = null
      }
    }
  }, [])

  return { fleet, refresh: pollFleetNow }
}
