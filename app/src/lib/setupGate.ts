/**
 * I4-4: the difference between "I want to choose the engine again" and
 * "the hash is still left over from earlier".
 *
 * #/setup survives reloads (hash router). If the backend was briefly unreachable on
 * the first load, or reported `configured: false` out of a foreign config folder,
 * the app sticks in first-run — even though engine and model have long been
 * chosen and are reachable. The engine chip navigates here on purpose,
 * so the intent needs a sign of its own; without it a surviving
 * hash leads back into the chat.
 */
import { getSetupStatus, skipSetup as skipSetupRequest, type SetupStatus } from './api'

export const SETUP_INTENT_KEY = 'ephe.setup_intent'

export interface SetupGate {
  ready: boolean
  configured: boolean
  skipped: boolean
}

export function markSetupIntent(): void {
  try {
    sessionStorage.setItem(SETUP_INTENT_KEY, '1')
  } catch {
    /* Private Mode: without the mark the manual route via the chip stays open,
       only the automatic re-routing applies — no crash. */
  }
}

/** Reads and deletes the intent — it is valid for exactly one visit. */
export function consumeSetupIntent(): boolean {
  try {
    const hit = sessionStorage.getItem(SETUP_INTENT_KEY) === '1'
    sessionStorage.removeItem(SETUP_INTENT_KEY)
    return hit
  } catch {
    return false
  }
}

export function shouldLeaveSetup(gate: SetupGate, intent: boolean): boolean {
  return gate.ready && gate.configured && !intent
}

// R25 (perceived latency): one answer per app load, and no paint that waits for it.
//
// Measured before this existed (2026-10-14, real product server, real engine): the gate's
// `GET /api/setup/status` costs ~320 ms because the route probes the engine over the
// network before it answers, and App's `GateRoute` rendered nothing but a spinner until
// that answer arrived. Two costs came from the same call: the first paint waited a full
// round trip, and every hash-route change remounted `GateRoute` and paid it again — with
// the server blocked by its own synchronous probe.
//
// The answer itself (`configured`/`skipped`) is not a live reading; it is "has an engine
// been chosen", and that changes when the user resets setup, not while they click around.
// So it is fetched once per app load and shared, and the last known answer is remembered
// as a *hint*: the paint may use it, the backend still decides (a `configured: false` from
// the network wins and sends the user to /setup, exactly as before).
export const SETUP_GATE_HINT_KEY = 'ephe.setup_gate'

const NO_ANSWER: SetupGate = { ready: false, configured: false, skipped: false }

/** The remembered answer from the last load. A hint for the paint — never the verdict. */
export function readSetupGateHint(): SetupGate | null {
  try {
    const raw = localStorage.getItem(SETUP_GATE_HINT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<SetupGate>
    if (typeof parsed?.configured !== 'boolean') return null
    return { ready: true, configured: parsed.configured, skipped: Boolean(parsed.skipped) }
  } catch {
    /* Private mode / corrupt value: paint the shell, the backend still decides. */
    return null
  }
}

function writeSetupGateHint(gate: SetupGate): void {
  try {
    localStorage.setItem(
      SETUP_GATE_HINT_KEY,
      JSON.stringify({ configured: gate.configured, skipped: gate.skipped }),
    )
  } catch {
    /* nothing to remember — a shorter first paint next time, no worse */
  }
}

let gate: SetupGate = readSetupGateHint() ?? NO_ANSWER
let inflight: Promise<void> | null = null
const listeners = new Set<() => void>()

/** Current gate state, readable synchronously (`useSyncExternalStore` snapshot). */
export function gateSnapshot(): SetupGate {
  return gate
}

export function subscribeGate(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function publish(next: SetupGate): void {
  gate = next
  for (const listener of listeners) listener()
}

/**
 * The one `GET /api/setup/status` of this app load. Idempotent: the first caller starts it,
 * everyone else joins the same promise. Call it as early as the entry point allows, so the
 * round trip overlaps the route chunk download instead of following it.
 */
export function loadSetupGate(): Promise<void> {
  if (inflight) return inflight
  const started = getSetupStatus()
    .then((status: SetupStatus) => {
      const next: SetupGate = {
        ready: true,
        configured: Boolean(status.configured),
        skipped: Boolean(status.skipped),
      }
      writeSetupGateHint(next)
      publish(next)
    })
    .catch(() => {
      // Backend offline → the gate opens (the chat fails closed on its own) and no hint
      // is written: a guess must not become the next load's remembered answer.
      inflight = null
      publish({ ready: true, configured: true, skipped: false })
    })
  inflight = started
  return started
}

/**
 * Drops the answer, the remembered hint and the single-flight promise.
 *
 * One product caller: `SetupPage.handleReset` just deleted engine.json, so both the answer
 * in memory and the hint on disk are now false. Without this the reload that follows renders
 * the chat from the stale hint and bounces to /setup a round trip later — a flash of the
 * wrong screen at the exact moment the user asked to choose an engine again. A test that
 * renders two "app loads" inside one module lifetime needs the same reset.
 */
/**
 * The tour's way past the engine question: the backend records the skip and the
 * local hint records it before the paint. Without the hint, `GateRoute` reads the
 * old "unconfigured" answer on the next render and throws the user back to /setup
 * right after the tour.
 */
export async function skipSetupGate(): Promise<void> {
  try {
    await skipSetupRequest()
  } catch {
    /* offline: the local answer keeps the tour's promise; the next load re-reads */
  }
  const next: SetupGate = { ready: true, configured: false, skipped: true }
  writeSetupGateHint(next)
  publish(next)
  inflight = Promise.resolve()
}

export function forgetSetupGate(): void {
  try {
    localStorage.removeItem(SETUP_GATE_HINT_KEY)
  } catch {
    /* Private mode: nothing was remembered, nothing to drop */
  }
  inflight = null
  publish(NO_ANSWER)
}
