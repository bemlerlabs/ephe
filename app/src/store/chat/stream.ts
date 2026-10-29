import { flushPendingSave } from '@/lib/db'
import { THINKING_MAX_CHARS } from '@/lib/thinking'
import { requestTaskNotifyPermission, notifyTaskDone } from '@/lib/taskNotify'
import i18n from '@/i18n'
import type { ChatMessage, ThinkingPhase } from '@/types'
import type { ChatState, StoreCtx } from './types'
import { closeThinkingPhases, updateActiveMessage } from './helpers'

/** In-place streaming actions (PWA chat UX plan, task A5) — 1:1 from chatStore.ts (610–935). */
export function makeStreamActions(ctx: StoreCtx): Partial<ChatState> {
  const { set, get, persistActive, setTransientMeta } = ctx
  return {
    startTurn: () => {
      const state = get()
      if (!state.activeSessionId || !state.currentSession) return
      // Idempotency: exactly ONE growing bubble per turn (PWA chat UX plan,
      // phase E1 invariant). handleSend calls startTurn() BEFORE the stream and
      // the thinking_start event calls it again → without this guard every turn
      // gets 2 assistant bubbles and chunks land in the wrong one.
      const msgs = state.currentSession.messages
      const alreadyStreaming = msgs.some((m) => m.role === 'assistant' && m.streaming)
      if (alreadyStreaming) return
      // Wave 3 (Finding 4): ask for the permission lazily at task start —
      // not at app start (a dialog with no context just annoys).
      requestTaskNotifyPermission()
      const message: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        thinking: { start: Date.now(), end: null },
        thinkingPhases: [],
        activities: [],
        blocks: [],
        streaming: true,
      }
      set((s) => {
        const sessions = s.sessions.map((sess) =>
          sess.id === s.activeSessionId ? { ...sess, messages: [...sess.messages, message] } : sess,
        )
        return {
          sessions,
          currentSession: sessions.find((sess) => sess.id === s.activeSessionId) ?? null,
          lastTurnUsage: null,
          // QD-015 Z2: the offer belongs to the turn that hit the cap; the next
          // turn replaces it.
          budgetNotice: null,
          // SOL: a learned rule belongs to the turn that proved it.
          solInsights: [],
        }
      })
      persistActive()
    },

    // QD-015 Z2: the budget frame arrived — the surface now offers the next
    // rounds instead of leaving the note as a dead end.
    markBudgetReached: (cap, extra) => {
      set({ budgetNotice: { cap, extra } })
    },

    markSolInsight: (rule) => {
      set((s) => ({ solInsights: s.solInsights.some((item) => item.id === rule.id) ? s.solInsights : [...s.solInsights, rule] }))
    },

    appendChunk: (chunk) => {
      set((s) =>
        updateActiveMessage(s, (m) => {
          // thinking.end = the moment of the FIRST visible content chunk (the
          // thinking-block collapse). thinking_chunk events before it do NOT
          // change thinking.end — only real content ends the phase.
          const now = Date.now()
          const phases = m.thinkingPhases
          const lastPhase = phases ? phases[phases.length - 1] : undefined
          const closedPhases =
            phases && lastPhase && lastPhase.end === null
              ? [...phases.slice(0, -1), { ...lastPhase, end: now }]
              : phases
          const thinking =
            m.thinking && m.thinking.end === null ? { ...m.thinking, end: now } : m.thinking
          // R1: text blocks in arrival order — the last text block grows, and
          // after a tool/thinking block a new text block begins.
          const prev = m.blocks
          let blocks = prev
          if (prev !== undefined) {
            const last = prev[prev.length - 1]
            blocks =
              last && last.kind === 'text'
                ? [...prev.slice(0, -1), { kind: 'text' as const, text: last.text + chunk }]
                : [...prev, { kind: 'text' as const, text: chunk }]
          }
          return {
            ...m,
            content: m.content + chunk,
            // P1-7: TTFT = turn start → arrival of the FIRST content chunk (the
            // thinking phase runs before it and does not count as a "first token").
            ...(m.content === '' ? { ttftMs: now - m.timestamp } : {}),
            thinking,
            ...(closedPhases ? { thinkingPhases: closedPhases } : {}),
            blocks,
          }
        }),
      )
      persistActive()
    },

    appendThinking: (chunk) => {
      set((s) =>
        updateActiveMessage(s, (m) => {
          const cap = (t: string) =>
            t.length > THINKING_MAX_CHARS ? t.slice(-THINKING_MAX_CHARS) : t
          const phases = m.thinkingPhases ?? []
          const last = phases[phases.length - 1]
          // An open phase grows — otherwise this event would open a new phase
          // (thinking → tool → thinking, the reference pattern) and give it its
          // own slot in the chronology.
          if (last && last.end === null) {
            const next = [...phases.slice(0, -1), { ...last, text: cap((last.text ?? '') + chunk) }]
            return { ...m, thinkingPhases: next, thinking: next[next.length - 1] }
          }
          const phase: ThinkingPhase = { start: Date.now(), end: null, text: cap(chunk) }
          const next = [...phases, phase]
          return {
            ...m,
            thinkingPhases: next,
            thinking: phase,
            ...(m.blocks !== undefined
              ? { blocks: [...m.blocks, { kind: 'thinking' as const, index: next.length - 1 }] }
              : {}),
          }
        }),
      )
      persistActive()
    },

    replaceText: (text) => {
      set((s) =>
        updateActiveMessage(s, (m) => {
          // R1: the last text block carries the (revised) answer; an earlier
          // tool block stays at its position in the chronology.
          const prev = m.blocks
          let blocks = prev
          if (prev !== undefined) {
            const last = prev[prev.length - 1]
            blocks =
              last && last.kind === 'text'
                ? [...prev.slice(0, -1), { kind: 'text' as const, text }]
                : [...prev, { kind: 'text' as const, text }]
          }
          return { ...m, content: text, blocks }
        }),
      )
      persistActive()
    },

    setReflecting: (on) => setTransientMeta('reflecting', on),
    setRevising: (on) => setTransientMeta('revising', on),
    setQualityCheck: (on) => setTransientMeta('qualityCheck', on),

    markStreamError: (msg, code) => {
      set((s) =>
        updateActiveMessage(s, (m) => ({
          ...m,
          error: msg,
          errorCode: code ?? null,
          streaming: false,
          // P6-Timeline (ref-01): even a failed turn has a measured wall-time
          // ("Worked for …" — never an invented default).
          durationMs: Math.max(0, Date.now() - m.timestamp),
          thinking: m.thinking ? { ...m.thinking, end: m.thinking.end ?? Date.now() } : null,
          thinkingPhases: closeThinkingPhases(m),
          streamMeta: { reflecting: false, revising: false, qualityCheck: false },
        })),
      )
      persistActive()
      // I6 P2b: the error path works like finishTurn — the text received so far
      // must survive the debounce window (see the finishTurn comment).
      flushPendingSave()
    },

    finishTurn: () => {
      set((s) => {
        const finalized = updateActiveMessage(s, (m) => ({
          ...m,
          streaming: false,
          // P6-Timeline (ref-01): turn wall-time for the "Worked for" header.
          durationMs: Math.max(0, Date.now() - m.timestamp),
          thinking: m.thinking ? { ...m.thinking, end: m.thinking.end ?? Date.now() } : null,
          thinkingPhases: closeThinkingPhases(m),
          streamMeta: { reflecting: false, revising: false, qualityCheck: false },
          // "Analyzing request…" fix: the backend feed often reports phases as
          // running only (with no explicit done) — at turn end NO phase is still
          // running. Close open activities here, otherwise the spinner keeps
          // turning inside a finished bubble.
          activities: m.activities?.map((a) =>
            a.status === 'running' ? { ...a, status: 'done' as const } : a,
          ),
        }))
        // R46 hygiene (owner live audit 28.09.): when the stream died BEFORE even
        // a single chunk arrived, an empty assistant bubble used to stay behind
        // (owner session: message [3] with content=''). A turn-end bubble with no
        // content at all is noise — it is removed again instead of persisted.
        const sessId = s.activeSessionId
        const sessions = finalized.sessions.map((sess) => {
          if (sess.id !== sessId) return sess
          const msgs = sess.messages
          const last = msgs[msgs.length - 1]
          const isEmptyBubble =
            last &&
            last.role === 'assistant' &&
            !last.streaming &&
            !last.error &&
            !last.content?.trim() &&
            !last.tool_calls?.length &&
            !last.activities?.length &&
            !last.thinkingPhases?.length &&
            !last.blocks?.length
          if (!isEmptyBubble) return sess
          return { ...sess, messages: msgs.slice(0, -1) }
        })
        return {
          sessions,
          currentSession: sessions.find((sess) => sess.id === sessId) ?? finalized.currentSession,
        }
      })
      persistActive()
      // I6 P2b: the debounced persist is retuned by every chunk and never fires
      // if the tab dies right after (stop + reload). At turn end the state must
      // be guaranteed on disk — otherwise the reload loses half the answer
      // (deep-test finding "Stop discards partial text").
      flushPendingSave()
      // Wave 3 (Finding 4): task done — a native notification, but ONLY when the
      // user is elsewhere right now (tab hidden) and the permission is granted.
      // Body = the assignment (the last user message), so the title can be
      // placed in the notification centre.
      const after = get()
      const sess = after.sessions.find((s2) => s2.id === after.activeSessionId)
      const lastUser = [...(sess?.messages ?? [])].reverse().find((m) => m.role === 'user')
      if (lastUser?.content?.trim()) {
        void notifyTaskDone(
          i18n.t('notify.taskDoneTitle'),
          i18n.t('notify.taskDoneBody', { task: lastUser.content.trim() }),
        )
      }
    },

    // N7/N8a: the usage frame arrives before done — the real balance survives the
    // turn, and the status-bar chip falls back to it when the server mirror
    // (restore) still comes back empty.
    markLastUsage: (u) => {
      // Wave 3: the usage frame ALSO accumulates the session total — the cost and
      // cache chips in the status bar need cumulative values, not just the last
      // turn. Carried by persistActive(): the debounced save writes usageTotals
      // into the IndexedDB as well.
      set((s) => {
        const sessions = s.sessions.map((sess) => {
          if (sess.id !== s.activeSessionId) return sess
          const prev = sess.usageTotals ?? { in: 0, out: 0, cached: 0 }
          return {
            ...sess,
            usageTotals: {
              in: prev.in + (u.in || 0),
              out: prev.out + (u.out || 0),
              cached: prev.cached + (u.cached || 0),
            },
          }
        })
        return {
          lastTurnUsage: u,
          sessions,
          currentSession:
            sessions.find((sess) => sess.id === s.activeSessionId) ?? s.currentSession,
        }
      })
      persistActive()
    },
  }
}
