/**
 * G8: compaction contract parity — the client mirror of the backend compactor.
 *
 * Uses the same fixture as the pytest contract (tests/test_compaction_contract.py):
 *   app/fixtures/compaction/sample-history.json   (input)
 *   app/fixtures/compaction/expected-ledger.json (golden: the backend ledger as a string)
 *
 * The client (lib/compact.ts) has to build the same ledger summary from the same
 * input fixture as the backend (core/conversation_compactor.py). This closes the
 * "keep in sync" gap: when one side drifts, exactly one of the two tests fails —
 * and it shows WHICH side drifted.
 */
import { describe, it, expect } from 'vitest'
import {
  compactMessages,
  buildWorkingMemory,
  COMPACT_MAX_MESSAGES,
  COMPACT_KEEP_RECENT,
  COMPACT_MAX_SUMMARY_CHARS,
} from './compact'
import type { ChatMessage } from '@/types'
import history from '../../fixtures/compaction/sample-history.json'
import golden from '../../fixtures/compaction/expected-ledger.json'

type FixtureMessage = { role: string; content: string }

function toChatMessages(items: FixtureMessage[]): ChatMessage[] {
  return items.map((m, i) => ({
    id: `fixture-${i}`,
    role: m.role as 'user' | 'assistant' | 'system',
    content: m.content,
    timestamp: 0,
  }))
}

describe('compaction parity: Client === Backend (shared fixture + golden)', () => {
  it('client-Ledger stimmt exakt mit der Backend-Golden überein', () => {
    const messages = toChatMessages(history)
    const expected = String(golden)

    const { compacted, stats } = compactMessages(messages, {
      maxMessages: COMPACT_MAX_MESSAGES,
      keepRecent: COMPACT_KEEP_RECENT,
    })

    expect(stats.changed).toBe(true)
    // W18: first(1) + ledger(1) + recent(10) = 12
    expect(compacted.length).toBe(2 + COMPACT_KEEP_RECENT)
    // index 0 = the protected first message (its role comes from the fixture), index 1 = the ledger
    expect(compacted[0]?.role).toBe(history[0]!.role)
    expect(compacted[0]?.content).toBe(history[0]!.content)
    expect(compacted[1]?.role).toBe('system')
    expect(compacted[1]?.content).toBe(expected)
    // the recent turns stay untouched 1:1 (same as the backend: history[-keep_recent:])
    expect(compacted.slice(2).map((m) => m.content)).toEqual(
      history.slice(-COMPACT_KEEP_RECENT).map((m) => m.content),
    )
  })

  it('client-Cap: buildWorkingMemory kappt auf COMPACT_MAX_SUMMARY_CHARS wie Backend', () => {
    const older = toChatMessages(history.slice(1, -COMPACT_KEEP_RECENT))
    const uncut = buildWorkingMemory(older, Number.POSITIVE_INFINITY)
    expect(uncut.length).toBeGreaterThan(COMPACT_MAX_SUMMARY_CHARS)
    expect(buildWorkingMemory(older).length).toBe(COMPACT_MAX_SUMMARY_CHARS)
  })
})
