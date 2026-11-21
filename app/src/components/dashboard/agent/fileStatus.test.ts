import { describe, expect, it } from 'vitest'
import type { ChangeSet, GitFileChange } from '@/lib/api'
import {
  changeState,
  hasPatch,
  indexChanges,
  indexOrigins,
  markHintKey,
  markKey,
  relFromRoot,
  sameDir,
} from './fileStatus'

const at = (path: string, status: GitFileChange['status']): GitFileChange => ({
  path,
  status,
  additions: 2,
  deletions: 1,
})

const set = (
  files: { path: string; op: string }[],
  provenance: Partial<ChangeSet['provenance']>,
): ChangeSet => ({
  id: 'cs-1',
  workspace_id: '/tmp/ws',
  summary: 'add the thing',
  files: files.map((f) => ({ ...f, diff_sha: 'sha' })),
  provenance: { session_id: '', agent_id: '', why: '', ...provenance },
  state: 'review',
})

describe('changeState', () => {
  it('takes untracked and added paths as new, everything else as modified', () => {
    expect(changeState('?')).toBe('new')
    expect(changeState('A')).toBe('new')
    expect(changeState('M')).toBe('modified')
    expect(changeState('D')).toBe('modified')
  })
})

describe('hasPatch', () => {
  it('refuses a patch only where git has no earlier version to diff', () => {
    expect(hasPatch('?')).toBe(false)
    expect(hasPatch('A')).toBe(false)
    expect(hasPatch('M')).toBe(true)
    expect(hasPatch('D')).toBe(true)
  })
})

describe('indexChanges', () => {
  it('keys every change by its path', () => {
    const index = indexChanges([at('src/a.ts', 'M'), at('src/b.ts', '?')])
    expect(Object.keys(index).sort()).toEqual(['src/a.ts', 'src/b.ts'])
    expect(index['src/a.ts']?.status).toBe('M')
  })
})

describe('indexOrigins', () => {
  it('marks a file whose change set names a writer', () => {
    const index = indexOrigins([
      set([{ path: 'src/a.ts', op: 'create' }], { agent_id: 'agent-7', why: 'the brief' }),
    ])
    expect(index['src/a.ts']).toEqual({ op: 'create', why: 'the brief' })
  })

  it('leaves a change set without provenance unlabelled', () => {
    expect(indexOrigins([set([{ path: 'src/a.ts', op: 'modify' }], {})])).toEqual({})
  })
})

describe('markKey', () => {
  it('names the agent where a change set recorded it', () => {
    expect(markKey('new', { op: 'create', why: '' })).toBe('agentPanel.fileAgentCreated')
    expect(markKey('modified', { op: 'modify', why: '' })).toBe('agentPanel.fileAgentModified')
    expect(markKey('modified', { op: 'delete', why: '' })).toBe('agentPanel.fileAgentDeleted')
  })

  it('falls back to the plain status without an origin', () => {
    expect(markKey('new')).toBe('agentPanel.fileStatusNew')
    expect(markKey('modified')).toBe('agentPanel.fileStatusModified')
    expect(markHintKey('new')).toBe('agentPanel.fileStatusHintNew')
    expect(markHintKey('modified')).toBe('agentPanel.fileStatusHintModified')
  })
})

describe('relFromRoot', () => {
  it('strips a root and tolerates a trailing slash on it', () => {
    expect(relFromRoot('/tmp/ws', '/tmp/ws/src/a.ts')).toBe('src/a.ts')
    expect(relFromRoot('/tmp/ws/', '/tmp/ws/src/a.ts')).toBe('src/a.ts')
  })

  it('refuses a path outside the root', () => {
    expect(relFromRoot('/tmp/ws', '/tmp/other/a.ts')).toBeNull()
    expect(relFromRoot('/tmp/ws', '/tmp/ws')).toBeNull()
  })
})

describe('sameDir', () => {
  it('compares the server spelling of two directories', () => {
    expect(sameDir('/tmp/ws', '/tmp/ws/')).toBe(true)
    expect(sameDir('/tmp/ws', '/tmp/other')).toBe(false)
    expect(sameDir(null, '/tmp/ws')).toBe(false)
    expect(sameDir('/tmp/ws', null)).toBe(false)
  })
})
