/**
 * Ephe — context meter (P2-5)
 *
 * Estimates how full a session's context is, deterministically from its
 * messages. Offline-first: no backend token usage is needed, the estimate is a
 * pure function over the messages.
 *
 * Chars per token is a heuristic and not a tokenizer: the ratio of a Latin run differs
 * between engines, and 4.2 is the conservative end of the band this meter was calibrated
 * on. The window belongs to the caller — the status bar passes `window_tokens` from
 * /api/context/budget and the compacting path passes the `context_window` the provider
 * list reports — so the constant below is only what the meter uses before either has
 * answered.
 */
import { formatNumber } from './dateLocale'

/** chars-per-token heuristic for a Latin run; every tokenizer answers differently */
export const CHARS_PER_TOKEN = 4.2

/** fallback window for a meter whose backend has not reported one yet */
export const CONTEXT_WINDOW_TOKENS = 8192

/** CJK counts as ~1 token per character in the tokenizer (calibration, P0-3) */
export const CJK_TOKENS_PER_CHAR = 1

export interface TokenBreakdown {
  system: number
  user: number
  assistant: number
  total: number
}

export interface ContextUsage {
  tokens: TokenBreakdown
  percent: number // 0..100, clamped
  remaining: number // tokens left
  window: number
}

/** Counts CJK ideographs/characters (tokenizer ~1 token per character). */
function isCjk(ch: string): boolean {
  const code = ch.charCodeAt(0) ?? 0
  // prettier-ignore-start — hex ranges are the Unicode-block granularity
  return (
    (code >= 0x3000 && code <= 0x30ff) ||
    (code >= 0x3400 && code <= 0x4dbf) ||
    (code >= 0x4e00 && code <= 0x9fff) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xff00 && code <= 0xffef) ||
    (code >= 0x31f0 && code <= 0x31ff)
  )
}
// prettier-ignore-end

/** Estimates the token count of a text (two buckets: CJK 1:1, Latin 4.2). */
export function estimateTokens(text: string): number {
  if (!text) return 0
  const trimmed = text.trim()
  if (!trimmed) return 0
  let cjk = 0
  for (const ch of trimmed) if (isCjk(ch)) cjk += 1
  const latin = trimmed.length - cjk
  // Conservative round-up for the safety margin (parity: core/usage.py).
  return Math.ceil(cjk * CJK_TOKENS_PER_CHAR + latin / CHARS_PER_TOKEN)
}

/** Estimates the context fill of a session over its messages. */
export function estimateContextUsage(
  messages: Array<{ role: string; content: string }>,
  window = CONTEXT_WINDOW_TOKENS,
): ContextUsage {
  let system = 0
  let user = 0
  let assistant = 0

  for (const msg of messages || []) {
    const tokens = estimateTokens(msg.content || '')
    switch (msg.role) {
      case 'system':
        system += tokens
        break
      case 'user':
        user += tokens
        break
      case 'assistant':
        assistant += tokens
        break
      default:
        user += tokens // unknown role → user message (safe)
    }
  }

  const total = system + user + assistant
  const percent = window > 0 ? Math.min(100, Math.round((total / window) * 100)) : 100
  const remaining = Math.max(0, window - total)

  return {
    tokens: { system, user, assistant, total },
    percent,
    remaining,
    window,
  }
}

/**
 * Curated formatting of the percent display (status bar).
 *
 * The separator follows the interface language. A bare `${percent}%` took the dot
 * from the number itself, so the German row printed "72.63%" next to "5.950 tok"
 * and "2.242 frei" — one line, two number languages (measured 2026-10-10).
 */
export function formatPercent(percent: number, language?: string): string {
  return `${formatNumber(percent, language, 2)}%`
}

/** Warning threshold: from this fill the meter turns red / suggests compacting. */
export const WARN_THRESHOLD = 0.75
