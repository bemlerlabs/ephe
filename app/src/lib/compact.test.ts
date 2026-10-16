/**
 * Ephe — lib/compact.ts (Phase F1)
 *
 * GIVEN a message list (ChatMessage[])
 * WHEN  compactMessages()
 * THEN  ≤28 unchanged; >28 → system ledger + the last 12
 * AND   consistent stats (before/after/tokensBefore>tokensAfter when >28)
 */
import { describe, it, expect } from 'vitest'
import {
  compactMessages,
  buildWorkingMemory,
  COMPACT_MAX_MESSAGES,
  COMPACT_KEEP_RECENT,
} from './compact'
import type { ChatMessage } from '@/types'

function msg(role: 'user' | 'assistant', content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, timestamp: Date.now() }
}

function nMessages(n: number, contentLen = 500): ChatMessage[] {
  return Array.from({ length: n }, (_, i) =>
    msg(i % 2 === 0 ? 'user' : 'assistant', `Nachricht ${i} ` + 'x'.repeat(contentLen)),
  )
}

describe('compactMessages', () => {
  it('GIVEN ≤ maxMessages WHEN compact THEN unverändert (1:1-Kopie)', () => {
    const input = nMessages(10)
    const { compacted, stats } = compactMessages(input)
    expect(compacted).toHaveLength(10)
    expect(stats.compactedCount).toBe(0)
    expect(stats.before).toBe(10)
    expect(stats.after).toBe(10)
    // same order & contents
    expect(compacted.map((m) => m.content)).toEqual(input.map((m) => m.content))
  })

  it('GIVEN 30 Messages WHEN compact THEN first-Schutz + System-Ledger + letzte 10', () => {
    const { compacted, stats } = compactMessages(nMessages(30))
    // W18: first(1) + ledger(1) + recent(10) = 12
    expect(compacted).toHaveLength(2 + COMPACT_KEEP_RECENT)
    expect(compacted[1]!.role).toBe('system')
    expect(compacted[1]!.content).toContain('Working Memory Ledger')
    // the last 10 survive (order + contents)
    const recent = compacted.slice(2)
    expect(recent.map((m) => m.content)).toEqual(
      nMessages(30)
        .slice(-10)
        .map((m) => m.content),
    )
    expect(stats.compactedCount).toBe(19)
    expect(stats.keptRecent).toBe(10)
    expect(stats.tokensAfter).toBeLessThan(stats.tokensBefore)
  })

  it('GIVEN exakt 28 Messages WHEN compact THEN unverändert (Grenze)', () => {
    const { stats } = compactMessages(nMessages(COMPACT_MAX_MESSAGES))
    expect(stats.compactedCount).toBe(0)
  })

  it('GIVEN Präferenz-/Projekt-/Entscheidungs-Texte WHEN compact THEN Ledger kategorisiert sie', () => {
    const msgs: ChatMessage[] = [
      msg('user', 'Nachricht 0 Basis'),
      msg('user', 'Meine Präferenz: strikt lokal, keine Cloud'),
      msg('user', 'Projekt: Ephe Repo /workspace'),
      msg('user', 'Unsere Entscheidung: wir machen SSE'),
      ...nMessages(26),
    ]
    const { compacted } = compactMessages(msgs)
    // index 0 = first (protected), index 1 = the ledger holding the category messages
    const first = compacted[0]!.content
    const ledger = compacted[1]!.content
    expect(first).toContain('Nachricht 0 Basis')
    expect(ledger).toContain('## User preferences')
    expect(ledger).toContain('lokal')
    expect(ledger).toContain('## Project facts')
    expect(ledger).toContain('Ephe')
    expect(ledger).toContain('## Decisions')
    expect(ledger).toContain('SSE')
  })

  it('GIVEN keine Fakten WHEN compact THEN Fallback-Bulletpoint', () => {
    const text = buildWorkingMemory(nMessages(5))
    expect(text).toContain('- Keine stabilen Fakten erkannt.')
  })
})
