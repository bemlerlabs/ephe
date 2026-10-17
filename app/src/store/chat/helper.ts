/**
 * Visibility wave: the helper chat inside the store.
 *
 * The three subagent events write the helper's session while the mother task
 * carries on with its own bubble — the cursor stays where it was. Plus the
 * reconstruction path from the helper ledger: clicking a history row opens the
 * very same chat a live event would.
 *
 * It persists like any other session (IndexedDB + debounced). Only the server
 * mirror stays closed: a helper's durable store is its ledger, not the sessions
 * folder (see lib/sessionSync.ts).
 */
import { getSubagent } from '@/lib/api'
import { debouncedSaveSession } from '@/lib/db'
import {
  helperChatFromDetail,
  helperSession,
  helperTitle,
  isHelperRunning,
  type HelperChat,
} from '@/lib/helperSession'
import type { ChatMessage, Session, ToolCall } from '@/types'
import type {
  ChatState,
  GetFn,
  HelperEndInput,
  HelperStartInput,
  HelperStepInput,
  SetFn,
} from './types'
import { closeThinkingPhases, toDbSession } from './helpers'

/** The mother task: the event names it, otherwise it is the active session. */
function motherOf(get: GetFn, parentSession?: string): string {
  return parentSession || get().activeSessionId || ''
}

function freshChat(input: {
  chatSessionId: string
  agentId: string
  parentSession: string
  title: string
  task: string
}): HelperChat {
  return {
    ...input,
    status: 'running',
    report: '',
    durationMs: null,
    startedTs: Date.now(),
    steps: [],
  }
}

/** The last assistant bubble of the helper session (the one that works and reports). */
function workBubble(sess: Session): ChatMessage | null {
  for (let i = sess.messages.length - 1; i >= 0; i--) {
    if (sess.messages[i]!.role === 'assistant') return sess.messages[i]!
  }
  return null
}

function replaceMessage(sess: Session, id: string, next: ChatMessage): Session {
  return { ...sess, messages: sess.messages.map((m) => (m.id === id ? next : m)) }
}

/** Finished steps of a bubble — the one still running is only ever one. */
function closedCalls(calls: ToolCall[]): ToolCall[] {
  return calls.map((c) => (c.status === 'pending' ? { ...c, status: 'completed' as const } : c))
}

/** args_preview is a truncated JSON dictation — show it honestly as a card. */
function stepArgs(preview: string): Record<string, unknown> {
  if (!preview) return {}
  try {
    const parsed: unknown = JSON.parse(preview)
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>)
      : { input: preview }
  } catch {
    return { input: preview }
  }
}

export function makeHelperActions(set: SetFn, get: GetFn): Partial<ChatState> {
  /**
   * Write the helper session and persist it on the way (IndexedDB).
   * An updater that returns `undefined` leaves the store alone —
   * late events for a session that never began write nothing.
   */
  const patch = (id: string, fn: (existing: Session | undefined) => Session | undefined) => {
    set((s) => {
      const existing = s.sessions.find((x) => x.id === id)
      const next = fn(existing)
      if (!next) return s
      const sessions = existing
        ? s.sessions.map((x) => (x.id === id ? next : x))
        : [next, ...s.sessions]
      return {
        sessions,
        currentSession: sessions.find((x) => x.id === s.activeSessionId) ?? s.currentSession,
      }
    })
    const touched = get().sessions.find((x) => x.id === id)
    if (touched) debouncedSaveSession(toDbSession(touched))
  }

  /** Session stub for late events (a reload mid-run never saw 'begin'). */
  const ensureHelper = (chatSessionId: string, agentId: string) =>
    patch(
      chatSessionId,
      (existing) =>
        existing ??
        helperSession(
          freshChat({
            chatSessionId,
            agentId,
            parentSession: motherOf(get),
            title: helperTitle('', '', agentId),
            task: '',
          }),
          motherOf(get),
        ),
    )

  /** Append a row to the helper's work. */
  const appendStep = (
    chatSessionId: string,
    agentId: string,
    tool: string,
    argsPreview: string,
  ) => {
    ensureHelper(chatSessionId, agentId)
    patch(chatSessionId, (existing) => {
      if (!existing) return undefined
      const bubble = workBubble(existing)
      if (!bubble) return undefined
      const done = closedCalls(bubble.tool_calls ?? [])
      return replaceMessage(existing, bubble.id, {
        ...bubble,
        streaming: true,
        tool_calls: [
          ...done,
          {
            id: `${chatSessionId}-step-${done.length}`,
            name: tool,
            args: stepArgs(argsPreview),
            status: 'pending' as const,
          },
        ],
      })
    })
  }

  /**
   * Take the helper ledger as the current state: for a finished run it is the
   * authority, while a running helper drives its own session — its live events
   * are ahead of the snapshot.
   */
  const takeFromLedger = (chat: HelperChat) =>
    patch(chat.chatSessionId, (existing) =>
      existing && isHelperRunning(chat.status)
        ? existing
        : helperSession(chat, chat.parentSession || existing?.parentId || motherOf(get)),
    )

  return {
    beginHelperChat: (e: HelperStartInput) => {
      const parentSession = motherOf(get, e.parentSession)
      patch(
        e.chatSessionId,
        (existing) =>
          // a second begin of the same session never overwrites work in progress
          existing ??
          helperSession(
            freshChat({
              chatSessionId: e.chatSessionId,
              agentId: e.agentId,
              parentSession,
              title: helperTitle(e.role ?? '', e.description ?? '', e.agentId),
              task: e.task,
            }),
            parentSession,
          ),
      )
    },

    stepHelperChat: (e: HelperStepInput) =>
      appendStep(e.chatSessionId, e.agentId, e.tool, e.argsPreview),

    endHelperChat: (e: HelperEndInput) => {
      // Late arrivals without a begin (a reload mid-run) get their session too.
      if (!get().sessions.some((s) => s.id === e.chatSessionId)) {
        ensureHelper(e.chatSessionId, e.agentId)
      }
      patch(e.chatSessionId, (existing) => {
        if (!existing) return undefined
        const bubble = workBubble(existing)
        if (!bubble) return undefined
        const now = Date.now()
        return replaceMessage(existing, bubble.id, {
          ...bubble,
          content: e.report || e.summary || bubble.content,
          streaming: false,
          durationMs: Math.max(0, now - bubble.timestamp),
          thinking: bubble.thinking
            ? { ...bubble.thinking, end: bubble.thinking.end ?? now }
            : null,
          thinkingPhases: closeThinkingPhases(bubble),
          tool_calls: closedCalls(bubble.tool_calls ?? []),
        })
      })
    },

    restoreHelperChat: takeFromLedger,

    openHelperChat: async ({
      agentId,
      chatSessionId,
      parentSession,
    }: {
      agentId: string
      chatSessionId?: string
      parentSession?: string
    }) => {
      if (chatSessionId && get().sessions.some((s) => s.id === chatSessionId)) {
        get().setActiveSession(chatSessionId)
        return true
      }
      let chat: HelperChat
      try {
        chat = helperChatFromDetail(await getSubagent(agentId), motherOf(get, parentSession))
      } catch {
        // without a record the link leads nowhere — an empty shell would be worse
        return false
      }
      takeFromLedger(chat)
      get().setActiveSession(chat.chatSessionId)
      return true
    },
  }
}
