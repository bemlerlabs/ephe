/**
 * Register #37 — one authoritative offline recipe.
 *
 * The interface answered "the backend is down" with two different commands. The
 * toast a refused send raises (`chat.sendOffline`) named `./dev.sh`, a script
 * that exists in the checkout and in no shipped build, so a user of the
 * installed product ran a file they do not have and reached a dead end. The
 * bubble a failed stream raises (`chat.offlineStreamError`) named `ephe doctor`.
 * Both describe one recovery, so the product owes one command.
 *
 * The installer is the only surface a user has already run, so its own printed
 * commands are the source of truth: the closing block of `install.sh` prints
 * `ephe configure`, `ephe doctor`, `ephe tui` and `ephe start --open`,
 * `docs/INSTALL.md` repeats them, and `core/_cli_onboarding.py` ends on
 * "Start the app with: ephe start". The web surface therefore recovers with
 * `ephe start`, and `ephe doctor` stays the step that reads back what is wrong.
 *
 * The strings live in the locale bundles, which this wave hands to the
 * orchestrator, so the one value that still names a repository script is listed
 * in `KNOWN`. The test fails the moment a second such value appears, and fails
 * once the listed one is fixed but left behind in the list, because `KNOWN` has
 * to equal the tree.
 */
import { describe, it, expect } from 'vitest'
import en from './en.json'
import de from './de.json'

type Bundle = typeof en

/** Every string the interface shows when the backend gives no answer. */
const RECIPE_KEYS: Array<[string, (l: Bundle) => string]> = [
  ['chat.sendOffline', (l) => l.chat.sendOffline],
  ['chat.offlineStreamError', (l) => l.chat.offlineStreamError],
  ['tools.errorOffline', (l) => l.tools.errorOffline],
]

/** A script that ships inside the checkout and in no installed build. */
const REPO_ONLY = /(?:^|[\s`(])(?:\.\/)?[\w.-]+\.(?:sh|py)\b|\bnpm\s+run\b|\bpnpm\b|\bvite\b/

/** A command the installer itself prints, so a user already has it on PATH. */
const INSTALLED = /\bephe (?:configure|doctor|tui|start|serve|update)\b/

/**
 * The values still pointing at a checkout script, pending the bundle handoff.
 * The orchestrator owns `en.json`/`de.json`; empty this set when the fix lands.
 */
const KNOWN = new Set<string>([])

const BUNDLES: Array<[string, Bundle]> = [
  ['en', en],
  ['de', de as Bundle],
]

function repoOnlyKeys(): string[] {
  const found: string[] = []
  for (const [_lng, bundle] of BUNDLES) {
    for (const [key, get] of RECIPE_KEYS) {
      if (REPO_ONLY.test(get(bundle))) found.push(key)
    }
  }
  return [...new Set(found)]
}

describe('the recovery the interface offers when the backend gives no answer', () => {
  it('names a checkout script only in the handoff-listed value', () => {
    expect(new Set(repoOnlyKeys())).toEqual(KNOWN)
  })

  it('keeps at least one recipe on a command the installer prints', () => {
    const named = BUNDLES.flatMap(([_lng, bundle]) =>
      RECIPE_KEYS.map(([, get]) => get(bundle)).filter((value) => INSTALLED.test(value)),
    )
    expect(named.length).toBeGreaterThan(0)
  })
})
