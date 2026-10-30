/** The tool-use reader behind the Discover bench (server: `GET /api/audit/usage`). */
import { request } from './http'

export interface ToolUsageRow {
  tool: string
  calls: number
  ok: number
  errors: number
  blocked: number
  last_ts: string
}

export interface ToolUsageView {
  tools: ToolUsageRow[]
  /** Entries the ranking was drawn from, so the bench can say how far it reaches. */
  population: number
  window: number
}

/** Calls per tool over the newest entries of the audit log, most called first. */
export function getToolUsage(top = 12): Promise<ToolUsageView> {
  return request<ToolUsageView>(`/api/audit/usage?top=${encodeURIComponent(String(top))}`)
}
