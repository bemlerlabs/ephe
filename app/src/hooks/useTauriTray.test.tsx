/**
 * N2 — the menu bar answers, in the two surfaces that can reach it.
 *
 * The shell raises the window and emits; this hook is the whole other half, so
 * every id in `app/src-tauri/src/lib.rs` needs a subscriber here or the item
 * fires into a void. The gate the tray work sets for itself is
 * "every menu item fires", and this file is where that is decided for the ids
 * the shell hands to the surface instead of solving on its own.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const createSession = vi.fn()
vi.mock('@/store/chatStore', () => ({
  useChatStore: { getState: () => ({ createSession }) },
}))

const openExternally = vi.fn(async (_url: string) => {})
vi.mock('@/lib/nativeBrowser', () => ({
  openExternally: (url: string) => openExternally(url),
}))

type ShellHandler = (payload: { payload?: unknown }) => void

/** The shell side of the bridge: record who subscribed, fire on demand. */
function installShell() {
  const handlers = new Map<string, ShellHandler[]>()
  const unlistened: string[] = []
  Object.defineProperty(window, '__TAURI__', {
    configurable: true,
    value: {
      event: {
        listen: (name: string, cb: ShellHandler) => {
          handlers.set(name, [...(handlers.get(name) ?? []), cb])
          return Promise.resolve(() => unlistened.push(name))
        },
      },
      core: { invoke: vi.fn(async () => {}) },
    },
  })
  return {
    fire(name: string) {
      for (const cb of handlers.get(name) ?? []) cb({ payload: undefined })
    },
    subscribed: () => [...handlers.keys()].sort(),
    released: () => unlistened.sort().join(' '),
  }
}

function removeShell() {
  delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
}

/**
 * The hook reads the bridge when the module loads, exactly as it does in the
 * shell — so the bridge has to be in place before the import, per case.
 */
async function loadHook() {
  vi.resetModules()
  const mod = await import('./useTauriTray')
  return mod.useTauriTray
}

const EVENTS = ['create-session', 'hide', 'open-docs', 'open-settings', 'quit', 'show']

let settingsEvents: string[] = []
let recordSettings: ((event: Event) => void) | null = null

beforeEach(() => {
  createSession.mockClear()
  openExternally.mockClear()
  settingsEvents = []
  recordSettings = (event: Event) => settingsEvents.push(event.type)
  window.addEventListener('ephe:open-settings', recordSettings)
})

afterEach(() => {
  if (recordSettings) window.removeEventListener('ephe:open-settings', recordSettings)
  removeShell()
})

describe('useTauriTray', () => {
  it('subscribes to every event the shell emits for a menu or tray entry', async () => {
    const shell = installShell()
    const useTauriTray = await loadHook()
    renderHook(() => useTauriTray())
    expect(shell.subscribed()).toEqual(EVENTS)
  })

  it('the Settings item opens the same panel the palette opens', async () => {
    const shell = installShell()
    const useTauriTray = await loadHook()
    window.location.hash = '#/chat'
    renderHook(() => useTauriTray())
    shell.fire('open-settings')
    await waitFor(() => expect(settingsEvents).toEqual(['ephe:open-settings']))
    expect(window.location.hash).toBe('#/chat')
  })

  it('Settings answers on a page that never mounts the chat panel', async () => {
    // The panel belongs to the chat surface and the menu bar is global: on
    // #/artifacts the event would have no listener, so the item takes the route.
    const shell = installShell()
    const useTauriTray = await loadHook()
    window.location.hash = '#/artifacts'
    renderHook(() => useTauriTray())
    shell.fire('open-settings')
    await waitFor(() => expect(window.location.hash).toBe('#/settings'))
    expect(settingsEvents).toEqual([])
  })

  it('New Session creates a session', async () => {
    const shell = installShell()
    const useTauriTray = await loadHook()
    renderHook(() => useTauriTray())
    shell.fire('create-session')
    await waitFor(() => expect(createSession).toHaveBeenCalledTimes(1))
  })

  it('Documentation leaves through the native opener', async () => {
    const shell = installShell()
    const useTauriTray = await loadHook()
    renderHook(() => useTauriTray())
    shell.fire('open-docs')
    await waitFor(() => expect(openExternally).toHaveBeenCalledWith('https://ephe.app/docs'))
  })

  it('a browser tab subscribes to nothing and stays quiet', async () => {
    removeShell()
    const useTauriTray = await loadHook()
    const { result } = renderHook(() => useTauriTray())
    expect(result.current.isTauri).toBe(false)
    expect(openExternally).not.toHaveBeenCalled()
  })

  it('every subscription is released with the hook', async () => {
    const shell = installShell()
    const useTauriTray = await loadHook()
    const { unmount } = renderHook(() => useTauriTray())
    unmount()
    await waitFor(() => expect(shell.released()).toBe(EVENTS.join(' ')))
  })
})
