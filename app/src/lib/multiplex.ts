/**
 * L1 — one live stream for the fleet and the cell.
 *
 * The server sends a full snapshot on every change, so a reconnect needs no replay
 * and a listener never has to merge a delta. The module keeps one EventSource for
 * the whole app: the first subscriber opens it, the last one closes it. A browser
 * without EventSource (or a stream that has not opened yet) leaves the callers'
 * polling fallback in charge — `multiplexIsOpen()` is the switch they read.
 */
import { apiUrl, type CellLife, type FleetRun, type Workspace } from '@/lib/api'

export interface MultiplexFleet {
  workspaces: Workspace[]
  runs: FleetRun[]
}

export interface MultiplexEvent {
  fleet?: MultiplexFleet
  cell?: CellLife | null
}

type Listener = (event: MultiplexEvent) => void

const listeners = new Set<Listener>()
let source: EventSource | null = null
let currentSession: string | undefined
let open = false

export function multiplexIsOpen(): boolean {
  return open
}

function urlFor(session?: string): string {
  const base = apiUrl('/api/events/multiplex')
  if (!session) return base
  return `${base}${base.includes('?') ? '&' : '?'}session=${encodeURIComponent(session)}`
}

function close(): void {
  source?.close()
  source = null
  open = false
  currentSession = undefined
}

function ensure(session?: string): void {
  // A listener without a session does not downgrade a stream another listener
  // already opened with one.
  const next = session || currentSession
  if (source && next === currentSession) return
  close()
  if (typeof EventSource === 'undefined') return
  currentSession = next
  source = new EventSource(urlFor(next))
  source.addEventListener('open', () => {
    open = true
  })
  source.addEventListener('error', () => {
    open = false
  })
  source.addEventListener('multiplex', (raw) => {
    open = true
    try {
      const event = JSON.parse((raw as MessageEvent).data) as MultiplexEvent
      for (const listener of listeners) listener(event)
    } catch {
      // A malformed frame is ignored; the next frame is a full snapshot.
    }
  })
}

export function subscribeMultiplex(listener: Listener, session?: string): () => void {
  listeners.add(listener)
  ensure(session)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) close()
  }
}
