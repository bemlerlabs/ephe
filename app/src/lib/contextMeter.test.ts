import { describe, it, expect } from 'vitest'

import { estimateTokens, estimateContextUsage, CONTEXT_WINDOW_TOKENS } from '@/lib/contextMeter'

describe('contextMeter token estimation', () => {
  it('estimates tokens from text length (chars -> token ratio)', () => {
    // gemma: ~4.2 chars/token, conservative estimate
    const text = 'a'.repeat(420)
    const tokens = estimateTokens(text)
    expect(tokens).toBeGreaterThanOrEqual(90)
    expect(tokens).toBeLessThanOrEqual(110)
  })

  it('returns 0 tokens for empty text', () => {
    expect(estimateTokens('')).toBe(0)
    expect(estimateTokens('   ')).toBe(0)
  })

  it('counts system messages toward the total', () => {
    const messages = [
      { role: 'system' as const, content: 'sys'.repeat(100) },
      { role: 'user' as const, content: 'user'.repeat(100) },
      { role: 'assistant' as const, content: 'assistant'.repeat(100) },
    ]
    const usage = estimateContextUsage(messages, 2000)
    expect(usage.tokens.system).toBeGreaterThan(0)
    expect(usage.tokens.user).toBeGreaterThan(0)
    expect(usage.tokens.assistant).toBeGreaterThan(0)
    expect(usage.tokens.total).toBe(
      usage.tokens.system + usage.tokens.user + usage.tokens.assistant,
    )
  })

  it('computes percent-full clamped to 100', () => {
    const huge = [{ role: 'user' as const, content: 'x'.repeat(500000) }]
    const usage = estimateContextUsage(huge, CONTEXT_WINDOW_TOKENS)
    expect(usage.percent).toBe(100)
    expect(usage.remaining).toBe(0)
  })

  // R36 / B12 edge case: before an engine is configured the context window is
  // unknown (0) — the meter must clamp to 100 %, never emit NaN into the UI.
  it('clamps to 100 percent and stays NaN-free for a zero window', () => {
    const messages = [{ role: 'user' as const, content: 'hello' }]
    const usage = estimateContextUsage(messages, 0)
    expect(usage.percent).toBe(100)
    expect(Number.isNaN(usage.percent)).toBe(false)
    expect(Number.isFinite(usage.remaining)).toBe(true)
  })

  it('returns zero usage for no messages', () => {
    const usage = estimateContextUsage([], CONTEXT_WINDOW_TOKENS)
    expect(usage.tokens.total).toBe(0)
    expect(usage.percent).toBe(0)
    expect(usage.remaining).toBe(CONTEXT_WINDOW_TOKENS)
  })

  it('exposes a sensible default context window', () => {
    expect(CONTEXT_WINDOW_TOKENS).toBeGreaterThan(0)
    expect(CONTEXT_WINDOW_TOKENS).toBeGreaterThan(1000)
  })

  it('W14/P0-3: CJK zaehlt 1 Token je Zeichen (Kalibrierung gegen 4.2)', () => {
    // 4 ideographs: the old ratio 4.2 => 1 token; calibrated => 4
    expect(estimateTokens('你好世界')).toBe(4)
    // mixed: 4 CJK + 4 Latin => 4 + 4/4.2 = 4.95 → round up to 5
    expect(estimateTokens('你好世界abcd')).toBe(5)
    // pure Latin fixtures stay numerically identical to the old ratio
    expect(estimateTokens('a'.repeat(420))).toBe(100)
  })

  it('W14/P0-1: die Belegung folgt dem mitgegebenen Fenster des Providers', () => {
    const messages = [{ role: 'user' as const, content: 'x'.repeat(42000) }] // ~10k tok
    const small = estimateContextUsage(messages, 8192)
    const dgx = estimateContextUsage(messages, 262144)
    expect(small.remaining).toBe(0) // 10k > 8192 → full
    expect(dgx.remaining).toBe(262144 - dgx.tokens.total)
    expect(dgx.percent).toBeLessThan(small.percent)
  })

  it('breaks down tokens by role for the status bar', () => {
    const messages = [
      { role: 'user' as const, content: 'user'.repeat(50) },
      { role: 'assistant' as const, content: 'assistant'.repeat(50) },
    ]
    const usage = estimateContextUsage(messages, 4096)
    // the breakdown fields exist and add up correctly
    expect(usage.tokens.user).toBeGreaterThan(0)
    expect(usage.tokens.assistant).toBeGreaterThan(0)
    expect(usage.tokens.system).toBe(0)
    expect(usage.percent).toBeGreaterThan(0)
    expect(usage.percent).toBeLessThanOrEqual(100)
  })
})
