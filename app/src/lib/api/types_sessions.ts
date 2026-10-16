/** Session mirror types (R6/S1): what the mirror carries and what restore
 *  returns. Split out of types.ts when the sync fields broke the module's
 *  400-line limit — the mirror is a contract in its own right. */
export interface SyncMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: number
  // R6/S1: the history of the message. The mirror accepted these fields since
  // 2026-10-01 — the sender had never sent them before, so a restored
  // session was a plain text transcript without cards.
  blocks?: unknown[]
  thinkingPhases?: Array<{ start?: number | null; end?: number | null; text?: string }>
  thinking?: unknown
  durationMs?: number
  activities?: unknown[]
  artifacts?: unknown[]
  error?: string
  turnId?: string
  tool_calls?: unknown[]
}

export interface SyncSession {
  id: string
  title: string
  mode?: string
  parent_id?: string
  /** Session birth in ms — without it restore dates the session to the mirror mtime. */
  created_at?: number
  messages: SyncMessage[]
}
export interface RestoredSession {
  id: string
  title: string
  updated_at: number
  created_at?: number
  mode?: string
  parent_id?: string
  messages: Array<Partial<import('@/types').ChatMessage> & { role: string; content: string }>
}

/*
 * Wave 4: the store's holdings and its retention (GET/POST /api/sessions)
 *
 * The response carries more than one count that a reader could call "the
 * sessions", and they answer different questions:
 *
 *   total              every JSON file in the store, all three namespaces —
 *                      what a prune bounds and what the disk holds;
 *   registered_sessions the registry rows — the tasks a list shows;
 *   listed_files        files a registry row reaches;
 *   by_namespace[ns]    the same file count, split into the task, `pwa-` and
 *                      `rest-` groups.
 *
 * A surface that shows one of these has to say which one it means; that is the
 * whole reason the fields are documented here and not folded into one number.
 * */

/** One namespace's slice of the store: `rest-`, `pwa-`, or `""` for a task. */
export interface SessionStoreNamespace {
  files: number
  bytes: number
}

/** The oldest or newest file the store holds, by mtime. */
export interface SessionStoreStamp {
  id: string
  namespace: string
  mtime: string
}

/** Body of `GET /api/sessions` (minus the `sessions` register list). */
export interface SessionStoreStats {
  session_dir: string
  /** Every JSON file, all namespaces. Not the task count — see the header note. */
  total: number
  bytes: number
  by_namespace: Record<string, SessionStoreNamespace>
  /** Registry rows: the tasks a list shows. */
  registered_sessions: number
  /** Files a registry row reaches. */
  listed_files: number
  /** `total` minus `listed_files`: the mirror files no list reaches. */
  unreachable_by_list: number
  /** How many `pwa-` files `GET /api/sessions/restore` can serve (capped at 50). */
  reachable_by_restore: number
  oldest: SessionStoreStamp | null
  newest: SessionStoreStamp | null
}

export interface SessionRegistryEntry {
  id: string
  title?: string
  last_active?: string
  [field: string]: unknown
}

/** Body of `GET /api/sessions`: the stats plus the register list. */
export interface SessionStoreView extends SessionStoreStats {
  sessions: SessionRegistryEntry[]
}

/** Body of `POST /api/sessions/prune`. `keep_registered` absent leaves the tasks alone. */
export interface SessionPruneRequest {
  keep_rest?: number
  keep_pwa?: number
  keep_registered?: number | null
  dry_run?: boolean
}

/** Answer of `POST /api/sessions/prune`: what went, what that freed, what stays. */
export interface SessionPruneResult {
  /** Stems of the files removed (or that a dry run would remove). */
  deleted: string[]
  /** Files the run kept — the fill of the retention counts. */
  kept: number
  bytes_freed: number
  /** File count per namespace after the run (projected, on a dry run). */
  remaining: Record<string, number>
  /** The namespaces the run considered. */
  namespaces: string[]
  dry_run: boolean
}
