/**
 * W1 — the conflict rule, pinned as a rule.
 *
 * The one thing this function must not do is cry wolf: two change sets inside a single
 * workspace are one agent's own sequencing, and reporting them as a collision would make
 * the notice meaningless on the page that exists to point at real ones.
 *
 * The other thing it must do is answer *when*, not only *who*: a reader deciding whether to
 * publish needs to know the other run has been in the file since 14:02, and a card needs to
 * pick its own rows out of the page-wide list without re-deriving the rule.
 */
import { describe, it, expect } from 'vitest'
import { pathConflicts, setConflicts } from './conflicts'
import type { ChangeSet } from '@/lib/api'

const cs = (id: string, paths: string[], workspace = 'w1', over: Partial<ChangeSet> = {}) => ({
  id,
  workspace_id: workspace,
  summary: '',
  files: paths.map((path) => ({ path, op: 'modify', diff_sha: 'sha256:aa' })),
  provenance: { session_id: '', agent_id: `agent-${workspace}`, why: '' },
  state: 'draft',
  created_at: '2026-10-14T12:00:00.000000+00:00',
  ...over,
})

const owners = { w1: 'agent-one', w2: 'agent-two' }

describe('pathConflicts', () => {
  it('finds nothing when the workspaces touch different files', () => {
    expect(
      pathConflicts({ w1: [cs('a', ['x.ts'])], w2: [cs('b', ['y.ts'], 'w2')] }, owners),
    ).toEqual([])
  })

  it('names a path two workspaces are changing at once', () => {
    const found = pathConflicts(
      { w1: [cs('a', ['shared.ts'])], w2: [cs('b', ['shared.ts'], 'w2')] },
      owners,
    )
    expect(found).toHaveLength(1)
    expect(found[0]?.path).toBe('shared.ts')
    expect(found[0]?.holders.map((h) => h.owner).sort()).toEqual(['agent-one', 'agent-two'])
  })

  it('leaves two change sets of ONE workspace alone', () => {
    // Same agent, same tree, one after the other — not a collision between agents.
    expect(pathConflicts({ w1: [cs('a', ['same.ts']), cs('b', ['same.ts'])] }, owners)).toEqual([])
  })

  it('does not report one change set that lists a path twice', () => {
    expect(pathConflicts({ w1: [cs('a', ['twice.ts', 'twice.ts'])] }, owners)).toEqual([])
  })

  it('sorts what it reports so two readings agree', () => {
    const found = pathConflicts(
      {
        w1: [cs('a', ['zeta.ts', 'alpha.ts'])],
        w2: [cs('b', ['zeta.ts', 'alpha.ts'], 'w2')],
      },
      owners,
    )
    expect(found.map((c) => c.path)).toEqual(['alpha.ts', 'zeta.ts'])
  })

  it('falls back to the workspace id when no owner is known', () => {
    const found = pathConflicts({ w1: [cs('a', ['p.ts'])], w2: [cs('b', ['p.ts'], 'w2')] })
    expect(found[0]?.holders.map((h) => h.owner).sort()).toEqual(['w1', 'w2'])
  })

  it('survives a workspace whose change sets were never read', () => {
    expect(pathConflicts({ w1: undefined, w2: [cs('b', ['p.ts'], 'w2')] }, owners)).toEqual([])
  })

  it('carries when each run took the path, not only which run it was', () => {
    const found = pathConflicts(
      {
        w1: [cs('a', ['shared.ts'], 'w1', { created_at: '2026-10-14T12:00:00.000000+00:00' })],
        w2: [
          cs('b', ['shared.ts'], 'w2', {
            created_at: '2026-10-14T12:05:00.000000+00:00',
            state: 'published',
            published_at: '2026-10-14T12:09:00.000000+00:00',
          }),
        ],
      },
      owners,
    )
    expect(found[0]?.holders.map((h) => [h.owner, h.since, h.state, h.landedAt])).toEqual([
      ['agent-one', '2026-10-14T12:00:00.000000+00:00', 'draft', ''],
      [
        'agent-two',
        '2026-10-14T12:05:00.000000+00:00',
        'published',
        '2026-10-14T12:09:00.000000+00:00',
      ],
    ])
  })
})

describe('setConflicts', () => {
  const rows = pathConflicts(
    { w1: [cs('a', ['shared.ts', 'mine.ts'])], w2: [cs('b', ['shared.ts'], 'w2')] },
    owners,
  )

  it('gives a card the rows its own set is a holder in', () => {
    const mine = rows.filter((row) => row.path === 'shared.ts')
    expect(setConflicts(cs('a', ['shared.ts', 'mine.ts']), rows)).toEqual(mine)
  })

  it('leaves a path this set does not touch to the set that does', () => {
    // A row exists because two *other* workspaces collide; that is not this set's news.
    const other = pathConflicts(
      { w2: [cs('b', ['theirs.ts'], 'w2')], w3: [cs('c', ['theirs.ts'], 'w3')] },
      owners,
    )
    expect(setConflicts(cs('a', ['mine.ts']), other)).toEqual([])
  })

  it('finds nothing for a set no other run shares a path with', () => {
    expect(setConflicts(cs('a', ['alone.ts']), rows)).toEqual([])
  })
})
