/**
 * Ephe — API client for the workspaces surface (W1).
 *
 * One agent run gets its own checkout (`core/workspace_lifecycle.py`) and what it
 * changed is a change set (`core/change_set.py`) that a reviewer decides on
 * (`core/review_gate.py`). This module is the reading and the review half: list the
 * live workspaces, read one workspace's change sets, file a verdict, publish what a
 * verdict cleared.
 *
 * The words here are the domain's own — `STATES` from both core modules and
 * `VERDICTS` from the review gate — so a surface never invents a second vocabulary
 * and a sentence it writes still means what the backend meant.
 */
import { request } from './http'

/** `core/workspace_lifecycle.STATES`: a checkout is created, becomes ready, may go
 * dirty or published, and a failed create is discarded. */
export type WorkspaceState = 'creating' | 'ready' | 'dirty' | 'published' | 'discarded'

/** `core.fleet.RUN_STATES` — what a run is *doing*, which is not what its tree is.

 * The register says what a checkout looks like; this says whether the run behind it is
 * working, stopped on a person, stuck, or finished. A run that waits on a human is its own
 * word on purpose: it is alive, so every status in every registry calls it "running". */
export type RunState = 'running' | 'waiting_on_human' | 'blocked' | 'done'

/** Where a run came from: a checkout in the register, a helper run, or a wait of its own. */
export type RunKind = 'workspace' | 'agent' | 'session'

/** The last thing a run touched. A file of its newest change set (`kind: 'file'`), its last
 * tool call (`'tool'`), the approval it stopped on (`'awaiting'`), or nothing yet. */
export interface RunEvent {
  kind: 'file' | 'tool' | 'awaiting' | 'none'
  text: string
  op: string
  age_seconds: number | null
}

/** One run on the fleet board (`core/fleet.py`). */
export interface FleetRun {
  run_id: string
  kind: RunKind
  agent: string
  task: string
  /** The register id of the checkout this run owns, or `''` when it owns none. */
  workspace_id: string
  path: string
  state: RunState
  needs_you: boolean
  running_for_seconds: number | null
  last_event: RunEvent
}

/** `core/change_set.STATES`: built as a draft, sent back for review, approved on a verdict,
 * then published; a reject leaves it rejected, which is a branch rather than a station. */
export type ChangeSetState = 'draft' | 'review' | 'approved' | 'published' | 'rejected'

/** `core/change_set.OPS` — the three operations git's status letters fold onto. */
export type FileOp = 'create' | 'modify' | 'delete'

/** `core/review_gate.VERDICTS`. */
export type Verdict = 'approve' | 'request_changes' | 'reject'

export interface Workspace {
  id: string
  path: string
  branch: string
  state: string
  owner: string
  created_at: string
  /** The run fields the fleet read adds beside the register's own (`core.fleet`). They are
   * optional so a surface built against the six-field register still reads a register. */
  run_state?: string
  needs_you?: boolean
  owner_alive?: boolean | null
  running_for_seconds?: number | null
  last_event?: RunEvent
}

export interface FileChange {
  path: string
  op: string
  diff_sha: string
}

/** `core/change_set.PROVENANCE_FIELDS`: who asked for this, and why. `why` is the
 * field a session cannot drop — without it a change set is only an undescribed diff. */
export interface ChangeSetProvenance {
  session_id: string
  agent_id: string
  why: string
}

export interface ChangeSet {
  id: string
  workspace_id: string
  summary: string
  files: FileChange[]
  provenance: ChangeSetProvenance
  state: string
  created_at?: string
  /** `core/change_set.published_at`: when the set landed, empty until it does. A later set
   * reads it to tell whether the branch moved under the diff it holds. */
  published_at?: string
}

/** One located finding: `path:line` plus the sentence a reviewer would say. The gate
 * refuses a reason missing any of the three, so all three are sent. */
export interface ReviewReason {
  path: string
  line: number
  why: string
}

export interface ReviewVerdict {
  change_set_id?: string
  verdict: string
  reviewer: string
  reasons: ReviewReason[]
}

export interface PublishResult {
  ok: boolean
  applied: string[]
  rolled_back: string[]
  reason: string
}

/** One station on a change set's line: `core/change_set_lifecycle.STATIONS`. */
export interface LifecycleStation {
  name: string
  done: boolean
  current: boolean
}

/** `core/change_set_lifecycle.view` — where a set stands and which moves are still open.
 *
 * `withdraw` names the states a surface may move it back to by hand, which is `draft` alone:
 * `approved` is reached by a verdict and `published` by a publish, so neither is written by a
 * caller. `decidable` says whether a fresh verdict can move the set at all. */
export interface ChangeSetLifecycle {
  change_set_id: string
  state: string
  author: string
  stations: LifecycleStation[]
  verdict: ReviewVerdict | null
  reasons: ReviewReason[]
  decidable: boolean
  amendable: boolean
  withdraw: string[]
  can_publish: boolean
}

export interface ReviewSubmission {
  verdict: Verdict
  reviewer: string
  reasons: ReviewReason[]
}

export interface PublishOptions {
  target?: string
  dry_run?: boolean
  /** Publish although another run holds a path this set touches. The route names the holder
   * first (`publish_path_claimed`); this is the reader's answer that they have read it. */
  force?: boolean
}

/** One path as the custody read saw it: the digest on record against the one on disk. */
export interface CustodyFile {
  path: string
  op: string
  recorded: string
  /** `null` when the tree could not be read, so nothing about the disk is claimed. */
  current: string | null
  moved: boolean
}

/** The refusal a route would answer with, stated before it is asked for. */
export interface CustodyRefusal {
  code: string
  sentence: string
  params?: Record<string, string>
}

export interface Custody {
  change_set: ChangeSet
  author: string
  approval: ReviewVerdict | null
  /** Owners of live trees who may sign this — everyone but the author. */
  custodians: string[]
  files: CustodyFile[]
  checked: boolean
  publishable: boolean
  refusal: CustodyRefusal | null
}

/** The register, and the fleet behind it: `runs` is every run this app can see, the ones
 * that need a person first (`server/routes/workspaces.py`, `core/fleet.py`). One poll of
 * this route is the whole board — there is no second endpoint to keep in step. */
export function listWorkspaces(): Promise<{ workspaces: Workspace[]; runs: FleetRun[] }> {
  return request('/api/workspaces')
}

export function listChangeSets(workspaceId: string): Promise<{ change_sets: ChangeSet[] }> {
  const usp = new URLSearchParams({ workspace_id: workspaceId })
  return request(`/api/change-sets?${usp.toString()}`)
}

export function reviewChangeSet(
  id: string,
  submission: ReviewSubmission,
): Promise<{ verdict: ReviewVerdict }> {
  return request(`/api/change-sets/${encodeURIComponent(id)}/review`, {
    method: 'POST',
    body: JSON.stringify(submission),
  })
}

export function publishChangeSet(
  id: string,
  options?: PublishOptions,
): Promise<{ result: PublishResult; sentence: string }> {
  // `target` is omitted rather than sent empty when the caller names none: the route
  // declares `min_length=1` and its own default is the branch a set usually lands on, so
  // an empty string would be refused as a malformed argument rather than defaulted.
  const body: Record<string, unknown> = { dry_run: Boolean(options?.dry_run) }
  if (options?.target) body.target = options.target
  if (options?.force) body.force = true
  return request(`/api/change-sets/${encodeURIComponent(id)}/publish`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** The record's chain of custody: who wrote it, who signed it, whether it still matches. */
export function getCustody(id: string): Promise<Custody> {
  return request(`/api/change-sets/${encodeURIComponent(id)}/custody`)
}

/** The life of one set: its stage, the last verdict with its located reasons, and the moves
 * still open to it. Read when a reviewer opens the card, so the page load stays one call. */
export function getChangeSetLifecycle(id: string): Promise<{ lifecycle: ChangeSetLifecycle }> {
  return request(`/api/change-sets/${encodeURIComponent(id)}/lifecycle`)
}

/** Read the workspace again under the same id and provenance, and stand the set in draft.
 * The summary is left alone unless a new one is named. */
export function amendChangeSet(id: string, summary?: string): Promise<{ change_set: ChangeSet }> {
  const body: Record<string, unknown> = {}
  if (summary) body.summary = summary
  return request(`/api/change-sets/${encodeURIComponent(id)}/amend`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Reopen a set as a draft by hand. The route accepts `draft` and refuses every other state:
 * `approved` comes from a verdict and `published` from a publish, never from here. */
export function moveChangeSetState(id: string, state: string): Promise<{ change_set: ChangeSet }> {
  return request(`/api/change-sets/${encodeURIComponent(id)}/state`, {
    method: 'POST',
    body: JSON.stringify({ state }),
  })
}
