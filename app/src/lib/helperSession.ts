/**
 * Visibility wave: the helper as a session of its own.
 *
 * A `spawn_agent` run used to be only one line in the helper tab. These
 * modules project the same run onto a real session: its own id (prefix
 * `helper-`), `parentId` = the parent task (sidebar branch + way back), the
 * task as a user line, the tool steps as activity lines, the report as answer.
 *
 * Two paths, one identity:
 *  - live: SSE events (`chat_session_id` travels along from the core) fill the
 *    session while the helper works;
 *  - reconstruction: the helper ledger (~/.ephe/subagent_history.json, via
 *    GET /api/subagents/<id>) yields the same id — clicking a history line
 *    opens the same chat, even after the cache was emptied.
 *
 * Pure and without store access: the store decides what happens with it.
 */
import type { ChatMessage, Session } from '@/types'
import type { SubagentDetail } from '@/lib/api/subagents'

/** Session prefix of a helper — the core uses exactly this schema too. */
export const HELPER_PREFIX = 'helper-'

export function isHelperSessionId(id: string | null | undefined): boolean {
  return !!id && id.startsWith(HELPER_PREFIX)
}

export interface HelperStep {
  tool: string
  argsPreview: string
  ms?: number | null
}

/** One helper run, fully described — the shared shape of both paths. */
export interface HelperChat {
  chatSessionId: string
  agentId: string
  /** The task the helper was started from (the way back). */
  parentSession: string
  title: string
  task: string
  /** running | ok | timeout | error | step_limit */
  status: string
  report: string
  durationMs: number | null
  /** Birth in milliseconds (the ledger reports seconds). */
  startedTs: number | null
  steps: HelperStep[]
}

export function isHelperRunning(status: string): boolean {
  return status === 'running'
}

/** Title: the delegation's short label, else the role, else the run id. */
export function helperTitle(role: string, description: string, agentId: string): string {
  const clean = (description || role || agentId).replace(/\s+/g, ' ').trim()
  return clean.length > 48 ? `${clean.slice(0, 48).trimEnd()}…` : clean || agentId
}

const STEP_LIMIT = 40

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

/** The helper's two lines: the task it was given, what it works on / finishes.
 *  Its steps are tool cards — the bubble renders them live and afterwards,
 *  while activity lines are filtered down to agent labels. */
export function helperMessages(chat: HelperChat): ChatMessage[] {
  const started = chat.startedTs ?? Date.now()
  const running = isHelperRunning(chat.status)
  const steps = chat.steps.slice(-STEP_LIMIT)
  const msgId = `${chat.chatSessionId}-work`
  return [
    {
      id: `${chat.chatSessionId}-task`,
      role: 'user',
      content: chat.task,
      timestamp: started,
    },
    {
      id: msgId,
      role: 'assistant',
      content: running ? '' : chat.report,
      timestamp: started,
      streaming: running,
      thinking: { start: started, end: running ? null : started + (chat.durationMs ?? 0) },
      tool_calls: steps.map((s, i) => ({
        id: `${chat.chatSessionId}-step-${i}`,
        name: s.tool,
        args: stepArgs(s.argsPreview),
        status: running && i === steps.length - 1 ? ('pending' as const) : ('completed' as const),
        ...(s.ms != null ? { duration_ms: s.ms } : {}),
      })),
      ...(chat.durationMs != null ? { durationMs: chat.durationMs } : {}),
    },
  ]
}

/** The helper session exactly as the store keeps it. */
export function helperSession(chat: HelperChat, parentId: string): Session {
  return {
    id: chat.chatSessionId,
    title: chat.title,
    messages: helperMessages(chat),
    createdAt: chat.startedTs ?? Date.now(),
    parentId,
    // The helper's sandbox is read-only; the parent task's mode does not apply.
    mode: 'ask',
  }
}

export function helperChatFromDetail(detail: SubagentDetail, parentFallback = ''): HelperChat {
  const agentId = detail.agent_id
  return {
    // Older ledger records (from before this wave) carry no id — derive it the
    // same way the core does, so both paths land on one and the same run.
    chatSessionId: detail.chat_session_id || `${HELPER_PREFIX}${agentId}`,
    agentId,
    parentSession: detail.parent_session || parentFallback,
    title: helperTitle(detail.role, detail.description, agentId),
    task: detail.task ?? '',
    status: detail.status ?? 'ok',
    report: detail.report ?? '',
    durationMs: detail.duration_ms ?? null,
    startedTs: detail.started_ts != null ? detail.started_ts * 1000 : null,
    steps: (detail.tool_calls ?? []).map((t) => ({
      tool: t.tool,
      argsPreview: t.args_preview,
      ms: t.ms,
    })),
  }
}
