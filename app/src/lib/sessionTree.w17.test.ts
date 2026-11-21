import { describe, it, expect } from 'vitest'
import { buildSessionTree, filterCollapsedRows } from './sessionTree'

interface Row0 {
  id: string
  parentId?: string
}

describe('buildSessionTree (W17 P1-2)', () => {
  it('nests children under their parents with rising depth', () => {
    const rows = buildSessionTree<Row0>([
      { id: 'r1' },
      { id: 'c1', parentId: 'r1' },
      { id: 'c2', parentId: 'c1' },
    ])
    expect(rows.map((r) => [r.session.id, r.depth])).toEqual([
      ['r1', 0],
      ['c1', 1],
      ['c2', 2],
    ])
  })

  it('assigns children to parents in the order passed in', () => {
    const rows = buildSessionTree<Row0>([
      { id: 'root' },
      { id: 'a', parentId: 'root' },
      { id: 'b', parentId: 'root' },
    ])
    expect(rows.map((r) => r.session.id)).toEqual(['root', 'a', 'b'])
    expect(rows[1]!.depth).toBe(1)
    expect(rows[2]!.depth).toBe(1)
  })

  it('treats orphans (a missing parent) as roots at level 0', () => {
    const rows = buildSessionTree<Row0>([{ id: 'o', parentId: 'missing' }])
    expect(rows).toHaveLength(1)
    expect(rows[0]!.depth).toBe(0)
  })

  it('walks cycle-safe and completes every session', () => {
    const rows = buildSessionTree<Row0>([
      { id: 'x' },
      { id: 'a', parentId: 'b' },
      { id: 'b', parentId: 'a' },
    ])
    const ids = rows.map((r) => r.session.id)
    expect(ids).toEqual(['x', 'a', 'b'])
    expect(rows[0]!.depth).toBe(0)
  })

  it('returns an empty list for no sessions', () => {
    expect(buildSessionTree<Row0>([])).toEqual([])
  })
})

describe('buildSessionTree rails/childCount (P1-9)', () => {
  it('marks sibling connectors and runs guides only for following siblings', () => {
    const rows = buildSessionTree<Row0>([
      { id: 'r' },
      { id: 'a', parentId: 'r' },
      { id: 'b', parentId: 'r' },
      { id: 'a1', parentId: 'a' },
    ])
    const byId = Object.fromEntries(rows.map((r) => [r.session.id, r]))
    expect(byId.a!.childCount).toBe(1)
    expect(byId.b!.childCount).toBe(0)
    // 'a' is NOT the last child → own connector ├ (rails[0]=true); 'b' last → └.
    expect(byId.a!.rails[byId.a!.depth - 1]).toBe(true)
    expect(byId.b!.rails[byId.b!.depth - 1]).toBe(false)
    // 'a1' under 'a': the ancestor rail in column 0 depends on whether 'a' has
    // later siblings (b) → rail true → │-line.
    expect(byId.a1!.rails[0]).toBe(true)
  })

  it('filterCollapsedRows versteckt den Teilbaum eines eingeklappten Astes', () => {
    const rows = buildSessionTree<Row0>([
      { id: 'r' },
      { id: 'a', parentId: 'r' },
      { id: 'a1', parentId: 'a' },
      { id: 'b', parentId: 'r' },
    ])
    const visible = filterCollapsedRows(rows, new Set(['a'])).map((r) => r.session.id)
    expect(visible).toEqual(['r', 'a', 'b']) // a1 hangs under a and is gone
    const collapsedRoot = filterCollapsedRows(rows, new Set(['r'])).map((r) => r.session.id)
    expect(collapsedRoot).toEqual(['r']) // whole branch closed
    expect(filterCollapsedRows(rows, new Set())).toHaveLength(rows.length)
  })
})
