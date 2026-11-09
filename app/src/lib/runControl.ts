/**
 * The one stop the composer already owns, reachable from the run view.
 *
 * The chat model holds the abort controller. The run view must call that same
 * function, so a second abort path cannot drift from the first.
 */

type Stop = () => void

let stop: Stop | null = null

export function registerRunStop(fn: Stop): () => void {
  stop = fn
  return () => {
    if (stop === fn) stop = null
  }
}

export function requestRunStop(): void {
  stop?.()
}
