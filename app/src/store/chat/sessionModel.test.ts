/**
 * Z53 — the session model: tags, folders, a restorable trash.
 *
 * The migration below starts from a captured payload, not from a payload shaped
 * to please this code. Origin of the capture, measured 2026-10-14 on this
 * machine: the Ephe PWA's own IndexedDB — Chrome profile 2, origin
 * http://localhost:5173, object stores `sessions` and `checkpoints` (both object
 * store names read out of the leveldb, UTF-16BE), 37 session rows. Every one of
 * those 37 rows carries `{id, title, messages, createdAt}`, and not one of them
 * carries `archived`, `unread`, `pinned`, `titleCustom`, `parentId`, `mode` or
 * `usageTotals` (0 occurrences of each in the whole store). Their message rows
 * carry `{id, role, content, timestamp}` plus, where present, `tool_calls`,
 * `thinking`, `activities` and `streaming`.
 *
 * The field names, value types and nesting are the capture's. Its own strings
 * are the user's, and German, so neutral English text of the same shape stands
 * in for them: this test pins the shape, and a session's content is not a test
 * fixture.
 */
import { describe, expect, it } from 'vitest'
import type { DbSession, Session } from '@/types'
import { fromDbSession, toDbSession } from './helpers'
import {
  SESSION_MODEL_FIELDS,
  isTrashed,
  migrateSessionRecord,
  migrateSessionRecords,
  normalizeFolder,
  normalizeFolders,
  normalizeTags,
  restoreSession,
  sessionState,
  setSessionFolder,
  setSessionTags,
  trashSession,
} from './sessionModel'

/** One row of the capture, field for field. */
const CAPTURED_ROW = {
  id: '533e7f37-de3b-4306-9aee-26fd970bee9c',
  title: 'Online search: research the topic and collect the key results',
  messages: [
    {
      id: 'de1a65ab-8eb2-4321-9169-558a04dc6622',
      role: 'user',
      content: 'Research the topic and collect the key results',
      timestamp: 1760353201749,
    },
    {
      id: 'c45b94ba-4122-4f6b-8611-349490e4f498',
      role: 'assistant',
      content: 'Hey! Hier sind die Ergebnisse.',
      timestamp: 1760353206123,
      streaming: false,
      activities: [{ id: 'a1', label: 'web_search', status: 'done' }],
      tool_calls: [{ id: 'c45b94ba', name: 'web_search', args: { query: 'ephe' }, status: 'ok' }],
    },
  ],
  createdAt: 1760353201700,
  updatedAt: 1760353206123,
}

/** A second row of the same capture, with the archive flag the writer sets (M2). */
const CAPTURED_ARCHIVED_ROW = toDbSession({
  id: '9c1f0e5a-77bd-4a10-8d2f-3f5c9b0a1e42',
  title: 'Old task',
  messages: [{ id: 'm1', role: 'user', content: 'hello', timestamp: 1760350000000 }],
  createdAt: 1760350000000,
  archived: true,
} as Session)

const CAPTURE: unknown[] = [CAPTURED_ROW, CAPTURED_ARCHIVED_ROW]

describe('the captured payload survives the migration', () => {
  it('hands back the captured row untouched when it carries nothing to normalise', () => {
    const out = migrateSessionRecord(CAPTURED_ROW)
    expect(out).toBe(CAPTURED_ROW)
    expect(out).toEqual(CAPTURED_ROW)
  })

  it('asks none of the three new fields of a row that had no place to be', () => {
    const out = migrateSessionRecord(CAPTURED_ROW) as unknown as Record<string, unknown>
    expect(out.tags).toBeUndefined()
    expect(out.folderId).toBeUndefined()
    expect(out.deletedAt).toBeUndefined()
  })

  it('keeps every message of the capture, id and order included', () => {
    const before = CAPTURED_ROW.messages.map((m) => m.id)
    const out = migrateSessionRecord(CAPTURED_ROW) as unknown as DbSession
    expect(out.messages).toHaveLength(2)
    expect((out.messages as Array<{ id: string }>).map((m) => m.id)).toEqual(before)
    expect(out.messages).toEqual(CAPTURED_ROW.messages)
  })

  it('does not drop a single row of the collection, and does not reorder it', () => {
    const out = migrateSessionRecords(CAPTURE)
    expect(out).toHaveLength(CAPTURE.length)
    expect(out.map((s) => s.id)).toEqual([
      '533e7f37-de3b-4306-9aee-26fd970bee9c',
      '9c1f0e5a-77bd-4a10-8d2f-3f5c9b0a1e42',
    ])
  })

  it('carries a key this generation never heard of through the migration', () => {
    const withUnknown = { ...CAPTURED_ROW, somethingNewer: { a: [1, 2] } }
    const out = migrateSessionRecord(withUnknown) as unknown as Record<string, unknown>
    expect(out.somethingNewer).toEqual({ a: [1, 2] })
  })

  it('passes a row it cannot read through instead of throwing it away', () => {
    for (const junk of [null, undefined, 'x', 7, ['not', 'a', 'row']]) {
      expect(migrateSessionRecord(junk)).toBe(junk)
    }
    expect(migrateSessionRecords([null, CAPTURED_ROW, 7])).toHaveLength(3)
  })
})

describe('archived is none of the three', () => {
  it('reads an archived row as archived, not as filed and not as trashed', () => {
    const out = migrateSessionRecord(CAPTURED_ARCHIVED_ROW) as DbSession & {
      tags?: string[]
      folderId?: string
      deletedAt?: number
    }
    expect(out.archived).toBe(true)
    expect(sessionState(out)).toBe('archived')
    expect(out.tags).toBeUndefined()
    expect(out.folderId).toBeUndefined()
    expect(out.deletedAt).toBeUndefined()
    expect(isTrashed(out)).toBe(false)
  })

  it('leaves the archive flag alone, whichever of the three is set', () => {
    const row: Session = {
      id: 's1',
      title: 'T',
      messages: [],
      createdAt: 1,
    }
    const archived = { ...row, archived: true }
    expect(sessionState(setSessionTags(archived, ['a']))).toBe('archived')
    expect(sessionState(trashSession(archived, 5))).toBe('trashed')
    expect(trashSession(archived, 5).archived).toBe(true)
    expect(restoreSession(trashSession(archived, 5))).toEqual(archived)
  })

  it('lets the trash outrank the archive shelf', () => {
    expect(sessionState({ archived: true, deletedAt: 5 })).toBe('trashed')
    expect(sessionState({ archived: true })).toBe('archived')
    expect(sessionState({})).toBe('live')
  })
})

describe('tags', () => {
  it('normalises a comma-separated tag line into one tag per word', () => {
    expect(normalizeTags('research, ephe ,  offline ')).toEqual(['research', 'ephe', 'offline'])
  })

  it('drops blanks and case-insensitive duplicates, keeping the first spelling', () => {
    expect(normalizeTags(['Ephe', 'ephe', '  ', 'EPHE', 'research'])).toEqual(['Ephe', 'research'])
  })

  it('collapses inner whitespace and ignores entries that are not strings', () => {
    expect(normalizeTags(['a   b', null, 4, { x: 1 }, 'c'])).toEqual(['a b', 'c'])
  })

  it('is not a value when it is empty: the field is removed, not emptied', () => {
    const s: Session = { id: 's1', title: 'T', messages: [], createdAt: 1, tags: ['a'] }
    const cleared = setSessionTags(s, [])
    expect('tags' in cleared).toBe(false)
    expect(setSessionTags(s, ['a', 'b']).tags).toEqual(['a', 'b'])
  })

  it('reaches the persisted row and comes back', () => {
    const s = setSessionTags({ id: 's1', title: 'T', messages: [], createdAt: 1 }, ['a'])
    expect(toDbSession(s).tags).toEqual(['a'])
    expect(fromDbSession(toDbSession(s)).tags).toEqual(['a'])
    const plain: Session = { id: 's1', title: 'T', messages: [], createdAt: 1 }
    expect('tags' in toDbSession(plain)).toBe(false)
    expect('tags' in fromDbSession(toDbSession(plain))).toBe(false)
  })
})

describe('folders', () => {
  it('keeps containment to one folder per session', () => {
    const s: Session = { id: 's1', title: 'T', messages: [], createdAt: 1 }
    expect(setSessionFolder(s, 'f1').folderId).toBe('f1')
    expect(setSessionFolder(setSessionFolder(s, 'f1'), 'f2').folderId).toBe('f2')
    expect('folderId' in setSessionFolder(s, null)).toBe(false)
  })

  it('does not accept a blank reference as a folder', () => {
    const s: Session = { id: 's1', title: 'T', messages: [], createdAt: 1 }
    expect('folderId' in setSessionFolder(s, '   ')).toBe(false)
    const migrated = migrateSessionRecord({ id: 's1', folderId: '  ' }) as DbSession
    expect('folderId' in migrated).toBe(false)
  })

  it('takes the id as what makes a folder addressable', () => {
    expect(normalizeFolder({ name: 'No id' })).toBeNull()
    expect(normalizeFolder({ id: '  ', name: 'x' })).toBeNull()
    expect(normalizeFolder({ id: 'f1', name: '  Recherche  ' })).toEqual({
      id: 'f1',
      name: 'Recherche',
    })
  })

  it('keeps a folder the user did not name, with the name left empty', () => {
    expect(normalizeFolder({ id: 'f1' })).toEqual({ id: 'f1', name: '' })
  })

  it('leaves an unknown creation date unknown rather than dating it to now', () => {
    expect(normalizeFolder({ id: 'f1', name: 'x' })).toEqual({ id: 'f1', name: 'x' })
    expect(normalizeFolder({ id: 'f1', name: 'x', createdAt: 0 })).toEqual({ id: 'f1', name: 'x' })
    expect(normalizeFolder({ id: 'f1', name: 'x', createdAt: 12 })).toEqual({
      id: 'f1',
      name: 'x',
      createdAt: 12,
    })
  })

  it('collapses a duplicated record onto the folder it names', () => {
    const out = normalizeFolders([
      { id: 'f1', name: 'first' },
      { id: 'f1', name: 'second' },
      { id: 'f2', name: 'other' },
    ])
    expect(out).toEqual([
      { id: 'f1', name: 'first' },
      { id: 'f2', name: 'other' },
    ])
  })

  it('reads a collection that is not a list as no folder at all', () => {
    expect(normalizeFolders(undefined)).toEqual([])
    expect(normalizeFolders('f1,f2')).toEqual([])
    expect(normalizeFolders([null, 4])).toEqual([])
  })
})

describe('the trash is a field write, not a second copy', () => {
  const s: Session = { id: 's1', title: 'T', messages: [], createdAt: 1 }

  it('moves a session to the trash with its messages still on it', () => {
    const row: Session = {
      ...s,
      messages: [{ id: 'm1', role: 'user', content: 'stays', timestamp: 3 }],
    }
    const trashed = trashSession(row, 99)
    expect(trashed.deletedAt).toBe(99)
    expect(trashed.messages).toEqual(row.messages)
    expect(sessionState(trashed)).toBe('trashed')
  })

  it('restores by clearing the stamp, leaving no key behind', () => {
    const restored = restoreSession(trashSession(s, 99))
    expect(restored).toEqual(s)
    expect('deletedAt' in restored).toBe(false)
    expect(sessionState(restored)).toBe('live')
  })

  it('reaches the persisted row in both directions', () => {
    const trashed = trashSession(s, 99)
    expect(toDbSession(trashed).deletedAt).toBe(99)
    expect(fromDbSession(toDbSession(trashed)).deletedAt).toBe(99)
    expect('deletedAt' in toDbSession(s)).toBe(false)
  })

  it('accepts no stamp the writer could not have written', () => {
    for (const junk of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, '99', null]) {
      const row = migrateSessionRecord({ id: 's1', deletedAt: junk }) as DbSession
      expect('deletedAt' in row).toBe(false)
      expect(isTrashed(row)).toBe(false)
    }
  })
})

describe('the migration is idempotent', () => {
  it('returns the same row the second time, untouched', () => {
    const dirty = {
      ...CAPTURED_ROW,
      tags: ' research , ephe , research ',
      folderId: '  f1  ',
      deletedAt: 1760353200000,
    }
    const once = migrateSessionRecord(dirty)
    expect((once as DbSession).tags).toEqual(['research', 'ephe'])
    expect((once as DbSession).folderId).toBe('f1')
    const twice = migrateSessionRecord(once)
    expect(twice).toBe(once)
    expect(twice).toEqual(once)
  })

  it('normalises a row that already carries the three fields in stored form', () => {
    const out = migrateSessionRecord({
      id: 's1',
      tags: ['a', 'A'],
      folderId: ' f1 ',
      deletedAt: 12,
    }) as DbSession
    expect(out.tags).toEqual(['a'])
    expect(out.folderId).toBe('f1')
    expect(out.deletedAt).toBe(12)
  })

  it('touches no key outside the three the model owns', () => {
    const dirty = { ...CAPTURED_ROW, tags: 'a,b', folderId: 'f1', deletedAt: 3 }
    const out = migrateSessionRecord(dirty) as unknown as Record<string, unknown>
    const before = Object.keys(dirty)
    const after = Object.keys(out)
    // The migration invents no key, and drops none.
    expect(after.filter((k) => !before.includes(k))).toEqual([])
    expect(before.filter((k) => !after.includes(k))).toEqual([])
    for (const key of before) {
      if (SESSION_MODEL_FIELDS.includes(key as (typeof SESSION_MODEL_FIELDS)[number])) continue
      expect(out[key]).toEqual((dirty as Record<string, unknown>)[key])
    }
  })
})
