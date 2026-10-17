import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  clearEngineKey,
  engineKeyStored,
  engineKeyStoreAvailable,
  storeEngineKey,
} from './engineKey'

type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>

function withShell(state: boolean, invoke: Invoke) {
  Object.defineProperty(window, '__TAURI__', {
    configurable: true,
    value: state ? { core: { invoke } } : undefined,
  })
}

afterEach(() => {
  withShell(false, async () => undefined)
})

describe('storeEngineKey', () => {
  it('asks the shell on the desktop and reports what happened there', async () => {
    const invoke = vi.fn<Invoke>(async () => null)
    withShell(true, invoke)

    await expect(storeEngineKey('typed-token')).resolves.toBe('stored')
    expect(invoke).toHaveBeenCalledWith('save_engine_key', { value: 'typed-token' })
  })

  it('says session-only in a browser, where there is no filesystem to write', async () => {
    withShell(false, async () => undefined)

    await expect(storeEngineKey('typed-token')).resolves.toBe('session-only')
    expect(engineKeyStoreAvailable()).toBe(false)
  })

  it('lets a shell refusal reach the caller instead of claiming a store', async () => {
    withShell(true, async () => {
      throw new Error('engine key must be one line')
    })

    await expect(storeEngineKey('one\ntwo')).rejects.toThrow('engine key must be one line')
  })
})

describe('engineKeyStored', () => {
  it('reads existence only — the command answers a boolean', async () => {
    const invoke = vi.fn<Invoke>(async () => true)
    withShell(true, invoke)

    await expect(engineKeyStored()).resolves.toBe(true)
    expect(invoke).toHaveBeenCalledWith('engine_key_state', {})
  })

  it('reports false without a shell rather than failing the surface', async () => {
    withShell(false, async () => undefined)
    await expect(engineKeyStored()).resolves.toBe(false)
    await expect(clearEngineKey()).resolves.toBe('no-shell')
  })
})
