/**
 * Issues #193/#194: the surface reads the shell's readiness instead of assuming it.
 */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { readBackendReadiness } from './backendReadiness'

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
          bereit: false,
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
