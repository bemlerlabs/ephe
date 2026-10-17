/**
 * Change mark and origin for one file row of the workspace panel (finding #70).
 *
 * The panel walks the workspace as a tree, and a row carried only the file's name — not
 * whether it differs from the committed version, and not who wrote the difference. Two
 * backends answer that today, and this module is the join between them, kept free of
 * React so the mapping can be tested on its own: the git change list of the active
 * workspace (`GET /api/git/status`) and the change sets with their recorded provenance
 * (`GET /api/change-sets`, `core/change_set.py`).
 *
 * Git names a changed path relative to the repository root — measured: `git status
 * --porcelain` prints `sub/a.ts` from inside `sub/` exactly as it does from the top — and
 * a change set records the same root-relative spelling. The panel's tree is relative to
 * the workspace instead, so the two spellings agree exactly when the workspace IS that
 * repository root. `sameDir` holds the join to that case; under any other root the same
 * relative path names a different file, and a refused join shows no mark rather than a
 * wrong one.
 */
import type { ChangeSet, GitFileChange } from '@/lib/api'

/**
 * What a row can say about a tracked path. `new` means git holds no committed version
 * yet — the `?` of `git status --porcelain`. `modified` means the working tree differs
 * from what git has. A deletion never reaches this tree at all, because the row it would
 * mark belongs to the file that is no longer on disk, so these two are the whole set.
 */
export type ChangeState = 'new' | 'modified'

export function changeState(code: string): ChangeState {
  return code === '?' || code === 'A' ? 'new' : 'modified'
}

/**
 * Whether git can build a patch for this code, which is what both the diff and the revert
 * need. An untracked file has no earlier version to diff against, so the row offers
 * neither action instead of a button whose fetch would answer 404 (`GET /api/git/diff`
 * does exactly that, carrying the detail `no pending change for path`).
 */
export function hasPatch(code: string): boolean {
  return code !== '?' && code !== 'A'
}

export function indexChanges(changes: GitFileChange[]): Record<string, GitFileChange> {
  const index: Record<string, GitFileChange> = {}
  for (const change of changes) index[change.path] = change
  return index
}

export interface OriginMark {
  /** `create` | `modify` | `delete` — the three values of `core/change_set.OPS`. */
  op: string
  /** The change set's own reason. Empty when its author recorded none. */
  why: string
}

/**
 * Only a change set whose provenance names a writer carries an origin. The panel may not
 * guess that the agent authored a change it never recorded, so an edit that sits in no
 * change set stays unlabelled and the plain status stands alone.
 */
export function indexOrigins(sets: ChangeSet[]): Record<string, OriginMark> {
  const index: Record<string, OriginMark> = {}
  for (const set of sets) {
    const provenance = set.provenance
    const who = `${provenance?.agent_id ?? ''}${provenance?.session_id ?? ''}`.trim()
    if (!who) continue
    for (const file of set.files ?? []) {
      index[file.path] = { op: file.op, why: provenance?.why ?? '' }
    }
  }
  return index
}

/**
 * The i18n key of a row's badge: the agent's own wording when a change set recorded the
 * writer, the plain status otherwise. The words live in the locale files, and the key is
 * returned as a literal so the i18n lint can still account for it.
 */
export function markKey(state: ChangeState, origin?: OriginMark): string {
  if (origin) {
    if (origin.op === 'create') return 'agentPanel.fileAgentCreated'
    if (origin.op === 'delete') return 'agentPanel.fileAgentDeleted'
    return 'agentPanel.fileAgentModified'
  }
  return state === 'new' ? 'agentPanel.fileStatusNew' : 'agentPanel.fileStatusModified'
}

/**
 * The i18n key of the sentence behind a badge. It exists so a row can explain the reason
 * it offers no action instead of hiding it: an untracked file shows why neither button is
 * there.
 */
export function markHintKey(state: ChangeState): string {
  return state === 'new' ? 'agentPanel.fileStatusHintNew' : 'agentPanel.fileStatusHintModified'
}

/**
 * The path of `abs` below `rootPath`, with the `/` separators the server renders, or null
 * when `abs` is not below that root. A trailing slash is dropped first because the tree
 * may be rooted at a mount point the OS spells with one.
 */
export function relFromRoot(rootPath: string, abs: string): string | null {
  const root = rootPath.replace(/\/+$/, '')
  if (!root || !abs.startsWith(`${root}/`)) return null
  return abs.slice(root.length + 1)
}

/**
 * Whether two absolute directories are the same one. Both sides arrive from the server as
 * `Path(...).resolve()` output, so comparing the strings compares the same spelling of
 * the same directory.
 */
export function sameDir(a: string | null, b: string | null): boolean {
  if (!a || !b) return false
  return a.replace(/\/+$/, '') === b.replace(/\/+$/, '')
}
