/**
 * W4 — the vision bindings reach the routes the server exposes.
 *
 * The multipart path is checked as a FormData body (the browser sets the
 * boundary), the base64 path as a JSON body. Both must carry the LAN token
 * header policy of the shared fetch helpers.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { analyzeImage, analyzeImageBase64 } from './index'

const ok = (body: unknown) =>
  ({ ok: true, status: 200, statusText: 'OK', json: async () => body }) as Response

const analysis = {
  analysis: 'a cat',
  filename: 'upload_1.png',
  image_url: '/images/upload_1.png',
  model: 'local:7b',
  question: 'What is this?',
}

describe('vision client bindings (W4)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('uploads an image as multipart to /api/vision/analyze', async () => {
    fetchMock.mockResolvedValueOnce(ok(analysis))
    const file = new File(['png'], 'shot.png', { type: 'image/png' })

    const result = await analyzeImage(file, 'What is this?')

    expect(result.analysis).toBe('a cat')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/vision/analyze')
    expect(init.method).toBe('POST')
    const body = init.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('question')).toBe('What is this?')
    expect((body.get('file') as File).name).toBe('shot.png')
    // The browser sets the boundary itself; a hand-set JSON type would break it.
    expect(init.headers).not.toHaveProperty('Content-Type')
  })

  it('sends the base64 path as JSON to /api/vision/base64', async () => {
    fetchMock.mockResolvedValueOnce(ok(analysis))

    await analyzeImageBase64('AAAA', 'What is this?')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/vision/base64')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      image_b64: 'AAAA',
      question: 'What is this?',
    })
  })

  it('surfaces the server detail when the upload is refused', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 415,
      statusText: 'Unsupported Media Type',
      json: async () => ({ detail: 'unsupported format: text/plain' }),
    } as Response)

    await expect(analyzeImage(new File(['x'], 'a.txt', { type: 'text/plain' }))).rejects.toThrow(
      'unsupported format: text/plain',
    )
  })
})
