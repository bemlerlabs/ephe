import { describe, expect, it } from 'vitest'
import { migrateDbSession } from '@/lib/db'
import type { DbSession } from '@/types'

/**
 * R44 (P1): IndexedDB schema migration on read. Stage-2 data (from before the
 * blocks/thinkingPhases chronology) may carry only the single `thinking` stamp;
 * the renderer goes by the phase list. The migration rebuilds the phase so the
 * stream keeps its full cadence.
 */

function base(id = 's1'): DbSession {
  return { id, title: 'T', messages: [], createdAt: 1, updatedAt: 1 }
}

describe('migrateDbSession (R44)', () => {
  it('rekonstruiert thinkingPhases aus dem Einzel-Stempel (Legacy)', () => {
    const legacy = {
      ...base(),
      messages: [
        {
          id: 'a1',
          role: 'assistant',
          content: 'X',
          timestamp: 1,
          thinking: { start: 10, end: 12, text: 'P' },
        },
      ],
    } as unknown as DbSession
    const out = migrateDbSession(legacy)
    const msg = out.messages[0] as { thinkingPhases?: { text: string }[] }
    expect(msg.thinkingPhases).toHaveLength(1)
    expect(msg.thinkingPhases?.[0]?.text).toBe('P')
  })

  it('laesst vorhandene Phasenliste unangetast', () => {
    const modern = {
      ...base(),
      messages: [
        {
          id: 'a1',
          role: 'assistant',
          content: 'X',
          timestamp: 1,
          thinking: { start: 10, end: 12, text: 'P' },
          thinkingPhases: [{ start: 10, end: 12, text: 'P' }],
        },
      ],
    } as unknown as DbSession
    const out = migrateDbSession(modern)
    const msg = out.messages[0] as { thinkingPhases?: unknown[] }
    expect(msg.thinkingPhases).toHaveLength(1)
  })

  it('is identisch bei ohne-thinking-Nachrichten', () => {
    const plain = {
      ...base(),
      messages: [{ id: 'u1', role: 'user', content: 'X', timestamp: 1 }],
    } as unknown as DbSession
    expect(migrateDbSession(plain)).toEqual(plain)
  })

  it('toleriert kaputte messages-Felder (nicht-Array, null-Eintraege)', () => {
    const broken = { ...base(), messages: null } as unknown as DbSession
    expect(migrateDbSession(broken)).toEqual(broken)
    const nullMsg = { ...base(), messages: [null] } as unknown as DbSession
    expect((migrateDbSession(nullMsg).messages as unknown[]).length).toBe(1)
  })
})
