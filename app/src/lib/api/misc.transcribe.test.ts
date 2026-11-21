/**
 * QD-008 M2/M3 — the transcription upload names its format and carries the refusal.
 *
 * The recorder decides which container it produces (webm on Chromium, MP4 in the
 * WKWebView shell); the multipart part has to say the same thing or the server
 * turns the upload away as an unsupported type. And when it does say no — the
 * speech model is missing, for instance — the reader gets the refusal's own
 * sentence instead of `API 409: Conflict`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k }),
}))

// The bundle lookup itself has its own tests; here the server's sentence is the fallback.
vi.mock('@/lib/serverError', () => ({
  serverErrorText: (_c?: string, _p?: unknown, fallback = '') => fallback,
}))

import { transcribeAudio } from './index'
import { seedDeepSettings } from '../deepSettings'

/** A fetch that never answers, but rejects with AbortError once the signal aborts (mirrors http.timeout.test.ts). */
const hangingFetch = () => (_url: string, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    const signal = init?.signal
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    if (!signal) return
    if (signal.aborted) abort()
    else signal.addEventListener('abort', abort)
  })

const ok = (body: unknown) =>
  ({ ok: true, status: 200, statusText: 'OK', json: async () => body }) as Response
const fail = (status: number, statusText: string, body: unknown) =>
  ({ ok: false, status, statusText, json: async () => body }) as Response

describe('transcribeAudio (QD-008)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const uploadedName = () => {
    const body = (fetchMock.mock.calls[0]![1] as RequestInit).body as FormData
    return (body.get('file') as File).name
  }

  it.each([
    ['audio/webm;codecs=opus', 'recording.webm'],
    ['audio/mp4;codecs=mp4a.40.2', 'recording.mp4'],
    ['audio/ogg;codecs=opus', 'recording.ogg'],
    ['audio/wav', 'recording.wav'],
  ])('names a %s upload %s', async (mime, name) => {
    fetchMock.mockResolvedValueOnce(ok({ text: 'hallo' }))
    await transcribeAudio(new Blob(['x'], { type: mime }))
    expect(uploadedName()).toBe(name)
  })

  it('still uploads a webm part when the blob carries no type', async () => {
    fetchMock.mockResolvedValueOnce(ok({ text: 'hallo' }))
    await transcribeAudio(new Blob(['x']))
    expect(uploadedName()).toBe('recording.webm')
  })

  it('marks the upload as the app\u2019s own call and leaves the boundary to the browser', async () => {
    fetchMock.mockResolvedValueOnce(ok({ text: 'hallo' }))
    await transcribeAudio(new Blob(['x'], { type: 'audio/webm' }))
    const init = fetchMock.mock.calls[0]![1] as RequestInit
    const headers = new Headers(init.headers as HeadersInit)
    // The marker is how the shell route recognises the PWA; a hand-set Content-Type on a
    // multipart body names no boundary and the server turns the upload away.
    expect(headers.get('X-Requested-With')).toBe('XMLHttpRequest')
    expect(headers.get('Content-Type')).toBeNull()
  })

  it('ends a silent transcription with the register\u2019s bound instead of holding the composer', async () => {
    // 0.03 s sits below the panel's own floor on purpose: the accessor reads the stored
    // number as it stands, so the case waits 30 ms instead of the field's 120 s default.
    seedDeepSettings([
      {
        key: 'advanced',
        fields: [
          {
            key: 'advanced.api_timeout',
            type: 'number',
            label: 'advanced.api_timeout',
            labelEn: 'advanced.api_timeout',
            default: 0.03,
            value: 0.03,
          },
        ],
      },
    ])
    fetchMock.mockImplementation(hangingFetch())
    try {
      await expect(transcribeAudio(new Blob(['x'], { type: 'audio/webm' }))).rejects.toMatchObject({
        name: 'ApiError',
        status: 408,
        reasonCode: 'request_timeout',
      })
    } finally {
      seedDeepSettings(null)
    }
  })

  it('surfaces the coded refusal and its status instead of the bare HTTP line', async () => {
    fetchMock.mockResolvedValueOnce(
      fail(409, 'Conflict', {
        error: {
          message: "Transcription needs the local speech model 'tiny'",
          reason_code: 'audio_model_download_required',
          reason_params: { model: 'tiny', size_mb: 78, host: 'huggingface.co' },
        },
      }),
    )

    const err = (await transcribeAudio(new Blob(['x'], { type: 'audio/webm' })).catch(
      (e: unknown) => e,
    )) as Error & { status?: number; reasonCode?: string }

    expect(err.message).toContain('speech model')
    expect(err.message).not.toContain('API 409')
    expect(err.status).toBe(409)
    expect(err.reasonCode).toBe('audio_model_download_required')
  })
})
