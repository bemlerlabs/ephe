/**
 * S23: the shell and the backend are updated by different mechanisms, so the
 * surface has to say when they disagree — and stay quiet when nothing was
 * measured.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { invoke, toast, health, guard, relaunch } = vi.hoisted(() => ({
  invoke: vi.fn(),
  toast: { error: vi.fn(), info: vi.fn() },
  health: vi.fn(),
  guard: { current: { blocked: false, reason: null as 'running' | 'draft' | null } },
  relaunch: vi.fn(),
}))

vi.mock('@/lib/toast', () => ({ toastBus: toast }))
vi.mock('@/lib/api', () => ({ healthCheck: health }))
vi.mock('@/lib/restartGuard', () => ({
  restartGuardNow: () => guard.current,
  relaunchApp: relaunch,
}))

const bridge = { core: { invoke: (cmd: string) => invoke(cmd) } }

import { announceBackendParity, announceBuildParity } from './backendParity'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${String(opts.shell ?? opts.build)}/${String(opts.backend)}` : key

beforeEach(() => {
  ;(window as unknown as { __TAURI__?: unknown }).__TAURI__ = bridge
  guard.current = { blocked: false, reason: null }
})

afterEach(() => {
  invoke.mockReset()
  health.mockReset()
  toast.error.mockReset()
  toast.info.mockReset()
  relaunch.mockReset()
  vi.useRealTimers()
})

describe('announceBackendParity', () => {
  it('names both versions when they disagree', async () => {
    invoke.mockResolvedValue({
      verdict: 'mismatch',
      shell: '0.1.8',
      backend: '0.1.7',
      note: 'dirty tree',
    })

    await expect(announceBackendParity(t)).resolves.toMatchObject({ verdict: 'mismatch' })

    expect(toast.error).toHaveBeenCalledWith('chat.backendMismatch:0.1.8/0.1.7', 'dirty tree')
  })

  it('asks for a restart after it moved the backend', async () => {
    invoke.mockResolvedValue({
      verdict: 'updated_restart',
      shell: '0.1.8',
      backend: '0.1.7',
      note: '',
    })

    await announceBackendParity(t)

    expect(toast.info).toHaveBeenCalledWith(
      'chat.backendUpdated',
      undefined,
      { label: 'update.relaunchNow', onClick: expect.any(Function) },
      'backend-parity',
    )
    expect(toast.error).not.toHaveBeenCalled()

    const action = toast.info.mock.calls[0]?.[2] as { onClick: () => void }
    action.onClick()
    expect(relaunch).toHaveBeenCalled()
  })

  it('holds the restart back while a turn still runs', async () => {
    guard.current = { blocked: true, reason: 'running' }
    invoke.mockResolvedValue({
      verdict: 'updated_restart',
      shell: '0.1.8',
      backend: '0.1.7',
      note: '',
    })

    await announceBackendParity(t)

    expect(toast.info).toHaveBeenCalledWith(
      'chat.backendUpdated',
      'update.restartBlockedRunning',
      undefined,
      'backend-parity',
    )
    expect(relaunch).not.toHaveBeenCalled()
  })

  it('names the refresh while it runs and follows it without asking again', async () => {
    vi.useFakeTimers()
    const refreshing = {
      verdict: 'updated_reinstalling',
      shell: '0.1.8',
      backend: '0.1.7',
      note: '',
    }
    invoke.mockResolvedValue(refreshing)

    await announceBackendParity(t)
    expect(toast.info).toHaveBeenCalledWith(
      'chat.backendReinstalling',
      undefined,
      undefined,
      'backend-parity',
    )

    invoke.mockResolvedValue({ verdict: 'updated_restart', shell: '0.1.8', backend: '', note: '' })
    toast.info.mockClear()
    await vi.advanceTimersByTimeAsync(30_000)

    expect(toast.info).toHaveBeenCalledWith(
      'chat.backendUpdated',
      undefined,
      { label: 'update.relaunchNow', onClick: expect.any(Function) },
      'backend-parity',
    )
  })

  it('stops following a refresh that never lands', async () => {
    vi.useFakeTimers()
    invoke.mockResolvedValue({
      verdict: 'updated_reinstalling',
      shell: '0.1.8',
      backend: '0.1.7',
      note: '',
    })

    await announceBackendParity(t)
    toast.info.mockClear()
    for (let i = 0; i < 70; i += 1) await vi.advanceTimersByTimeAsync(30_000)

    const reads = invoke.mock.calls.length
    expect(reads).toBeGreaterThan(30)
    // the shell's own bound is 30 minutes; past it the surface stops asking,
    // because the next start re-reads the verdict on its own
    for (let i = 0; i < 10; i += 1) await vi.advanceTimersByTimeAsync(30_000)
    expect(invoke).toHaveBeenCalledTimes(reads)
    expect(toast.info).not.toHaveBeenCalled()
  })

  it('says nothing when there is no measurement to report', async () => {
    for (const verdict of ['current', 'unknown', 'no_backend']) {
      invoke.mockResolvedValue({ verdict, shell: '0.1.8', backend: '', note: '' })
      await announceBackendParity(t)
    }

    expect(toast.error).not.toHaveBeenCalled()
    expect(toast.info).not.toHaveBeenCalled()
  })

  it('returns null when the shell has no parity command', async () => {
    invoke.mockRejectedValue(new Error('command backend_parity not found'))

    await expect(announceBackendParity(t)).resolves.toBeNull()

    expect(toast.error).not.toHaveBeenCalled()
  })
})

describe('announceBuildParity', () => {
  it("announces an older window without putting commits in the reader's face", async () => {
    health.mockResolvedValue({ git_sha: 'bbbbbbbbbbbb' })

    await expect(announceBuildParity(t, undefined, 'aaaaaaaaaaaa', false)).resolves.toEqual({
      verdict: 'mismatch',
      build: 'aaaaaaaaaaaa',
      backend: 'bbbbbbbbbbbb',
    })

    expect(toast.error).toHaveBeenCalledWith('chat.buildMismatch')
  })

  // Measured 2026-11-02 on the installed app: the shell said `Reload the window to load
  // it.` while the newer interface sat in the freshly installed `.app` — a reload re-reads
  // the same bundle, so the one instruction the toast gave could not do the thing it asked.
  it('in the shell the same verdict names the update and opens the page that runs it', async () => {
    await expect(
      announceBuildParity(t, { git_sha: 'bbbbbbbbbbbb' }, 'aaaaaaaaaaaa', true),
    ).resolves.toMatchObject({ verdict: 'mismatch' })

    const call = toast.error.mock.calls.at(-1) ?? []
    expect(call[0]).toBe('chat.buildMismatchShell')
    expect(call[2]).toEqual({ label: 'update.applyNow', onClick: expect.any(Function) })
    expect(call[3]).toBe('build-parity')

    const seen: string[] = []
    const onTab = (e: Event) => seen.push((e as CustomEvent<{ tab?: string }>).detail?.tab ?? '')
    window.addEventListener('ephe:settings-tab', onTab)
    try {
      ;(call[2] as { onClick: () => void }).onClick()
    } finally {
      window.removeEventListener('ephe:settings-tab', onTab)
    }
    expect(seen).toEqual(['about'])
  })

  it('stays quiet when the bundle was built from the commit that serves it', async () => {
    health.mockResolvedValue({ git_sha: '76c4223ad094' })

    await expect(announceBuildParity(t, undefined, '76c4223ad094')).resolves.toMatchObject({
      verdict: 'match',
    })

    expect(toast.error).not.toHaveBeenCalled()
  })

  it('stays quiet when either side has no commit to compare', async () => {
    health.mockResolvedValue({ git_sha: '' })
    await expect(announceBuildParity(t, undefined, 'aaaaaaaaaaaa')).resolves.toMatchObject({
      verdict: 'unknown',
    })

    health.mockResolvedValue({ git_sha: 'bbbbbbbbbbbb' })
    await expect(announceBuildParity(t, undefined, 'unknown')).resolves.toMatchObject({
      verdict: 'unknown',
    })

    expect(toast.error).not.toHaveBeenCalled()
  })

  it('returns null when the backend cannot be read', async () => {
    health.mockRejectedValue(new Error('offline'))

    await expect(announceBuildParity(t, undefined, 'aaaaaaaaaaaa')).resolves.toBeNull()

    expect(toast.error).not.toHaveBeenCalled()
  })

  it('reads the health answer once when the caller already has it', async () => {
    await announceBuildParity(t, { git_sha: 'bbbbbbbbbbbb' }, 'aaaaaaaaaaaa')

    expect(health).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledTimes(1)
  })
})
