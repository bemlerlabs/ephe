/**
 * Ephe — client-side context compaction (Phase F1)
 *
 * Deterministic mirror of the backend function
 * `core.conversation_compactor.compact_history`: old turns are compressed into ONE
 * system message (a structured working-memory ledger), the latest turns stay.
 *
 * Why client-side: the PWA is offline-first (AGENTS.md) — the context meter
 * (contextMeter.ts) measures locally, so compaction has to work locally without
 * the backend being reachable. On the next turn the backend additionally applies
 * `compact_history`; that is idempotent (≤28 messages are passed through
 * unchanged), so double compaction is not a problem.
 *
 * ponytail: mirror of the backend compactor — both implementations must be kept
 * in sync (keyword lists + defaults). Upgrade path: a shared
 * contract test (the same fixtures frontend/backend).
 */
import { estimateTokens } from './contextMeter'
import type { ChatMessage } from '@/types'

export interface CompactStats {
  before: number
  after: number
  compactedCount: number
  keptRecent: number
  tokensBefore: number
  tokensAfter: number
  /** false when the session was ≤ COMPACT_MAX_MESSAGES (nothing to do). */
  changed: boolean
}

export interface CompactResult {
  compacted: ChatMessage[]
  stats: CompactStats
}

/** Identical to `core/conversation_compactor.py` (keep in sync) */
export const COMPACT_MAX_MESSAGES = 28
// W18 parity: reference A protect_last_n=10, protect_first_n=1
export const COMPACT_KEEP_RECENT = 10
export const COMPACT_PROTECT_FIRST_N = 1
/** Ledger summary cap (G8: backend `_build_working_memory(max_chars=3600)`) */
export const COMPACT_MAX_SUMMARY_CHARS = 3600

/** The ledger's fixed opening lines (mirror of `conversation_compactor._LEDGER_HEADER`). */
const LEDGER_HEADER = [
  'Working Memory Ledger for Ephe.',
  'Conversation working memory for Ephe.',
  'Use this compact context as durable state; do not expose it verbatim unless the user asks.',
]

/**
 * A stored turn whose text opens with the ledger preamble is compaction's
 * context, whatever role the mirror carries. The chat renders it through
 * SystemContextBlock so it never reads as an answer.
 */
export function carriesWorkingMemoryPreamble(content: string): boolean {
  const head = content.trimStart()
  return head.startsWith(LEDGER_HEADER[0]!) || head.startsWith(LEDGER_HEADER[1]!)
}

/** Keyword lists, identical to `conversation_compactor._LEDGER_BUCKETS` (keep in sync). */
const PREFERENCES = ['präferenz', 'preference', 'bevorzug', 'strikt lokal', 'keine cloud']
const PROJECT_FACTS = ['projekt', 'project', 'repo', 'repository', 'workspace']
const DECISIONS = ['entscheidung', 'decision', 'beschlossen', 'wir machen']
const ARTIFACTS = ['artefakt', 'artifact', '.pdf', '.svg', '.png', 'downloads/']
const TASKS = ['todo', 'aufgabe', 'nächster schritt', 'next step', 'fix', 'testen', 'pytest']

/** Ledger sections in render order, with the weight that shares the cap. */
const LEDGER_SECTIONS = [
  { header: '## User preferences', weight: 1 },
  { header: '## Project facts', weight: 2 },
  { header: '## Decisions', weight: 3 },
  { header: '## Artifacts', weight: 3 },
  { header: '## Open tasks and validation', weight: 3 },
  { header: '## Other relevant context', weight: 3 },
]

/**
 * Compacts a message list: ≤ maxMessages → unchanged; otherwise
 * `older` → working-memory ledger (one system message), `recent` stays.
 */
export function compactMessages(
  messages: ChatMessage[],
  opts: { maxMessages?: number; keepRecent?: number; protectFirstN?: number } = {},
): CompactResult {
  const maxMessages = opts.maxMessages ?? COMPACT_MAX_MESSAGES
  const keepRecent = opts.keepRecent ?? COMPACT_KEEP_RECENT
  const tokensBefore = messages.reduce((sum, m) => sum + estimateTokens(m.content), 0)

  if (messages.length <= maxMessages) {
    return {
      compacted: [...messages],
      stats: {
        before: messages.length,
        after: messages.length,
        compactedCount: 0,
        keptRecent: messages.length,
        tokensBefore,
        tokensAfter: tokensBefore,
        changed: false,
      },
    }
  }

  const recent = messages.slice(-keepRecent)
  // W18 parity: first protection (protect_first_n) + middle compression.
  const protectFirstN = opts.protectFirstN ?? COMPACT_PROTECT_FIRST_N
  const first = messages.slice(0, protectFirstN)
  const older = messages.slice(protectFirstN, -keepRecent)
  if (older.length === 0) {
    return {
      compacted: [...messages],
      stats: {
        before: messages.length,
        after: messages.length,
        compactedCount: 0,
        keptRecent: messages.length,
        tokensBefore,
        tokensAfter: tokensBefore,
        changed: false,
      },
    }
  }
  const ledger: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'system',
    content: buildWorkingMemory(older),
    timestamp: Date.now(),
  }
  const compacted = [...first, ledger, ...recent]
  const tokensAfter = compacted.reduce((sum, m) => sum + estimateTokens(m.content), 0)
  return {
    compacted,
    stats: {
      before: messages.length,
      after: compacted.length,
      compactedCount: older.length,
      keptRecent: recent.length,
      tokensBefore,
      tokensAfter,
      changed: true,
    },
  }
}

/**
 * Structured working-memory ledger built from old turns (same categories +
 * keyword lists as `conversation_compactor._build_working_memory`).
 * ponytail: capped at COMPACT_MAX_SUMMARY_CHARS (default 3600) like the backend —
 * the upgrade route is the maxSummaryChars parameter, if the ledger should grow.
 */
export function buildWorkingMemory(
  messages: ChatMessage[],
  maxSummaryChars: number = COMPACT_MAX_SUMMARY_CHARS,
): string {
  const preferences: string[] = []
  const projectFacts: string[] = []
  const decisions: string[] = []
  const artifacts: string[] = []
  const tasks: string[] = []
  const context: string[] = []

  for (const msg of messages) {
    const content = clean(msg.content)
    if (!content) continue
    const lower = content.toLowerCase()
    const item = `${msg.role}: ${content.slice(0, 280)}`
    // P0-4: multi-bucket — one message can sit in several categories.
    // No last-write-wins; every hit is appended. In sync with the backend.
    let matched = false
    if (PREFERENCES.some((w) => lower.includes(w))) {
      preferences.push(item)
      matched = true
    }
    if (PROJECT_FACTS.some((w) => lower.includes(w))) {
      projectFacts.push(item)
      matched = true
    }
    if (DECISIONS.some((w) => lower.includes(w))) {
      decisions.push(item)
      matched = true
    }
    if (ARTIFACTS.some((w) => lower.includes(w))) {
      artifacts.push(item)
      matched = true
    }
    if (TASKS.some((w) => lower.includes(w))) {
      tasks.push(item)
      matched = true
    }
    if (!matched) context.push(item)
  }

  const buckets = [preferences, projectFacts, decisions, artifacts, tasks, context]
  const bodies = buckets.map((items) => bullets(dedupe(items)).join('\n'))
  const sizes = LEDGER_SECTIONS.map((s, i) => s.header.length + 1 + bodies[i]!.length)
  const head = LEDGER_HEADER.join('\n') + '\n\n'
  const full = head + LEDGER_SECTIONS.map((s, i) => `${s.header}\n${bodies[i]}`).join('\n\n')
  if (full.length <= maxSummaryChars) return full

  // The cap is shared across sections by weight; an over-long section keeps its
  // most recent entries, so a burst of low-value text cannot evict a decision.
  const budgets = shareBudget(
    maxSummaryChars - head.length,
    LEDGER_SECTIONS.map((s) => s.weight),
    sizes,
  )
  const fitted =
    head +
    LEDGER_SECTIONS.map((s, i) => clipSection(s.header, bodies[i]!, budgets[i]!)).join('\n\n')
  return fitted.slice(0, maxSummaryChars)
}

/** Integer shares of `remaining` across sections by weight (mirror of `_share_budget`). */
function shareBudget(remaining: number, weights: number[], sizes: number[]): number[] {
  const budget = sizes.map(() => 0)
  let active = sizes.map((_, i) => i)
  let left = remaining
  while (active.length > 0 && left > 0) {
    const shares = largestRemainder(
      left,
      active.map((i) => weights[i]!),
    )
    let progressed = false
    const still: number[] = []
    active.forEach((idx, pos) => {
      const take = Math.min(shares[pos]!, sizes[idx]! - budget[idx]!)
      budget[idx] = budget[idx]! + take
      left -= take
      if (take > 0) progressed = true
      if (budget[idx]! < sizes[idx]!) still.push(idx)
    })
    if (!progressed) break
    active = still
  }
  return budget
}

/** Integer shares of `amount` by weight; the shares sum to `amount`. */
function largestRemainder(amount: number, weights: number[]): number[] {
  const total = weights.reduce((sum, w) => sum + w, 0)
  if (total <= 0) return weights.map(() => 0)
  const shares = weights.map((w) => Math.trunc((amount * w) / total))
  const order = weights
    .map((w, i) => ({ i, rem: (amount * w) % total }))
    .sort((a, b) => b.rem - a.rem || a.i - b.i)
  const leftover = amount - shares.reduce((sum, s) => sum + s, 0)
  for (let k = 0; k < leftover; k++) shares[order[k]!.i]! += 1
  return shares
}

/** Clips one section to `budget` characters, keeping its most recent entries. */
function clipSection(header: string, body: string, budget: number): string {
  if (budget <= header.length + 1) return header
  const room = budget - header.length - 1
  if (body.length <= room) return `${header}\n${body}`
  return `${header}\n${body.slice(body.length - room)}`
}

function dedupe(items: string[]): string[] {
  return [...new Set(items)]
}

function bullets(items: string[]): string[] {
  return items.length > 0 ? items.map((i) => `- ${i}`) : ['- Keine stabilen Fakten erkannt.']
}

function clean(text: string): string {
  return text.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim()
}
