/**
 * U-1: the surface asks by itself, and only as often as the feed can afford.
 *
 * The moments are app start, the window coming back to the front, and the
 * half-hour tick of a session that stays open. All three want a live answer
 * (the backend skips its six-hour TTL cache for ?force=1), so what is held
 * here is the gate around them: one live question every five minutes, a
 * quarter hour of quiet after a failed one, and nothing at all while the answer
 * is known.
 *
 * The install path is measured with the updater module stubbed: download() and
 * install() are two calls precisely so that the installing phase is not a
 * guess, and the phases the surface draws have to be the ones that happened.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render } from '@testing-library/react'
import type { UpdateState } from '@/lib/useUpdateCheck'

const realFetch = global.fetch

/** One canned answer from /api/update/check. */
function answer(body: Record<string, unknown>) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

function fetchStub(body: Record<string, unknown>) {
  return vi.fn(async () => answer(body))
}

/** The calls the stub saw, as strings — which is where ?force=1 shows up. */
function urls(fn: ReturnType<typeof vi.fn>) {
  return fn.mock.calls.map((c) => String(c[0]))
}

async function mount() {
  const { useUpdateCheck } = await import('@/lib/useUpdateCheck')
  const phases: string[] = []
  const shares: string[] = []
  let hook: ReturnType<typeof useUpdateCheck> | undefined
  const Probe = () => {
    hook = useUpdateCheck()
    const s: UpdateState = hook.state
    if (phases[phases.length - 1] !== s.phase) phases.push(s.phase)
    if (s.phase === 'downloading' && s.progress !== null) shares.push(String(s.progress))
    return null
  }
  const view = render(<Probe />)
  return {
    state: () => hook?.state,
    install: () => hook?.install(),
    phases,
    shares,
    view,
  }
}

/** Let every pending promise and re-render run to the end. */
const flush = () =>
  act(async () => {
    await Promise.resolve()
  })

function front() {
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('U-1 — automatic detection', () => {
  let clock = 1_000_000_000

  beforeEach(() => {
    vi.resetModules()
    clock = 1_000_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => clock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.doUnmock('@tauri-apps/plugin-updater')
    delete (window as unknown as Record<string, unknown>).__TAURI__
    global.fetch = realFetch
  })

  it('the desktop compares against the shell version, not a backend from another checkout', async () => {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {
      app: { getVersion: async () => '0.1.0-beta.4' },
    }
    vi.doMock('@tauri-apps/plugin-updater', () => ({
      check: async () => ({
        available: false,
        currentVersion: '0.1.0-beta.4',
        version: '0.1.0-beta.4',
        body: '',
      }),
    }))
    // The backend still reports the stale version it was started with.
    global.fetch = fetchStub({
      enabled: true,
      available: true,
      current: '0.1.0-beta.2',
      latest: '0.1.0-beta.4',
    }) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    expect(probe.state()?.phase).toBe('current')
    expect(probe.state()?.current).toBe('0.1.0-beta.4')
  })

  it('the first question of a session leaves the backend cache behind', async () => {
    const fetchMock = fetchStub({ enabled: true, available: false, current: '0.1.0-beta.1' })
    global.fetch = fetchMock as unknown as typeof fetch
    const probe = await mount()
    await flush()
    expect(urls(fetchMock)).toEqual(['/api/update/check?force=1'])
    expect(probe.state()?.phase).toBe('current')
  })

  it('a window that comes back within the gate asks nothing', async () => {
    const fetchMock = fetchStub({ enabled: true, available: false, current: '0.1.0-beta.1' })
    global.fetch = fetchMock as unknown as typeof fetch
    await mount()
    await flush()
    clock += 10_000
    await act(async () => {
      front()
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('a window that comes back after the gate asks again, live', async () => {
    const fetchMock = fetchStub({ enabled: true, available: false, current: '0.1.0-beta.1' })
    global.fetch = fetchMock as unknown as typeof fetch
    await mount()
    await flush()
    clock += 6 * 60 * 1000
    await act(async () => {
      front()
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(urls(fetchMock).every((u) => u.endsWith('?force=1'))).toBe(true)
  })

  it('an update that is already known is not asked for a second time', async () => {
    const fetchMock = fetchStub({
      enabled: true,
      available: true,
      current: '0.1.0-beta.1',
      latest: '0.1.0-beta.2',
      url: 'https://example.invalid/releases',
    })
    global.fetch = fetchMock as unknown as typeof fetch
    const probe = await mount()
    await flush()
    expect(probe.state()?.phase).toBe('available')
    clock += 20 * 60 * 1000
    await act(async () => {
      front()
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(probe.state()?.phase).toBe('available')
  })

  it('a source that just failed gets a quarter hour of quiet', async () => {
    const fetchMock = fetchStub({
      enabled: true,
      available: false,
      current: '0.1.0-beta.1',
      error: 'the release source could not be reached',
    })
    global.fetch = fetchMock as unknown as typeof fetch
    const probe = await mount()
    await flush()
    expect(probe.state()?.phase).toBe('failed')
    expect(probe.state()?.failedAt).toBe('check')
    clock += 6 * 60 * 1000
    await act(async () => {
      front()
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    clock += 10 * 60 * 1000
    await act(async () => {
      front()
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('the return to the front is the one that asks, not the hidden stretch', async () => {
    const fetchMock = fetchStub({ enabled: true, available: false, current: '0.1.0-beta.1' })
    global.fetch = fetchMock as unknown as typeof fetch
    await mount()
    await flush()
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    clock += 6 * 60 * 1000
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('U-3 — the install path names its own phases', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.doUnmock('@tauri-apps/plugin-updater')
    delete (window as unknown as Record<string, unknown>).__TAURI__
  })

  it('the share comes from the events, then the installation, then the finish', async () => {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {}
    // The download is held open by the test, so every phase it passes through
    // is read while it is the current one: a chunked arrival over the network
    // is what the surface has to draw, not one jump to the end.
    let emit: (e: unknown) => void = () => {}
    let release: () => void = () => {}
    const download = vi.fn(async (onEvent: (e: unknown) => void) => {
      emit = onEvent
      await new Promise<void>((done) => {
        release = done
      })
    })
    let releaseInstall: () => void = () => {}
    const install = vi.fn(async () => {
      await new Promise<void>((done) => {
        releaseInstall = done
      })
    })
    vi.doMock('@tauri-apps/plugin-updater', () => ({
      check: async () => ({ available: true, download, install }),
    }))
    global.fetch = fetchStub({
      enabled: true,
      available: true,
      current: '0.1.0-beta.1',
      latest: '0.1.0-beta.2',
    }) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    expect(probe.state()?.phase).toBe('available')

    let running: Promise<boolean> | undefined
    act(() => {
      running = probe.install()
    })
    // The first flush lets the updater import and its check() resolve, which is
    // what opens the download and hands over the event callback.
    await flush()
    expect(probe.state()?.phase).toBe('downloading')
    expect(probe.state()?.progress).toBe(0)

    emit({ event: 'Started', data: { contentLength: 100 } })
    await flush()
    expect(probe.state()?.progress).toBe(0)

    emit({ event: 'Progress', data: { chunkLength: 40 } })
    await flush()
    expect(probe.state()?.progress).toBe(0.4)

    emit({ event: 'Progress', data: { chunkLength: 60 } })
    await flush()
    expect(probe.state()?.progress).toBe(1)

    // The download is done and the installer is writing: the phase between the
    // two is a frame of its own in the app, because installing() takes time.
    release()
    await flush()
    expect(probe.state()?.phase).toBe('installing')
    expect(probe.state()?.progress).toBe(1)

    await act(async () => {
      releaseInstall()
      await running
    })
    expect(install).toHaveBeenCalledTimes(1)
    expect(probe.phases).toContain('installing')
    expect(probe.state()?.phase).toBe('ready')
    expect(probe.state()?.progress).toBe(1)

    global.fetch = realFetch
  })

  it('an installer that refuses carries the failure, and says where', async () => {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {}
    const download = vi.fn(async (onEvent: (e: unknown) => void) => {
      onEvent({ event: 'Started', data: { contentLength: 100 } })
    })
    vi.doMock('@tauri-apps/plugin-updater', () => ({
      check: async () => ({
        available: true,
        download,
        install: async () => {
          throw new Error('the installer refused the bundle')
        },
      }),
    }))
    global.fetch = fetchStub({
      enabled: true,
      available: true,
      current: '0.1.0-beta.1',
      latest: '0.1.0-beta.2',
    }) as unknown as typeof fetch
    const probe = await mount()
    await flush()

    await act(async () => {
      await probe.install()
    })
    expect(probe.state()?.phase).toBe('failed')
    expect(probe.state()?.failedAt).toBe('install')

    global.fetch = realFetch
  })
})
