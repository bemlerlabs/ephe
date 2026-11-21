/**
 * The chat store's session model — what a session is apart from its messages.
 *
 * The store knew exactly one thing about a session's place in the world:
 * `archived`, a boolean (M2). A user needs three ideas, and none of them is
 * that boolean:
 *
 *   tags    free-form labels, many per session — a session can be "research"
 *           and "ephe" at the same time.
 *   folders containment, at most one per session — a session is filed in one
 *           place or nowhere.
 *   trash   a soft delete the user can undo: the session leaves every list,
 *           its messages stay, and a restore puts it back as it was.
 *
 * `archived` stays where it is and keeps its meaning. Archive is a shelf the
 * user keeps — an archived session is still reachable (the sidebar's archive
 * filter shows it) and nothing about it is pending a decision. Trash is a
 * question. A folder is a group the user made. `migrateSessionRecord` below
 * refuses to read one of the three into another.
 *
 * Nothing in here touches the store, IndexedDB or React. These are the shapes
 * and the field operations the store actions will be wired to.
 */
import type { DbSession, Session, SessionFolder, SessionState } from '@/types'

/** One persisted session row, as any generation of the writer left it. */
export type PersistedSession = Record<string, unknown>

/**
 * The keys this model owns. Everything else in a persisted row belongs to the
 * writer that wrote it and travels through untouched: the migration may rename
 * no field, drop no field and invent no field.
 */
export const SESSION_MODEL_FIELDS = ['tags', 'folderId', 'deletedAt'] as const

/**
 * A stored stamp is an epoch in milliseconds, positive and finite. `0`, a
 * negative value and `NaN` are not times this store could have written, so they
 * read as "no stamp" — the same rule the mirror reader applies to message
 * timestamps (`lib/restore.ts` rejects a seconds-based epoch and a skewed clock
 * instead of dating a session to 1970).
 */
function isStamp(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0
}

/**
 * Where a session sits. Trash wins over the archiving shelf: a trashed session
 * is out of every list, the archive filter included. The `archived` flag
 * underneath survives untouched, so a restore returns the session to the shelf
 * it came from.
 */
export function sessionState(s: Pick<Session, 'archived' | 'deletedAt'>): SessionState {
  if (isTrashed(s)) return 'trashed'
  return s.archived ? 'archived' : 'live'
}

export function isTrashed(s: Pick<Session, 'deletedAt'>): boolean {
  return isStamp(s.deletedAt)
}

/**
 * Tags in stored form: whitespace collapsed, blanks dropped, duplicates
 * dropped case-insensitively (the first spelling wins — "Ephe" and "ephe" are
 * one tag, and the store keeps the spelling the user typed first).
 *
 * A bare string is split on commas. A writer that stored a comma-separated tag
 * line produced one tag list, and reading it back as a single tag would show
 * the user a label with commas in it.
 *
 * No length cap. Cutting a long tag would file the session under a word nobody
 * typed, and the store is local, so the only cost of a long tag is a long chip.
 */
export function normalizeTags(input: unknown): string[] {
  const list: unknown[] =
    typeof input === 'string' ? input.split(',') : Array.isArray(input) ? input : []
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of list) {
    if (typeof raw !== 'string') continue
    const tag = raw.replace(/\s+/g, ' ').trim()
    if (!tag) continue
    const key = tag.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(tag)
  }
  return out
}

function sameTags(before: unknown, after: string[]): boolean {
  // A row that never had a tag field and normalises to no tag is unchanged. Read
  // through Array.isArray alone, a row with no tags at all would look changed and
  // be copied on every read.
  if (before === undefined) return after.length === 0
  if (!Array.isArray(before) || before.length !== after.length) return false
  return before.every((t, i) => t === after[i])
}

/** A folder name in stored form: whitespace collapsed, trimmed. A name the user
 *  left empty stays empty; it is not repaired into "Untitled", because a folder
 *  the user did not name is not a folder the store may rename. */
export function normalizeFolderName(name: unknown): string {
  return typeof name === 'string' ? name.replace(/\s+/g, ' ').trim() : ''
}

/** A persisted folder record, or null when it is not one. The id is what makes
 *  a folder addressable, so a record without one is not a folder. */
export function normalizeFolder(raw: unknown): SessionFolder | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const rec = raw as Record<string, unknown>
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const folder: SessionFolder = { id, name: normalizeFolderName(rec.name) }
  // An unknown creation date stays unknown; stamping it with "now" would date
  // the folder to the moment the store happened to read it.
  if (isStamp(rec.createdAt)) folder.createdAt = rec.createdAt
  return folder
}

/** The folder collection of a persisted row. Duplicates by id collapse onto the
 *  first record: a later copy is not a second folder, and keeping both would
 *  give one folder two names. */
export function normalizeFolders(input: unknown): SessionFolder[] {
  if (!Array.isArray(input)) return []
  const out: SessionFolder[] = []
  const seen = new Set<string>()
  for (const raw of input) {
    const folder = normalizeFolder(raw)
    if (!folder || seen.has(folder.id)) continue
    seen.add(folder.id)
    out.push(folder)
  }
  return out
}

/** A stored folder reference, or undefined when the row names no folder. */
export function normalizeFolderId(input: unknown): string | undefined {
  return typeof input === 'string' && input.trim() ? input.trim() : undefined
}

// Field operations: one session in, one session out.

/** Replace the tag list. An empty list removes the field: a session with no
 *  tags carries no tags, rather than an empty array every reader must test. */
export function setSessionTags(s: Session, tags: unknown): Session {
  const next: Session = { ...s }
  const clean = normalizeTags(tags)
  if (clean.length > 0) next.tags = clean
  else delete next.tags
  return next
}

/** File the session in one folder, or in none when `folderId` is null/blank. */
export function setSessionFolder(s: Session, folderId: string | null): Session {
  const next: Session = { ...s }
  const id = normalizeFolderId(folderId)
  if (id) next.folderId = id
  else delete next.folderId
  return next
}

/** Move a session to the trash. The messages are kept: the trash exists so the
 *  user can undo, and a delete that dropped the content first would leave
 *  nothing to undo. */
export function trashSession(s: Session, at: number = Date.now()): Session {
  return { ...s, deletedAt: at }
}

/** Take a session out of the trash. The `archived` flag is left alone, so a
 *  session trashed from the archive shelf returns to it. */
export function restoreSession(s: Session): Session {
  const next: Session = { ...s }
  delete next.deletedAt
  return next
}

// The persisted-shape migration.

function assign(target: Record<string, unknown>, key: string, value: unknown): void {
  if (value === undefined) delete target[key]
  else target[key] = value
}

/**
 * One persisted session row, read into this generation's shape.
 *
 * A row from a generation that never wrote the three fields comes back with none
 * of them: no tags array, no folder derived from `archived`, no `deletedAt`
 * derived from `archived`. What the writer left out stays left out. The row's own
 * keys, values and order are otherwise copied through unchanged.
 *
 * The row itself is returned when nothing had to change, so a caller (and a
 * test) can tell a row the normaliser had to touch from one it left alone.
 */
export function migrateSessionRecord(raw: unknown): DbSession {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return raw as DbSession
  const rec = raw as PersistedSession
  const tags = normalizeTags(rec.tags)
  const folderId = normalizeFolderId(rec.folderId)
  const deletedAt = isStamp(rec.deletedAt) ? rec.deletedAt : undefined
  if (sameTags(rec.tags, tags) && rec.folderId === folderId && rec.deletedAt === deletedAt) {
    return raw as DbSession
  }
  const next: PersistedSession = { ...rec }
  assign(next, 'tags', tags.length > 0 ? tags : undefined)
  assign(next, 'folderId', folderId)
  assign(next, 'deletedAt', deletedAt)
  return next as unknown as DbSession
}

/**
 * A whole stored collection, read row by row.
 *
 * Count and order are preserved exactly. A migration that dropped one session
 * would be the one mistake the user cannot work around: the messages of that
 * session are in this array and nowhere else.
 */
export function migrateSessionRecords(raw: readonly unknown[]): DbSession[] {
  return raw.map(migrateSessionRecord)
}
