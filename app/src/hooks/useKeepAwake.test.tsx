/**
 * Keep-awake (P2-B automations) — two honest paths, both mocked:
 *  - web/jsdom without Tauri → the Screen Wake Lock API (navigator.wakeLock)
 *  - desktop → window.__TAURI__.core.invoke('set_keep_awake', { enabled })
 * Interaction with the chat: the lock only while an assistant message is
 * streaming AND the toggle is on (store subscribe + interval sync).
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useKeepAwake } from './useKeepAwake'

// ── chatStore mock (lightweight, no real store side effects) ───────────────
type Listener = () => void
const listeners = new Set<Listener>()
const storeState: {
  currentSession: { messages: Array<{ role: string; streaming?: boolean }> } | null
} = {
  currentSession: null,
}
vi.mock('@/store/chatStore', () => ({
  useChatStore: Object.assign((sel: (s: unknown) => unknown) => sel(storeState), {
    getState: () => storeState,
    subscribe: (l: Listener) => {
      listeners.add(l)
      return () => {
        listeners.delete(l)
      }
    },
  }),
}))

function setStreaming(streaming: boolean | null) {
  storeState.currentSession =
    streaming === null ? null : { messages: [{ role: 'assistant', streaming }] }
  for (const l of listeners) l()
}

// ── Wake Lock mock ─────────────────────────────────────────────────────────
function makeSentinel() {
  const s = {
    released: false,
    release: vi.fn(async () => {
      s.released = true
    }),
  }
  return s
}

function installWakeLock(requestImpl: () => Promise<unknown>) {
  Object.defineProperty(navigator, 'wakeLock', {
    value: { request: vi.fn(requestImpl) },
    configurable: true,
  })
}

function installTauri(
  invokeImpl: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>,
) {
  Object.defineProperty(window, '__TAURI__', {
    value: { core: { invoke: vi.fn(invokeImpl) } },
    configurable: true,
  })
}

type TauriInvokeMock = ReturnType<typeof vi.fn> | undefined
function tauriInvokeMock(): TauriInvokeMock {
  const t = (window as { __TAURI__?: { core?: { invoke?: TauriInvokeMock } } }).__TAURI__
  return t?.core?.invoke
}

beforeEach(() => {
  storeState.currentSession = null
  Object.defineProperty(window, '__TAURI__', { value: undefined, configurable: true })
  // jsdom has no wakeLock — remove it cleanly so the detection stays honest
  delete (navigator as { wakeLock?: unknown }).wakeLock
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useKeepAwake', () => {
  it('ohne Tauri und ohne Wake Lock: supported=false (UI darf Toggle deaktivieren)', async () => {
    const { result } = renderHook(() => useKeepAwake(true))
    expect(result.current.supported).toBe(false)
    expect(result.current.active).toBe(false)
    // even after streaming starts: no crash, no active lock
    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.supported).toBe(false))
    expect(result.current.active).toBe(false)
  })

  it('Wake-Lock-Pfad: Lock wird angefragt, sobald enabled UND streaming', async () => {
    const sentinel = makeSentinel()
    installWakeLock(async () => sentinel)
    const { result } = renderHook(() => useKeepAwake(true))
    expect(result.current.via).toBe('wakeLock')

    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.active).toBe(true))
    expect(navigator.wakeLock.request).toHaveBeenCalledWith('screen')

    // Turn ends → release
    await act(async () => {
      setStreaming(false)
    })
    await waitFor(() => expect(result.current.active).toBe(false))
    expect(sentinel.release).toHaveBeenCalled()
  })

  it('Toggle aus (enabled=false): kein Lock, auch nicht beim Streaming', async () => {
    installWakeLock(async () => makeSentinel())
    const { result, rerender } = renderHook(({ enabled }) => useKeepAwake(enabled), {
      initialProps: { enabled: false },
    })
    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.active).toBe(false))
    expect(navigator.wakeLock.request).not.toHaveBeenCalled()

    // Switching the toggle on during streaming → lock immediately (effect sync)
    rerender({ enabled: true })
    await waitFor(() => expect(result.current.active).toBe(true))
  })

  it('Wake-Lock-API-Fail → active=false, kein Crash (UI zeigt Hinweis)', async () => {
    installWakeLock(async () => {
      throw new Error('denied')
    })
    const { result } = renderHook(() => useKeepAwake(true))
    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.active).toBe(false)
  })

  it('Unmount während aktiv → Lock wird freigegeben', async () => {
    const sentinel = makeSentinel()
    installWakeLock(async () => sentinel)
    const { result, unmount } = renderHook(() => useKeepAwake(true))
    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.active).toBe(true))
    unmount()
    expect(sentinel.release).toHaveBeenCalled()
  })

  it('visibilitychange → visible: auto-releastes Wake Lock wird neu angefragt', async () => {
    const sentinel = makeSentinel()
    installWakeLock(async () => sentinel)
    const { result } = renderHook(() => useKeepAwake(true))
    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.active).toBe(true))

    // Browser behaviour: hiding the tab releases the lock quietly
    await act(async () => {
      sentinel.released = true
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(navigator.wakeLock.request).toHaveBeenCalledTimes(2))
    expect(result.current.active).toBe(true)
  })

  it('Tauri-Pfad: invoke("set_keep_awake") wird mit enabled true/false gerufen', async () => {
    installTauri(async () => true)
    const { result } = renderHook(() => useKeepAwake(true))
    expect(result.current.via).toBe('tauri')

    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.active).toBe(true))
    expect(tauriInvokeMock()).toHaveBeenCalledWith('set_keep_awake', { enabled: true })

    await act(async () => {
      setStreaming(false)
    })
    await waitFor(() => expect(result.current.active).toBe(false))
    expect(tauriInvokeMock()).toHaveBeenCalledWith('set_keep_awake', { enabled: false })
  })

  it('Tauri meldet false (Plattform ohne caffeinate) → supported wird ehrlich false', async () => {
    installTauri(async () => false)
    const { result } = renderHook(() => useKeepAwake(true))
    expect(result.current.supported).toBe(true)

    await act(async () => {
      setStreaming(true)
    })
    await waitFor(() => expect(result.current.supported).toBe(false))
    expect(result.current.active).toBe(false)
  })
})
