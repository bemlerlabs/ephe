/**
 * P4 — restoreFromServer carries the composer mode out of the server mirror into
 * the DbSession (otherwise a fresh browser falls back to 'ask' after a reload).
 */
import { describe, it, expect, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  restoreSessions: vi.fn(async () => ({
    sessions: [
      {
        id: 'm1',
        title: 'T',
        updated_at: 123,
        mode: 'full-access',
        messages: [{ role: 'user', content: 'hi' }],
      },
      { id: 'm2', title: 'T2', updated_at: 122, messages: [{ role: 'user', content: 'yo' }] },
      {
        id: 'm3',
        title: 'T3',
        updated_at: 121,
        parent_id: 'm1',
        messages: [{ role: 'user', content: 'fork' }],
      },
      {
        // R6/S3: an empty shell is not a history — this row is expected to be gone.
        id: 'm5',
        title: 'New task',
        updated_at: 119,
        messages: [],
      },
      {
        // R6/S1: the mirror carries the history — and the fresh browser has to
        // show it, not only the text.
        id: 'm4',
        title: 'T4',
        updated_at: 120,
        created_at: 55,
        messages: [
          { role: 'user', content: 'bau mir das', timestamp: 1759750001000 },
          {
            role: 'assistant',
            content: 'fertig',
            timestamp: 1759750010000,
            turnId: 't-1',
            tool_calls: [{ id: 'c1', name: 'run_shell', args: { command: 'ls' }, status: 'ok' }],
            activities: [{ id: 'a1', label: 'ls', status: 'done', path: '/tmp/x' }],
          },
        ],
      },
    ],
  })),
}))
vi.mock('@/lib/api', () => apiMock)

import { restoreFromServer } from './restore'
import type { ChatMessage } from '@/types'

describe('restoreFromServer — modus-durchlassig', () => {
  it('uebernimmt mode aus dem Mirror-Eintrag', async () => {
    const out = await restoreFromServer()
    expect(out.find((s) => s.id === 'm1')?.mode).toBe('full-access')
  })
  it('laesst mode weg, wenn der Mirror ihn nicht fuehrt', async () => {
    const out = await restoreFromServer()
    expect(out.find((s) => s.id === 'm2')?.mode).toBeUndefined()
  })
  it('mapt parent_id aus dem Mirror zu parentId (Sitzungs-Baum)', async () => {
    const out = await restoreFromServer()
    expect(out.find((s) => s.id === 'm3')?.parentId).toBe('m1')
    expect(out.find((s) => s.id === 'm1')?.parentId).toBeUndefined()
  })
})

describe('restoreFromServer — die Geschichte reist mit (R6/S1)', () => {
  it('uebernimmt Werkzeugrufe, Aktivitaeten und den Turn-Anker', async () => {
    const out = await restoreFromServer()
    const sitzung = out.find((s) => s.id === 'm4')
    const antwort = sitzung?.messages[1] as ChatMessage | undefined
    expect(antwort?.turnId).toBe('t-1')
    expect(antwort?.tool_calls).toHaveLength(1)
    expect(antwort?.activities).toHaveLength(1)
  })

  it('datiert die Sitzung nach ihrer Geburt, nicht nach der Mirror-Datei', async () => {
    const out = await restoreFromServer()
    const sitzung = out.find((s) => s.id === 'm4')
    expect(sitzung?.createdAt).toBe(55)
    // "last active" comes from the message rows; the mirror mtime would say "now".
    expect(sitzung?.updatedAt).toBe(1759750010000)
    // without created_at the mtime stays the fallback (no jump to "now")
    expect(out.find((s) => s.id === 'm2')?.createdAt).toBe(122)
  })
})
it('datiert „zuletzt aktiv" nach den Zeilen, nicht nach der Mirror-Datei', async () => {
  const out = await restoreFromServer()
  const sitzung = out.find((s) => s.id === 'm4')
  expect(sitzung?.updatedAt).toBe(1759750010000)
  // Without readable timestamps the mtime stays the honest fallback.
  expect(out.find((s) => s.id === 'm2')?.updatedAt).toBe(122)
})
it('laesst Sitzungen ohne Nachrichten nicht in die Seitenleiste', async () => {
  const out = await restoreFromServer()
  expect(out.find((s) => s.id === 'm5')).toBeUndefined()
})

/**
 * The mirror projection writes role/content/timestamp and the optional payloads and
 * carries no message id (server/routes/session_mirror.py:229-249). Measured 2026-10-13
 * on this machine: 72 non-empty ~/.ephe/sessions/pwa-*.json files hold 298 message rows,
 * and all 298 arrive id-less. Cast straight to ChatMessage[] they keyed the virtual list
 * `key={msg.id}` with undefined on every row, so React warned "Encountered two children
 * with the same key" on every restored chat.
 */
describe('restoreFromServer — an id-less mirror row gets a usable id', () => {
  it('stamps an id on every row that arrived without one', async () => {
    const out = await restoreFromServer()
    const rows = out.flatMap((s) => s.messages as ChatMessage[])
    expect(rows.length).toBe(5)
    for (const m of rows) {
      expect(typeof m.id).toBe('string')
      expect(m.id.length).toBeGreaterThan(0)
    }
  })

  it('keeps the keys unique inside a session', async () => {
    const out = await restoreFromServer()
    for (const s of out) {
      const ids = (s.messages as ChatMessage[]).map((m) => m.id)
      expect(new Set(ids).size).toBe(ids.length)
    }
  })

  it('is deterministic, so a re-hydrate yields the keys the first hydrate used', async () => {
    const first = await restoreFromServer()
    const second = await restoreFromServer()
    const keys = (sessions: typeof first) =>
      sessions.map((s) => (s.messages as ChatMessage[]).map((m) => m.id))
    expect(keys(first)).toEqual(keys(second))
  })
})
