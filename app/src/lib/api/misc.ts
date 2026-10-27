/**
 * Endpoints: audio, git (branches/status/diff/actions), artifacts, search,
 * context budget, voice, pack index, audit, security, export/feedback, provider.
 * Moved 1:1 out of lib/api.ts (lines 842–1185) — relocation only, no logic change.
 */
import { BASE_URL, LAN_TOKEN, apiErrorFromResponse, apiUrl, request } from './http'
import type {
  AuditEntry,
  CellLife,
  ContextBudget,
  SessionSearchResult,
  SkillPackInfo,
  SkyData,
  VoiceSettings,
} from './types'
import type {
  CodeExecPolicy,
  GitAddResult,
  GitApplyResult,
  GitBranchesInfo,
  GitCommitResult,
  GitDiffResponse,
  GitStatusResponse,
  SecuritySettings,
  SessionSearchResponse,
} from './types_extra'
import type { ProviderSettings } from '@/types'

// ── Audio: transcription + TTS (the backend lives in routes/audio.py) ─────────

/** Upload name matching the recording's own container — the server whitelists by type. */
function audioUploadName(type: string): string {
  const base = (type.split(';')[0] ?? '').trim().toLowerCase()
  const ext =
    base === 'audio/mp4' || base === 'audio/m4a' || base === 'audio/x-m4a'
      ? 'mp4'
      : base === 'audio/ogg'
        ? 'ogg'
        : base === 'audio/wav' || base === 'audio/x-wav'
          ? 'wav'
          : base === 'audio/mpeg'
            ? 'mp3'
            : 'webm'
  return `recording.${ext}`
}

/** Upload an audio blob and have it transcribed (whisper.cpp, local). */
export async function transcribeAudio(blob: Blob): Promise<string> {
  const fd = new FormData()
  fd.append('file', blob, audioUploadName(blob.type))
  const headers: Record<string, string> = {}
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/audio/transcribe`, { method: 'POST', headers, body: fd })
  if (!res.ok) throw await apiErrorFromResponse(res)
  const data = (await res.json()) as { text: string }
  return data.text
}

/** Synthesize text via Edge-TTS → playable URL (LAN token in the query, <audio> can send no headers). */
export async function synthesizeSpeech(text: string): Promise<string> {
  const data = await request<{ audio_url: string }>('/api/audio/synthesize', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
  return LAN_TOKEN ? `${data.audio_url}?token=${encodeURIComponent(LAN_TOKEN)}` : data.audio_url
}

/** Round 12: git branch info for the header chip (read-only). */
export function listGitBranches(): Promise<GitBranchesInfo> {
  return request<GitBranchesInfo>('/api/git/branches')
}

/** Switch the branch in the workspace (no force, no create — the backend validates). */
export function checkoutGitBranch(branch: string): Promise<{ ok: boolean; branch: string }> {
  return request<{ ok: boolean; branch: string }>('/api/git/checkout', {
    method: 'POST',
    body: JSON.stringify({ branch }),
  })
}

// ── Session full-text search (R25, FTS5) ──────────────────────────────────────

export function searchSessionContent(
  q: string,
  limit = 12,
  signal?: AbortSignal,
): Promise<{ query: string; results: SessionSearchResult[]; total: number; elapsed_ms: number }> {
  return request(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`, { signal })
}

/** Real context-budget numbers from the backend (R25: honest display instead of a pure estimate). */
export function getContextBudget(sessionId?: string): Promise<ContextBudget> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  return request<ContextBudget>(`/api/context/budget${qs}`)
}

/** S4 workbench parity: the sky — orbits of the last days (d/h/k/n, purely read-only). */
export function getSky(days = 7): Promise<SkyData> {
  return request<SkyData>(`/api/ephemeris?days=${days}`)
}

// ── R18: voice settings (TTS engine/STT → voice.json) ──────────────────────

export function getVoiceSettings(): Promise<VoiceSettings> {
  return request('/api/settings/voice')
}

export function saveVoiceSettings(
  payload: Partial<Omit<VoiceSettings, 'piper_available' | 'installed_piper_voices' | 'stt_model_cached'>>,
): Promise<VoiceSettings> {
  return request('/api/settings/voice', { method: 'PUT', body: JSON.stringify(payload) })
}

// ── R16: curated offline pack index ─────────────────────────────────

export function getPackIndex(): Promise<{ version: number; packs: SkillPackInfo[] }> {
  return request('/api/skills/pack-index')
}

/** Export a topic pack as a zip (shareable offline, <a download>-safe). */
export function exportPackUrl(packId: string): string {
  return apiUrl(`/api/skills/export-pack/${encodeURIComponent(packId)}`)
}

// ── R23: audit log (append-only, read-only inspection) ──────────────────

export function getAudit(limit = 100, kind = ''): Promise<{ entries: AuditEntry[] }> {
  const kindQ = kind ? `&kind=${encodeURIComponent(kind)}` : ''
  return request(`/api/audit?limit=${limit}${kindQ}`)
}

// ── WP5: life line (read-only, only numbers from the cell registry) ──────

export function getCellLife(session: string): Promise<{ cell: CellLife }> {
  return request(`/api/cell?session=${encodeURIComponent(session)}`)
}

// Round G: review tab (read-only working-tree/index view of the workspace)

export function gitStatus(staged = false): Promise<GitStatusResponse> {
  return request(`/api/git/status?staged=${staged ? 'true' : 'false'}`)
}

export function gitDiff(path: string, staged = false): Promise<GitDiffResponse> {
  return request(
    `/api/git/diff?path=${encodeURIComponent(path)}&staged=${staged ? 'true' : 'false'}`,
  )
}

// ── W3c (2026-09-09): git actions from the git tab ───────────────────────

/** Stages files (paths) or the whole working tree (no paths → -A). */
export function gitAdd(paths?: string[]): Promise<GitAddResult> {
  return request('/api/git/add', { method: 'POST', body: JSON.stringify({ paths: paths ?? null }) })
}

/** Commit with a message; empty index/invalid input → HTTP error path. */
export function gitCommit(message: string): Promise<GitCommitResult> {
  return request('/api/git/commit', { method: 'POST', body: JSON.stringify({ message }) })
}

/** W16: apply a hunk patch — staged=true only stages into the index (--cached),
 *  reverse=true discards the change (-R). Errors arrive as HTTP status. */
export function gitApplyPatch(
  patch: string,
  opts?: { staged?: boolean; reverse?: boolean },
): Promise<GitApplyResult> {
  return request('/api/git/apply', {
    method: 'POST',
    body: JSON.stringify({ patch, staged: opts?.staged ?? false, reverse: opts?.reverse ?? false }),
  })
}

// ── R23: security settings (approval profile + shell sandbox) ────────────

export function getSecuritySettings(): Promise<SecuritySettings> {
  return request('/api/settings/security')
}

export function saveSecuritySettings(
  payload: Partial<Omit<SecuritySettings, never>>,
): Promise<SecuritySettings> {
  return request('/api/settings/security', { method: 'PUT', body: JSON.stringify(payload) })
}

/** Wave E1: effective cell ceilings for code execution (read-only). */
export function getCodeExecPolicy(): Promise<CodeExecPolicy> {
  return request('/api/settings/code-exec')
}

// ── K2 (2026-09-08): wire up the orphan routes — Z38 export + Z13 thumbs ──

/** Z38: POST /api/export (text/markdown — not JSON, hence a raw fetch). */
export async function exportChatMarkdown(
  messages: Array<{ role: string; content: string }>,
): Promise<string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/export`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ messages }),
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.text()
}

/** Z13: thumbs up — FeedbackStore path (few-shot context).
 *  `saved` is the answer from the disk, not a label: False means the example
 *  file is not there (core/feedback.py reports the OSError). */
export function feedbackThumbsUp(
  prompt: string,
  response: string,
): Promise<{ saved: boolean; journal?: boolean | null }> {
  return request('/api/feedback/thumbs_up', {
    method: 'POST',
    body: JSON.stringify({ prompt, response }),
  })
}

/** Z13: thumbs down — closes the correction-journal loop. */
export function feedbackThumbsDown(
  prompt: string,
  response: string,
  reason?: string,
): Promise<{ saved: boolean; journal?: boolean | null }> {
  return request('/api/feedback/thumbs_down', {
    method: 'POST',
    body: JSON.stringify({ prompt, response, reason }),
  })
}

/** K3 Z24: switch the active provider (PUT /api/model/provider, SSOT helper).
 *  base_url: carried along by environment-scan picks — without it a scan model
 *  landed on the previously configured engine. Confirming the
 *  online provider is part of the click (the route's 409 gate). */
export function setModelProvider(
  provider: string,
  model?: string,
  baseUrl?: string,
): Promise<{ active: ProviderSettings }> {
  return request('/api/model/provider', {
    method: 'PUT',
    body: JSON.stringify({
      provider,
      ...(model ? { model } : {}),
      ...(baseUrl ? { base_url: baseUrl } : {}),
      ...(provider === 'openai_compatible' ? { confirm_online: true } : {}),
    }),
  })
}

/** K3 Z35: session full-text search (FTS5, GET /api/search — R25 route). */
export function searchSessions(q: string, limit = 8): Promise<SessionSearchResponse> {
  return request(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`)
}

/** Blob download of a text payload (export download without an extra dependency). */
export function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Wave 3: usage billing (7/30 days, content-free) ─────────────────────────

export interface UsageDay {
  d: string
  in: number
  out: number
  cached: number
  est_turns: number
  turns: number
}

export interface UsageSummary {
  days: number
  totals: { in: number; out: number; cached: number; est_turns: number; turns: number }
  by_day: UsageDay[]
  pricing: { in_per_m?: number; out_per_m?: number } | null
  cost: { in_usd: number; out_usd: number; total_usd: number } | null
}

/** Daily aggregate of the content-free usage ledger; cost only when a price is configured. */
export function getUsageSummary(days = 30): Promise<UsageSummary> {
  return request<UsageSummary>(`/api/usage/summary?days=${days}`)
}
