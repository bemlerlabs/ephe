import { BASE_URL, LAN_TOKEN, request } from './http'
import type {
  ContextStage,
  DetectResponse,
  FsListing,
  HealthInfo,
  ImageEndpointProbe,
  ImageSettings,
  LearningProposal,
  McpSettings,
  MemoryStats,
  ModelProvidersResponse,
  PersonaResponse,
  ProjectSummary,
  ProviderProbeResponse,
  ProxyResult,
  SkillInstallResult,
  SkillSummary,
  SetupStatus,
} from './types'
import type {
  RestoredSession,
  SessionPruneRequest,
  SessionPruneResult,
  SessionStoreView,
  ServerSessionTranscript,
  SyncSession,
} from './types_sessions'
import type { AppSettings, AskAnswerResponse } from '@/types'
export function getSettings(): Promise<AppSettings> {
  return request<AppSettings>('/api/settings')
}

/**
 * Sandbox confirmation to the backend (PWA chat-UX plan, replaces the WS path).
 * 200 {status: ok} for a known token; 404 (known error contract,
 * tests/test_api.py::TestSandboxApproveEndpoint) when the token has expired.
 */
export function approveSandbox(
  token: string,
  approved: boolean,
  remember = false,
): Promise<{ status: string }> {
  return request<{ status: string }>('/api/sandbox/approve', {
    method: 'POST',
    body: JSON.stringify({ token, approved, remember }),
  })
}

/**
 * G1: the answer to a pending `ask_user`, back into the run that is awaiting it.
 * `token` comes from the stream's `ask_user` frame. 200 {status: ok} wakes that turn;
 * 404 means the wait already ended (timeout, stop button) and the run went on with its
 * stated default; 422 means the answer was empty — an unanswered run reaches its
 * timeout instead, so the two cases stay apart.
 */
export function answerAsk(token: string, answer: string): Promise<AskAnswerResponse> {
  return request<AskAnswerResponse>('/api/ask/answer', {
    method: 'POST',
    body: JSON.stringify({ token, answer }),
  })
}

export function updateSettings(settings: Partial<AppSettings>): Promise<AppSettings> {
  return request<AppSettings>('/api/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
}

// ── Wave 6: plugin store + deep section register ────────────────────────────

/** One plugin entry from the aggregated store view (GET /api/plugins). */
export interface PluginEntry {
  id: string
  name: string
  description: string
  tags: string[]
  example_prompts: string[]
  enabled: boolean
  /** E4b detail-sheet facts (best-effort, only when a manifest dir exists). */
  version?: string
  sha256?: string
  manifest?: boolean
  source?: 'builtin' | 'user'
  permissions?: string[]
  /** E3: provenance — first-party (built-in) vs external (vendor/community). */
  origin?: 'first-party' | 'external'
}

export interface PluginView {
  public: PluginEntry[]
  personal: PluginEntry[]
  orphans?: string[]
  /** E1 master kill-switch: false = stock Ephe, all toggles inactive. */
  master_enabled?: boolean
}
/** Aggregated store view: curated catalog + installed registry. */
export function getPlugins(): Promise<PluginView> {
  return request<PluginView>('/api/plugins')
}

/** Set a plugin's enabled switch (best effort, always able to return 200). */
export function setPluginEnabled(
  id: string,
  enabled: boolean,
): Promise<{ id: string; enabled: boolean; saved: boolean }> {
  return request<{ id: string; enabled: boolean; saved: boolean }>(
    `/api/plugins/${encodeURIComponent(id)}/enable`,
    {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    },
  )
}

/** E1: master kill switch — false = stock Ephe without plugin gating. */
export function setPluginMaster(
  enabled: boolean,
): Promise<{ master_enabled: boolean; saved: boolean }> {
  return request<{ master_enabled: boolean; saved: boolean }>('/api/plugins/master', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

/** E2: manifest-declared slash commands of the enabled plugins. */
export interface PluginCommandInfo {
  name: string
  description: string
  template: string
  plugin: string
}

export function getPluginCommands(): Promise<{ commands: PluginCommandInfo[] }> {
  return request<{ commands: PluginCommandInfo[] }>('/api/plugins/commands')
}

/** Persist the section register with hard validation (422 on a range violation). */
export function saveSections(
  sections: Record<string, Record<string, string | number | boolean>>,
): Promise<unknown> {
  return request<unknown>('/api/settings', {
    method: 'POST',
    body: JSON.stringify({ sections }),
  })
}

// ── W44 P1c: MCP server attachment (GET/PUT /settings/mcp) ──────────────────

export function getMcpSettings(): Promise<McpSettings> {
  return request<McpSettings>('/api/settings/mcp')
}

export function putMcpSettings(servers: string[]): Promise<McpSettings> {
  return request<McpSettings>('/api/settings/mcp', {
    method: 'PUT',
    body: JSON.stringify({ servers }),
  })
}

// ── E3c: MCP page — health probe + curated catalog ─────────────────────────

export interface McpHealthServer {
  spec: string
  status: 'ok' | 'unreachable'
  tool_count: number
  transport: string
  latency_ms: number | null
  error: string | null
}

export interface McpCatalogEntry {
  id: string
  name: string
  description: string
  /** Backend-supplied English text (I7-4) — the German `description` is primary. */
  description_en?: string
  category: string
  spec?: string
  install_hint?: string
  docs?: string
}

/** Probes the server-side configured MCP servers (no parameters). */
export function probeMcpHealth(): Promise<{ servers: McpHealthServer[] }> {
  return request<{ servers: McpHealthServer[] }>('/api/mcp/health', { method: 'POST' })
}

export function getMcpCatalog(): Promise<{ entries: McpCatalogEntry[] }> {
  return request<{ entries: McpCatalogEntry[] }>('/api/mcp/catalog')
}

// ── R28: Agent Identity — persona editor ────────────────────────────────────

export function getPersona(): Promise<PersonaResponse> {
  return request<PersonaResponse>('/api/settings/persona')
}

export function updatePersona(text: string): Promise<PersonaResponse> {
  return request<PersonaResponse>('/api/settings/persona', {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}
// ── R29: context transparency — assembled prompt stages ───────────────────────

export function getContextStages(): Promise<{ stages: ContextStage[]; total_chars: number }> {
  return request<{ stages: ContextStage[]; total_chars: number }>('/api/context/stages')
}
// ── R30: session sync (PWA → server, powers FTS5 over browser sessions) ──────

export function syncSessions(payload: {
  sessions: SyncSession[]
  deleted: string[]
}): Promise<{ stored_sessions: number; dropped_sessions: number }> {
  return request('/api/sessions/sync', { method: 'POST', body: JSON.stringify(payload) })
}

// ── Restore-on-empty (PWA ← server): hydrate from the sync mirror when the
// browser cache is lost. The server strips the pwa- prefix and returns the
// newest sessions first; ids map 1:1 back onto local sessions.

export function restoreSessions(limit = 50): Promise<{ sessions: RestoredSession[] }> {
  return request(`/api/sessions/restore?limit=${limit}`)
}

// ── W6: portable session bundle (zip/tar.gz) — per-device folder parity ──────

/** Bundle the session store as zip (default) or tar.gz; raw bytes. */
export async function exportSessionsBundle(format: 'zip' | 'tgz' = 'zip'): Promise<Uint8Array> {
  const headers: Record<string, string> = {}
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/sessions/export?format=${format}`, { headers })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return new Uint8Array(await res.arrayBuffer())
}

/** Restore a previously exported bundle into the session store. */
export async function importSessionsBundle(
  bytes: Uint8Array,
  filename = 'bundle.zip',
): Promise<{ restored: number }> {
  const form = new FormData()
  form.append('file', new Blob([bytes], { type: 'application/zip' }), filename)
  const headers: Record<string, string> = {}
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/sessions/import`, {
    method: 'POST',
    body: form,
    headers,
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json() as Promise<{ restored: number }>
}

// Wave 4: the session store — what it holds, and the retention bound.

/**
 * The store on the server's machine: how many files it holds per namespace, in
 * bytes, and the register list.
 *
 * `total` counts *files* across all three namespaces, so it is larger than the
 * task count a sidebar shows; `registered_sessions` is that smaller number. A
 * surface showing either of them has to name which one it means.
 */
export function getSessionStore(): Promise<SessionStoreView> {
  return request<SessionStoreView>('/api/sessions')
}

/** One server store transcript (the same session the CLI and the TUI use). */
export function getServerSession(id: string): Promise<ServerSessionTranscript> {
  return request<ServerSessionTranscript>(`/api/sessions/${encodeURIComponent(id)}`)
}

/**
 * Apply the retention counts (`core.session_lifecycle.prune_store`).
 *
 * With `dry_run: true` the endpoint reports what a run would remove and frees
 * nothing — the preview a caller shows before it deletes. With `dry_run: false`
 * it unlinks the files and drops their registry rows; the active task is never
 * among them.
 */
export function pruneSessions(body: SessionPruneRequest): Promise<SessionPruneResult> {
  return request<SessionPruneResult>('/api/sessions/prune', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Delete the whole session store (all namespaces, nothing kept). */
export function clearSessions(): Promise<SessionPruneResult> {
  return request<SessionPruneResult>('/api/sessions/clear', { method: 'POST' })
}

// ── R31: learning loop proposals ─────────────────────────────────────────────

export function getLearningProposals(): Promise<{ proposals: LearningProposal[] }> {
  return request('/api/learning/proposals')
}

export function dismissLearningProposal(id: string): Promise<{ status: string }> {
  return request(`/api/learning/proposals/${encodeURIComponent(id)}/dismiss`, { method: 'POST' })
}

export function acceptLearningProposal(
  id: string,
  model: string,
): Promise<{ installed: string; status: string }> {
  return request(`/api/learning/proposals/${encodeURIComponent(id)}/accept`, {
    method: 'POST',
    body: JSON.stringify({ model }),
  })
}

// ── F round 4: file system (explorer + workspace dialog, read-only) ─────────

export function listFs(path?: string): Promise<FsListing> {
  return request<FsListing>(`/api/fs${path ? `?path=${encodeURIComponent(path)}` : ''}`)
}

/** W19 F3: create a folder for the workspace dialog (parent + one segment). */
export function createWorkspaceFolder(
  parent: string,
  name: string,
): Promise<{ path: string; created: boolean }> {
  return request<{ path: string; created: boolean }>('/api/fs/mkdir', {
    method: 'POST',
    body: JSON.stringify({ parent, name }),
  })
}

// ── R26: workspace projects (sidebar tree + welcome cards) ──────────────────

export function listProjects(): Promise<{
  workspace: string
  projects: ProjectSummary[]
  generated_at: string
}> {
  return request<{ workspace: string; projects: ProjectSummary[]; generated_at: string }>(
    '/api/projects',
  )
}

// ── Model provider / memory (G5: settings reality) ──────────────────────────

/**
 * Active provider + locally available models (live from the engine).
 * G5: the model picker in the settings lists THOSE instead of being hardcoded.
 */
export function getModelProviders(): Promise<ModelProvidersResponse> {
  return request<ModelProvidersResponse>('/api/model/providers')
}

/** Number of stored memory vectors (G5: real memory statistics). */
export function getMemoryStats(): Promise<MemoryStats> {
  return request<MemoryStats>('/api/memory/stats')
}

/** G1 full terminal: runs a whitelisted shell command through the existing
 *  run_shell tool (the whitelist/blocked patterns stay the hard boundary).
 *  `approved: true` is that call's explicit statement that a person pressed Run on this
 *  command: the route refuses without it, so a request that reuses our CSRF header does not
 *  run anything by itself. */
export function runShell(
  command: string,
): Promise<{ command: string; output: string; ok: boolean }> {
  return request<{ command: string; output: string; ok: boolean }>('/api/shell', {
    method: 'POST',
    body: JSON.stringify({ command, approved: true }),
  })
}

/** W17 P1-1: PTY-backed run (onlcr CRLF, ANSI) with optional stdin feeding. */
export function runShellPty(
  command: string,
  input = '',
): Promise<{ command: string; output: string; ok: boolean }> {
  return request<{ command: string; output: string; ok: boolean }>('/api/shell/pty', {
    method: 'POST',
    body: JSON.stringify({ command, input, approved: true }),
  })
}

export function proxyFetch(port: number, path = '/'): Promise<ProxyResult> {
  return request<ProxyResult>(`/api/proxy/${port}/${path.startsWith('/') ? path.slice(1) : path}`)
}

/** Deletes ALL memory entries (G5: 'Memory leeren'). */
export function clearMemory(): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>('/api/memory', { method: 'DELETE' })
}

// ── Skills (G6: /skills shows the backend skills in the PWA) ────────────────

/** Lists the available skills (GET /api/skills). */
export function listSkills(): Promise<{ skills: SkillSummary[]; total: number }> {
  return request<{ skills: SkillSummary[]; total: number }>('/api/skills')
}

/** R16: installs a skill pack (zip/tgz) — multipart, no JSON header. */
export async function installSkill(file: File, force = false): Promise<SkillInstallResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('force', String(force))
  const headers: Record<string, string> = {}
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/skills/install`, { method: 'POST', headers, body: form })
  if (!res.ok) {
    let detail = `API ${res.status}: ${res.statusText}`
    try {
      const body = (await res.json()) as { error?: { message?: string }; detail?: string }
      detail = body.error?.message || body.detail || detail
    } catch {
      /* Body is not JSON → generic message */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<SkillInstallResult>
}

/** R16: installs a skill pack from a URL (POST /api/skills/install/url). */
export async function installSkillFromUrl(url: string, force = false): Promise<SkillInstallResult> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/skills/install/url`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ url, force }),
  })
  if (!res.ok) {
    let detail = `API ${res.status}: ${res.statusText}`
    try {
      const body = (await res.json()) as { error?: { message?: string }; detail?: string }
      detail = body.error?.message || body.detail || detail
    } catch {
      /* Body is not JSON → generic message */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<SkillInstallResult>
}

/** R16: disables a skill (still listed, but never auto-resolved). */
export function disableSkill(name: string): Promise<{ name: string; disabled: boolean }> {
  return request(`/api/skills/${encodeURIComponent(name)}/disable`, { method: 'POST' })
}

/** R16: re-enables a disabled skill. */
export function enableSkill(name: string): Promise<{ name: string; disabled: boolean }> {
  return request(`/api/skills/${encodeURIComponent(name)}/enable`, { method: 'POST' })
}

/** Deletes a user skill (built-ins are protected). */
export function deleteSkill(name: string): Promise<{ deleted: string }> {
  return request(`/api/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

// ── R16: image endpoint settings (settings → image.json) ────────────────────

export function getImageSettings(): Promise<ImageSettings> {
  return request('/api/settings/image')
}

/** Omit api_key = keep the existing key; '' = delete the key. */
export function saveImageSettings(payload: {
  base_url: string
  model: string
  api_key?: string
}): Promise<ImageSettings> {
  return request('/api/settings/image', { method: 'PUT', body: JSON.stringify(payload) })
}

export function testImageEndpoint(): Promise<ImageEndpointProbe> {
  return request('/api/settings/image/test', { method: 'POST' })
}

export function healthCheck(): Promise<HealthInfo> {
  return request<HealthInfo>('/api/health')
}

// ── Setup (first-run engine choice) ─────────────────────────────────────────

export function getSetupStatus(): Promise<SetupStatus> {
  return request<SetupStatus>('/api/setup/status')
}

/**
 * Parallel auto-scan of every engine candidate (local Ollama + OpenAI-compatible
 * such as DGX Spark/vLLM). Per candidate it returns reachability + models and the
 * index of the first reachable one. Drives mount auto-detect and the re-scan button.
 */
export function detectEngines(): Promise<DetectResponse> {
  return request<DetectResponse>('/api/setup/detect')
}

/**
 * Check the endpoint + list available models (Ollama: /api/tags,
 * OpenAI-compatible: /v1/models). No persist — detection only.
 */
export function probeProvider(
  provider: 'local_ollama' | 'custom_ollama' | 'openai_compatible',
  baseUrl?: string,
  apiKey?: string,
): Promise<ProviderProbeResponse> {
  return request<ProviderProbeResponse>('/api/model/providers/probe', {
    method: 'POST',
    body: JSON.stringify({
      provider,
      base_url: baseUrl || null,
      api_key: apiKey || null,
    }),
  })
}

export function resetSetup(): Promise<{ configured: boolean }> {
  return request<{ configured: boolean }>('/api/setup/reset', { method: 'POST' })
}

/** W19: skip onboarding — no silent default, the chat stays fail-closed. */
export function skipSetup(): Promise<{ configured: boolean; skipped: boolean }> {
  return request<{ configured: boolean; skipped: boolean }>('/api/setup/skip', { method: 'POST' })
}

// ── W1-b: reading view (server/routes/reader.py) ─────────────────────────────

export type ReaderResult = {
  ok: boolean
  reason: string
  title: string
  text: string
  chars: number
  truncated: boolean
  target: string
}

/** The reading version of an external page — fetched through the same
 *  reach guard as the agent tools, not a second network window. */
export function readUrl(url: string): Promise<ReaderResult> {
  return request<ReaderResult>(`/api/reader?url=${encodeURIComponent(url)}`)
}
