// I1 (2026-09-07): chat-stream aggregation — consecutive tool calls of the
// same family are grouped into ONE compact row
// (reference look: "Terminal · 3 Befehle"), details stay expandable. // language-gate: ignore — quotes the German summary row the UI renders
// Pure function, no React — the rendering consumes only the groups.
import { classifyToolCall, type ToolFamily } from './toolCardModel'

export interface ToolCallShape {
  id: string
  name: string
  args?: unknown
  result?: unknown
  status?: unknown
}

export interface ToolStreamGroup {
  family: ToolFamily
  /** i18n key of the family label ("streamGroup.terminal" etc.). */
  summaryKey: string
  count: number
  calls: ToolCallShape[]
  /** Target of the solo call (file basename for 1x edit/write/read), otherwise ''. */
  target: string
  additions: number
  deletions: number
  /** Any call of the group failed or was refused (red accent). */
  hasFailure: boolean
}

const SUMMARY_KEY: Partial<Record<ToolFamily, string>> = {
  shell: 'streamGroup.terminal',
  read: 'streamGroup.read',
  search: 'streamGroup.search',
  web: 'streamGroup.web',
  edit: 'streamGroup.edit',
  write: 'streamGroup.write',
  task: 'streamGroup.task',
  subagent: 'streamGroup.subagent',
}

/**
 * w10-12: two words mean the same thing for the row — the call did not run.
 * `failed` is the outcome the server sends on `tool_done` for a refusal (a coded
 * result), `denied` is the store status the stream maps it onto; the sandbox flow
 * writes `denied` directly when the user refuses the dialog. Before, only `failed`
 * was read here and no producer ever sent it, so a refusal kept the success accent.
 */
function isFailedOrRefused(status: unknown): boolean {
  return status === 'failed' || status === 'denied'
}

export function aggregateToolCalls(calls: ToolCallShape[]): ToolStreamGroup[] {
  const groups: ToolStreamGroup[] = []
  for (const tc of calls) {
    const model = classifyToolCall(tc as Parameters<typeof classifyToolCall>[0])
    const failed = isFailedOrRefused(tc.status)
    const last = groups[groups.length - 1]
    if (last && last.family === model.family) {
      last.calls.push(tc)
      last.count += 1
      last.hasFailure = last.hasFailure || failed
      continue
    }
    groups.push({
      family: model.family,
      summaryKey: SUMMARY_KEY[model.family] ?? 'streamGroup.tool',
      count: 1,
      calls: [tc],
      target: model.target,
      additions: model.stats?.added ?? 0,
      deletions: model.stats?.removed ?? 0,
      hasFailure: failed,
    })
  }
  return groups
}
