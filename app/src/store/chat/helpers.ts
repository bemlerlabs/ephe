/**
 * Pure chat-store helpers: the session row shapes, the transcript edits and the
 * composer-mode vocabulary. The module imports nothing that runs — no i18n boot, no IO —
 * because the surfaces and the `lib/` readers (the plan-card handoff) name these values,
 * and reaching them must not put the production catalog into their graph. The one helper
 * that needs a translated string, the compaction indicator, sits with the action that
 * writes it (`session.ts`).
 */
import type { ChatMessage, ComposerMode, DbSession, Session, ThinkingPhase } from '@/types'

/** Default title (G2: the auto title only ever applies to this one) — English,
 * the product's default language since round 14; the auto title replaces it anyway. */
export const DEFAULT_SESSION_TITLE = 'New task'

/**
 * G2: auto title from the first user message — ~48 characters, cut at a word
 * boundary, whitespace collapsed (AI-client parity).
 */
export function deriveSessionTitle(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= 48) return clean
  const cut = clean.slice(0, 48)
  const lastSpace = cut.lastIndexOf(' ')
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut).trimEnd() + '…'
}

// The shared default mode of a fresh session: a mode that may use tools, so that
// "just start writing" works without looking tools up first (parity with leading
// agent frameworks). Every mode fallback uses this one.
export const DEFAULT_COMPOSER_MODE: ComposerMode = 'operator'

/**
 * Task 3 rename: the names a session may still carry from before the rename. Each maps to
 * the one current mode whose behaviour it had — the server's alias table
 * (`server/routes/chat.py::_MODE_ALIASES`, Task 2) resolves the same pairs, so the
 * rename moves no privilege here. Only the three values the retired menu could
 * write get rewritten at load (`MIGRATABLE_LEGACY_MODES`). Two legacy values keep
 * their stored spelling: `agent` (tools available, manual approvals), because a
 * rewrite would strip such a session of its tools, and `edit-auto`, because the
 * Operator tile auto-approves every tool where the stored value asked for
 * everything outside the edit family — see `COMPAT_EDIT_FAMILY_MODE`.
 */
const LEGACY_COMPOSER_MODES: Record<string, ComposerMode> = {
  ask: 'analyst',
  plan: 'architect',
  'full-access': 'operator',
}

/** The stored values the load-time migration rewrites: exactly the three values the
 *  retired menu could write, each landing on a mode with the same privileges. */
export const MIGRATABLE_LEGACY_MODES: ReadonlySet<string> = new Set(['ask', 'plan', 'full-access'])

/**
 * The wire value of the menu-retired `edit-auto`. The server resolves it to the
 * edit-family compatibility factor: the edit tools run and every other tool keeps
 * asking, under all four approval profiles (the equivalence is pinned by
 * `tests/test_composer_mode_rename.py`). Stored sessions and the accepted-plan
 * handoff (`planCardModel.ts`) keep sending this exact string — retirement
 * happened to the tile alone, so no privilege moved anywhere.
 */
export const COMPAT_EDIT_FAMILY_MODE = 'edit-auto'

/** The modes that own a tile in the menu — the whole `ComposerMode` union. */
const TILED_COMPOSER_MODES: readonly ComposerMode[] = [
  'analyst',
  'architect',
  'operator',
  'creator',
]

/**
 * Map a stored (or current, or empty) mode value onto one selectable mode key.
 * A value with no tile — the retired `edit-auto`, the legacy `agent`, another
 * client's mode — keeps its stored spelling, so an unchecked string never enters
 * `ComposerMode`; the surfaces that name it fall back to its section wording
 * (`ComposerModeChip.tsx`).
 */
export function normalizeComposerMode(value: string | undefined): string {
  if (!value) return DEFAULT_COMPOSER_MODE
  const mapped = LEGACY_COMPOSER_MODES[value]
  if (mapped) return mapped
  const tiled = TILED_COMPOSER_MODES.find((m) => m === value)
  return tiled ?? value
}

export function toDbSession(s: Session): DbSession {
  return {
    id: s.id,
    title: s.title,
    messages: s.messages,
    createdAt: s.createdAt,
    updatedAt: Date.now(),
    ...(s.pinned ? { pinned: true } : {}),
    ...(s.titleCustom ? { titleCustom: true } : {}),
    ...(s.archived ? { archived: true } : {}),
    // Z53: the three stored ideas beside the archive flag. Each is omitted when
    // empty, so a row with no tags carries no `tags` key at all.
    ...(s.tags && s.tags.length > 0 ? { tags: s.tags } : {}),
    ...(s.folderId ? { folderId: s.folderId } : {}),
    ...(s.deletedAt ? { deletedAt: s.deletedAt } : {}),
    ...(s.unread ? { unread: true } : {}),
    ...(s.parentId ? { parentId: s.parentId } : {}),
    ...(s.mode ? { mode: s.mode } : {}),
    // Wave 3: measured session totals survive the reload (cost monitor).
    ...(s.usageTotals ? { usageTotals: s.usageTotals } : {}),
  }
}

export function fromDbSession(d: DbSession): Session {
  return {
    id: d.id,
    title: d.title,
    messages: d.messages as ChatMessage[],
    createdAt: d.createdAt,
    ...(d.pinned ? { pinned: true } : {}),
    ...(d.titleCustom ? { titleCustom: true } : {}),
    ...(d.archived ? { archived: true } : {}),
    ...(d.tags && d.tags.length > 0 ? { tags: d.tags } : {}),
    ...(d.folderId ? { folderId: d.folderId } : {}),
    ...(d.deletedAt ? { deletedAt: d.deletedAt } : {}),
    ...(d.unread ? { unread: true } : {}),
    ...(d.parentId ? { parentId: d.parentId } : {}),
    ...(d.mode ? { mode: d.mode } : {}),
    ...(d.usageTotals ? { usageTotals: d.usageTotals } : {}),
  }
}

/**
 * Update the ACTIVE assistant message (streaming=true) of the session the turn
 * belongs to, in place. Pure state transformation (Zustand `set` updater).
 *
 * The turn's own session wins over whatever is displayed: a chunk that arrives
 * after the reader moved to another task belongs to the question that was asked
 * where they came from. `currentSession` only follows while the two are the same
 * session — otherwise the answer would repaint the screen the user left.
 */
export function updateActiveMessage(
  s: {
    sessions: Session[]
    activeSessionId: string | null
    streamSessionId?: string | null
    currentSession?: Session | null
  },
  fn: (m: ChatMessage) => ChatMessage,
): { sessions: Session[]; currentSession: Session | null } {
  const target = s.streamSessionId ?? s.activeSessionId
  if (!target) return { sessions: s.sessions, currentSession: null }
  const sessions = s.sessions.map((sess) => {
    if (sess.id !== target) return sess
    const msgs = sess.messages
    let last = -1
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i]!.role === 'assistant' && msgs[i]!.streaming) {
        last = i
        break
      }
    }
    if (last === -1) return sess
    const next = [...msgs]
    next[last] = fn(msgs[last]!)
    return { ...sess, messages: next }
  })
  const shown = sessions.find((sess) => sess.id === s.activeSessionId) ?? null
  return {
    sessions,
    currentSession: target === s.activeSessionId ? shown : (s.currentSession ?? null),
  }
}

/** Close all open reasoning phases (turn end, error, healing). */
export function closeThinkingPhases(m: ChatMessage): ThinkingPhase[] | undefined {
  if (!m.thinkingPhases) return undefined
  const now = Date.now()
  return m.thinkingPhases.map((p) => (p.end === null ? { ...p, end: now } : p))
}
