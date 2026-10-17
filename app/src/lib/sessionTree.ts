/**
 * W17 P1-2: revision tree for the sidebar list.
 *
 * `branchSession` sets a `parentId` at every fork; the list used to sit
 * flat, one below another. This builder orders children behind their parents
 * (deeper indent), treats orphans as roots and is cycle-safe.
 */

export interface SessionLike {
  id: string
  parentId?: string
}

export interface SessionTreeRow<T extends SessionLike> {
  session: T
  depth: number
  /** Direct children — drives the branch badge and the collapse. */
  childCount: number
  /** Last child of the parent node (└) rather than a middle one (├). */
  isLast: boolean
  /**
   * P1-9: rail routing per column, length = depth.
   * rails[k] = true → the vertical line in column k reaches further
   * (an ancestor at level k+1 still has following siblings). Column depth-1 is
   * the node's own connector (├ when true, otherwise └).
   */
  rails: boolean[]
}

export function buildSessionTree<T extends SessionLike>(sessions: T[]): SessionTreeRow<T>[] {
  const byId = new Map<string, T>()
  for (const s of sessions) byId.set(s.id, s)

  const children = new Map<string, T[]>()
  for (const s of sessions) {
    const pid = s.parentId
    if (pid && byId.has(pid)) {
      const list = children.get(pid) ?? []
      list.push(s)
      children.set(pid, list)
    }
  }

  const rows: SessionTreeRow<T>[] = []
  const seen = new Set<string>()
  const visit = (s: T, depth: number, isLast: boolean, parentRails: boolean[]) => {
    if (seen.has(s.id)) return
    seen.add(s.id)
    const kids = children.get(s.id) ?? []
    const rails = depth === 0 ? [] : [...parentRails, !isLast]
    rows.push({ session: s, depth, childCount: kids.length, isLast, rails })
    kids.forEach((c, i) => visit(c, depth + 1, i === kids.length - 1, rails))
  }

  // Roots in the order they were given (pinned-first stays intact).
  for (const s of sessions) {
    const pid = s.parentId
    if (!pid || !byId.has(pid)) visit(s, 0, true, [])
  }
  // Cycle fallback: unreachable nodes attach as roots.
  for (const s of sessions) {
    if (!seen.has(s.id)) visit(s, 0, true, [])
  }
  return rows
}

/**
 * P1-9: hide the rows of a collapsed branch.
 * DFS pre-order: skip everything with depth > the collapsed level,
 * until the next row shows up at/above the node's level.
 */
export function filterCollapsedRows<T extends SessionLike>(
  rows: SessionTreeRow<T>[],
  collapsed: ReadonlySet<string>,
): SessionTreeRow<T>[] {
  const out: SessionTreeRow<T>[] = []
  let skipBelow = -1
  for (const row of rows) {
    if (skipBelow >= 0) {
      if (row.depth > skipBelow) continue
      skipBelow = -1
    }
    out.push(row)
    if (row.childCount > 0 && collapsed.has(row.session.id)) skipBelow = row.depth
  }
  return out
}
