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
import type { UpdateState } from '@/lib/updateCheckRun'
import { useChatStore } from '@/store/chatStore'
import { setComposerDraft } from '@/lib/restartGuard'

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
    apply: () => hook?.apply(),
    relaunch: () => hook?.relaunch(),
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
      core: { invoke: async () => undefined },
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

  it('a merge before the next tag arrives on the commit channel, not as an install', async () => {
    global.fetch = fetchStub({
      enabled: true,
      available: true,
      channel: 'commit',
      updateChannel: 'commit',
      current: '0.6.0',
      commit: '2a1405a837f0',
      git_sha: 'deadbeefcafe',
      latest: '0.6.0+deadbeefcafe',
      commitsBehind: 2,
      url: 'https://github.com/bemlerlabs/ephe/compare/2a1405a837f0...main',
      notes: 'fix(chat): quieter rows',
      apply: { ok: true, code: '' },
    }) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    const state = probe.state()
    expect(state?.phase).toBe('available')
    expect(state?.channel).toBe('commit')
    expect(state?.updateChannel).toBe('commit')
    expect(state?.commitsBehind).toBe(2)
    expect(state?.commit).toBe('2a1405a837f0')
    expect(state?.latest).toBe('0.6.0+deadbeefcafe')
    expect(state?.applyOk).toBe(true)
  })

  it('the apply button takes the commits and reports the steps', async () => {
    global.fetch = vi.fn(async (url: string) =>
      String(url).includes('/api/update/apply')
        ? answer({
            ok: true,
            steps: [{ name: 'pull', ok: true, detail: 'a1 → b2' }],
            restart: true,
            after: 'b2',
          })
        : answer({ enabled: true, available: false, current: '0.5.1' }),
    ) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    await act(async () => {
      await probe.apply()
    })
    const state = probe.state()
    expect(state?.phase).toBe('applied')
    expect(state?.restart).toBe(true)
    expect(state?.steps?.[0]?.name).toBe('pull')
  })

  it('a stalled installer contributes its own words to the failure line', async () => {
    // The 2026-11-17 desktop update: the popup offered "the installer stopped with an
    // error" while the step output said npm was missing. Only the second tells a person
    // what to do, so it is the line the surface keeps.
    global.fetch = vi.fn(async (url: string) =>
      String(url).includes('/api/update/apply')
        ? answer({
            ok: false,
            reason: 'install_failed',
            detail: 'the installer stopped with an error',
            steps: [
              { name: 'pull', ok: true, detail: 'a1 → b2' },
              {
                name: 'install',
                ok: false,
                detail:
                  '▶ Building the PWA (web app)\n✗ npm is missing — required for the PWA build.',
              },
            ],
          })
        : answer({ enabled: true, available: false, current: '0.5.1' }),
    ) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    await act(async () => {
      await probe.apply()
    })
    const state = probe.state()
    expect(state?.phase).toBe('failed')
    expect(state?.failedAt).toBe('install')
    expect(state?.reasonCode).toBe('install_failed')
    expect(state?.reason).toContain('npm is missing')
    expect(state?.reason).not.toContain('stopped with an error')
  })

  it('an answer with no failing step keeps the backend detail as the failure line', async () => {
    global.fetch = vi.fn(async (url: string) =>
      String(url).includes('/api/update/apply')
        ? answer({
            ok: false,
            reason: 'install_failed',
            detail: 'the installer stopped with an error',
          })
        : answer({ enabled: true, available: false, current: '0.5.1' }),
    ) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    await act(async () => {
      await probe.apply()
    })
    expect(probe.state()?.reason).toBe('the installer stopped with an error')
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

  it('a surface that mounts after the first one reads its answer', async () => {
    const fetchMock = fetchStub({
      enabled: true,
      available: true,
      channel: 'commit',
      latest: 'deadbeefcafe',
    })
    global.fetch = fetchMock as unknown as typeof fetch
    const header = await mount()
    await flush()
    expect(header.state()?.phase).toBe('available')
    // Settings opens a minute later, on a page the live gate had already closed
    // for a second machine: it holds the answer, and the action its button draws.
    const { updateActionOf } = await import('@/lib/useUpdateCheck')
    const settings = await mount()
    await flush()
    expect(settings.state()?.phase).toBe('available')
    expect(updateActionOf(settings.state() ?? { phase: 'idle', progress: null })?.run).toBe('apply')
    expect(fetchMock).toHaveBeenCalledTimes(1)
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
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {
      core: { invoke: async () => undefined },
    }
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
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {
      core: { invoke: async () => undefined },
    }
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

describe('the relaunch the shell did not take', () => {
  beforeEach(() => {
    vi.resetModules()
    global.fetch = fetchStub({
      enabled: true,
      available: false,
      current: '0.7.0',
      latest: '0.7.0',
    }) as unknown as typeof fetch
    // The guard is a collaborator with state of its own, and this file's describes
    // share one chat store: a turn an earlier test left typing holds the restart
    // back, and `relaunch()` returns before it ever asks the shell.
    useChatStore.setState({ isTyping: false })
    setComposerDraft('')
  })

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI__
    global.fetch = realFetch
  })

  /**
   * The bridge goes in after the mount, because the bridge decides which check runs
   * at all: with `core.invoke` present the start-of-life question stops being the
   * feed's and becomes the signed updater's (`runDesktopCheck`), and that dials a
   * shell this test does not have. Red on CI 2026-11-17 that way — the click
   * reported the restart, and the state still answered for the failed check.
   */
  function giveShell(bridge: Record<string, unknown>): void {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = bridge
  }

  it('a surface that survives the click says the restart did not happen', async () => {
    const probe = await mount()
    await flush()

    let taken: boolean | undefined
    await act(async () => {
      taken = await probe.relaunch()
    })

    expect(taken).toBe(false)
    expect(probe.state()?.phase).toBe('failed')
    expect(probe.state()?.failedAt).toBe('relaunch')
    const { updateFailureKey } = await import('@/lib/useUpdateCheck')
    expect(updateFailureKey(probe.state() as UpdateState)).toBe('update.restartNotTaken')
  })

  it('a shell that refuses the restart is reported the same way', async () => {
    const probe = await mount()
    await flush()
    giveShell({
      core: {
        invoke: async () => {
          throw new Error('no such command')
        },
      },
      process: {
        relaunch: async () => {
          throw new Error('the shell would not restart')
        },
      },
    })

    await act(async () => {
      expect(await probe.relaunch()).toBe(false)
    })
    expect(probe.state()?.phase).toBe('failed')
    expect(probe.state()?.failedAt).toBe('relaunch')
  })

  it('the restart verdict is the newest verdict, not the check that came before', async () => {
    // The feed answers 503: the check has nothing to say and says it.
    global.fetch = vi.fn(async () => {
      return { ok: false, status: 503, json: async () => ({}) }
    }) as unknown as typeof fetch
    const probe = await mount()
    await flush()
    // Setup for what follows: the check did fail, and wrote its own verdict.
    expect(probe.state()?.failedAt).toBe('check')

    giveShell({
      process: {
        relaunch: async () => {
          throw new Error('the shell would not restart')
        },
      },
    })
    await act(async () => {
      expect(await probe.relaunch()).toBe(false)
    })

    expect(probe.state()?.failedAt).toBe('relaunch')
    const { updateFailureKey } = await import('@/lib/useUpdateCheck')
    expect(updateFailureKey(probe.state() as UpdateState)).toBe('update.restartNotTaken')
  })

  it('a restart the shell takes stays no failure', async () => {
    const relaunch = vi.fn(async () => {})
    const probe = await mount()
    await flush()
    giveShell({ process: { relaunch } })

    await act(async () => {
      expect(await probe.relaunch()).toBe(true)
    })
    expect(probe.state()?.phase).not.toBe('failed')
    expect(relaunch).toHaveBeenCalledTimes(1)
  })
})
