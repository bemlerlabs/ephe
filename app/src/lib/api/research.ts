import { request } from './http'

/**
 * Wave 3 (web intake): the evidence list behind the chat's source cards.
 *
 * `GET /api/research/evidence` reads the runs this server process still holds.
 * A restarted server answers with an empty list, which the card treats as "no
 * panel" rather than as a failure: the tool result already carries its sources.
 */
export interface ResearchSource {
  source_id: string
  url: string
  title: string
  fetched_at: string
  sha256: string
  excerpt: string
  query: string
  run_id: string
}

/** One copied workspace line; `reference` is the `path:line` the answer cites. */
export interface ResearchWorkspaceHit {
  path: string
  line: number
  reference: string
  text: string
  query: string
  run_id: string
}

export interface ResearchRunView {
  run_id: string
  query: string
  site: string
  started_at: string
  provider: string
  depth: number
  freshness: string
  pages: number
  considered: number
  sources: number
  workspace: number
  claims: { text: string; source_id: string; reference: string; kind: string }[]
  answer: string[]
  gaps: string[]
  verification: { checked: number; verified: number; issues: string[] }
  turn_id: string
}

export interface ResearchEvidence {
  ok: boolean
  runs: ResearchRunView[]
  sources: ResearchSource[]
  workspace: ResearchWorkspaceHit[]
  total: number
}

export function getResearchEvidence(
  params: { query?: string; runId?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ResearchEvidence> {
  const query = new URLSearchParams()
  if (params.query) query.set('query', params.query)
  if (params.runId) query.set('run_id', params.runId)
  if (params.limit) query.set('limit', String(params.limit))
  const encoded = query.toString()
  const suffix = encoded ? `?${encoded}` : ''
  return request<ResearchEvidence>(`/api/research/evidence${suffix}`, { signal })
}
