import {
  dbDeleteSession,
  dbGetAllSessions,
  dbGetCheckpoints,
  dbSaveSession,
  debouncedSaveSession,
} from '@/lib/db'
import { restoreFromServer } from '@/lib/restore'
import { isTombstoned } from '@/lib/sessionSync'
import { compactMessages } from '@/lib/compact'
import type { ChatMessage, Session } from '@/types'
import type { ChatState, GetFn, SetFn } from './types'
import {
  closeThinkingPhases,
  DEFAULT_COMPOSER_MODE,
  DEFAULT_SESSION_TITLE,
  deriveSessionTitle,
  fromDbSession,
  indicatorMessage,
  toDbSession,
} from './helpers'

/** On load, heals a bubble left streaming (streaming=true) by a dead tab. */
function healOrphan(m: ChatMessage): ChatMessage {
  if (m.role !== 'assistant' || !m.streaming) return m
  return {
    ...m,
    streaming: false,
    thinking: m.thinking ? { ...m.thinking, end: m.thinking.end ?? Date.now() } : null,
    thinkingPhases: closeThinkingPhases(m),
    streamMeta: {
      ...(m.streamMeta ?? {}),
      reflecting: false,
      revising: false,
      qualityCheck: false,
    },
    activities: m.activities?.map((a) =>
      a.status === 'running' ? { ...a, status: 'done' as const } : a,
    ),
  }
}

/** Session lifetime + persistence actions (IndexedDB + server mirror). */
export function makeSessionActions(
  set: SetFn,
  get: GetFn,
  persistActive: () => void,
): Partial<ChatState> {
  return {
    // Load persisted sessions from IndexedDB on first mount
    initFromDb: async () => {
      try {
        let dbSessions = await dbGetAllSessions()
        // W19 (storage model): the server copy (~/.ephe/sessions/) is the durable
        // store per device — the browser is only a cache. Always merge with the
        // mirror: sessions missing locally come back (cache loss, storage eviction,
        // a fresh browser), local ones are left untouched.
        try {
          const serverSessions = await restoreFromServer()
          const known = new Set(dbSessions.map((d) => d.id))
          // R-fix bug 1: sessions deleted locally but not yet confirmed in the
          // mirror (tombstones) must not come back from the server mirror.
          const missing = serverSessions.filter((d) => !known.has(d.id) && !isTombstoned(d.id))
          if (missing.length > 0) {
            dbSessions = [...dbSessions, ...missing].sort(
              (a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0),
            )
            for (const d of missing) await dbSaveSession(d)
          }
        } catch {
          /* offline or an empty mirror — the local sessions are enough */
        }
        if (dbSessions.length > 0) {
          // I6 P2b: a reload NEVER finds a continued stream — a bubble saved with
          // streaming=true still on it when the tab died would come back as a
          // zombie with an eternal spinner and empty content. Heal on load: close
          // the turn, keep the text that was rescued. The in-memory state (a mode
          // just chosen, not flushed yet) outranks the persisted snapshot,
          // otherwise the late-arriving hydrate overwrites a mode set by a click.
          const memById = new Map(get().sessions.map((m) => [m.id, m]))
          const sessions = dbSessions.map((d) => {
            const s = fromDbSession(d)
            const healed: Session = { ...s, messages: s.messages.map(healOrphan) }
            const mem = memById.get(s.id)
            if (mem?.mode) healed.mode = mem.mode
            return healed
          })
          // Found 2026-10-01 (F-AB): getAll() returns primary-key order — without
          // sorting, "sessions[0]" was an ARBITRARY session and the reload landed
          // in the wrong chat. The most recently updated one wins; the explicitly
          // remembered choice ('ephe.lastSession') beats everything.
          sessions.sort((a, b) => {
            const da = dbSessions.find((d) => d.id === a.id)?.updatedAt ?? a.createdAt
            const dbb = dbSessions.find((d) => d.id === b.id)?.updatedAt ?? b.createdAt
            return dbb - da
          })
          const first = sessions[0]!
          let lastActive: string | null = null
          try {
            lastActive = localStorage.getItem('ephe.lastSession')
          } catch {
            /* Private Mode */
          }
          const activeId =
            (lastActive && sessions.some((x) => x.id === lastActive) ? lastActive : null) ??
            get().activeSessionId ??
            first.id
          const active = sessions.find((x) => x.id === activeId) ?? first
          set({ sessions, activeSessionId: active.id, currentSession: active })
          // Load the checkpoints of the active session
          const cps = await dbGetCheckpoints(active.id)
          if (cps.length > 0) {
            set((state) => ({ checkpoints: { ...state.checkpoints, [first.id]: cps } }))
          }
        }
      } catch (err) {
        console.warn('[ChatStore] Failed to load sessions from IndexedDB:', err)
      } finally {
        // P1-10: boot hydration finished — also in the empty/error case, so the
        // message-list skeleton gives way to real content or the welcome state.
        set({ hydrated: true })
      }
    },

    setSessions: (sessions) => {
      set({ sessions })
      // Persist all sessions to IndexedDB
      for (const s of sessions) {
        debouncedSaveSession(toDbSession(s))
      }
    },
    setActiveSession: (id) => {
      const session = get().sessions.find((s) => s.id === id)
      set({ activeSessionId: id, currentSession: session ?? null })
      // F-AB: the active choice survives a reload.
      try {
        localStorage.setItem('ephe.lastSession', id)
      } catch {
        /* Private Mode */
      }
    },
    // W19: the composer mode is a session attribute — it survives a reload and a
    // server restore, instead of falling back to 'ask' on every unmount.
    setSessionMode: (id, mode) => {
      set((s) => {
        const sessions = s.sessions.map((sess) => (sess.id === id ? { ...sess, mode } : sess))
        return {
          sessions,
          currentSession: sessions.find((x) => x.id === s.activeSessionId) ?? null,
        }
      })
      const updated = get().sessions.find((x) => x.id === id)
      if (updated) debouncedSaveSession(toDbSession(updated))
    },
    createSession: (title) => {
      const newSession: Session = {
        id: crypto.randomUUID(),
        title: title || DEFAULT_SESSION_TITLE,
        messages: [],
        mode: DEFAULT_COMPOSER_MODE,
        createdAt: Date.now(),
        // A title passed in explicitly counts as set (G2: no auto-title)
        ...(title ? { titleCustom: true } : {}),
      }
      set((state) => ({
        sessions: [newSession, ...state.sessions],
        activeSessionId: newSession.id,
        currentSession: newSession,
      }))
      // F-AB: the active choice survives a reload.
      try {
        localStorage.setItem('ephe.lastSession', newSession.id)
      } catch {
        /* Private Mode */
      }
      // Persist new session to IndexedDB
      debouncedSaveSession(toDbSession(newSession))
    },
    deleteSession: (id) => {
      set((state) => {
        const updated = state.sessions.filter((s) => s.id !== id)
        return {
          sessions: updated,
          activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
          currentSession: state.currentSession?.id === id ? null : state.currentSession,
        }
      })
      // Delete from IndexedDB
      dbDeleteSession(id)
    },
    renameSession: (id, title) => {
      const clean = title.trim()
      if (!clean) return
      set((state) => {
        const sessions = state.sessions.map((s) =>
          s.id === id ? { ...s, title: clean, titleCustom: true } : s,
        )
        return {
          sessions,
          currentSession:
            state.currentSession?.id === id
              ? { ...state.currentSession, title: clean, titleCustom: true }
              : state.currentSession,
        }
      })
      // Persist renamed session (debounced)
      const renamed = get().sessions.find((s) => s.id === id)
      if (renamed) debouncedSaveSession(toDbSession(renamed))
    },
    togglePin: (id) => {
      set((state) => {
        const sessions = state.sessions.map((s) => (s.id === id ? { ...s, pinned: !s.pinned } : s))
        return {
          sessions,
          currentSession:
            state.currentSession?.id === id
              ? { ...state.currentSession, pinned: !state.currentSession.pinned }
              : state.currentSession,
        }
      })
      const pinned = get().sessions.find((s) => s.id === id)
      if (pinned) debouncedSaveSession(toDbSession(pinned))
    },
    // M2 (reference parity): archived/unread as slim flags — the same persistence
    // path togglePin uses (debouncedSaveSession).
    toggleArchive: (id) => {
      set((state) => {
        const sessions = state.sessions.map((s) =>
          s.id === id ? { ...s, archived: !s.archived } : s,
        )
        return {
          sessions,
          currentSession:
            state.currentSession?.id === id
              ? { ...state.currentSession, archived: !state.currentSession.archived }
              : state.currentSession,
        }
      })
      const touched = get().sessions.find((s) => s.id === id)
      if (touched) debouncedSaveSession(toDbSession(touched))
    },
    markUnread: (id) => {
      set((state) => ({
        sessions: state.sessions.map((s) => (s.id === id ? { ...s, unread: !s.unread } : s)),
      }))
      const touched = get().sessions.find((s) => s.id === id)
      if (touched) debouncedSaveSession(toDbSession(touched))
    },
    compactSession: () => {
      const state = get()
      if (!state.activeSessionId) return { changed: false }
      const session = state.sessions.find((s) => s.id === state.activeSessionId)
      if (!session || session.messages.length === 0) return { changed: false }

      const { compacted, stats } = compactMessages(session.messages)
      if (!stats.changed) return { changed: false, stats }

      set((st) => {
        const sessions = st.sessions.map((s) =>
          s.id === state.activeSessionId
            ? { ...s, messages: [...compacted, indicatorMessage(stats)] }
            : s,
        )
        return {
          sessions,
          currentSession: sessions.find((s) => s.id === state.activeSessionId) ?? null,
        }
      })
      persistActive()
      return { changed: true, stats }
    },
    addMessage: (role, content, toolCalls) => {
      set((state) => {
        if (!state.activeSessionId) return state
        const message: ChatMessage = {
          id: crypto.randomUUID(),
          role,
          content,
          timestamp: Date.now(),
          tool_calls: toolCalls,
        }
        const sessions = state.sessions.map((s) => {
          if (s.id !== state.activeSessionId) return s
          // G2: auto title from the first user message (unless titleCustom)
          const autoTitle =
            role === 'user' &&
            !s.titleCustom &&
            s.title === DEFAULT_SESSION_TITLE &&
            s.messages.length === 0
              ? { title: deriveSessionTitle(content) }
              : {}
          return { ...s, ...autoTitle, messages: [...s.messages, message] }
        })
        const currentSession = sessions.find((s) => s.id === state.activeSessionId)
        return { sessions, currentSession }
      })
      persistActive()
    },
    setTyping: (typing) => set({ isTyping: typing }),
    setPendingToolCall: (tool) => set({ pendingToolCall: tool }),

    // ── Z37: session fork (parity) ───────────────────────────────────────
    // A prefix copy following the truncateAfter pattern: identical objects are
    // enough, because messages are treated as immutable records.
    branchSession: (fromMsgId) => {
      const st = get()
      const src = st.currentSession ?? st.sessions.find((x) => x.id === st.activeSessionId)
      if (!src) return
      const idx = src.messages.findIndex((m) => m.id === fromMsgId)
      if (idx === -1) return
      const fork: Session = {
        id: crypto.randomUUID(),
        title: `${src.title} · #${idx + 1}`,
        messages: src.messages.slice(0, idx + 1).map((m) => ({ ...m })),
        createdAt: Date.now(),
        parentId: src.id,
      }
      set((state) => ({
        sessions: [fork, ...state.sessions],
        activeSessionId: fork.id,
        currentSession: fork,
      }))
      debouncedSaveSession(toDbSession(fork))
    },

    // ── Edit / Regenerate / Retry (G1 messaging parity) ───────────────────
    truncateAfter: (messageId) => {
      set((state) => {
        if (!state.activeSessionId) return state
        const sessions = state.sessions.map((s) => {
          if (s.id !== state.activeSessionId) return s
          const idx = s.messages.findIndex((m) => m.id === messageId)
          if (idx === -1) return s
          return { ...s, messages: s.messages.slice(0, idx + 1) }
        })
        return {
          sessions,
          currentSession: sessions.find((s) => s.id === state.activeSessionId) ?? null,
        }
      })
      persistActive()
    },

    updateMessageContent: (messageId, content) => {
      set((state) => {
        if (!state.activeSessionId) return state
        const sessions = state.sessions.map((s) => {
          if (s.id !== state.activeSessionId) return s
          const idx = s.messages.findIndex((m) => m.id === messageId)
          if (idx === -1) return s
          const msgs = [...s.messages]
          msgs[idx] = { ...msgs[idx]!, content }
          return { ...s, messages: msgs }
        })
        return {
          sessions,
          currentSession: sessions.find((s) => s.id === state.activeSessionId) ?? null,
        }
      })
      persistActive()
    },

    removeMessage: (messageId) => {
      set((state) => {
        if (!state.activeSessionId) return state
        const sessions = state.sessions.map((s) =>
          s.id === state.activeSessionId
            ? { ...s, messages: s.messages.filter((m) => m.id !== messageId) }
            : s,
        )
        return {
          sessions,
          currentSession: sessions.find((s) => s.id === state.activeSessionId) ?? null,
        }
      })
      persistActive()
    },
  }
}
