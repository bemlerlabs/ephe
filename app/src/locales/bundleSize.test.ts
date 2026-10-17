/**
 * WD-33 — the locale weight budget.
 *
 * `src/i18n.ts` used to import `./locales/en.json` and `./locales/de.json` at the top of
 * the module, which put both files in the entry chunk: every byte here was downloaded by
 * every user before the first paint, in both languages. Since the WD-33 split each
 * catalog is a chunk of its own and is fetched when its language is chosen, so a file's
 * size is what one reader of that language pays — the honest proxy the ceilings measure.
 * (`src/i18n.lazySplit.test.ts` guards the split itself; this file weighs the bytes.)
 *
 * The ceilings sit just above the sizes measured on 2026-10-11 and behave as a
 * ratchet: a translation wave that pushes a file past its number fails here and has
 * to raise that number on purpose. A ceiling nobody can reach would measure nothing.
 *
 * Key parity and placeholder correctness live in the neighbour gates
 * (`completeness.test.ts`, `../lib/locales.test.ts`). This file measures weight only.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findLocales(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src', 'locales')
    if (existsSync(resolve(candidate, 'de.json'))) return candidate
  }
  throw new Error(`app/src/locales not found below ${process.cwd()}`)
}
const LOCALES = findLocales()
const size = (name: string) => statSync(resolve(LOCALES, name)).size

// Snapshot 2026-10-11: en ~90 KB, de ~96 KB (~186 KB together). The two files move
// as translation work lands, so the ceilings are the line that holds, not the bytes.
// Raised on purpose on 2026-10-14 (wave 4): the session-store row adds 13 keys
// (~1.0 KB in en.json, ~1.1 KB in de.json) and en.json sat 69 B under the old
// 100_000 before it — the store's dry-run row and the two counts it names had no
// copy of their own. Both halves move by the same 1,500 B, so the pair stays in
// the 1.07x band the two files are measured in.
// Raised again on purpose on 2026-10-14 (the fleet and ask lanes). 31 leaf keys
// arrived — 24 the fleet board's (workspaces.runState, workspaces.fleet and the
// stale line) and 7 the ask card's (chat.ask*) — and each lane had measured only
// its own delta, so the two sums met here for the first time. One of the seven was
// a duplicate and did not become a key: chat.askSend said "Send"/"Senden", the same
// word in both languages as chat.send, so the card's send button reads chat.send
// and the key is gone from both files (30 new leaves, not 31). The rest are new
// words rather than English homonyms: the two that collide in English only —
// runState.running ("working", beside chat.rowWorking) and runState.done ("done",
// beside settings.taskToggle) — read "arbeitet" and "fertig" in German where the
// neighbours read "Läuft" and "Erledigt", so they are not that string either. The
// two plural bases (fleet.count, fleet.needsYou) repeat their own _one form, as 30
// of the catalog's other 34 plural groups carry a base identical to one of their
// two forms. Both halves move by the same 1,000 B and stay in the 1.08x band; each
// sits 358 B / 388 B under the new number with the reuse counted.
// Raised once more on purpose on 2026-10-14 (the cli, docs, memory and onboard lanes —
// the four that merged after the fleet/ask pair). Eleven leaf keys arrived: six the fact
// editor's under agentPanel.trajectoryFact* and five the setup page's (setup.keyHelp*,
// setup.localHint*). trajectoryFactRewrite said "Rewrite" and the same component already
// read memoryRewriteAction for the button six lines above it, so turnMemories.tsx:116 now
// reads that key and it is gone from both files: ten new leaves, not eleven. All ten are
// new words and all ten carry German, so none is an English homonym that another key could
// have served. Each half moves 566 B / 552 B and stays in the 1.08x band.
// Raised again on 2026-10-14 (n1): the custody page adds 32 keys to each file (the
// two steps of the signature, the byte comparison, the two refusals), which is
// 1,722 B in en.json and 2,046 B in de.json — no trim of the copy could have found
// that under the 562 B en.json had left. Both halves move by the same 2,500 B again.
// Set here from the merged tree, not from a lane's own number: each lane measured its
// ceiling against a tree that lacked the keys the other two brought, so 104_000 / 112_000
// and 103_000 / 111_500 each stood over a catalog that was not this one. The third lane
// raised nothing: its three collision keys add 295 B in en.json and 320 B in de.json,
// under the numbers it inherited. Measured as committed, after the three merges — en.json
// 106,722 B and de.json 115,678 B — with the 1.08x band the two files sit in held to.
// Raised again on 2026-10-15 by two lanes that met in one worktree. The session header's
// workspace-instruction badge added two keys (header.workspaceRules, header.workspaceRulesHint):
// 113 B in en.json and 112 B in de.json. The change-set lane's two coded refusals
// (workspaces.change_set_approval_superseded, workspaces.change_set_unpublish_refused) added
// 298 B and 350 B to the same two files. Before either landed the halves read en.json 107,253 B
// and de.json 116,209 B, so 247 B and 291 B stood under the numbers above and the two deltas met
// each other here. All four keys are new words with their own German; none is a homonym an
// existing key could have served. Both halves move by the same 500 B: en.json 107,664 B and
// de.json 116,671 B, which holds the 1.08x band the two files are measured in.
// The update dialog's Details block names the package, the two versions, the
// size and the notes the feed carried, and a held-back restart needs its own
// sentence; 12 keys added 1,255 B in en.json and 1,421 B in de.json, so both
// halves move by the same 1,500 B and the 1.08x band holds.
const EN_CEILING = 109_500
const DE_CEILING = 118_500
// The pair may reach what its two halves allow. It was 200_000 from the 2026-10-11
// snapshot, which made it stricter than the two numbers it sums — a total that can only
// fire where no per-file ceiling does says nothing the halves do not say. Raised on
// purpose on 2026-10-14 for the workspaces page (86 keys, 4,770 B in en.json); the halves
// remain the ratchet. Since the WD-33 split the sum is no longer a download cost at all:
// no reader fetches both files. It stands as the census of the pair, and the per-language
// numbers above are what a user pays. Raised again on 2026-10-14 (n1-publish): the change
// set's life adds 14 workspaces keys and three coded refusals — measured +1,427 B in
// en.json and +1,793 B in de.json, both halves moved on purpose with the ceilings.
const TOTAL_CEILING = EN_CEILING + DE_CEILING
// German runs 1.07x English here (96,075 / 89,756). A pair far outside that range
// is a defect rather than a translation: a duplicated block, or English pasted into
// the German file and left half-migrated.
const MAX_INFLATION = 1.4

describe('locale weight budget', () => {
  const en = size('en.json')
  const de = size('de.json')

  it('reports what the pair weighs', () => {
    console.log(`locale weight: en ${en} B, de ${de} B, both ${en + de} B`)
    expect(en).toBeGreaterThan(0)
    expect(de).toBeGreaterThan(0)
  })

  it('keeps each file under its own ceiling', () => {
    expect(en, `en.json ${en} B exceeds ${EN_CEILING} B`).toBeLessThanOrEqual(EN_CEILING)
    expect(de, `de.json ${de} B exceeds ${DE_CEILING} B`).toBeLessThanOrEqual(DE_CEILING)
  })

  it('keeps the pair under the combined ceiling', () => {
    expect(en + de, `locales ${en + de} B exceed ${TOTAL_CEILING} B`).toBeLessThanOrEqual(
      TOTAL_CEILING,
    )
  })

  it('keeps German in a plausible range of English', () => {
    expect(de / en, `de/en = ${(de / en).toFixed(3)} exceeds ${MAX_INFLATION}`).toBeLessThanOrEqual(
      MAX_INFLATION,
    )
  })
})
