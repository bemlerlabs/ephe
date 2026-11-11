/**
 * Issues #193/#194: the surface reads the shell's readiness instead of assuming it.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { composerBlocked, readBackendReadiness } from './backendReadiness'

const win = window as unknown as { __TAURI__?: unknown }

afterEach(() => {
  delete win.__TAURI__
  vi.restoreAllMocks()
})

describe('backend readiness', () => {
  it('says nothing outside the shell — a browser tab always has the server it was loaded from', async () => {
    expect(await readBackendReadiness()).toBeNull()
  })

  it('reads the shell answer, including the sentence and the action', async () => {
    win.__TAURI__ = {
      core: {
        invoke: vi.fn(async () => ({
          ready: false,
          state: 'unconfigured',
          port: 8765,
          base_url: 'http://127.0.0.1:8765',
          config: '/home/read/.ephe/desktop.json',
          sentence: 'No backend is configured for this window.',
          action: 'Run `ephe desktop` to let the app start one.',
        })),
      },
    }
    const readiness = await readBackendReadiness()
    expect(readiness).not.toBeNull()
    expect(readiness?.ready).toBe(false)
    expect(readiness?.state).toBe('unconfigured')
    expect(readiness?.action).toContain('ephe desktop')
  })

  it('treats a failing bridge as unknown rather than ready', async () => {
    win.__TAURI__ = {
      core: {
        invoke: vi.fn(async () => {
          throw new Error('no ipc')
        }),
      },
    }
    expect(await readBackendReadiness()).toBeNull()
  })
})

describe('the contract the shell actually writes', () => {
  const invoke = (answer: Record<string, unknown>) => {
    win.__TAURI__ = { core: { invoke: vi.fn(async () => answer) } }
  }

  it('reads the serialised `ready` field as ready', async () => {
    invoke({
      ready: true,
      state: 'starting',
      port: 8765,
      base_url: 'http://127.0.0.1:8765',
      config: '/home/read/.ephe/desktop.json',
      sentence: 'This window started the backend on http://127.0.0.1:8765.',
      action: '',
    })
    const readiness = await readBackendReadiness()
    expect(readiness?.ready).toBe(true)
    expect(readiness?.state).toBe('starting')
  })

  it('still understands the old spelling, so a mixed pair cannot lock the composer', async () => {
    invoke({
      bereit: true,
      state: 'ready',
      port: 8765,
      base_url: '',
      config: '',
      sentence: '',
      action: '',
    })
    expect((await readBackendReadiness())?.ready).toBe(true)
  })

  it('is not ready when the shell says so', async () => {
    invoke({
      ready: false,
      state: 'unconfigured',
      port: 8765,
      base_url: '',
      config: '',
      sentence: '',
      action: '',
    })
    expect((await readBackendReadiness())?.ready).toBe(false)
  })
})

describe('composerBlocked', () => {
  const ready = (state: string, isReady = false) => ({
    ready: isReady,
    state,
    port: 8765,
    baseUrl: '',
    config: '',
    sentence: '',
    action: '',
  })

  it('lets a window send while the backend is still coming up', () => {
    expect(composerBlocked(ready('starting'))).toBe(false)
  })

  it('lets a browser tab send — there is always a server behind it', () => {
    expect(composerBlocked(null)).toBe(false)
  })

  it('locks a window with nothing to talk to', () => {
    expect(composerBlocked(ready('unconfigured'))).toBe(true)
    expect(composerBlocked(ready('unreachable'))).toBe(true)
    expect(composerBlocked(ready('refused'))).toBe(true)
  })

  it('never locks a window whose backend answered', () => {
    expect(composerBlocked(ready('ready', true))).toBe(false)
  })
})
