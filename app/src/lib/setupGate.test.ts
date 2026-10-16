// I4-4: a hash that survived the session vs. an explicit intent to pick the engine.
import { describe, it, expect, beforeEach, vi } from 'vitest'

// The gate's request itself is the unit under test in the last block: the network call is
// counted, never made.
const probe = vi.hoisted(() => ({
  calls: 0,
  answer: null as null | (() => Promise<unknown>),
}))

vi.mock('./api', () => ({
  getSetupStatus: () => {
    probe.calls += 1
    if (probe.answer) return probe.answer()
    return Promise.resolve({ configured: true, skipped: false })
  },
}))

import {
  SETUP_INTENT_KEY,
  consumeSetupIntent,
  markSetupIntent,
  shouldLeaveSetup,
} from './setupGate'

beforeEach(() => sessionStorage.clear())

describe('shouldLeaveSetup', () => {
  it('bleibt im Setup, solange der Status noch laeuft', () => {
    expect(shouldLeaveSetup({ ready: false, configured: true, skipped: false }, false)).toBe(false)
  })

  it('geht zurueck in den Chat, wenn eine Engine gewaehlt ist und niemand das Setup wollte', () => {
    expect(shouldLeaveSetup({ ready: true, configured: true, skipped: false }, false)).toBe(true)
  })

  it('bleibt, wenn der Nutzer das Setup ausdruecklich aufgerufen hat', () => {
    expect(shouldLeaveSetup({ ready: true, configured: true, skipped: false }, true)).toBe(false)
  })

  it('bleibt bei unkonfigurierter Engine — sonst kaeme niemand je zur Auswahl', () => {
    expect(shouldLeaveSetup({ ready: true, configured: false, skipped: false }, false)).toBe(false)
  })
})

describe('Absicht markieren und verbrauchen', () => {
  it('gilt genau einen Besuch', () => {
    markSetupIntent()
    expect(consumeSetupIntent()).toBe(true)
    expect(consumeSetupIntent()).toBe(false)
    expect(sessionStorage.getItem(SETUP_INTENT_KEY)).toBeNull()
  })

  it('ohne Markierung keine Absicht', () => {
    expect(consumeSetupIntent()).toBe(false)
  })
})

// R25 freezes, 2026-10-14. The gate used to send one request per mount and to paint nothing
// until it answered: a route change paid the round trip again (measured ~320 ms on the real
// engine, twice per cold load — the gate and the composer each had their own call). These
// three tests hold the two halves of the fix: one request per app load, and a paint that
// does not wait for it.
async function freshGate() {
  vi.resetModules()
  return await import('./setupGate')
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  probe.calls = 0
  probe.answer = null
})

describe('one answer per app load', () => {
  it('serves every asker from a single request', async () => {
    const gate = await freshGate()
    await Promise.all([gate.loadSetupGate(), gate.loadSetupGate(), gate.loadSetupGate()])

    expect(probe.calls).toBe(1)
  })

  it('does not ask again when a second component mounts later', async () => {
    const gate = await freshGate()
    await gate.loadSetupGate()
    await gate.loadSetupGate()

    expect(probe.calls).toBe(1)
  })

  it('still lets the backend decide: a late unconfigured answer closes the gate', async () => {
    const gate = await freshGate()
    probe.answer = () => Promise.resolve({ configured: false, skipped: false })
    await gate.loadSetupGate()

    expect(gate.gateSnapshot()).toEqual({ ready: true, configured: false, skipped: false })
  })
})

describe('the remembered answer is what the first paint uses', () => {
  it('is ready before the network has answered', async () => {
    localStorage.setItem('ephe.setup_gate', JSON.stringify({ configured: true, skipped: false }))
    let release: (value: unknown) => void = () => {}
    probe.answer = () => new Promise((resolve) => (release = resolve))

    const gate = await freshGate()
    expect(gate.gateSnapshot()).toEqual({ ready: true, configured: true, skipped: false })

    void gate.loadSetupGate()
    expect(gate.gateSnapshot().ready).toBe(true)
    release({ configured: true, skipped: false })
  })

  it('remembers the answer the backend gave', async () => {
    const gate = await freshGate()
    probe.answer = () => Promise.resolve({ configured: false, skipped: true })
    await gate.loadSetupGate()

    expect(JSON.parse(localStorage.getItem('ephe.setup_gate') ?? '{}')).toEqual({
      configured: false,
      skipped: true,
    })
  })

  it('does not remember a guess when the backend is unreachable', async () => {
    const gate = await freshGate()
    probe.answer = () => Promise.reject(new Error('offline'))
    await gate.loadSetupGate()

    expect(gate.gateSnapshot()).toEqual({ ready: true, configured: true, skipped: false })
    expect(localStorage.getItem('ephe.setup_gate')).toBeNull()
  })
})
