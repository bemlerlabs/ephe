import i18n from '@/i18n'
import { localizeActivityLabel } from '@/lib/activityLabels'
import type { Activity, ToolCall } from '@/types'
import type { ChatState, StoreCtx } from './types'
import { closeThinkingPhases, updateActiveMessage } from './helpers'

/** Tool/activity/artifact actions — 1:1 from chatStore.ts (739–885). */
export function makeToolActions(ctx: StoreCtx): Partial<ChatState> {
  const { set, persistActive, markSandboxStatus } = ctx
  return {
    upsertToolCall: (tool: {
      id?: string
      name: string
      args?: Record<string, unknown>
      result?: string
      status: ToolCall['status']
      rememberable?: boolean
      durationMs?: number
      stdout?: string
      reasonCode?: string
      reasonParams?: Record<string, string | number>
    }) => {
      set((s) =>
        updateActiveMessage(s, (m) => {
          const calls = m.tool_calls ?? []
          if (tool.id) {
            const idx = calls.findIndex((c) => c.id === tool.id)
            if (idx !== -1) {
              const next = [...calls]
              const prev = next[idx]!
              next[idx] = {
                ...prev,
                name: tool.name,
                args: tool.args ?? prev.args,
                result: tool.result ?? prev.result,
                status: tool.status,
                ...(tool.durationMs !== undefined ? { duration_ms: tool.durationMs } : {}),
                ...(tool.stdout !== undefined
                  ? { stdout: (prev.stdout ?? '') + tool.stdout || undefined }
                  : {}),
                ...(tool.reasonCode !== undefined ? { reason_code: tool.reasonCode } : {}),
                ...(tool.reasonParams !== undefined ? { reason_params: tool.reasonParams } : {}),
              }
              return { ...m, tool_calls: next }
            }
            // an id arrived but the entry is missing (e.g. tool_done without tool_start) → append
            return {
              ...m,
              tool_calls: [
                ...calls,
                {
                  id: tool.id,
                  name: tool.name,
                  args: tool.args ?? {},
                  result: tool.result,
                  status: tool.status,
                  ...(tool.durationMs !== undefined ? { duration_ms: tool.durationMs } : {}),
                  ...(tool.stdout !== undefined ? { stdout: tool.stdout } : {}),
                  ...(tool.reasonCode !== undefined ? { reason_code: tool.reasonCode } : {}),
                  ...(tool.reasonParams !== undefined ? { reason_params: tool.reasonParams } : {}),
                },
              ],
              ...(m.blocks !== undefined
                ? { blocks: [...m.blocks, { kind: 'tool' as const, callId: tool.id }] }
                : {}),
              // The beat ends with the tool row — that way the next reasoning
              // phase gets its own place in the chronology.
              ...(m.thinkingPhases ? { thinkingPhases: closeThinkingPhases(m) } : {}),
            }
          }
          // tool_start (no id): create the entry — match by name if one is already open
          const open = calls.find((c) => c.name === tool.name && !c.result)
          if (open) {
            const next = [...calls]
            const idx = next.indexOf(open)
            next[idx] = {
              ...open,
              args: tool.args ?? open.args,
              result: tool.result ?? open.result,
              status: tool.status,
              ...(tool.durationMs !== undefined ? { duration_ms: tool.durationMs } : {}),
              ...(tool.stdout !== undefined ? { stdout: (open.stdout ?? '') + tool.stdout } : {}),
              ...(tool.reasonCode !== undefined ? { reason_code: tool.reasonCode } : {}),
              ...(tool.reasonParams !== undefined ? { reason_params: tool.reasonParams } : {}),
            }
            return { ...m, tool_calls: next }
          }
          const newId = crypto.randomUUID()
          return {
            ...m,
            tool_calls: [
              ...calls,
              {
                id: newId,
                name: tool.name,
                args: tool.args ?? {},
                result: tool.result,
                status: tool.status,
                ...(tool.durationMs !== undefined ? { duration_ms: tool.durationMs } : {}),
                ...(tool.stdout !== undefined ? { stdout: tool.stdout } : {}),
                ...(tool.reasonCode !== undefined ? { reason_code: tool.reasonCode } : {}),
                ...(tool.reasonParams !== undefined ? { reason_params: tool.reasonParams } : {}),
              },
            ],
            ...(m.blocks !== undefined
              ? { blocks: [...m.blocks, { kind: 'tool' as const, callId: newId }] }
              : {}),
            ...(m.thinkingPhases ? { thinkingPhases: closeThinkingPhases(m) } : {}),
          }
        }),
      )
      persistActive()
    },

    setTurnId: (turnId: string) => {
      set((s) => updateActiveMessage(s, (m) => (m.turnId ? m : { ...m, turnId })))
      persistActive()
    },

    setProgress: (progress) => {
      // Ephemeral: the live line is not part of the persisted transcript.
      set((s) => updateActiveMessage(s, (m) => ({ ...m, progress })))
    },

    upsertActivity: (activity: {
      label: string
      status: Activity['status']
      detail?: string
      path?: string
      fileType?: string
      artifactId?: string
    }) => {
      // G8: localise the backend phase labels (known EN strings → i18n);
      // tool-command and artifact labels pass through unchanged.
      const label = localizeActivityLabel(activity.label, i18n.t)
      // Subagent parity: `subagent_started` creates "SubAgent N (role)",
      // `subagent_done` upserts "SubAgent N" — the match normalises to the
      // label core (drops the " (…)" suffix), else the role stays "running" forever.
      const norm = (l: string) => l.replace(/\s*\([^)]*\)\s*$/, '')
      set((s) =>
        updateActiveMessage(s, (m) => {
          const acts = m.activities ?? []
          const idx = acts.findIndex((a) => norm(a.label) === norm(label))
          if (idx !== -1) {
            const next = [...acts]
            const prev = next[idx]!
            next[idx] = {
              ...prev,
              status: activity.status,
              detail: activity.detail ?? prev.detail,
              path: activity.path ?? prev.path,
              fileType: activity.fileType ?? prev.fileType,
              artifactId: activity.artifactId ?? prev.artifactId,
            }
            return { ...m, activities: next }
          }
          const act: Activity = {
            id: crypto.randomUUID(),
            label,
            status: activity.status,
          }
          if (activity.detail) act.detail = activity.detail
          if (activity.path) act.path = activity.path
          if (activity.fileType) act.fileType = activity.fileType
          if (activity.artifactId) act.artifactId = activity.artifactId
          return {
            ...m,
            activities: [...acts, act],
          }
        }),
      )
      persistActive()
    },

    attachArtifact: (artifact) => {
      // F-01: attach to the active (streaming) assistant message. Idempotent
      // per artifact id — the same message can arrive again on a revision.
      set((s) =>
        updateActiveMessage(s, (m) => {
          const existing = m.artifacts ?? []
          if (existing.some((a) => a.id === artifact.id)) return m
          return { ...m, artifacts: [...existing, artifact] }
        }),
      )
      persistActive()
    },

    setPlan: (plan) => {
      set((s) => updateActiveMessage(s, (m) => ({ ...m, plan })))
      persistActive()
    },

    beginGoal: (goal, check, maxTurns) => {
      // goal_start: the loop names its three values before the first round, and a
      // second run in the same turn replaces the first one's state instead of
      // merging two goals into one line.
      set((s) =>
        updateActiveMessage(s, (m) => ({
          ...m,
          goal: { goal, check, maxTurns, turn: 0, ok: null },
        })),
      )
      persistActive()
    },

    advanceGoal: (turn, ok) => {
      set((s) =>
        updateActiveMessage(s, (m) => {
          // A goal_turn/goal_check without its goal_start — an older backend, a
          // replayed stream — carries no goal to move; the message keeps what it has.
          if (!m.goal) return m
          return { ...m, goal: { ...m.goal, turn, ok: ok === undefined ? m.goal.ok : ok } }
        }),
      )
      persistActive()
    },

    resolveSandbox: (token, tool, args, rememberable, diff) => {
      ctx.get().upsertToolCall({ name: tool, args, status: 'waiting', rememberable })
      // Store the token as the description of the last waiting call (for /sandbox/approve).
      // Wave B1: attach the real diff preview as an ephemeral approval_diff — the
      // waiting call is the only place the approval dialog needs it, and it does
      // NOT land in the persisted ToolCallModel (the schema stays free of it).
      set((s) =>
        updateActiveMessage(s, (m) => {
          const calls = m.tool_calls ?? []
          for (let i = calls.length - 1; i >= 0; i--) {
            const c = calls[i]!
            if (c.status === 'waiting') {
              const next = [...calls]
              next[i] = {
                ...c,
                description: token,
                args: c.args ?? args,
                ...(diff ? { approval_diff: diff } : {}),
              }
              return { ...m, tool_calls: next }
            }
          }
          return m
        }),
      )
      persistActive()
    },

    approveSandbox: () => markSandboxStatus('approved'),
    denySandbox: () => markSandboxStatus('denied'),

    resolveAsk: (ask) => {
      // G1: the ask rides on the assistant message of the turn that asked. One live
      // question per turn — a second `ask_user` in the same turn replaces the frame's
      // state it no longer waits on.
      set((s) =>
        updateActiveMessage(s, (m) => ({
          ...m,
          ask: {
            token: ask.token,
            question: ask.question,
            options: ask.options.map((label) => ({ label })),
            ...(ask.recommendation ? { recommendation: ask.recommendation } : {}),
            ...(ask.multiSelect ? { multiSelect: true } : {}),
            ...(ask.timeoutS !== undefined ? { timeoutS: ask.timeoutS } : {}),
            ...(ask.defaultAnswer ? { defaultAnswer: ask.defaultAnswer } : {}),
            status: 'waiting',
          },
        })),
      )
      persistActive()
    },

    markAskAnswered: (token, answer) => {
      // The token check keeps a late frame from closing the ask that replaced it.
      set((s) =>
        updateActiveMessage(s, (m) =>
          m.ask && m.ask.token === token
            ? { ...m, ask: { ...m.ask, status: 'answered', answer } }
            : m,
        ),
      )
      persistActive()
    },

    markAskTimedOut: (token) => {
      set((s) =>
        updateActiveMessage(s, (m) =>
          m.ask && m.ask.token === token ? { ...m, ask: { ...m.ask, status: 'timeout' } } : m,
        ),
      )
      persistActive()
    },

    markAskExpired: (token) => {
      set((s) =>
        updateActiveMessage(s, (m) =>
          m.ask && m.ask.token === token ? { ...m, ask: { ...m.ask, status: 'expired' } } : m,
        ),
      )
      persistActive()
    },
  }
}
