import { afterEach, describe, expect, it, vi } from 'vitest'
import { syncDockStatus } from './dockStatus'

type Bridge = { __TAURI__?: unknown }

function shell(invoke: ReturnType<typeof vi.fn>) {
  ;(window as Bridge).__TAURI__ = { core: { invoke } }
}

afterEach(() => {
  delete (window as Bridge).__TAURI__
})

describe('N8 — the dock follows the run', () => {
  it('paints the plan ratio as badge and bar while a turn streams', async () => {
    const invoke = vi.fn(async () => undefined)
    shell(invoke)

    await syncDockStatus({ busy: true, done: 2, total: 5 })

    expect(invoke).toHaveBeenCalledWith('set_dock_badge', { badge: '2/5' })
    expect(invoke).toHaveBeenCalledWith('set_dock_progress', { percent: 40 })
  })

  it('marks a busy turn without a plan with a dot and no bar', async () => {
    const invoke = vi.fn(async () => undefined)
    shell(invoke)

    await syncDockStatus({ busy: true, done: 0, total: 0 })

    expect(invoke).toHaveBeenCalledWith('set_dock_badge', { badge: '●' })
    expect(invoke).toHaveBeenCalledWith('set_dock_progress', { percent: null })
  })

  it('clears both fields when the turn ended', async () => {
    const invoke = vi.fn(async () => undefined)
    shell(invoke)

    await syncDockStatus({ busy: false, done: 5, total: 5 })

    expect(invoke).toHaveBeenCalledWith('set_dock_badge', { badge: '' })
    expect(invoke).toHaveBeenCalledWith('set_dock_progress', { percent: null })
  })

  it('asks for nothing in a browser', async () => {
    const invoke = vi.fn(async () => undefined)
    delete (window as Bridge).__TAURI__

    await syncDockStatus({ busy: true, done: 1, total: 2 })

    expect(invoke).not.toHaveBeenCalled()
  })
})
