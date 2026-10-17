/**
 * Ephe — session sync to the server (R30).
 *
 * Sessions live in IndexedDB; the server-side FTS5 index could never see
 * them (documented search gap). This module mirrors saved/deleted sessions
 * to POST /api/sessions/sync — local-only (same machine), fire-and-forget,
 * debounced, never throws into the UI.
 *
 * Opt-out: localStorage 'ephe.sessions.sync' === '0'.
 */
import type { ChatMessage, DbSession } from '@/types'
import { syncSessions, type SyncSession } from '@/lib/api'
import { isHelperSessionId } from '@/lib/helperSession'
import i18n from '@/i18n'
import { toastBus } from '@/lib/toast'

const OPT_OUT_KEY = 'ephe.sessions.sync'
const TOMBSTONE_KEY = 'ephe.sessions.deleted'
const FLUSH_MS = 5000

const pendingSessions = new Map<string, DbSession>()
const pendingDeleted = new Set<string>()
let flushTimer: ReturnType<typeof setTimeout> | null = null
let flushing = false

export function isSessionSyncEnabled(): boolean {
  try {
    return localStorage.getItem(OPT_OUT_KEY) !== '0'
  } catch {
    return true
  }
}

/**
 * Synchronously persisted tombstone registry (R-Fix bug 1).
 *
 * The 5s debounced flush can be lost on a hard reload before the DELETE reaches
 * the server mirror. The mirror would still be filled and `restoreFromServer`
 * would bring the session back. The tombstones (localStorage, synchronous)
 * survive the reload and filter the mirror row out until the delete POST has
 * been caught up.
 */
function readTombstones(): string[] {
  try {
    const raw = localStorage.getItem(TOMBSTONE_KEY)
    const arr = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(arr) ? arr.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function writeTombstones(ids: string[]): void {
  try {
    localStorage.setItem(TOMBSTONE_KEY, JSON.stringify(ids))
  } catch {
    /* quota / storage unavailable — tombstones are best-effort */
  }
}

/** True when the session was deleted locally but the mirror delete is not yet
 *  confirmed. initFromDb filters such ids out of the server restore. */
export function isTombstoned(id: string): boolean {
  return readTombstones().includes(id)
}

export function queueSessionSync(session: DbSession): void {
  if (!isSessionSyncEnabled() || !session?.id) return
  // Visibility wave: helper sessions never enter the mirror. Their durable storage
  // is the helper ledger (~/.ephe/subagent_history.json), and a click on a helper
  // row rebuilds the chat from it. Mirrored, twenty delegations would crowd real
  // tasks out of the 50-entry restore window and fill the full-text index with
  // duplicate content.
  if (isHelperSessionId(session.id)) return
  pendingSessions.set(session.id, session)
  scheduleFlush()
}

export function queueSessionDeleted(id: string): void {
  if (!isSessionSyncEnabled() || !id) return
  pendingSessions.delete(id)
  pendingDeleted.add(id)
  // Synchronously into the tombstone set — survives a reload before the debounced flush.
  const tombs = readTombstones()
  if (!tombs.includes(id)) writeTombstones([...tombs, id])
  scheduleFlush()
}

function scheduleFlush(): void {
  if (flushTimer) clearTimeout(flushTimer)
  flushTimer = setTimeout(() => void flushSessionSync(), FLUSH_MS)
}

/**
 * The server refuses a single call above this cap
 * (`server/routes/session_mirror.py: MAX_SESSIONS_PER_CALL`) with a 413. The
 * flush used to put the whole pending queue into one call, so a store of more
 * than this many pending sessions could never drain: every flush sent the same
 * oversized batch, got the 413, and left the queue untouched — new tasks never
 * reached the mirror (W10 blocker). The cap is a deliberate input guard (batch
 * size, id validation, message size), so the fix belongs on this side: send the
 * queue in batches. A store of any size now drains, and only a batch the server
 * confirmed leaves the queue. Keep this equal to the route constant.
 */
export const MAX_SESSIONS_PER_CALL = 50

/** One DbSession in the wire shape the mirror route accepts. */
function toWireSession(s: DbSession): SyncSession {
  return {
    id: s.id,
    title: s.title ?? '',
    ...(s.mode ? { mode: s.mode } : {}),
    ...(s.parentId ? { parent_id: s.parentId } : {}),
    // R6/S1: the birth date travels along, otherwise the restore dates to the
    // mtime of the mirror file — and that slides to "now" on every sync.
    ...(typeof s.createdAt === 'number' ? { created_at: s.createdAt } : {}),
    messages: ((s.messages as ChatMessage[]) ?? [])
      .filter((m) => m && (m.role === 'user' || m.role === 'assistant' || m.role === 'system'))
      .map((m) => ({
        role: m.role,
        content: String(m.content ?? ''),
        timestamp: m.timestamp ?? 0,
        // R44 (P2): the cadence chronology travels too — the index sees the
        // same order as the UI (tool-/thinking line positions).
        ...(Array.isArray(m.blocks) ? { blocks: m.blocks } : {}),
        // R6/S1: cards, activities, artifact links and the turn anchor.
        // blocks carries only the order ({kind, callId}) — without the
        // payloads a restored history shows empty references.
        ...(Array.isArray(m.tool_calls) ? { tool_calls: m.tool_calls } : {}),
        ...(Array.isArray(m.activities) ? { activities: m.activities } : {}),
        ...(Array.isArray(m.artifacts) ? { artifacts: m.artifacts } : {}),
        ...(typeof m.turnId === 'string' && m.turnId ? { turnId: m.turnId } : {}),
        ...(typeof m.durationMs === 'number' ? { durationMs: m.durationMs } : {}),
        ...(m.thinking ? { thinking: m.thinking } : {}),
        ...(Array.isArray(m.thinkingPhases)
          ? {
              thinkingPhases: (
                m.thinkingPhases as Array<{ start?: number; end?: number; text?: string }>
              ).map((ph) => ({
                start: ph?.start ?? null,
                end: ph?.end ?? null,
                text: String(ph?.text ?? ''),
              })),
            }
          : {}),
      })),
  }
}

/** Send everything queued in batches of at most MAX_SESSIONS_PER_CALL; keeps the
 *  batches the server did not confirm (retried next flush). */
export async function flushSessionSync(): Promise<void> {
  flushTimer = null
  if (flushing) return
  if (pendingSessions.size === 0 && pendingDeleted.size === 0) return
  if (!isSessionSyncEnabled()) return
  flushing = true
  // R6/S3: an empty shell is not mirror content. Otherwise boot put "New task"
  // rows with null messages into the mirror and, after every restore, into the
  // sidebar of a fresh profile.
  const sessions = [...pendingSessions.values()].filter((s) => (s.messages?.length ?? 0) > 0)
  const deleted = [...pendingDeleted]
  if (sessions.length === 0 && deleted.length === 0) {
    flushing = false
    return
  }
  // One call per batch, never above the route cap — that is what lets a store of
  // any size drain. Queue a standalone call for deletions when nothing else is
  // pending; otherwise they ride with the first batch.
  const batches: Array<{ sessions: DbSession[]; deleted: string[] }> =
    sessions.length === 0
      ? [{ sessions: [], deleted }]
      : Array.from({ length: Math.ceil(sessions.length / MAX_SESSIONS_PER_CALL) }, (_, i) => ({
          sessions: sessions.slice(i * MAX_SESSIONS_PER_CALL, (i + 1) * MAX_SESSIONS_PER_CALL),
          deleted: i === 0 ? deleted : [],
        }))
  let droppedTotal = 0
  try {
    for (const batch of batches) {
      const result = await syncSessions({
        sessions: batch.sessions.map(toWireSession),
        deleted: batch.deleted,
      })
      droppedTotal += result?.dropped_sessions ?? 0
      // only clear what this call actually confirmed
      for (const s of batch.sessions) {
        if (pendingSessions.get(s.id) === s) pendingSessions.delete(s.id)
      }
      for (const id of batch.deleted) pendingDeleted.delete(id)
    }
    // Mirror delete confirmed — the tombstone may go (idempotent, only the ids
    // actually sent, not the ones queued again afterwards).
    if (deleted.length > 0) {
      const tombs = readTombstones()
      const kept = tombs.filter((t) => !deleted.includes(t))
      if (kept.length !== tombs.length) writeTombstones(kept)
    }
  } catch {
    // offline/backend down — the unconfirmed batches stay queued for the next
    // mutation or page load
  } finally {
    // W4: the response had no reader until here. A drop is not a statistic — the
    // affected tasks are missing from the full-text index, and someone searching
    // afterwards searches in half the surface. That has to be said. Reported once,
    // summed over every batch of this flush.
    if (droppedTotal > 0) {
      toastBus.info(
        i18n.t('sync.droppedTitle'),
        i18n.t('sync.droppedBody', { count: droppedTotal }),
      )
    }
    flushing = false
  }
}
