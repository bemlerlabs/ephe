/** Agent Center and Agent Teams (server: core/agent_store.py, core/agent_teams.py). */
import { request } from './http'

export interface AgentModelRef {
  provider?: string | null
  model: string
  tier?: string
}

export interface AgentAvatar {
  seed: string
  pattern: string
}

export type AgentAccess = 'allow' | 'ask' | 'block'

export interface AgentRule {
  tool: string
  access: AgentAccess
  purpose: string
}

export interface AgentRecord {
  id: string
  name: string
  description: string
  avatar: AgentAvatar
  instructions: string
  model: AgentModelRef | null
  tools: string[]
  permissions: { approval: string; rules: AgentRule[] }
  limits: { max_turns: number; timeout: number }
  origin: string
  enabled: boolean
  archived: boolean
  created_at: string
  updated_at: string
  read_only?: boolean
  etag?: string | null
}

export interface AgentList {
  agents: AgentRecord[]
  quarantined: Record<string, string>
}

export interface AgentTool {
  name: string
  families: string[]
}

export interface AgentRun {
  run_id: string
  agent_id: string
  agent_name: string
  model: string
  model_source: 'agent' | 'global' | 'team'
  source: string
  status: string
  duration_ms: number
  tool_calls: number
  prompt_chars: number
  report_chars: number
  finished_at: string
}

export interface AgentTestResult {
  run_id: string
  agent_id: string
  agent_name: string
  provider: string
  model: string
  model_source: string
  status: string
  report: string
  tool_calls: { tool: string; args_preview: string }[]
}

export function listAgents(): Promise<AgentList> {
  return request<AgentList>('/api/agents')
}

export function listAgentTools(): Promise<{ tools: AgentTool[] }> {
  return request<{ tools: AgentTool[] }>('/api/agents/tools')
}

export function getAgent(id: string): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${encodeURIComponent(id)}`)
}

export function createAgent(payload: Partial<AgentRecord>): Promise<AgentRecord> {
  return request<AgentRecord>('/api/agents', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateAgent(
  id: string,
  payload: Partial<AgentRecord>,
  etag: string,
): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'If-Match': etag },
    body: JSON.stringify(payload),
  })
}

export function duplicateAgent(id: string): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${encodeURIComponent(id)}/duplicate`, {
    method: 'POST',
  })
}

export function setAgentArchived(id: string, archived: boolean): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
    body: JSON.stringify({ archived }),
  })
}

export function testAgent(id: string, prompt: string): Promise<AgentTestResult> {
  return request<AgentTestResult>(`/api/agents/${encodeURIComponent(id)}/test`, {
    method: 'POST',
    body: JSON.stringify({ prompt }),
    // One helper run: a member's own timeout plus engine latency.
    timeoutMs: 1_000_000,
  })
}

export function listAgentRuns(id: string, limit = 20): Promise<{ runs: AgentRun[] }> {
  return request<{ runs: AgentRun[] }>(`/api/agents/${encodeURIComponent(id)}/runs?limit=${limit}`)
}

export type TeamOrchestration = 'leader' | 'parallel' | 'sequential' | 'review'
export type TeamModelPolicy = 'inherit' | 'team' | 'per_member'

export interface TeamBudget {
  max_rounds: number
  wall_timeout: number
}

export interface TeamRecord {
  id: string
  name: string
  description: string
  instructions: string
  leader_id: string
  member_ids: string[]
  orchestration: TeamOrchestration
  shared_context: {
    session: boolean
    workspace: boolean
    artifacts: boolean
    memory: boolean
  }
  model_policy: TeamModelPolicy
  model: AgentModelRef | null
  budget: TeamBudget
  template: string
  origin: string
  archived: boolean
  created_at: string
  updated_at: string
  read_only?: boolean
  etag?: string | null
}

export interface TeamTemplate {
  key: string
  name: string
  description: string
}

export interface TeamRunMember {
  agent_id: string
  name: string
  model: string
  model_source: string
  status: string
  duration_ms: number
  report: string
  tool_calls: number
  role?: 'leader' | 'member'
}

export interface TeamRunResult {
  run_id: string
  team_id: string
  status: string
  report: string
  members: TeamRunMember[]
  budget_hit?: boolean
  duration_ms?: number
  orchestration?: string
  model_policy?: string
}

export interface TeamRunSummary {
  run_id: string
  team_id: string
  status: string
  members: number
  budget_hit: boolean
  duration_ms: number
  finished_at: string
}

export function listTeams(): Promise<{
  teams: TeamRecord[]
  quarantined: Record<string, string>
}> {
  return request('/api/agent-teams')
}

export function listTeamTemplates(): Promise<{ templates: TeamTemplate[] }> {
  return request('/api/agent-teams/templates')
}

export function createTeam(payload: Partial<TeamRecord>): Promise<TeamRecord> {
  return request<TeamRecord>('/api/agent-teams', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTeam(
  id: string,
  payload: Partial<TeamRecord>,
  etag: string,
): Promise<TeamRecord> {
  return request<TeamRecord>(`/api/agent-teams/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'If-Match': etag },
    body: JSON.stringify(payload),
  })
}

export function setTeamArchived(id: string, archived: boolean): Promise<TeamRecord> {
  return request<TeamRecord>(`/api/agent-teams/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
    body: JSON.stringify({ archived }),
  })
}

export function runTeam(
  id: string,
  task: string,
  model?: string,
  runId?: string,
): Promise<TeamRunResult> {
  return request<TeamRunResult>(`/api/agent-teams/${encodeURIComponent(id)}/run`, {
    method: 'POST',
    body: JSON.stringify({
      task,
      ...(model ? { model } : {}),
      ...(runId ? { run_id: runId } : {}),
    }),
    timeoutMs: 1_900_000,
  })
}

export function listTeamRuns(id: string, limit = 20): Promise<{ runs: TeamRunSummary[] }> {
  return request<{ runs: TeamRunSummary[] }>(
    `/api/agent-teams/${encodeURIComponent(id)}/runs?limit=${limit}`,
  )
}

export function getTeamRun(runId: string): Promise<TeamRunResult> {
  return request<TeamRunResult>(`/api/agent-teams/runs/${encodeURIComponent(runId)}`)
}

export function cancelTeamRun(runId: string): Promise<TeamRunResult> {
  return request<TeamRunResult>(`/api/agent-teams/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}
