/**
 * Ephe — canonical shared types (the single source of truth)
 *
 * The module types (api.ts, chatStore.ts, db.ts) all import from here and
 * re-export from here, so existing import paths stay stable. Duplicates that
 * used to live in the individual modules are centralised here.
 */

export type MessageRole = 'user' | 'assistant' | 'system'

// ── Remote / REST-API shapes ───────────────────────────────────────────────

/** The session as the REST API returns it */
export interface ApiSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

/** The message as the REST API returns it */
export interface ApiMessage {
  id: string
  role: MessageRole
  content: string
  tool_calls?: unknown[]
}

/** Chat payload of a REST request */
export interface ApiChatMessage {
  role: MessageRole
  content: string
}

// ── Lokale Chat/Store-Shapes ───────────────────────────────────────────────

/** A tool call in the chat model (local, persisted in the store) */
export interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
  /** Wave 16: the guard's own reason code, when the refusal knows one. `result`
   * stays the text a client that predates this field reads. */
  reason_code?: string
  reason_params?: Record<string, string | number>
  status: 'pending' | 'approved' | 'denied' | 'completed' | 'failed' | 'waiting'
  description?: string
  /** K3 Z08: run time of the call (from the tool_done frame, seconds) */
  duration_ms?: number
  /** K3 Z07: live tail of the stdout chunks (a growing pre-block in the detail) */
  stdout?: string
  /** R23: the backend offers "remember for this session" as an option (session profile only, never run_shell). */
  rememberable?: boolean
  /** Wave B1: the real unified-diff preview (edit_file/write_file) for the approval dialog. */
  approval_diff?: string
  /** E1: sha256 of the result payload as delivered, so the proof ledger's digest can be re-hashed. */
  sha256?: string
}

/** Pending tool call until the user approves or denies it (local + WS payload) */
export interface PendingToolCall {
  id: string
  tool_name: string
  tool_args: Record<string, unknown>
  description: string
  session_id: string
}

/**
 * Activity in the chat model (local, persisted in the store) — AI-client style
 * inline activity feed. Status flow: running → done | failed (final).
 */
export interface Activity {
  id: string
  label: string
  status: 'running' | 'done' | 'failed'
  detail?: string
  /** P2-1: path + type of a generated artifact (only set for file_result). */
  path?: string
  fileType?: string
  /** A0: the id of the registered artifact. Bytes travel through it, not through
   * the path. Older sessions have none — there the path stays the way out. */
  artifactId?: string
}

/**
 * Thinking phase (local): `start` is set by the thinking_start event, `end` by
 * the first visible chunk (or at done) → duration = end - start.
 * `text` = streamed reasoning text (thinking_chunk events, AI-client parity),
 * capped at THINKING_MAX_CHARS inside the store.
 */
export interface ThinkingPhase {
  start: number
  end: number | null
  text?: string
}

/**
 * Artifact recognised by the backend artifact detector (SSE 'artifact' event).
 * Its content renders inline as a CodeBlock (F-01: code must never end up in
 * the bubble as placeholder text only).
 */
export interface ArtifactInfo {
  id: string
  artifact_type: string
  content: string
  language: string
  title: string
  filename: string
}

/**
 * The goal loop's own state (core/goal_loop.py, reached from the chat as `/goal`):
 * what the loop works toward, the command it is judged by and the round it is in.
 * The `goal_start` frame opens it, `goal_turn` moves the round, `goal_check` carries
 * that round's verdict.
 */
export interface GoalRunState {
  goal: string
  check: string
  maxTurns: number
  turn: number
  /** The last check's verdict; null while this round's check has not answered yet. */
  ok: boolean | null
}

export interface StreamGoalStart {
  type: 'goal_start'
  goal: string
  check: string
  max_turns: number
}

export interface StreamGoalTurn {
  type: 'goal_turn'
  turn: number
}

export interface StreamGoalCheck {
  type: 'goal_check'
  turn: number
  ok: boolean
  output: string
}

/** #92: one step of a plan, in the four states the core models (core/ephe_plan.py). */
export type PlanItemStatus = 'pending' | 'active' | 'done' | 'failed' | 'cancelled'

export interface PlanCardItem {
  status: PlanItemStatus
  text: string
}

/** The plan of a turn: the shape the guard instructs, the emitter writes and the
 *  reader renders — whether it arrived as a `plan` frame or as text in the answer. */
export interface PlanCardSpec {
  items: PlanCardItem[]
  done: number
  total: number
}

/**
 * Ordered content block of an assistant message (round 1, reference parity):
 * the chat stream renders to the beat of the events — text segments and tool
 * lines in arrival order (text → tool → text), not as two separate accumulators.
 */
export type MessageBlock =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; callId: string }
  /** Index into `ChatMessage.thinkingPhases` — every phase keeps its own
   *  arrival slot (thinking → tool → thinking → tool, the reference pattern). */
  | { kind: 'thinking'; index: number }

/** Chat message in the store (local, persisted) */
export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  /** A3: the assignment that produced this answer. The same id sits on every
   * workbench card born from it — the chain runs in both directions because
   * both sides carry the same value. */
  turnId?: string
  /** S17: the live `progress` frame of the running tool (round, query, elapsed). */
  progress?: TurnProgress
  tool_calls?: ToolCall[]
  /** Chronological render plan (text/tool/thinking blocks); missing for legacy seeds → old fixed order */
  blocks?: MessageBlock[]
  /** In-place streaming events (PWA chat UX plan) — optional, legacy messages are null */
  thinking?: ThinkingPhase | null
  /** All reasoning phases in their arrival slots; `blocks[].index` points into this field */
  thinkingPhases?: ThinkingPhase[]
  activities?: Activity[]
  /** #92: the plan of this turn, from the `plan` frame or parsed out of the answer text */
  plan?: PlanCardSpec
  /** The goal loop's state of this turn, from the `goal_*` frames (P6 B3: the
   *  status panel shows this goal — the one the loop works toward — and falls back
   *  to the session's opening query only where no goal run recorded one). */
  goal?: GoalRunState
  /** P1-7: time-to-first-token of the running answer in ms (turn start → first content chunk) */
  ttftMs?: number
  /** P6-Timeline (ref-01): measured turn wall-time (stream end − turn start) */
  durationMs?: number
  /** F-01: detector artifacts (code blocks ≥ threshold) — inline below the content */
  artifacts?: ArtifactInfo[]
  /** G1: the live ask of this turn — `status: 'waiting'` means the run is paused on it
   *  right now, and the answer goes back into THAT run (not into a new turn). */
  ask?: AskMessageState
  streaming?: boolean
  error?: string | null
  /** Stable reason behind `error`: a server reason code or a stream error code. */
  errorCode?: string | null
  /** Transient UI phases (not persisted): reflecting / revising / quality-check running */
  streamMeta?: {
    reflecting?: boolean
    revising?: boolean
    qualityCheck?: boolean
  }
}

/** A session in the store (local, IndexedDB) */
export interface Session {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  /** Pinned session — held at the top of the list (an Ephe feature) */
  pinned?: boolean
  /** G2: renamed by hand → the auto title never overwrites it again */
  titleCustom?: boolean
  /** M2 (reference parity): archived sessions fall below the list rule */
  archived?: boolean
  /**
   * Z53: free-form labels, many per session. Stored normalised (whitespace
   * collapsed, blanks and case-insensitive duplicates dropped) — see
   * store/chat/sessionModel.ts. Absent means "no tags", never an empty array.
   */
  tags?: string[]
  /**
   * Z53: the folder this session is filed in. At most one, because containment
   * is a different statement from `tags` (many) and from `parentId` (lineage).
   * Absent means unfiled — the root of the session list.
   */
  folderId?: string
  /**
   * Z53: soft delete. Epoch ms the session went to the trash; absent means it
   * is not trashed. The messages stay, so a restore is a field write.
   */
  deletedAt?: number
  /** M2: unread marker (a dot before the title) */
  unread?: boolean
  /** Z37: fork origin (id of the session this branch was cut from) */
  parentId?: string
  /** W19: composer mode (ask | edit-auto | plan | full-access) — persisted per session */
  mode?: string
  /** Wave 3 (cost monitor): the session's accumulated measured token balance —
   *  the sum of all usage frames; the base for the USD chip in the status bar. */
  usageTotals?: SessionUsageTotals
}

/** Wave 3: measured token sums of a session (never estimated — accumulated only
 *  from provider usage frames; without a frame everything stays at 0). */
export interface SessionUsageTotals {
  in: number
  out: number
  cached: number
}

/**
 * Z53: where a session sits. One derived answer for the three storied places a
 * user thinks in — trashed outranks archived, since a trashed session is out of
 * the archive shelf too (store/chat/sessionModel.ts:sessionState).
 */
export type SessionState = 'live' | 'archived' | 'trashed'

/**
 * Z53: a named group of sessions. Flat, and a first-class record rather than a
 * value derived from the sessions that point at it — otherwise a folder the
 * user just created would not exist until something was dragged into it, and
 * "create folder" would show nothing.
 */
export interface SessionFolder {
  id: string
  name: string
  /** Epoch ms the folder was created. Absent for a record that arrived without
   *  a stamp — an unknown date stays unknown rather than reading as "now". */
  createdAt?: number
}

// ── Provider / Settings ────────────────────────────────────────────────────

export type ProviderType = 'local_ollama' | 'custom_ollama' | 'openai_compatible'

export interface ProviderSettings {
  type: ProviderType
  endpoint?: string
  /** Request payload only: the server never returns a stored key. */
  api_key?: string
  /** Response: whether the server holds a key, and its last four characters. */
  api_key_configured?: boolean
  api_key_hint?: string
  model: string
  /** Only present in the /api/model/providers response (backend descriptor). */
  offline_capable?: boolean
}

/** Wave 5: generation block — the fine-grained parameters of the model. */
export interface GenerationBlock {
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  tool_budget?: number | null
  context_window?: number | null
  memory_max_entries?: number | null
  swarm_max_parallel?: number | null
}

export interface AppSettings {
  provider: ProviderSettings
  memory_enabled: boolean
  language: string
  /** F: workspace/project folder — the shell and file tools work inside it. */
  workspace_dir?: string | null
  /** R44 (P4): output path for document/image tools; empty = the Downloads default. */
  output_dir?: string | null
  /** M2: approval profile shown by the composer badge (strict|session|autonomous). */
  approval_profile?: string
  /** Wave 5: deep generation parameters (the finely adjustable dials). */
  generation?: GenerationBlock | null
  /** I3-3/I3-9: the bound and the explanation of every dial
   *  (core/engine_config.py::GENERATION_BOUNDS + core/settings_hints.py) — the
   *  client shows both and clamps before sending, instead of making the user
   *  type both. max = null means 'no upper bound'. */
  generation_meta?: Record<
    string,
    { default: number | null; min: number; max: number | null; hint?: string; hintEn?: string }
  >
  /** Wave 6: the deep section register (from core.settings_schema). */
  deep?: DeepSection[] | null
}

/** I3: one field entry of the deep settings register. */
export interface DeepField {
  key: string
  type: 'bool' | 'number' | 'select' | 'text'
  label: string
  labelEn: string
  /** A locale key that carries the label in both languages; product copy stays
   *  in app/src/locales, never in the Python register. */
  labelKey?: string
  hintKey?: string
  default: string | number | boolean | null
  value: string | number | boolean | null
  min?: number
  max?: number
  /** I3-3: step size of the number input, derived from the register. */
  step?: number
  /** I3: explains what the value changes. Only present on fields that have a
   *  reader (core/settings_hints.py) — text nobody reads is decoration. */
  hint?: string
  hintEn?: string
  options?: string[]
  /** Wave 2 (B1): the cap a text field is edited under, and whether it renders as a
   *  full-width editor rather than the one-line control of the register. */
  maxChars?: number
  multiline?: boolean
  /** I6-3: display text per option in both languages. The value stays the
   *  identifier (validation, persistence); the text comes from the register, so
   *  the German interface shows no English word — and the reverse holds too. */
  optionLabels?: { value: string; label: string; labelEn: string }[]
}

/** Wave 6: one section of the deep settings register. */
export interface DeepSection {
  key: string
  fields: DeepField[]
}

// ── SSE Stream Events (POST /api/chat/stream) ───────────────────────────────
//
// Discriminated union on `type` — the single source of truth for the frontend
// SSE client (lib/stream.ts). Payload shapes are anchored in
// server/routes/chat.py (the emit call) — move them together with a backend change.
// Unknown `type` values are treated as a no-op by the reducer (forward
// compatible: the backend may introduce new events without breaking the PWA).

export interface StreamThinkingStart {
  type: 'thinking_start'
}

/** AI-client parity: one reasoning token/segment coming from the model */
export interface StreamThinkingChunk {
  type: 'thinking_chunk'
  data: string
}

export interface StreamChunk {
  type: 'chunk'
  data: string
}

export interface StreamActivity {
  type: 'activity'
  cmd: string
  status: string
}

export interface StreamToolStart {
  type: 'tool_start'
  tool: string
  args: Record<string, unknown>
}

export interface StreamToolDone {
  type: 'tool_done'
  tool: string
  result: string
  /** K3 Z08: duration in seconds (1 decimal), measured on the backend */
  duration_ms?: number
  /** Wave 16: present only when the tool refused with a known reason */
  reason_code?: string
  reason_params?: Record<string, string | number>
  /**
   * w10-12: the call's outcome in the vocabulary the activity lines already use.
   * `failed` = the call did not run (a refusal carrying a reason code); the stream
   * maps it onto the store's `denied`. Absent on frames from an older backend.
   */
  status?: 'completed' | 'failed'
  /** E1: sha256 of `result` as sent (computed after the size cap). */
  sha256?: string
}

/** K3 Z07: stdout chunk as an optional frame on the activity channel */
export interface StreamStdout {
  type: 'stdout'
  tool: string
  data: string
}

export interface StreamPhase {
  type: 'phase'
  name: string
  status: string
}

export interface StreamQualityCheck {
  type: 'quality_check'
  status: string
  skill?: string
}

export interface StreamArtifactCheck {
  type: 'artifact_check'
  artifact_type: string
  status: string
  path?: string
  warnings: string[]
}

export interface StreamReflect {
  type: 'reflect'
  status: string
  needs_revision?: boolean
}

export interface StreamRevision {
  type: 'revision'
  reason: string
}

export interface StreamReplaceText {
  type: 'replace_text'
  text: string
}

export interface StreamArtifact {
  type: 'artifact'
  artifact: Record<string, unknown>
}

/** #92: the turn's plan — the steps and their state, one frame per change. */
export interface StreamPlan {
  type: 'plan'
  state: string
  done: number
  total: number
  steps: { title: string; status: string }[]
}

/** Wave 7 — knowledge-gap loop: one per gap recognised after the research. */
export interface StreamGap {
  type: 'gap'
  topic: string
  status: string
  sources: string[]
}

export interface StreamSkillCreated {
  type: 'skill_created'
  skill: { name: string; trigger: string; description: string }
}

export interface StreamSwarmAgentRef {
  agent_id: string
  role: string
  model: string
  task_spec_hash: string
}

export interface StreamSwarmCreated {
  type: 'swarm_created'
  swarm_id: string
  agents: StreamSwarmAgentRef[]
  model: string
}

export interface StreamSwarmAgentStarted {
  type: 'swarm_agent_started'
  swarm_id: string
  agent_id: string
  role?: string
  model?: string
  task_spec_hash?: string
  subtask: string
}

export interface StreamSwarmAgentDone {
  type: 'swarm_agent_done'
  swarm_id: string
  agent_id: string
  status?: string
  summary: string
  /** What the engine reported for this agent; 0/absent = it reported nothing. */
  tokens_in?: number
  tokens_out?: number
}

export interface StreamSwarmDone {
  type: 'swarm_done'
  swarm_id: string
  agent_count: number
  final: string
}

/** R36-S: spawn_agent delegation — live events of a helper subagent.
 *
 * Visibility wave: `chat_session_id` is the helper's own chat session and
 * `parent_session` the task it was started from (the way back). Both fields are
 * optional — an older server does not send them, and then the mother task keeps
 * showing just the activity line. `report` carries the helper chat the full
 * report length, `summary` stays the short form shown on the activity. */
export interface StreamSubagentStarted {
  type: 'subagent_started'
  agent_id: string
  role: string
  task: string
  model: string
  description?: string
  chat_session_id?: string
  parent_session?: string
}

export interface StreamSubagentTool {
  type: 'subagent_tool'
  agent_id: string
  tool: string
  args_preview: string
  chat_session_id?: string
  /** N24: the gate's own record for this call (exempt/approved/denied). */
  gate?: string
}

/** core/steering.py: a direction change reached (or missed) the run. */
export interface StreamSteer {
  type: 'steer'
  status: string
  actor: string
  msg: string
  text: string
  turn_id?: string
  round?: number | null
  agent_id?: string
  stop?: boolean
}

export interface StreamSubagentDone {
  type: 'subagent_done'
  agent_id: string
  status: 'ok' | 'timeout' | 'error' | 'step_limit'
  summary: string
  report?: string
  chat_session_id?: string
  parent_session?: string
}

export interface StreamVisionLearning {
  type: 'vision_learning'
  target: string
}

export interface StreamVisionLearnedSuccess {
  type: 'vision_learned_success'
  target: string
}

export interface StreamSandboxConfirm {
  type: 'sandbox_confirm'
  token: string
  tool: string
  args: Record<string, unknown>
  rememberable?: boolean
  /** Wave B1: the real unified-diff preview for edit_file/write_file (optional, additive). */
  diff?: string
}

/**
 * G1: the live question of a RUNNING turn (server: `core/tools/ask_gate.ask_user`
 * through `server/routes/chat.py::_ask_confirm`).
 *
 * `token` names the wait this frame belongs to. The turn is paused on it right now,
 * and `POST /api/ask/answer` with the same token wakes that same turn — the answer
 * arrives there as the tool result, so the run continues with it in context. A token
 * that is unknown or already finished answers 404 (timeout, stop button).
 */
export interface StreamAskUser {
  type: 'ask_user'
  token: string
  question: string
  /** Offered labels (empty = free text). */
  options: string[]
  recommendation?: string
  /** What the run continues on when nobody answers — stated with the question. */
  default?: string
  multiSelect?: boolean
  timeout_s?: number
}

/** G1: the wait ended unanswered — the same run continues on `default` (frame `ask_timeout`). */
export interface StreamAskTimeout {
  type: 'ask_timeout'
  token: string
  timeout_s?: number
  default?: string
}

/**
 * G1: the live ask as the transcript holds it. `status: 'waiting'` means the run is
 * paused on this message at this moment; `"answered"` carries the text that went back
 * into it, `"timeout"` means it continued on `defaultAnswer`, and `"expired"` means the
 * answer could not be delivered because the run had already gone on (the server answered
 * 404 — the wait timed out, or the stop button cancelled it).
 */
export interface AskMessageState {
  token: string
  question: string
  options: Array<{ label: string; description?: string }>
  recommendation?: string
  multiSelect?: boolean
  /** Seconds the run waits for an answer before it continues on `defaultAnswer`. */
  timeoutS?: number
  /** The value the run continues on when nobody answers. */
  defaultAnswer?: string
  status: 'waiting' | 'answered' | 'timeout' | 'expired'
  /** The answer that went back into the run (status 'answered'). */
  answer?: string
}

export interface StreamSwarmStatus {
  type: 'swarm_status'
  phase: string
  message: string
  swarm_id?: string
}

export interface TurnProgress {
  tool: string
  round: number
  roundCap: number
  phase: string
  elapsedMs: number
  query?: string
  providers?: string
  status?: string
}

export interface StreamProgress {
  type: 'progress'
  turn_id?: string
  round: number
  round_cap: number
  tool: string
  phase: string
  elapsed_ms: number
  query?: string
  providers?: string
  status?: string
}

export interface StreamTurn {
  type: 'turn'
  turn_id: string
  session_id?: string
}

/** QD-015 Z2: the turn stopped on the tool budget. `action` is the offer the
 *  surface renders as a button; `extra` is the number of rounds it adds. */
export interface StreamBudget {
  type: 'budget'
  action: 'continue_turn'
  cap: number
  extra: number
}

export interface StreamFileResult {
  type: 'file_result'
  file_type: string
  path: string
  label?: string
  /** A0: id of the registered artifact ('' when registration was missing). */
  id?: string
}

export interface StreamModelInfo {
  type: 'model_info'
  tier: string
  model: string
  provider?: string
  offline_capable?: boolean
  requires_internet?: boolean
}

export interface StreamError {
  type: 'error'
  msg: string
  /** The refusal's own name, when the server sent one — stable across languages, so the
   * reader can look the sentence up in the bundle instead of displaying the fallback. */
  reason_code?: string
  reason_params?: Record<string, string | number>
}

export interface StreamDone {
  type: 'done'
}

/** N7/N8a: the real per-turn provider counts (SSOT core.usage); usage_estimated
 *  is true when only the calibrated heuristic applies. */
export interface StreamUsage {
  type: 'usage'
  usage: {
    model?: string
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    usage_estimated?: boolean
    /** Wave 3: measured prompt-cache hit (OpenAI prompt_tokens_details) */
    prompt_tokens_details?: { cached_tokens?: number }
  }
}

export type StreamEvent =
  | StreamTurn
  | StreamProgress
  | StreamThinkingStart
  | StreamThinkingChunk
  | StreamChunk
  | StreamActivity
  | StreamStdout
  | StreamToolStart
  | StreamToolDone
  | StreamPhase
  | StreamQualityCheck
  | StreamArtifactCheck
  | StreamReflect
  | StreamRevision
  | StreamReplaceText
  | StreamArtifact
  | StreamPlan
  | StreamGoalStart
  | StreamGoalTurn
  | StreamGoalCheck
  | StreamBudget
  | StreamGap
  | StreamSkillCreated
  | StreamSwarmCreated
  | StreamSwarmAgentStarted
  | StreamSwarmAgentDone
  | StreamSubagentStarted
  | StreamSubagentTool
  | StreamSteer
  | StreamSubagentDone
  | StreamSwarmDone
  | StreamVisionLearning
  | StreamVisionLearnedSuccess
  | StreamSandboxConfirm
  | StreamAskUser
  | StreamAskTimeout
  | StreamSwarmStatus
  | StreamFileResult
  | StreamModelInfo
  | StreamUsage
  | StreamError
  | StreamDone

/** Request payload of POST /api/chat/stream (server model: StreamRequest) */
export interface StreamChatRequest {
  message: string
  model?: string
  history: Array<{ role: string; content: string }>
  session_id?: string
  autonomous?: boolean
  skill?: string | null
  images?: string[]
  /** W19: UI mode — backend skips the fast path + sets the anti-hallucination guard on 'ask' */
  mode?: string
  /** QD-015 Z2: per-turn tool rounds. The budget card sends the cap it read
   *  plus the rounds the button adds; unset keeps the class default. */
  tool_budget?: number
}

/** Response of POST /api/sandbox/approve (a token that is known) */
export interface SandboxApproveResponse {
  status: 'ok'
}

/** Response of POST /api/ask/answer (a token the run is currently waiting on).
 *  404 = unknown/finished token, 422 = an empty answer (an unanswered run reaches
 *  its timeout instead). */
export interface AskAnswerResponse {
  status: 'ok'
}

// ── IndexedDB ──────────────────────────────────────────────────────────────

export interface DbSession {
  id: string
  title: string
  messages: unknown[]
  createdAt: number
  updatedAt: number
  /** Pinned session — stays fixed at the top */
  pinned?: boolean
  /** G2: renamed by hand → the auto title never overwrites it again */
  titleCustom?: boolean
  /** M2: archived/unread (reference parity) */
  archived?: boolean
  /** Z53: labels (many per session) — normalised on read, see migrateDbSession */
  tags?: string[]
  /** Z53: containment (at most one folder per session) */
  folderId?: string
  /** Z53: soft delete — epoch ms, absent means not trashed */
  deletedAt?: number
  unread?: boolean
  /** Z37: fork origin (id of the session this branch was cut from) */
  parentId?: string
  /** W19: composer mode — persisted per session (browser cache AND server mirror) */
  mode?: string
  /** Wave 3: cumulative measured token balance (cost monitor) */
  usageTotals?: { in: number; out: number; cached: number }
}
