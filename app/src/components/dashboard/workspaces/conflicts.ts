/**
 * Ephe — where two live workspaces want the same file (W1).
 *
 * The owner's question was "which agents are running, on which files, and are there
 * conflicts". Two workspaces are parallel agent runs with their own checkout, so the
 * conflict that matters across them is a path two of them are changing at the same time:
 * whoever publishes second meets a file the other one already moved.
 *
 * Every holder carries *when* it took the path — the change set's own `created_at`, and for a
 * set that landed, its landing — so the answer is not only "who else is in this file" but
 * "since when". A run that reads its own card gets the same answer as the page-wide strip,
 * because both read this one rule.
 *
 * Two change sets inside ONE workspace on the same path are not reported here. That is a
 * sequencing question inside one agent's own tree, not a collision between agents, and
 * mixing the two would make the notice cry wolf.
 */
import type { ChangeSet } from '@/lib/api'

export interface ConflictHolder {
  changeSetId: string
  workspaceId: string
  owner: string
  /** When this run read the path out of its own tree — `core.change_set` `created_at`. */
  since: string
  /** The set's own state: `draft`/`review` is a run still in the file, `published` a landing. */
  state: string
  /** When the set landed, and empty until it does — `core.change_set` `published_at`. */
  landedAt: string
}

export interface PathConflict {
  path: string
  holders: ConflictHolder[]
}

/**
 * Paths touched by change sets of two or more different workspaces, each with the
 * holders that touch them. Sorted by path so two readings of the same state agree.
 */
export function pathConflicts(
  byWorkspace: Record<string, ChangeSet[] | undefined>,
  owners: Record<string, string> = {},
): PathConflict[] {
  const holders = new Map<string, ConflictHolder[]>()
  for (const [workspaceId, changeSets] of Object.entries(byWorkspace)) {
    for (const cs of changeSets ?? []) {
      for (const file of cs.files ?? []) {
        if (!file.path) continue
        const list = holders.get(file.path) ?? []
        list.push({
          changeSetId: cs.id,
          workspaceId,
          owner: owners[workspaceId] || workspaceId,
          since: cs.created_at ?? '',
          state: cs.state,
          landedAt: cs.published_at ?? '',
        })
        holders.set(file.path, list)
      }
    }
  }
  return [...holders.entries()]
    .filter(([, list]) => new Set(list.map((h) => h.workspaceId)).size > 1)
    .map(([path, list]) => ({ path, holders: list }))
    .sort((a, b) => a.path.localeCompare(b.path))
}

/**
 * The rows of a page-wide conflict list that name one change set, plus the other runs in them.
 *
 * This is what a card reads, so the run that just wrote a path hears about the other run on that
 * path in its own surface and not only in a strip above twenty workspaces. A row is this set's
 * business when the set touches that path and stands as one of its holders.
 */
export function setConflicts(changeSet: ChangeSet, conflicts: PathConflict[]): PathConflict[] {
  const mine = new Set((changeSet.files ?? []).map((file) => file.path))
  return conflicts.filter(
    (row) => mine.has(row.path) && row.holders.some((h) => h.changeSetId === changeSet.id),
  )
}
