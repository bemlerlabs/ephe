import type {
  Activity,
  ArtifactInfo,
  ChatMessage,
  PendingToolCall,
  PlanCardSpec,
  Session,
  SessionFolder,
  SessionState,
  ToolCall,
} from '@/types'
import type { HelperChat } from '@/lib/helperSession'
import type { CompactStats } from '@/lib/compact'
import type { ChatCheckpoint } from '@/lib/checkpoints'

export type {
  ToolCall,
  PendingToolCall,
  ChatMessage,
  Session,
  SessionFolder,
  SessionState,
  Activity,
  ArtifactInfo,
  CompactStats,
}

/** Minimal model of a persisted tool_calls entry (the index signature). */
export interface ToolCallModel {
  id: string
  name: string
  description?: string
  status: 'pending' | 'approved' | 'denied' | 'completed' | 'waiting'
  args?: Record<string, unknown>
  result?: string
  duration_ms?: number
  stdout?: string
}

/** Visibility wave: the three live events of one helper, in store form.
 *  The mapping (lib/streamActions.ts) keeps SSE vocabulary off the field names. */
export interface HelperStartInput {
  chatSessionId: string
  agentId: string
  parentSession?: string
  role?: string
  description?: string
  task: string
}

export interface HelperStepInput {
  chatSessionId: string
  agentId: string
  tool: string
  argsPreview: string
}

export interface HelperEndInput {
  chatSessionId: string
  agentId: string
  status: string
  report?: string
  summary?: string
  parentSession?: string
}

/** Chat store state + action contract (1:1 from the original chatStore.ts, lines 121–204). */
export interface ChatState {
  sessions: Session[]
  activeSessionId: string | null
  isTyping: boolean
  pendingToolCall: PendingToolCall | null
  currentSession: Session | null
  /** P1-10: false until initFromDb() settles — drives the boot skeleton so the
   *  welcome/empty state never flashes while persisted sessions hydrate. */
  hydrated: boolean
  checkpoints: Record<string, ChatCheckpoint[]>
  setSessions: (sessions: Session[]) => void
  setActiveSession: (id: string) => void
  /** W19: set the composer mode for one session (persisted in IndexedDB + server mirror). */
  setSessionMode: (id: string, mode: string) => void
  createSession: (title?: string) => void
  deleteSession: (id: string) => void
  /** Rename a session (persisted). */
  renameSession: (id: string, title: string) => void
  /** R26: pin/unpin a session (persisted) — pinned sessions sort to the top. */
  togglePin: (id: string) => void
  /** M2 (reference parity): archive — hidden from the list, the data stays. */
  toggleArchive: (id: string) => void
  /** M2: unread dot in front of the title (set once, the click opens it + marks it read). */
  markUnread: (id: string) => void
  /** Compact the active session (lib/compact.ts) + indicator message + persist. */
  compactSession: () => { changed: boolean; stats?: CompactStats }
  /**
   * Z37: session fork — copy the prefix up to and including the target message
   * into a new session with a parentId; the branch becomes active. Unknown id → no-op.
   */
  branchSession: (fromMsgId: string) => void
  addMessage: (
    role: 'user' | 'assistant' | 'system',
    content: string,
    toolCalls?: ToolCall[],
  ) => void
  /** Remove everything after the target message (the target stays) — Edit/Regenerate (G1) */
  truncateAfter: (messageId: string) => void
  /** Replace the content of a message by id (Edit, G1) */
  updateMessageContent: (messageId: string, content: string) => void
  /** Remove a single message by id (retry after a stream error, G1) */
  removeMessage: (messageId: string) => void
  /**
   * Visibility wave: the helper as its own session. Three events write it live,
   * `restoreHelperChat` builds it from the ledger, `openHelperChat` opens it
   * (reconstructing it for that purpose when needed).
   */
  beginHelperChat: (e: HelperStartInput) => void
  stepHelperChat: (e: HelperStepInput) => void
  endHelperChat: (e: HelperEndInput) => void
  restoreHelperChat: (chat: HelperChat) => void
  openHelperChat: (input: {
    agentId: string
    chatSessionId?: string
    parentSession?: string
  }) => Promise<boolean>
  setTyping: (typing: boolean) => void
  setPendingToolCall: (tool: PendingToolCall | null) => void
  /** Starts an assistant turn: ONE empty message (streaming=true) */
  startTurn: () => void
  /** Appends one SSE chunk to the active assistant message */
  appendChunk: (chunk: string) => void
  /** AI-client parity: append a reasoning chunk to Thinking.text (with a cap) */
  appendThinking: (chunk: string) => void
  /** Replaces the whole content of the active message (replace_text) */
  replaceText: (text: string) => void
  /** Upsert a tool call (tool_start without id / tool_done with id) */
  upsertToolCall: (tool: {
    id?: string
    name: string
    args?: Record<string, unknown>
    result?: string
    status: ToolCall['status']
    rememberable?: boolean
    /** K3 Z08: runtime of the call (seconds) — from the tool_done frame */
    durationMs?: number
    /** K3 Z07: stdout chunk; repeated calls append to it (growing tail) */
    stdout?: string
    /** Wave 16: reason code of a coded refusal (tool_done), with its params */
    reasonCode?: string
    reasonParams?: Record<string, string | number>
  }) => void
  /** Upsert an activity (in place, 1 entry per label; detail overrides) */
  /** A3: write the turn id onto the active assistant message. */
  setTurnId: (turnId: string) => void
  upsertActivity: (activity: {
    label: string
    status: Activity['status']
    detail?: string
    path?: string
    fileType?: string
    artifactId?: string
  }) => void
  /** F-01: attach the detector artifact to the current assistant message (inline render) */
  attachArtifact: (artifact: ArtifactInfo) => void
  /** #92: the plan frame of the running turn, replacing the previous state of the same plan */
  setPlan: (plan: PlanCardSpec) => void
  /** The goal run of the running turn: `goal_start` opens it (a new run replaces the
   *  previous one), `goal_turn`/`goal_check` advance it (P6 B3: the status panel's goal). */
  beginGoal: (goal: string, check: string, maxTurns: number) => void
  advanceGoal: (turn: number, ok?: boolean) => void
  /** Ask for a sandbox confirmation (from the sandbox_confirm event) */
  resolveSandbox: (
    token: string,
    tool: string,
    args: Record<string, unknown>,
    rememberable?: boolean,
    /** Wave B1: real unified diff preview (edit_file/write_file), ephemeral. */
    diff?: string,
  ) => void
  /** Mark the last waiting tool call approved */
  approveSandbox: () => void
  /** Mark the last waiting tool call denied */
  denySandbox: () => void
  /** G1: open the live ask of the running turn (frame `ask_user`). Its `token` is the
   *  handle the answer travels back through; `status: 'waiting'` on the message means
   *  the run is paused on it right now. */
  resolveAsk: (ask: {
    token: string
    question: string
    options: string[]
    recommendation?: string
    multiSelect?: boolean
    timeoutS?: number
    defaultAnswer?: string
  }) => void
  /** G1: the answer landed in the waiting run — the card closes with the text it sent. */
  markAskAnswered: (token: string, answer: string) => void
  /** G1: nobody answered in time — the run continued on the default it stated. */
  markAskTimedOut: (token: string) => void
  /** G1: the answer did not reach the run (POST /api/ask/answer answered 404) — the
   *  wait had already ended and the run went on without it. */
  markAskExpired: (token: string) => void
  /** Error event: set the error text + end the stream state */
  markStreamError: (msg: string) => void
  /** N7/N8a: the measured token balance of the last completed turn */
  lastTurnUsage: { in: number; out: number; cached?: number } | null
  /** The usage frame sets the balance (before done); starting a new turn clears it.
   *  Wave 3: ALSO accumulates the session total (usageTotals) — the basis for the
   *  USD and cache chip in the status bar. Persisted through DbSession. */
  markLastUsage: (u: { in: number; out: number; cached?: number }) => void
  /** Wave 3 (cost monitor): the price table of the active model — USD per 1M tokens
   *  from engine.json `pricing` (via /api/model/providers). null = no price kept →
   *  the status bar shows no cost chip (never guess a number). */
  enginePricing: { in_per_m?: number; out_per_m?: number } | null
  setEnginePricing: (p: { in_per_m?: number; out_per_m?: number } | null) => void
  /** Transient UI phases: reflecting / revising / qualityCheck */
  setReflecting: (on: boolean) => void
  setRevising: (on: boolean) => void
  setQualityCheck: (on: boolean) => void
  /** End the turn: streaming=false, set thinking.end */
  finishTurn: () => void
  createCheckpoint: (label?: string) => void
  rollbackToCheckpoint: (id: string) => void
  deleteCheckpoint: (id: string) => void
  /** IndexedDB hydration + server mirror (P0-3), once per app start. */
  initFromDb: () => Promise<void>
}

/** Minimal setState contract of the state factory, for the action modules. */
export type SetFn = (u: Partial<ChatState> | ((s: ChatState) => Partial<ChatState>)) => void
export type GetFn = () => ChatState

/** Shared context of the action factories (from the create initialization). */
export interface StoreCtx {
  set: SetFn
  get: GetFn
  persistActive: () => void
  setTransientMeta: (key: 'reflecting' | 'revising' | 'qualityCheck', on: boolean) => void
  markSandboxStatus: (status: ToolCall['status']) => void
}

/** Alias for the old interface name (streamActions.ts, tests). */
export type ChatStore = ChatState
