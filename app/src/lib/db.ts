/**
 * Ephe — IndexedDB session cache
 *
 * Replaces localStorage with IndexedDB for session persistence.
 * Provides autoload on init and debounced save on message changes.
 */

import type { DbSession, SessionFolder } from '@/types'
import type { ChatCheckpoint } from '@/lib/checkpoints'
import { queueSessionDeleted, queueSessionSync } from '@/lib/sessionSync'
import { migrateSessionRecord, normalizeFolders } from '@/store/chat/sessionModel'

const DB_NAME = 'ephe'
const DB_VERSION = 4
const STORE_NAME = 'sessions'
const CHECKPOINT_STORE = 'checkpoints'
/** Schema stamp of the current generation (R44): 3 = blocks/thinkingPhases chronology.
 *  Z53: 4 = the session model's three fields (tags / folderId / deletedAt) — the
 *  upgrade adds no object store, so the versionchange transaction only rewrites the
 *  stamp. */
const SCHEMA_VERSION = 4
const META_STORE = 'meta'
/** Z53: the folder collection of the chat store, one row in the meta store above.
 *  Folders are the authority on their own existence, so they cannot be derived from
 *  the sessions that point at them (an empty folder would vanish). */
const FOLDERS_KEY = 'sessionFolders'

export type { DbSession }

// ── Open DB ────────────────────────────────────────────────────────────────

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('updatedAt', 'updatedAt', { unique: false })
      }
      if (!db.objectStoreNames.contains(CHECKPOINT_STORE)) {
        db.createObjectStore(CHECKPOINT_STORE, { keyPath: 'sessionId' })
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE)
      }
      // Set the schema stamp after every generation; older data (without a
      // stamp, or with a level < 3) comes from before the blocks/thinkingPhases
      // chronology and is normalised on read (migrateDbSession). A stamp reset
      // per upgrade is intended: it marks the youngest generation that has
      // been written.
      // IMPORTANT: onupgradeneeded already runs inside the versionchange
      // transaction (request.transaction). A separate db.transaction() here would
      // be a nested access and would abort the upgrade — the store would never be
      // created and every save would fail.
      request.transaction?.objectStore(META_STORE).put(SCHEMA_VERSION, 'schemaVersion')
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

// ── CRUD ───────────────────────────────────────────────────────────────────

export async function dbGetAllSessions(): Promise<DbSession[]> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const request = store.getAll()
      request.onsuccess = () => resolve((request.result as DbSession[]).map(migrateDbSession))
      request.onerror = () => reject(request.error)
    })
  } catch {
    return []
  }
}

/**
 * R44: legacy normalisation on read. Level-2 data (before the block
 * chronology) may carry a `thinking` end stamp but no `thinkingPhases`
 * list — the renderer holds to the phase list. One phase entry rebuilt
 * out of the single stamp reconstructs the tick line, so that after the
 * update no thinking line is missing from the stream.
 *
 * Z53: the same read hands the row to the session model's migration, which
 * normalises `tags` / `folderId` / `deletedAt` and copies every other key
 * through untouched. A generation that never wrote the three fields is not
 * given any: an `archived` row comes back archived, not filed and not trashed.
 */
export function migrateDbSession(d: DbSession): DbSession {
  if (!Array.isArray(d.messages)) return migrateSessionRecord(d)
  const messages = d.messages.map((m) => {
    const msg = m as {
      thinking?: { start?: number; end?: number; text?: string } | null
      thinkingPhases?: unknown[]
      [k: string]: unknown
    }
    if (!msg || typeof msg !== 'object') return m
    const hasPhases = Array.isArray(msg.thinkingPhases) && msg.thinkingPhases.length > 0
    if (hasPhases || !msg.thinking || typeof msg.thinking !== 'object') return m
    return { ...msg, thinkingPhases: [msg.thinking] }
  })
  return migrateSessionRecord({ ...d, messages }) as DbSession
}

export async function dbGetSession(id: string): Promise<DbSession | null> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const request = tx.objectStore(STORE_NAME).get(id)
      request.onsuccess = () => resolve(request.result ?? null)
      request.onerror = () => reject(request.error)
    })
  } catch {
    return null
  }
}

export async function dbSaveSession(session: DbSession): Promise<void> {
  queueSessionSync(session)
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      tx.objectStore(STORE_NAME).put(session)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch (err: unknown) {
    console.warn('[IndexedDB] Failed to save session:', session.id, err)
  }
}

export async function dbDeleteSession(id: string): Promise<void> {
  queueSessionDeleted(id)
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      tx.objectStore(STORE_NAME).delete(id)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    // ignore
  }
}

export async function dbClearAll(): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      tx.objectStore(STORE_NAME).clear()
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    // ignore
  }
}

/**
 * Z53: read the folder collection (one row in the meta store).
 *
 * The collection is a first-class row rather than something derived from the
 * sessions that point at a folder, so a folder the user created and has not
 * filled yet survives a reload. Every record is normalised on the way out —
 * same contract as the session rows.
 *
 * A store that cannot be opened yields an empty collection: folders are a
 * convenience, and a read that failed must not cost the caller its sessions.
 */
export async function dbGetSessionFolders(): Promise<SessionFolder[]> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readonly')
      const request = tx.objectStore(META_STORE).get(FOLDERS_KEY)
      request.onsuccess = () => resolve(normalizeFolders(request.result))
      request.onerror = () => reject(request.error)
    })
  } catch {
    return []
  }
}

export async function dbSetSessionFolders(folders: SessionFolder[]): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readwrite')
      tx.objectStore(META_STORE).put(normalizeFolders(folders), FOLDERS_KEY)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch (err: unknown) {
    console.warn('[IndexedDB] Failed to save session folders:', err)
  }
}

// ── Debounced save helper ──────────────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null
let pendingSession: DbSession | null = null

export function debouncedSaveSession(session: DbSession, delayMs: number = 1500): void {
  if (saveTimer) {
    clearTimeout(saveTimer)
  }
  pendingSession = session
  saveTimer = setTimeout(() => {
    const next = pendingSession
    saveTimer = null
    pendingSession = null
    if (next) dbSaveSession(next)
  }, delayMs)
}

/**
 * Flush the outstanding debounced write immediately (I6 P2b).
 *
 * Every chunk re-times the timer — if the stream stops just before a reload
 * (stop click, tab stop) it never fires and IndexedDB keeps the old snapshot.
 * The store calls this at the end of a turn (finishTurn /
 * markStreamError); installDbAutoFlush() additionally catches
 * tab changes and page unload.
 */
export function flushPendingSave(): void {
  if (!pendingSession) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  const next = pendingSession
  pendingSession = null
  void dbSaveSession(next)
}

let autoFlushInstalled = false

/**
 * Flush on tab change/unload — installed once by the app entry point.
 *
 * Chunk placement (audited 2026-10-15): this call holds `lib/db.ts` in the entry chunk. The
 * store's imports of the same module sit behind a route and would split away; this one runs
 * before the first render, so `dist/assets/index-*.js` carries the checkpoint store. The
 * audit read the store imports as the cause, and turning them into `import()` leaves the
 * module where it is. The build's single remaining warning is the 500 kB chunk-size notice,
 * whose subjects are the vendor chunks (`elk`, `mermaid`, `cynefin`).
 */
export function installDbAutoFlush(): void {
  if (autoFlushInstalled || typeof window === 'undefined') return
  autoFlushInstalled = true
  window.addEventListener('beforeunload', () => flushPendingSave())
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushPendingSave()
  })
}

// ── Checkpoints (P2-7) ─────────────────────────────────────────────────────

export async function dbGetCheckpoints(sessionId: string): Promise<ChatCheckpoint[]> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(CHECKPOINT_STORE, 'readonly')
      const request = tx.objectStore(CHECKPOINT_STORE).get(sessionId)
      request.onsuccess = () =>
        resolve((request.result as { items?: ChatCheckpoint[] })?.items ?? [])
      request.onerror = () => reject(request.error)
    })
  } catch {
    return []
  }
}

export async function dbSaveCheckpoints(
  sessionId: string,
  checkpoints: ChatCheckpoint[],
): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(CHECKPOINT_STORE, 'readwrite')
      tx.objectStore(CHECKPOINT_STORE).put({ sessionId, items: checkpoints })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch (err: unknown) {
    console.warn('[IndexedDB] Failed to save checkpoints:', sessionId, err)
  }
}

export async function dbDeleteCheckpoints(sessionId: string): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(CHECKPOINT_STORE, 'readwrite')
      tx.objectStore(CHECKPOINT_STORE).delete(sessionId)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    // ignore
  }
}
