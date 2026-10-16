// Type declarations of the API client (1:1 from lib/api.ts).
import type { ProviderSettings } from '@/types'
export interface McpSettings {
  servers: string[]
  source: 'env' | 'file' | 'none' | string
  tools: string[]
}
export interface PersonaResponse {
  source: string
  text: string
}
export interface ContextStage {
  name: string
  chars: number
  preview: string
}
export interface LearningProposal {
  id: string
  kind: string
  topic: string
  evidence: string
  count: number
  status: string
  session_id?: string
}
export interface FsEntry {
  name: string
  type: 'dir' | 'file' | 'info'
  size?: number
}

export interface FsListing {
  path: string
  parent: string | null
  home: string
  workspace: string | null
  /** True when the user chose a project; false = neutral "Workspace" state. */
  workspace_set?: boolean
  entries: FsEntry[]
}
export interface ProjectSummary {
  name: string
  path: string
  stacks: string[]
  score: number
  workspace: boolean
}
/** Model option with UI metadata (from the Ollama / OpenAI list). */
export interface ModelOption {
  name: string
  label?: string
  family?: string
  parameter_size?: string
}

export interface ModelProvidersResponse {
  active: ProviderSettings
  /** Entry form from /api/model/providers: `provider` = id, `model` = model name. */
  providers: Array<{ id?: string; provider?: string; model?: string; label: string }>
  local_models: string[]
  local_model_options: ModelOption[]
  /** max_model_len of the active engine (vLLM); null with Ollama -> default 8192. */
  context_window?: number | null
  /** Wave 3 (cost monitor): price table USD per 1M tokens from engine.json
   *  `pricing`; null = not maintained → the UI shows no cost chip. */
  pricing?: { in_per_m?: number; out_per_m?: number } | null
}
/** W17 P1-3: reverse proxy onto a local dev server (preview panel). */
export interface ProxyResult {
  ok: boolean
  status: number
  body: string
  url: string
}
/** R4: the install note beside a user skill (core/skill_provenance.py). */
export interface SkillInstallRecord {
  kind: string
  origin: string
  version?: string
  pack_id?: string
  installed_at?: string
  content_hash: string
}

export interface SkillSummary {
  name: string
  trigger: string
  description: string
  is_builtin?: boolean
  /** R16 pack format: semantic version from the SKILL.md frontmatter. */
  version?: string
  /** R16 skill manager: disabled (listed, but never auto-resolved). */
  disabled?: boolean
  /** R4: where the package came from — null for built-ins and installs before the chain. */
  install?: SkillInstallRecord | null
  /** R4: is the file still what was noted? null = not provable. */
  unchanged?: boolean | null
}

export interface SkillInstallResult {
  installed: {
    name: string
    version: string
    trigger: string
    origin?: string
    content_hash?: string
  }[]
  updated: {
    name: string
    version: string
    trigger: string
    origin?: string
    content_hash?: string
  }[]
  skipped: { name: string; reason: string }[]
}
export interface ImageSettings {
  base_url: string
  model: string
  has_api_key: boolean
  api_key_hint: string
}

export interface ImageEndpointProbe {
  reachable: boolean
  models: string[]
  base_url_used: string
  detail: string
}
/**
 * Active engine status from the backend (single source of truth).
 * Mirrors server/routes/health.py::HealthResponse.
 */
export interface HealthInfo {
  status: string
  version?: string
  ollama: boolean
  models: string[]
  active_tier: string
  active_model: string
  dgx_online: boolean
  active_provider: string
  offline_capable: boolean
  requires_internet: boolean
  model_installed?: boolean
  detail?: string
  /** F-02: real engine reachability (for openai_compatible via the /models probe) */
  engine_online?: boolean
  /**
   * W18/A5: three-valued engine state — `ok` answers, `busy` does not answer in
   * time (model loading / GPU occupied), `unreachable` is down.
   * Source: server/routes/health.py (same classification as core/chat.py).
   */
  engine_state?: EngineState
  /**
   * The engine answered and refused the credential (401/403) — a live endpoint
   * turning this run away, which is a different problem from one that never replies.
   * Source: server/routes/health.py; the desktop reuse branch reads the same field
   * (`app/src-tauri/src/backend.rs`).
   */
  engine_key_challenge?: boolean
  /** Whether this process can resolve a credential for the active endpoint at all. */
  engine_key_configured?: boolean
}

/** Three-valued engine states from the health and probe routes. */
export type EngineState = 'ok' | 'busy' | 'unreachable'
/**
 * Setup status: is an engine already persisted (engine.json)?
 * configured=false → the PWA shows the engine selection (SetupPage).
 */
export interface SetupStatus {
  configured: boolean
  /** W19: the user consciously skipped onboarding → gate open, chat fail-closed. */
  skipped?: boolean
  provider: string
  model: string | null
  url: string | null
  reachable: boolean
  available_models: string[]
  /** P3: all candidates due for the auto-scan (persisted + env + default). */
  candidates?: EngineCandidate[]
}

/** An engine candidate for the parallel auto-scan (URL null => local default). */
export interface EngineCandidate {
  provider: string
  url: string | null
  /** Port hint of the loopback scan: it names what a port commonly serves, so it is
   *  never a recognition. `hint_code` is the machine half, `hint` the sentence an old
   *  client and the log read. Both come from `_ENGINE_PORTS` in
   *  server/routes/settings.py. */
  hint?: string
  hint_code?: string
  /** From this machine's loopback scan (not from engine.json/history/env).
   *  R9: the surface uses it to say WHERE a suggestion comes from, instead of
   *  calling both "recognised". */
  sweep?: boolean
}

/** Result of a single candidate probe from /api/setup/detect. */
export interface DetectedEngine {
  provider: string
  url: string | null
  reachable: boolean
  models: string[]
  detail: string
  state?: EngineState
  /** Port hint, same pair as on the candidate. */
  hint?: string
  hint_code?: string
}

/** Response from GET /api/setup/detect — parallel multi-engine scan. */
export interface DetectResponse {
  candidates: EngineCandidate[]
  detected: DetectedEngine[]
  /** Index of the first reachable candidate with >= 1 model, otherwise -1. */
  first_reachable: number
}

export interface ProviderProbeResponse {
  reachable: boolean
  models: string[]
  detail: string
  /** Probed endpoint (echoed by the server; used for structured UI rendering). */
  url?: string
  /** W18/A5: ok | busy | unreachable (busy = timeout, NOT offline). */
  state?: EngineState
}
export interface ScheduleJob {
  id: string
  task: string
  cron: string
  next_run?: string
  enabled?: boolean
  max_runs?: number
}

// R19: shape = core/scheduler._run_task entry (no more id/status/output).
export interface ScheduleResult {
  job_id: string
  task: string
  executed_at: string
  result: string
  error: string | null
}

export interface SchedulePreset {
  id: string
  title: string
  task: string
  cron: string
}
/** Tasks (settings hub): reads the existing /api/tasks list. */
export interface TaskItem {
  id: string
  title: string
  status: string
  project?: string | null
}
/** Mobile connection (AI client parity): QR code for LAN/public PWA. */
export interface MobileQR {
  url: string
  qr_base64: string
  mode: string
  is_public: boolean
  requires_internet: boolean
  lan_reachable: boolean
  message: string
}
export interface TelegramStatus {
  token_configured: boolean
  token_masked: string | null
  running: boolean
  bot_username: string | null
  paired_count: number
  session_count: number
  last_error: string | null
}

export interface TelegramPairing {
  deep_link: string
  qr_base64: string
  issued_at: number
  expires_at: number
  ttl_seconds: number
}

export interface TelegramDevice {
  user_id: number
  label: string
  paired_at: string
}
export interface DiscordStatus {
  configured: boolean
  token_masked: string | null
  running: boolean
  last_error: string | null
  message: string
}
export interface SessionSearchResult {
  session_id: string
  session_title: string
  role: 'user' | 'assistant' | 'system'
  snippet: string
  content: string
  updated_at: string
}
/** Real context budget numbers from the backend (R25: honest display instead of a pure estimate). */
export interface ContextBudget {
  message_count: number
  char_count: number
  estimated_tokens: number
  window_tokens: number
  /** Where the window comes from: env override, engine probe, tier table or legacy fallback. */
  window_source?: 'env' | 'engine' | 'tier' | 'legacy'
  /** W16: active counter backend — exact with tiktoken BPE, otherwise calibrated. */
  tokenizer?: 'tiktoken-bpe' | 'calibrated-4.2'
  percent: number
  compaction_threshold: number
  compaction_active: boolean
  /** Share per category in % (Messages, MCP tools, System tools, System prompt, Skills, Meta context) */
  breakdown?: { name: string; percent: number }[]
}
/** S4 workbench parity: the sky as read-only JSON (d/h/k/n — WHEN, never WHAT). */
export interface SkyDayRow {
  d: string
  weekday: string
  label: string
  total: number
  peak_hour: number | null
  hours: Record<string, number>
}
export interface SkyData {
  available: boolean
  days: number
  today: string | null
  empty: boolean
  total: number
  faded: number
  kinds: { session: number; tool: number; artifact: number }
  rows: SkyDayRow[]
}
export interface VoiceSettings {
  tts_engine: 'auto' | 'piper' | 'edge'
  piper_voice: string
  edge_voice: string
  stt_model: 'tiny' | 'base' | 'small'
  stt_language: 'auto' | 'de' | 'en'
  piper_available: boolean
  installed_piper_voices: string[]
}
export interface SkillPackInfo {
  id: string
  title: string
  description: string
  skills: { name: string; installed: boolean; trigger: string }[]
  complete: boolean
}
export * from './types_memory'

export interface AuditEntry {
  ts: string
  kind: string
  tool: string
  args_hash: string
  args: string
  decision: string
  status: string
  duration_ms: number | null
  detail: string
}

/** WP5: what `core.ephemeral_cell.cell_life` knows about a session's cell.
 *  When the cell is dead the registry answers briefly — only these three fields
 *  still count then, so the others are optional and never invented. */
export interface CellLife {
  alive: boolean
  calls: number
  avg_ms: number | null
  ordinal?: number
  kind?: string
  age_seconds?: number
  idle_seconds?: number
  ttl_seconds?: number
  seconds_left?: number
}
