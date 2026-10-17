/** P4-D: Subagent-History (Backend: core/subagent_history.py + routes/subagents.py). */
import { request } from './http'

export interface SubagentSummary {
  agent_id: string
  role: string
  description: string
  task: string
  status: string
  started_ts: number | null
  duration_ms: number | null
  tool_count: number
  /** Visibility wave: the helper's own chat session + its parent assignment. */
  chat_session_id?: string
  parent_session?: string
}

export interface SubagentToolCall {
  tool: string
  args_preview: string
  ms: number
}

export interface SubagentDetail {
  agent_id: string
  role: string
  description: string
  task: string
  model: string
  status: string
  started_ts: number | null
  finished_ts: number | null
  duration_ms: number | null
  report: string
  tool_calls: SubagentToolCall[]
  transcript: { role: string; text: string }[]
  /** Visibility wave: the run's own chat session and its parent assignment. */
  chat_session_id?: string
  parent_session?: string
}

export interface SubagentListPage {
  agents: SubagentSummary[]
  nextCursor: string | null
}

export function listSubagents(cursor?: string | null): Promise<SubagentListPage> {
  // P6 B1 (ref-02): cursor pagination — `cursor` is the absolute position
  // number of the last loaded page; null/undefined = first page.
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return request<SubagentListPage>(`/api/subagents${q}`)
}

export function getSubagent(agentId: string): Promise<SubagentDetail> {
  return request<SubagentDetail>(`/api/subagents/${encodeURIComponent(agentId)}`)
}
