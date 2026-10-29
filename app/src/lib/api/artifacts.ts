/**
 * Ephe — API client for the workbench (R4).
 *
 * Split out of misc.ts because the artifact surface has had more endpoints
 * since A0/A1/A4 than the rest of the client combined, and misc.ts
 * would have broken the 400-line limit of the architecture policy. The facade
 * (lib/api/index.ts) still re-exports everything, so the surfaces keep their
 * existing '@/lib/api' entry point.
 */
import { apiUrl, request } from './http'
import type { ArtifactEntry, ArtifactExpiry, ArtifactExpiryAnswer } from './types_extra'

// ── R17: artifact hub (persistent library across all sessions) ────────

export function listArtifacts(params?: {
  q?: string
  kind?: string
  favorite?: boolean
  /** A3 backwards: only what this job gave birth to. */
  turn_id?: string
  session_id?: string
  limit?: number
}): Promise<{ artifacts: ArtifactEntry[]; total: number }> {
  const usp = new URLSearchParams()
  if (params?.q) usp.set('q', params.q)
  if (params?.kind) usp.set('kind', params.kind)
  if (params?.favorite !== undefined) usp.set('favorite', String(params.favorite))
  if (params?.turn_id) usp.set('turn_id', params.turn_id)
  if (params?.session_id) usp.set('session_id', params.session_id)
  if (params?.limit) usp.set('limit', String(params.limit))
  const qs = usp.toString()
  return request(`/api/artifacts${qs ? `?${qs}` : ''}`)
}

export function favoriteArtifact(
  id: string,
  favorite: boolean,
): Promise<{ id: string; favorite: boolean }> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/favorite`, {
    method: 'POST',
    body: JSON.stringify({ favorite }),
  })
}

/**
 * A0: the bytes of a card through its **id**. A path the surface picks for
 * itself is the reason previews grab the wrong file
 * (core/artifact_workbench.artifact_target is the one check behind it).
 * `download` tells viewing (inline) apart from adopting (attachment).
 */
export function artifactFileUrl(id: string, download = false): string {
  return apiUrl(`/api/artifacts/${encodeURIComponent(id)}/file${download ? '?download=1' : ''}`)
}

/**
 * A foreign image URL in an answer, fetched through the server's guard.
 *
 * The CSP allows `'self'` for images, so a remote URL can never load directly
 * (it used to sit there as a broken image). The proxy resolves and checks the
 * address, keeps one copy per URL and answers it same-origin.
 */
export function artifactProxyUrl(url: string, sessionId = ''): string {
  const usp = new URLSearchParams({ url })
  if (sessionId) usp.set('session_id', sessionId)
  return apiUrl(`/api/artifacts/proxy?${usp.toString()}`)
}

/**
 * Bulk export URL (zip) — <a download> cannot send headers, hence the
 * LAN token as a query param (same convention as fileUrl).
 */
export function artifactExportUrl(params?: { ids?: string[]; q?: string; kind?: string }): string {
  const usp = new URLSearchParams()
  if (params?.ids?.length) usp.set('ids', params.ids.join(','))
  if (params?.q) usp.set('q', params.q)
  if (params?.kind) usp.set('kind', params.kind)
  const qs = usp.toString()
  return apiUrl(`/api/artifacts/export${qs ? `?${qs}` : ''}`)
}

/** The deadline question: what has been lying in the workbench for N days? */
export function listArtifactExpiry(): Promise<ArtifactExpiry> {
  return request('/api/artifacts/expiry')
}

/** Header line of the storage: count, bytes and the next deadline date. */
export interface ArtifactStats {
  count: number
  bytes: number
  by_kind: { kind: string; count: number; bytes: number }[]
  expiring_count: number
  expiring_bytes: number
  next_expiry: string | null
}

export function artifactStats(): Promise<ArtifactStats> {
  return request('/api/artifacts/stats')
}

/** The answer to the deadline — the only route by which artifact files disappear. */
export function answerArtifactExpiry(
  ids: string[],
  action: 'keep' | 'delete',
): Promise<ArtifactExpiryAnswer> {
  return request('/api/artifacts/expiry/answer', {
    method: 'POST',
    body: JSON.stringify({ ids, action }),
  })
}

/**
 * A1: adopt — a copy of the workbench file to the place the user
 * names. Empty = the remembered adoption target from the settings. 422 means
 * "no target known", 409 "we do not overwrite a foreign file".
 */
export interface ArtifactAdoptResult {
  id: string
  adopted_path: string
  content_hash: string
  adopted_hash: string
  size: number
}

export function adoptArtifact(id: string, destination = ''): Promise<ArtifactAdoptResult> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/adopt`, {
    method: 'POST',
    body: JSON.stringify({ destination }),
  })
}

/** A card in full — including the state of its adopted copy. */
export interface ArtifactDetail extends ArtifactEntry {
  adopted_state: 'none' | 'current' | 'stale' | 'missing' | 'unknown'
}

export function getArtifact(id: string): Promise<ArtifactDetail> {
  return request(`/api/artifacts/${encodeURIComponent(id)}`)
}

/** The chain behind a card: turn, call, the tool calls of this turn. */
export interface ArtifactProvenanceCall {
  ts?: string
  kind?: string
  tool?: string
  args?: string
  decision?: string
  status?: string
  duration_ms?: number | null
}

export interface ArtifactProvenance {
  known: boolean
  turn_id: string
  call_id: string
  args_hash: string
  session_id: string
  calls: ArtifactProvenanceCall[]
}

export function artifactProvenance(id: string): Promise<ArtifactProvenance> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/provenance`)
}

/** Set tags — the list replaces the old ones completely (PUT, not PATCH). */
export function setArtifactTags(
  id: string,
  tags: string[],
): Promise<{ id: string; tags: string[] }> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/tags`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  })
}

/** The version line of a card (regenerate builds v2/v3 under a shared root_id). */
export function listArtifactVersions(id: string): Promise<{ versions: ArtifactEntry[] }> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/versions`)
}

/** Content preview for xlsx/docx — `mode: 'none'` is an answer, not an error. */
export interface ArtifactContentPreview {
  mode: 'table' | 'text' | 'slides' | 'none'
  reason?: string
  sheets?: string[]
  header?: string[]
  rows?: string[][]
  truncated?: boolean
  format?: string
  text?: string
  /** A deck's slides: the title and the body lines the file carries. */
  slides?: Array<{ title: string; lines: string[] }>
  count?: number
}

export function artifactPreview(id: string): Promise<ArtifactContentPreview> {
  return request(`/api/artifacts/${encodeURIComponent(id)}/preview`)
}

/** Remove. `deleteFile` deletes the file only when it sits inside an allowed
 * root — the answer says so, the surface claims nothing. */
export function removeArtifact(
  id: string,
  deleteFile = false,
): Promise<{ deleted: string; file_removed: boolean }> {
  return request(
    `/api/artifacts/${encodeURIComponent(id)}?delete_file=${deleteFile ? 'true' : 'false'}`,
    {
      method: 'DELETE',
    },
  )
}
