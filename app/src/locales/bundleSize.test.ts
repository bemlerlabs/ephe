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
// The first open added the greeting, four stops and the desk: 30 keys. Measured
// on 2026-10-17 at +2,504 B in en.json (112,004 B) and +2,895 B in de.json
// (121,395 B). The ceilings also hold the workspaces clarity lane's keys when it
// lands (+1,134 / +1,261), so they move to 114,000 / 124,000 once.
// Raised again on 2026-10-17 (the four-audit round): the replay step count, the
// artifact detail hint, the engine-error sentence and its setup action, the
// turn-failed label, and the six clear-all/dialog keys added 219 B in en.json
// (114,219 B) and 194 B in de.json. Both halves move by the same 1,000 B, which
// leaves room for the German side of the next copy fix without reaching the band.
// Raised on 2026-10-19 for Wave 2, measured as committed: B1's custom-instruction card
// (3 keys), B2's stage and rule-file status rows (7 keys), B3's ask-more toggles
// (3 keys) and B4's reasoning-effort row (4 keys) put en.json at 116,584 B and de.json
// at 126,400 B — +584 B / +400 B over the ceilings this wave inherited. Both halves
// move by the same 1,000 B so a later slice is not forced to raise the band mid-cut.
// Raised on 2026-10-20 for Wave 5B: the companion quick panel and studio card
// add twelve control and description keys. Measured en 117,574 B / de 127,488 B.
// Raised again the same day for Wave 5C's appearance profile (three rows and
// five refusal reasons): measured en 118,861 B / de 128,907 B. Both halves move
// by 2,000 B, as the previous waves did.
// Raised on 2026-10-22 for the Agent Center and Agent Teams surfaces: 125
// product strings each (list and editor labels, model and budget fields, run
// states, six template names and descriptions, permission rows). Measured as
// committed: en.json 125,353 B and de.json 135,881 B, +5,353 B / +5,881 B over
// the numbers this wave inherited. Both halves move by the same 2,000 B; every
// key carries German, and the four same-by-design leaves (Name, Ephe, Plugin,
// Budget) are named in germanSurface.test.ts. The unused extension-hub keys were
// removed before the measurement rather than shipped as dead strings.
// Raised on 2026-10-22 for the Extension Center: 49 marketplace strings
// (sources, discover, updates, trust, permission review and actions). Measured
// as committed: en.json 127,453 B and de.json 138,213 B. Both halves move by
// 1,400 B; the three same-by-design leaves (HTTPS, Details, Version) are named
// in germanSurface.test.ts.
// Raised on 2026-10-25 for the 0.1.6 patch: the setup page's probe/save progress
// sentences and the tools page's two field labels added 4 keys per file, measured
// as committed: en.json 129,049 B and de.json 139,895 B. Both halves move by
// 1,000 B so the pair keeps its ratchet step.
// Raised on 2026-10-26 for the engine-key repair: the setup page names the
// mismatch, both engines, the key source and the four actions. Measured as
// committed: en.json 130,623 B and de.json 141,551 B, +627 B / +733 B over the
// numbers this lane inherited. Both halves move by 1,000 B, the same step the
// earlier waves took.
// Raised on 2026-10-27 for the companion's co-pilot (QD-005): the three mode
// labels, the countdown and cancel row, the receipt heading and the 24 action and
// reason strings of the five surface targets. Measured as committed: en.json
// 132,420 B and de.json 143,458 B, +1,371 B / +1,458 B over the inherited
// numbers. Both halves move by 1,000 B, the same step the earlier waves took.
// Raised on 2026-10-27 for QD-009: one build-parity sentence, the artifact row's
// reveal/open verbs and their refusal line, and the interrupted word the helper
// directory needs. Measured as committed: en.json 133,274 B and de.json 144,383 B,
// +371 B / +414 B over the inherited numbers. Both halves move by 500 B.
// Raised on purpose on 2026-10-28 (QD-012): the codebase index adds the
// `codebase.*` block — pill, dialog, progress and failure lines — twelve leaves in
// both files. Measured en.json 133,870 B and de.json 145,056 B (278,926 B together),
// so the ceilings move by the measured delta and keep the ~600 B headroom the
// earlier waves held.
// G3 + C1: capability matrix, stage switch and the swarm deck's five strings.
// Raised on 2026-10-28 (QD-013): the companion countdown row and readout, plus the
// co-pilot's codebase-index action and reason. Measured as committed: en.json
// 136,036 B and de.json 147,373 B; both halves take the ~600 B headroom again.
// Grown again on 2026-10-28 (E2, C2): the approval card names its three actions
// ("Allow once" / "Einmalig") and the deck's seal carries the guard's tool count.
// Measured as committed: en.json 135,271 B and de.json 146,565 B, so both halves
// move to keep the ~600 B headroom the earlier waves held.
// Raised on purpose on 2026-10-28 (QD-014): the Skills Studio adds the builder
// card (ten keys: title, hint, open, name, trigger, description, prompt, create,
// created, failed), the pack preview's show-all/show-less pair, the run chip, the
// verified-recipe seal and the provenance label; the marketplace adds its try-in-
// chat button and the catalog seal. Seventeen leaves in both files, measured as
// committed: en.json 137,002 B and de.json 148,410 B, +966 B / +1,037 B over the
// numbers this wave inherited. Both halves move by the same 1,000 B, which keeps
// the ~600 B headroom the earlier waves held.
// 2026-10-29 (E2): the deny-with-correction row added three leaves to both
// files. Measured from app/src/locales: en 137 613 B, de 149 093 B; the rows
// carry ~40 B and ~57 B of headroom, the same shape the notes above describe.
// 2026-10-29 (P2): the one-click setup button added four leaves per file
// (setup.oneClick, oneClickHint, oneClickRunning, oneClickNone). Measured:
// en 137 876 B, de 149 370 B — each half moves by ~300 B, headroom ~74/~80 B.
// 2026-10-29 (R3): the tool catalog card added four leaves per file
// (tools.catalogTitle, catalogHint, catalogSafe, catalogAsks). Measured:
// en 138 081 B, de 149 602 B — headroom ~79/~88 B.
// 2026-10-29 (SOL): the insight card and the rules inspector add thirteen leaves
// per file (learned, open, group, empty and its hint, unavailable and its hint,
// edit and its hint, action label, save, delete, confirm delete). Measured as
// committed: en 138 719 B, de 150 343 B — both halves move by 1,000 B, the step
// the earlier waves took, which keeps the ~600 B headroom.
// 2026-10-29 (capabilities): the catalog's switches and the helper's allow-list
// editor add ten leaves per file (on-count, filter, switch label, locked, failed,
// allow title, hint, pick, add, remove). Measured as committed: en 139 320 B,
// de 151 028 B — both halves move by 1,000 B, the step the earlier waves took.
// Lowered on 2026-10-30 by measuring again: the in-Settings marketplace surfaces
// moved to /discover and 69 dead `market*` keys per file went with them — en
// 140,411 B → 137,362 B, de 152,236 B → 148,893 B.
// 2026-10-30 (discover S3): the bento, the section heads and the detail surface
// add ~1.2 kB per file (badge, see-all, detail labels, category names). Measured
// as committed: en 138,620 B, de 150,266 B.
// 2026-10-30 (Y5 + Y6): the credential fields inside the discover sheet and the
// vault area with its five nav groups add 1,351 B to en.json and 1,467 B to de.json.
// Measured as committed: en 139,971 B, de 151,733 B — the halves move by the
// measured delta and keep the ~600 B headroom the earlier waves held.
// 2026-10-30 (discover wave): the featured pick, the weekly-downloads line and the
// popular badge add 98 B to en.json and 105 B to de.json. Measured as committed:
// en 140,651 B, de 152,472 B — both halves move by 700 B, the step the earlier
// waves took, which keeps the ~600 B headroom.
// 2026-10-30 (store shelf): the page became a store — a segmented toolbar with two
// menu labels, a subject line for every section, the pick's own fact rail and a named
// add verb (actionAddNamed, bentoLede, detailKind, detailSource, facetAnyOrigin and the
// grouped download count). Three dead band keys left in the same pass (eyebrow,
// headline, lede of the removed hero band, −228 B in en.json). Measured as committed:
// en 141,912 B, de 153,765 B — both halves move by the measured step plus the ~600 B
// headroom the earlier waves held.
// 2026-10-31 (tools catalogue, then the featured shelf): six family names, then the
// featured tier's five labels. Measured as committed: en 142,821 B, de 154,687 B —
// both halves move by 400 B, the step the earlier waves took.
const EN_CEILING = 143_200
const DE_CEILING = 155_100
// The pair may reach what its two halves allow. It was 200_000 from the 2026-10-11
// snapshot, which made it stricter than the two numbers it sums — a total that can only
// fire where no per-file ceiling does says nothing the halves do not say. Raised on
// purpose on 2026-10-14 for the workspaces page (86 keys, 4,770 B in en.json); the halves
// remain the ratchet. Since the WD-33 split the sum is no longer a download cost at all:
// no reader fetches both files. It stands as the census of the pair, and the per-language
// numbers above are what a user pays. Raised again on 2026-10-14 (n1-publish): the change
// set's life adds 14 workspaces keys and three coded refusals — measured +1,427 B in
// en.json and +1,793 B in de.json, both halves moved on purpose with the ceilings. A
// third time on 2026-10-18 for the model picker's `modelPicker` namespace (22 keys,
// measured +710 B in en.json and +760 B in de.json): a new surface pays its own words,
// and the halves stay the ratchet.
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
