/**
 * S23: the shell and the backend are updated by different mechanisms, so the
 * surface has to say when they disagree — and stay quiet when nothing was
 * measured.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { invoke, toast, health } = vi.hoisted(() => ({
  invoke: vi.fn(),
  toast: { error: vi.fn(), info: vi.fn() },
  health: vi.fn(),
}))

vi.mock('@/lib/toast', () => ({ toastBus: toast }))
vi.mock('@/lib/api', () => ({ healthCheck: health }))

const bridge = { core: { invoke: (cmd: string) => invoke(cmd) } }

import { announceBackendParity, announceBuildParity } from './backendParity'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${String(opts.shell ?? opts.build)}/${String(opts.backend)}` : key

beforeEach(() => {
  ;(window as unknown as { __TAURI__?: unknown }).__TAURI__ = bridge
})

afterEach(() => {
  invoke.mockReset()
  health.mockReset()
  toast.error.mockReset()
  toast.info.mockReset()
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
      undefined,
      'backend-parity',
    )
    expect(toast.error).not.toHaveBeenCalled()
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
  it('announces an older window without putting commits in the reader\'s face', async () => {
    health.mockResolvedValue({ git_sha: 'bbbbbbbbbbbb' })

    await expect(announceBuildParity(t, undefined, 'aaaaaaaaaaaa')).resolves.toEqual({
      verdict: 'mismatch',
      build: 'aaaaaaaaaaaa',
      backend: 'bbbbbbbbbbbb',
    })

    expect(toast.error).toHaveBeenCalledWith(
      'chat.buildMismatch',
    )
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
