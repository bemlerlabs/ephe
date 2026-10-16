/**
 * The install flag the first-run scene is gated on.
 *
 * It sits in `lib/` because `main.tsx` reads it at boot, before it decides whether to
 * fetch the scene's chunk: a browser that carries the flag downloads nothing for a scene
 * it would not show. One key, spelled once, so the boot gate and the scene itself can not
 * disagree about where the answer lives.
 */

/** Written once per browser, when the scene ends. The value is the moment it did. */
export const INTRO_SEEN_KEY = 'ephe.intro.seen.v1'

/**
 * Whether this browser carries the flag.
 *
 * A store that refuses to be read (a hardened browser, blocked site data) answers `true`:
 * the scene is decoration over an app that is already usable underneath it, and a load
 * that can not remember having run it would bring it back on every reload.
 */
export function hasSeenFirstRunIntro(): boolean {
  try {
    return window.localStorage.getItem(INTRO_SEEN_KEY) !== null
  } catch {
    return true
  }
}

/** Writes the flag. A refused store costs the next load one replay of the scene. */
export function markFirstRunIntroSeen(stamp: string): void {
  try {
    window.localStorage.setItem(INTRO_SEEN_KEY, stamp)
  } catch {
    /* the replay on the next load is the whole cost */
  }
}
