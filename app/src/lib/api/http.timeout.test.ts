/**
 * R36 — the request bound: a silent backend cannot hold the first paint.
 *
 * The first screen waited on GET /api/setup/status. A server that accepted the
 * connection and then answered nothing left that promise pending for good — no
 * status, no rejection — so the gate spinner never stopped and no error ever
 * reached the user. A browser fetch does not end that wait by itself; only the
 * signal does, which is why `hangingFetch` below rejects on abort exactly as a
 * real fetch does. The cases pin the bound, the register that sets it, and the
 * two paths that have to stay untouched: a caller's own abort signal, and a
 * request that is meant to run long (timeoutMs: 0).
 *
 * The chat stream never enters this path — lib/stream.ts keeps its own idle
 * bound (chat.stream_idle_seconds) and calls fetch itself.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { ApiError, request } from './index'
import { seedDeepSettings } from '../deepSettings'
import type { DeepSection } from '@/types'
import en from '../../locales/en.json'
import de from '../../locales/de.json'

const ok = (body: unknown) =>
  ({ ok: true, status: 200, statusText: 'OK', json: async () => body }) as Response

/** A fetch that never answers, but rejects with AbortError once the signal aborts. */
const hangingFetch = () => (_url: string, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    const signal = init?.signal
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    if (!signal) return
    if (signal.aborted) abort()
    else signal.addEventListener('abort', abort)
  })

function field(key: string, value: number): DeepSection['fields'][number] {
  return { key, type: 'number', label: key, labelEn: key, default: value, value }
}

describe('the request bound (R36)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    seedDeepSettings(null)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('ends a silent backend with a coded error instead of waiting for good', async () => {
    fetchMock.mockImplementation(hangingFetch())
    const started = Date.now()

    await expect(request('/api/setup/status', { timeoutMs: 40 })).rejects.toMatchObject({
      name: 'ApiError',
      status: 408,
      reasonCode: 'request_timeout',
    })
    expect(Date.now() - started).toBeLessThan(1000)
  })

  it('hands the reader the sentence from the bundle, in their language', async () => {
    fetchMock.mockImplementation(hangingFetch())

    const err = (await request('/api/setup/status', { timeoutMs: 30 }).catch((e) => e)) as ApiError

    expect(err).toBeInstanceOf(ApiError)
    // The inline fallback in http.ts reads differently from both bundle entries,
    // so a match here proves the bundle answered and not the fallback.
    expect([de.serverError.request_timeout, en.serverError.request_timeout]).toContain(err.message)
  })

  it('takes its bound from the register field advanced.api_timeout', async () => {
    // 0.03 s sits below the panel's own floor; the accessor reads the stored
    // number as it stands, which keeps this case short instead of 120 s long.
    seedDeepSettings([{ key: 'advanced', fields: [field('advanced.api_timeout', 0.03)] }])
    fetchMock.mockImplementation(hangingFetch())

    await expect(request('/api/setup/status')).rejects.toMatchObject({ status: 408 })
  })

  it('leaves a request that asked for no bound alone', async () => {
    let settle: (r: Response) => void = () => {}
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          settle = resolve
        }),
    )

    const pending = request('/api/shell', { method: 'POST', timeoutMs: 0 })
    const raced = await Promise.race([
      pending.then(() => 'settled'),
      new Promise((resolve) => setTimeout(() => resolve('still-waiting'), 60)),
    ])

    expect(raced).toBe('still-waiting')
    settle(ok({ ok: true }))
    await expect(pending).resolves.toEqual({ ok: true })
  })

  it('keeps the caller signal a cancellation and not a timeout', async () => {
    fetchMock.mockImplementation(hangingFetch())
    const ac = new AbortController()

    const pending = request('/api/search?q=a', { signal: ac.signal, timeoutMs: 5000 })
    ac.abort()

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('passes a signal to fetch and returns a normal answer untouched', async () => {
    fetchMock.mockResolvedValueOnce(ok({ configured: true }))

    await expect(request('/api/setup/status')).resolves.toEqual({ configured: true })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })
})
