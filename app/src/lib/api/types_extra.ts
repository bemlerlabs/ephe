// Git/audit/search/security types of the API client (1:1 out of lib/api.ts).

// R4: the workbench artifact types — moved here because types.ts holds
// the core shapes of the HTTP client and the card has had more fields since A0.
export interface ArtifactEntry {
  id: string
  root_id: string
  version: number
  session_id: string
  name: string
  path: string
  kind: string
  size: number
  topic: string
  created_at: string
  favorite: boolean
  /** legacy rows can deliver the list as a JSON string (the Store reads it that way). */
  tags: string[] | string
  // ── A0: identity instead of path ────────────────────────────────────────
  origin_path?: string
  adopted_path?: string
  adopted_hash?: string
  content_hash?: string
  viewed_at?: string | null
  turn_id?: string
  call_id?: string
  args_hash?: string
  // ── The deadline (30 days) and its question ────────────────────────────
  keep?: boolean
  expires_at?: string | null
  expiry_answered_at?: string | null
}

/** GET /api/artifacts/expiry — what the deadline has reached. Counting, not deleting. */
export interface ArtifactExpiry {
  due: ArtifactEntry[]
  count: number
  bytes: number
  days: number
}

export interface ArtifactExpiryAnswer {
  kept: string[]
  deleted: string[]
  skipped: string[]
}
/** Round 12: git branch info for the header chip (read-only). */
export interface GitBranchesInfo {
  workspace: string
  git: boolean
  current: string
  branches: string[]
}
export interface GitFileChange {
  path: string
  status: 'M' | 'A' | 'D' | 'R' | 'C' | 'T' | 'U' | '?'
  additions: number
  deletions: number
}

export interface GitStatusResponse {
  workspace: string
  git: boolean
  branch: string
  changes: GitFileChange[]
  /** Absolute directory the status was read in; the paths above are relative to it.
   *  Empty when git could not answer, so a consumer that needs it fails closed. */
  root?: string
}

export interface GitDiffResponse {
  path: string
  diff: string
  binary: boolean
}
export interface GitAddResult {
  ok: boolean
  staged: number
}

export interface GitCommitResult {
  ok: boolean
  hash: string
  branch: string
}
export interface GitApplyResult {
  ok: boolean
}
export interface SecuritySettings {
  /** The four values the server accepts (core/security_config.py::VALID_APPROVAL_PROFILES). */
  approval_profile: 'strict' | 'session' | 'plan' | 'full'
  sandbox_enabled: boolean
}

/**
 * Wave E1: the effective caps of model Python execution
 * (GET /api/settings/code-exec). Read-only, no secrets — `report == enforced`.
 */
export interface CodeExecPolicy {
  runtime: string
  max_fuel: number
  max_memory_mb: number
  timeout_seconds: number
  io_cpu_seconds: number
  io_budget_bytes: number
  disk_quota_bytes: number
  /** Per session across all files of /work — enforced by ephe, not by the engine. */
  work_quota_bytes?: number
  /** For each cap, who sets it and how much space it applies to. */
  quota_scopes?: Record<string, string>
  output_cap_bytes: number
  /** The sink wall that the pass-through protects against (measured, not invented). */
  sink_ceiling_bytes?: number
  guest_forward_bytes?: number
  guest_tee_cap_bytes?: number
  preopens: string[]
  network: string
  guest: {
    version: string
    installed: boolean
    library: boolean
    entry_hash_ok: boolean
    stdlib_hash_ok: boolean
    path: string
    reason: string
  }
  license: { guest: string; cell_runtime: string }
  measured: Record<string, number | string>
  gaps: string[]
}
/** K3 Z35: full-text session search (FTS5, GET /api/search — R25 route). */
export interface SessionSearchHit {
  session_id: string
  session_title: string
  role: string
  snippet: string
  content: string
}
export interface SessionSearchResponse {
  query: string
  results: SessionSearchHit[]
  total: number
  elapsed_ms: number
}
