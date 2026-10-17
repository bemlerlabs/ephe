/**
 * Pure building blocks of the command palette (toggles, fuzzy scoring, usage
 * frequency). Its own module: keeps useCommandPalette under the architecture line
 * (maxFileLines 400) and makes each function testable on its own.
 */

// G6 (parity audit 2026-09-04): usage frequency per command, so the most used ones
// appear on top. localStorage = native, no dependency. Best effort (private mode → empty).
// P1-3 (parity audit 2026-10-13): the counter now also carries the last use, so the
// score can decay. A bare count pinned a once-hot command to the top forever.
const FREQ_KEY = 'ephe_cmd_freq'

/** One persisted usage entry: how often a command ran, and when it last did. */
export interface FreqEntry {
  count: number
  lastUsedAt: number
}

/**
 * The persisted usage map in the current `{count, lastUsedAt}` shape. A legacy bare
 * number (written before P1-3) migrates to `{count, lastUsedAt: 0}`: an unknown
 * timestamp cannot claim recency, so that entry simply decays away.
 */
export function readFrecency(): Record<string, FreqEntry> {
  try {
    const raw = JSON.parse(localStorage.getItem(FREQ_KEY) || '{}') as Record<
      string,
      FreqEntry | number
    >
    const out: Record<string, FreqEntry> = {}
    for (const [id, v] of Object.entries(raw)) {
      if (typeof v === 'number') out[id] = { count: v, lastUsedAt: 0 }
      else if (v && typeof v.count === 'number')
        out[id] = { count: v.count, lastUsedAt: v.lastUsedAt || 0 }
    }
    return out
  } catch {
    return {}
  }
}

/**
 * Counts only, keyed by id — the shape every existing reader expects (their arithmetic
 * stays a number). A projection of `readFrecency`, so no reader has to change.
 */
export function readFreq(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [id, e] of Object.entries(readFrecency())) out[id] = e.count
  return out
}

/** Bumps a command-run counter by one and stamps the time (best-effort, private mode included). */
export function bumpFreq(id: string): void {
  try {
    const f = readFrecency()
    const prev = f[id]
    f[id] = { count: (prev?.count || 0) + 1, lastUsedAt: Date.now() }
    localStorage.setItem(FREQ_KEY, JSON.stringify(f))
  } catch {
    /* localStorage full / private mode — frequency is best-effort; the core path stays */
  }
}

/** One week, the decay half-life. */
const WEEK_MS = 7 * 24 * 60 * 60 * 1000

/**
 * P1-3: recency-weighted frecency as a multiplier on a command's score:
 * `(1 + 0.15·ln(1+count)) · 0.5^(weeksSinceUse)`. A bounded boost that halves every
 * week, so one run nudges a command up while an old favourite cannot pin the top
 * forever. No entry (or a zero count) = neutral 1 — an unused command is neither
 * helped nor hurt. Exported pure for the unit test.
 */
export function frecencyMultiplier(entry?: FreqEntry, now: number = Date.now()): number {
  if (!entry || entry.count <= 0) return 1
  const weeks = Math.max(0, (now - entry.lastUsedAt) / WEEK_MS)
  return (1 + 0.15 * Math.log(1 + entry.count)) * Math.pow(0.5, weeks)
}

/** Applies the frecency multiplier to a fuzzy score (the sort key a caller uses). */
export function frecencyScore(score: number, entry?: FreqEntry, now: number = Date.now()): number {
  return score * frecencyMultiplier(entry, now)
}

/** One palette row that can be ranked: enough to score it and to look up its usage. */
export interface Rankable {
  id: string
  label: string
  section: string
}

/**
 * R63: the palette's own ordering key, one number per row. The fuzzy tier is an
 * integer — the 1000 prefix band, the 700 word-boundary band, the ≤499
 * subsequence band — and the time-decayed frecency adds a fraction strictly
 * below 1, so it can only order rows that share a tier. A scattered match can
 * therefore never outrank an exact prefix, however often it was run, and a
 * once-hot command decays back out of the top as its last use ages.
 *
 * A tie-breaker was chosen over a decayed score on purpose: multiplying the tier
 * by the frecency is unbounded in `count` (the subsequence cap 499 times a large
 * multiplier clears the 900 prefix floor), whereas a fraction under 1 provably
 * cannot. Frecency keeps its job — among equally good matches the fresher, more
 * used row leads, and with no query every tier is 1 so it orders the whole list.
 */
export function paletteRankKey(
  item: Rankable,
  query: string,
  freq: Record<string, FreqEntry> = {},
  now: number = Date.now(),
): number {
  const tier = fuzzyScore(item, query)
  if (tier <= 0) return 0
  const m = frecencyMultiplier(freq[item.id], now)
  return tier + m / (1 + m) // ∈ [tier, tier + 1) — the next tier stays out of reach
}

/**
 * R63: groups rows by section and orders each group with `paletteRankKey`, so a
 * section leads with its best match rather than its most-run one. One `now` for
 * the whole pass keeps the ordering stable. Array.sort is stable (ES2019), so
 * rows of equal rank — session entries with no usage, say — keep input order.
 */
export function groupBySection<T extends Rankable>(
  items: T[],
  query: string,
  freq: Record<string, FreqEntry> = {},
  now: number = Date.now(),
): Record<string, T[]> {
  const grouped: Record<string, T[]> = {}
  for (const item of items) {
    grouped[item.section] = [...(grouped[item.section] ?? []), item]
  }
  for (const arr of Object.values(grouped)) {
    arr.sort((a, b) => paletteRankKey(b, query, freq, now) - paletteRankKey(a, query, freq, now))
  }
  return grouped
}

/**
 * F-03: a pure toggle test — case-independent ('k' vs. 'K' under CapsLock/Shift)
 * and with a KeyK code fallback. Exported for the unit test.
 */
export function isPaletteToggle(e: {
  key: string
  code?: string
  metaKey?: boolean
  ctrlKey?: boolean
}): boolean {
  if (!(e.metaKey || e.ctrlKey)) return false
  return e.key?.toLowerCase() === 'k' || e.code === 'KeyK'
}

// P1-3: a word starts at the label start or right after a separator.
const WORD_SEP = /[\s/·–-]/

/** True when index i of the (lower-cased) label sits at a word start. */
function atWordStart(hay: string, i: number): boolean {
  return i === 0 || WORD_SEP.test(hay[i - 1] ?? '')
}

/** The first occurrence of q in hay that begins at a word start, else -1. */
function wordBoundaryIndex(hay: string, q: string): number {
  let from = 0
  for (;;) {
    const at = hay.indexOf(q, from)
    if (at < 0) return -1
    if (atWordStart(hay, at)) return at
    from = at + 1
  }
}

/** Tier 3: run-weighted scattered score. The case bonus marks an isolated hit only. */
function subsequenceScore(item: { label: string; section: string }, q: string): number {
  const hay = item.label.toLowerCase()
  let hi = 0
  let score = 0
  let run = 0
  for (let qi = 0; qi < q.length; qi++) {
    const ch = q[qi]
    let found = false
    while (hi < hay.length) {
      if (hay[hi] === ch) {
        run += 1
        score += 10 + run // consecutive runs are worth more
        const at = item.label[hi]
        // A case edge only counts for an isolated hit; a run already earns its weight.
        if (at && at !== at.toLowerCase() && run === 1) score += 5
        hi += 1
        found = true
        break
      }
      run = 0
      hi += 1
    }
    if (!found) return 0
  }
  if (item.section.toLowerCase().includes(q)) score += 2
  return Math.min(score, 499) // stays below the word-boundary band
}

/**
 * P1-2 / P1-3: weighted fuzzy scoring in three tiers — prefix > word-boundary >
 * subsequence. Higher scores win; 0 = no match. A whole-word-prefix hit (contiguous
 * match at a word start) outranks a scattered subsequence, whose case bonus can no
 * longer outvote it. Exported for the unit test.
 */
export function fuzzyScore(item: { label: string; section: string }, query: string): number {
  const q = query.toLowerCase()
  if (!q) return 1
  const hay = item.label.toLowerCase()
  // Tier 1 — exact prefix on the label (strongest signal).
  if (hay.startsWith(q)) return 1000 - Math.min(hay.length, 100)
  // Tier 2 — the query is a prefix of some word inside the label.
  if (wordBoundaryIndex(hay, q) >= 0) {
    const section = item.section.toLowerCase().includes(q) ? 2 : 0
    return 700 + Math.min(q.length * 3, 99) + section
  }
  // Tier 3 — scattered subsequence.
  return subsequenceScore(item, q)
}
