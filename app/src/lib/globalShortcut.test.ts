import { afterEach, describe, expect, it, vi } from 'vitest'

import { ensureGlobalShortcut } from './globalShortcut'

type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>

function bridge(invoke: Invoke) {
  ;(window as unknown as { __TAURI__?: { core?: { invoke: Invoke } } }).__TAURI__ = {
    core: { invoke },
  }
}

afterEach(() => {
  delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
})

describe('ensureGlobalShortcut', () => {
  it('asking for the chord registers it and reports applied', async () => {
    const invoke = vi.fn().mockResolvedValue('registered')
    bridge(invoke)
    await expect(ensureGlobalShortcut(true)).resolves.toBe('applied')
    expect(invoke).toHaveBeenCalledWith('set_global_shortcut', { enabled: true })
  })

  it('a taken chord reports failed and releases the registration', async () => {
    const invoke = vi
      .fn()
      .mockRejectedValueOnce(new Error('already registered'))
      .mockResolvedValueOnce('unregistered')
    bridge(invoke)
    await expect(ensureGlobalShortcut(true)).resolves.toBe('failed')
    expect(invoke).toHaveBeenNthCalledWith(2, 'set_global_shortcut', { enabled: false })
  })

  it('off releases the chord', async () => {
    const invoke = vi.fn().mockResolvedValue('unregistered')
    bridge(invoke)
    await expect(ensureGlobalShortcut(false)).resolves.toBe('disabled')
    expect(invoke).toHaveBeenCalledWith('set_global_shortcut', { enabled: false })
  })

  it('a browser tab says unsupported instead of pretending', async () => {
    await expect(ensureGlobalShortcut(true)).resolves.toBe('unsupported')
  })
})
