/**
 * QD-005 — the companion's co-pilot brain.
 *
 * The classifier between the five Ephe surface targets and the three companion
 * modes (`perch`, `scout`, `copilot`). Everything here is deterministic and
 * local: no engine request, no network, no token. The security boundary is the
 * shell-command allowlist — a command that chains, writes, reaches the network
 * or leaves the workspace never earns `auto_act`, so the co-pilot can only ever
 * click what a careful user would have clicked next anyway.
 *
 * The countdown exists because an automatic act has to be visible before it
 * happens: 2500 ms on screen, canceled by Escape or the Cancel button.
 */
export const COUNTDOWN_MS = 2500
/** QD-013: the countdown is a setting now; this is only its default. */
export const DEFAULT_COUNTDOWN_SECONDS = 2.5

/** Seconds as the schema allows them (0-10), rounded to whole milliseconds. */
export function countdownMs(seconds: number | null | undefined): number {
  const value = typeof seconds === 'number' && Number.isFinite(seconds)
    ? Math.min(10, Math.max(0, seconds))
    : DEFAULT_COUNTDOWN_SECONDS
  return Math.round(value * 1000)
}
export const RECEIPT_CAP = 10

export type CopilotMode = 'perch' | 'scout' | 'copilot'
export type CopilotVerdict = 'auto_act' | 'warn_only' | 'focus'
export type CopilotTargetId =
  | 'tool_approval'
  | 'ask_user'
  | 'context_compact'
  | 'open_review_or_preview'
  | 'error_or_setup_repair'
  | 'codebase_index'

export interface CopilotFinding {
  target: CopilotTargetId
  verdict: CopilotVerdict
  /** Locale keys — the German surface renders German, whatever the engine said. */
  actionKey: string
  actionParam?: string
  reasonKey: string
  reasonParam?: string
  /** The stable element the scout highlights; null when the companion itself is the pointer. */
  selector: string | null
}

export interface CopilotReceipt {
  at: number
  target: CopilotTargetId
  verdict: 'auto_act' | 'warn_only' | 'focus'
  actionKey: string
  actionParam?: string
  reasonKey: string
}

export interface CopilotSnapshot {
  waitingTool: { name: string; args?: Record<string, unknown>; description?: string } | null
  ask: { recommendation?: string; options: string[]; token?: string } | null
  runState: 'ready' | 'working' | 'waiting' | 'done'
  contextPercent: number | null
  hasCompact: boolean
  compactedThisSession: boolean
  turnJustFinished: boolean
  newArtifacts: number
  newEdits: number
  toolError: boolean
  repairVisible: boolean
  /** The workspace has no codebase index yet, so pointing at it is the next step. */
  codebaseIdle?: boolean
  /** Verbs the user taught it through "Remember this command shape". */
  remembered?: readonly string[]
}

/** The exact command prefixes a co-pilot may approve without being taught.
 * The CI verbs came first; the read-only inspection verbs are what an agent
 * actually runs in a user's folder, so they moved in under the same fence. */
const SAFE_PREFIXES = [
  'pytest',
  'python -m pytest',
  'python3 -m pytest',
  'npm test',
  'npm run lint',
  'npm run build',
  'npx vitest',
  'cargo check',
  'cargo test',
  'cargo clippy',
  'git status',
  'git diff',
  'git log',
  'ruff check',
  'ls',
  'cat',
  'head',
  'tail',
  'wc',
  'stat',
  'du',
  'pwd',
  'which',
  'file',
  'rg',
  'grep',
  'find',
]

/**
 * Fail-closed patterns. Destructive verbs, state-changing git verbs, network
 * tools, chaining and redirection operators, command substitution, absolute or
 * home paths, credential-shaped paths, the flags that turn a read-only program
 * into a writer, and multi-line input.
 *
 * The path and flag rows exist because the allowlist is a prefix test: `pytest`
 * is safe, and `pytest --rootdir /` is the same prefix asking for something
 * else. A prefix that still matches after any of these fire is refused.
 */
const FORBIDDEN =
  /(?:^|\s)(?:rm|mv|dd|chmod|chown|sudo|su|kill|pkill)(?:\s|$)|git\s+(?:push|reset|clean)|git\s+checkout\s+--|\b(?:curl|wget|ssh|scp)\b|[;&|><`]|\$\(|\$\{|\.\.|~\/\.ephe|\.ephe\/|\.env|\n|(?:^|\s)[/~]|(?:^|\s)-[co]\b|(?:^|\s)--(?:output|config|override-ini|rootdir|git-dir|work-tree|in-place)\b|\bsed\s+-[a-z]*i\b|(?:^|\s)-(?:delete|exec|execdir|ok|okdir|fprint|fls)\b/i

/** The one tool whose args are a shell command line. */
const SHELL_TOOL = 'run_shell'

export function shellCommandOf(tool: { name: string; args?: Record<string, unknown> }): string {
  const args = tool.args ?? {}
  if (typeof args.command === 'string') return args.command
  if (typeof args.cmd === 'string') return args.cmd
  return ''
}

function normalize(command: string): string {
  return command.trim().replace(/[ \t]+/g, ' ')
}

/** True when the command carries any fail-closed marker. Nothing overrides this. */
export function isShellForbidden(command: string): boolean {
  return FORBIDDEN.test(normalize(command))
}

/** The leading word of a command line, when it is a plain program name. */
export function shellVerb(command: string): string | null {
  const verb = normalize(command).split(' ')[0] ?? ''
  return /^[a-z][a-z0-9._-]*$/i.test(verb) ? verb : null
}

export function classifyShellCommand(
  command: string,
  remembered: readonly string[] = [],
): 'auto_act' | 'warn_only' {
  const normalized = normalize(command)
  if (!normalized) return 'warn_only'
  if (FORBIDDEN.test(normalized)) return 'warn_only'
  const allowed = [...SAFE_PREFIXES, ...remembered].some(
    (prefix) => normalized === prefix || normalized.startsWith(`${prefix} `),
  )
  return allowed ? 'auto_act' : 'warn_only'
}

export function classifyAsk(
  recommendation: string | undefined,
  options: string[],
): 'auto_act' | 'warn_only' {
  if (!recommendation) return 'warn_only'
  if (options.length === 0) return 'warn_only'
  return options.includes(recommendation) ? 'auto_act' : 'warn_only'
}

export function shouldCompact(state: {
  runState: string
  contextPercent: number | null
  hasCompact: boolean
  compactedThisSession: boolean
}): boolean {
  return (
    (state.runState === 'done' || state.runState === 'ready') &&
    state.contextPercent != null &&
    state.contextPercent >= 90 &&
    state.hasCompact &&
    !state.compactedThisSession
  )
}

export function shouldOpenReview(state: {
  turnJustFinished: boolean
  newArtifacts: number
  newEdits: number
}): boolean {
  return state.turnJustFinished && (state.newArtifacts > 0 || state.newEdits > 0)
}

/**
 * The one crawl: which target the surface shows next, judged through the mode.
 * Priority matches what a careful user would attend to first: a waiting
 * approval outranks an open question, which outranks a full context.
 */
export function findCopilotTarget(
  snapshot: CopilotSnapshot,
  mode: CopilotMode,
): CopilotFinding | null {
  if (mode === 'perch') return null

  if (snapshot.waitingTool) {
    const shellTool = snapshot.waitingTool.name === SHELL_TOOL
    // The allowlist describes a shell command line, so only the shell tool can
    // earn its benefit of the doubt. A tool that carries a `command` arg under
    // another name is a tool the co-pilot does not act on — and its argument is
    // not a shell command either, so it must not reach `reasonParam`, where the
    // panel would offer to remember a verb the classifier never judged.
    const command = shellTool ? shellCommandOf(snapshot.waitingTool) : ''
    const safe = shellTool && classifyShellCommand(command, snapshot.remembered ?? []) === 'auto_act'
    const selector = '[role="alertdialog"]'
    const reasonKey = command
      ? safe
        ? 'copilot.reason.safeCheck'
        : 'copilot.reason.needsReview'
      : 'copilot.reason.commandUnreadable'
    if (mode === 'scout') {
      return {
        target: 'tool_approval',
        verdict: 'focus',
        actionKey: safe ? 'copilot.action.approveYourself' : 'copilot.action.reviewRisk',
        reasonKey,
        reasonParam: command || undefined,
        selector,
      }
    }
    if (safe && command) {
      return {
        target: 'tool_approval',
        verdict: 'auto_act',
        actionKey: 'copilot.action.approve',
        actionParam: command,
        reasonKey: 'copilot.reason.safeCheck',
        selector,
      }
    }
    return {
      target: 'tool_approval',
      verdict: 'warn_only',
      actionKey: 'copilot.action.noApprove',
      reasonKey,
      reasonParam: command || undefined,
      selector,
    }
  }

  if (snapshot.ask) {
    const recommendation = snapshot.ask.recommendation
    const safe = classifyAsk(recommendation, snapshot.ask.options) === 'auto_act'
    const selector = '[data-testid="ask-card"]'
    if (mode === 'scout') {
      return {
        target: 'ask_user',
        verdict: 'focus',
        actionKey: safe ? 'copilot.action.questionSuggests' : 'copilot.action.questionWaits',
        actionParam: safe ? recommendation : undefined,
        reasonKey: 'copilot.reason.safeQuestion',
        selector,
      }
    }
    if (safe) {
      return {
        target: 'ask_user',
        verdict: 'auto_act',
        actionKey: 'copilot.action.answer',
        actionParam: recommendation,
        reasonKey: 'copilot.reason.recommendation',
        selector,
      }
    }
    return {
      target: 'ask_user',
      verdict: 'warn_only',
      actionKey: 'copilot.action.noAnswer',
      reasonKey: 'copilot.reason.noRecommendation',
      selector,
    }
  }

  if (shouldCompact(snapshot)) {
    const reasonParam = String(Math.round(snapshot.contextPercent ?? 0))
    if (mode === 'scout') {
      return {
        target: 'context_compact',
        verdict: 'focus',
        actionKey: 'copilot.action.contextLimit',
        reasonKey: 'copilot.reason.contextAfterTurn',
        reasonParam,
        selector: '[data-testid="status-bar"]',
      }
    }
    return {
      target: 'context_compact',
      verdict: 'auto_act',
      actionKey: 'copilot.action.compact',
      reasonKey: 'copilot.reason.contextAfterTurn',
      reasonParam,
      selector: '[data-testid="status-bar"]',
    }
  }

  if (shouldOpenReview(snapshot)) {
    return {
      target: 'open_review_or_preview',
      verdict: mode === 'scout' ? 'focus' : 'auto_act',
      actionKey: 'copilot.action.openReview',
      reasonKey: 'copilot.reason.newFiles',
      selector: null,
    }
  }

  if (snapshot.toolError || snapshot.repairVisible) {
    return {
      target: 'error_or_setup_repair',
      verdict: 'focus',
      actionKey: 'copilot.action.focusRepair',
      reasonKey: snapshot.repairVisible ? 'copilot.reason.repair' : 'copilot.reason.toolFailed',
      selector: snapshot.repairVisible
        ? '[data-testid="setup-repair"]'
        : '[data-testid="tool-call-error"], [data-testid="tool-card"]',
    }
  }

  // Lowest priority of all: it is a suggestion, never a repair.
  if (snapshot.codebaseIdle) {
    return {
      target: 'codebase_index',
      verdict: mode === 'scout' ? 'focus' : 'auto_act',
      actionKey: 'copilot.action.indexCodebase',
      reasonKey: 'copilot.reason.codebaseIdle',
      selector: '[data-testid="codebase-pill"]',
    }
  }

  return null
}

/** Newest first, capped — the trail the popover shows. */
export function pushReceipt(
  list: CopilotReceipt[],
  entry: Omit<CopilotReceipt, 'at'> & { at?: number },
): CopilotReceipt[] {
  return [{ ...entry, at: entry.at ?? Date.now() }, ...list].slice(0, RECEIPT_CAP)
}

/** A 2.5 s one-shot timer the surface renders and the user can cancel. */
export class CopilotCountdown {
  private timer: ReturnType<typeof setTimeout> | null = null

  constructor(private readonly ms: number) {}

  start(onComplete: () => void): void {
    this.cancel()
    this.timer = setTimeout(() => {
      this.timer = null
      onComplete()
    }, this.ms)
  }

  cancel(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
  }
}

/** Esc aborts the running countdown; returns the listener release. */
export function bindEscapeCancel(cancel: () => void): () => void {
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') cancel()
  }
  window.addEventListener('keydown', onKeyDown)
  return () => window.removeEventListener('keydown', onKeyDown)
}
