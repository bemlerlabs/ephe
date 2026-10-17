/**
 * Ephe — the shared words of the workspaces surface (W1).
 *
 * States, operations and verdicts are the domain's own (`core/workspace_lifecycle.py`,
 * `core/change_set.py`, `core/review_gate.py`); this module names them for the screen,
 * gives each one a tone on the *existing* badge variants, and turns the two raw things a
 * reader must not see — a duration in milliseconds and an `ApiError` — into a sentence.
 *
 * Nothing here invents a state. A word the backend sends that this module does not know
 * is printed unchanged, so a state added later reads as itself instead of as a key path.
 */
import { ApiError } from '@/lib/api'
import { serverErrorText } from '@/lib/serverError'

/** Badge variants of `components/ui/Badge` — the only tones a state may wear. */
export type Tone = 'default' | 'outline' | 'success' | 'warning' | 'destructive' | 'info'

const WORKSPACE_TONES: Record<string, Tone> = {
  creating: 'info',
  ready: 'success',
  dirty: 'warning',
  published: 'success',
  discarded: 'outline',
}

const CHANGE_SET_TONES: Record<string, Tone> = {
  draft: 'outline',
  review: 'info',
  approved: 'success',
  published: 'success',
  rejected: 'destructive',
}

const OP_TONES: Record<string, Tone> = {
  create: 'success',
  modify: 'info',
  delete: 'destructive',
}

export function workspaceStateTone(state: string): Tone {
  return WORKSPACE_TONES[state] ?? 'outline'
}

export function changeSetStateTone(state: string): Tone {
  return CHANGE_SET_TONES[state] ?? 'outline'
}

export function opTone(op: string): Tone {
  return OP_TONES[op] ?? 'outline'
}

/** `core.change_set_lifecycle.BACK_MOVES` — the one state a surface may set by hand. */
const WITHDRAW_LABELS: Record<string, string> = { draft: 'toDraft' }

/** The label key for reopening one set as a draft by hand, or null when it is no move. */
export function withdrawLabelKey(state: string): string | null {
  const leaf = WITHDRAW_LABELS[state]
  return leaf ? `workspaces.withdraw.${leaf}` : null
}

/** `core.change_set_lifecycle`: the states a fresh verdict can still move. `rejected` is
 * amended and `published` has shipped, so neither answers a verdict with a move. */
const VERDICT_MOVABLE = new Set(['draft', 'review', 'approved'])

export function verdictCanMove(state: string): boolean {
  return VERDICT_MOVABLE.has(state)
}

/**
 * The four states of a run (`core.fleet.RUN_STATES`), and the tone each wears.
 *
 * The tones are the load-bearing part: a run that waits on a person and a run that is stuck
 * must not read as a run that is working. `waiting_on_human` wears the warning tone and
 * `blocked` the destructive one — different from each other and from `running`, which wears
 * the neutral outline. The word still travels beside the tone, so colour is never the only
 * reading.
 */
const RUN_STATE_TONES: Record<string, Tone> = {
  running: 'outline',
  waiting_on_human: 'warning',
  blocked: 'destructive',
  done: 'success',
}

/** The label of each run state. Written as literals so the i18n gate checks every one. */
const RUN_STATE_LABELS: Record<string, (t: (key: string) => string) => string> = {
  running: (t) => t('workspaces.runState.running'),
  waiting_on_human: (t) => t('workspaces.runState.waitingOnHuman'),
  blocked: (t) => t('workspaces.runState.blocked'),
  done: (t) => t('workspaces.runState.done'),
}

export function runStateTone(state: string): Tone {
  return RUN_STATE_TONES[state] ?? 'outline'
}

/** An unknown state is its own label, the way `vocabLabel` treats an unknown register state. */
export function runStateLabel(state: string, t: (key: string) => string): string {
  return RUN_STATE_LABELS[state]?.(t) ?? state
}

/** The run state a row shows: what the run is doing, falling back to the register's own word
 * for a server that does not send the fleet fields yet. */
export function runStateOf(workspace: { state: string; run_state?: string | null }): string {
  return workspace.run_state || workspace.state
}

/**
 * The label of one of the three closed vocabularies. An unknown value is its own label:
 * a reader who meets a state the product does not know should read that state, not
 * `workspaces.state.<something>`.
 */
export function vocabLabel(
  kind: 'state' | 'op' | 'changeSetState' | 'verdict',
  value: string,
  t: (key: string) => string,
): string {
  const known =
    kind === 'state'
      ? value in WORKSPACE_TONES
      : kind === 'op'
        ? value in OP_TONES
        : kind === 'changeSetState'
          ? value in CHANGE_SET_TONES
          : value === 'approve' || value === 'request_changes' || value === 'reject'
  return known ? t(`workspaces.${kind}.${value}`) : value
}

export type AgeUnit = 'now' | 'minutes' | 'hours' | 'days'

/**
 * How long a workspace has existed, in the largest unit that still reads as a number.
 *
 * The register writes microseconds and a `+00:00` offset (`core/change_set._now_iso`);
 * the fractional part is cut to the three digits every engine parses, so a valid stamp
 * never becomes `NaN` on one browser and a date on another.
 */
export function ageOf(iso: string, now: number = Date.now()): { unit: AgeUnit; n: number } | null {
  if (!iso) return null
  const parsed = Date.parse(iso.replace(/(\.\d{3})\d+/, '$1'))
  if (Number.isNaN(parsed)) return null
  const minutes = Math.floor(Math.max(0, now - parsed) / 60_000)
  if (minutes < 1) return { unit: 'now', n: 0 }
  if (minutes < 60) return { unit: 'minutes', n: minutes }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return { unit: 'hours', n: hours }
  return { unit: 'days', n: Math.floor(hours / 24) }
}

/**
 * The age of a stamp as one string, for the sentences assembled in code rather than in JSX.
 *
 * A holder inside a translation slot cannot carry a component, so `AgeText` cannot reach it;
 * this is the same reading with the same units, from the same `ageOf`.
 */
export function ageLabel(
  iso: string,
  t: (key: string, options?: Record<string, unknown>) => string,
  now: number = Date.now(),
): string {
  const age = ageOf(iso, now)
  if (!age) return ''
  return age.unit === 'now' ? t('workspaces.ageNow') : t(`workspaces.age.${age.unit}`, { n: age.n })
}

/** `sha256:9f2c…` as the short form a reviewer can compare by eye. */
export function diffPrefix(sha: string, keep = 8): string {
  const cut = sha.indexOf(':')
  if (cut < 0) return sha.slice(0, keep)
  const hex = sha.slice(cut + 1)
  return hex.length > keep ? `${sha.slice(0, cut + 1)}${hex.slice(0, keep)}` : sha
}

/** A bundle entry that still carries an unfilled `{{slot}}` is not yet a sentence. */
const UNFILLED_SLOT = /\{\{\s*\w+\s*\}\}/

/**
 * A refused action as a sentence.
 *
 * `server/refusals.py` sends a stable code beside the transport status so the reader's own
 * language wins; an unknown code (or a route that refused without one) leaves the server's
 * own sentence, which is still a sentence. The status number never reaches the reader —
 * "422" is a fact about the transport, not an answer about their change set.
 *
 * A code whose bundle entry carries slots this call cannot fill — `review_refused` renders
 * `{{reason}}`, and the params ride in a field `ApiError` does not keep — would otherwise put
 * a template in front of the reader. The server's own sentence is filled in by construction,
 * so it wins there.
 *
 * A thrown value that carries no readable text at all answers `''` rather than
 * `[object Object]`: the callers have a sentence of their own for that case, and a
 * placeholder is the one thing a refusal must never become.
 */
export function refusalSentence(error: unknown): string {
  if (error instanceof ApiError) {
    const translated = serverErrorText(error.reasonCode, undefined, '')
    if (translated && !UNFILLED_SLOT.test(translated)) return translated
    return error.message
  }
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>
    for (const key of ['reason', 'detail', 'message']) {
      const value = record[key]
      if (typeof value === 'string' && value.trim()) return value
    }
  }
  return ''
}
