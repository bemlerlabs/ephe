/**
 * The workspace column points at a file, the workbench card at an id: two doors.
 *
 * `GET /api/file` streams the bytes, `GET /api/file/preview` renders the formats a browser
 * cannot draw. The preview helper is the only thing between a path in the tree and that
 * route, so its own address is pinned here — the route, and the encoding that keeps a path
 * with a space or a query marker inside one parameter.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { filePreviewByPath } from './index'

describe('the file preview binding (workspace column)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('asks the preview route for the path it was given', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ mode: 'table', header: ['item'], rows: [['bread']], sheets: [] }),
    } as Response)

    const answer = await filePreviewByPath('/werk/zahlen.xlsx')

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit?]
    expect(String(url)).toContain('/api/file/preview?path=%2Fwerk%2Fzahlen.xlsx')
    expect(answer.mode).toBe('table')
  })

  it('keeps a space and a question mark inside one parameter', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ mode: 'none', reason: 'no-text-preview' }),
    } as Response)

    await filePreviewByPath('/werk/mein? bericht.docx')

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit?]
    expect(String(url)).toContain('path=%2Fwerk%2Fmein%3F%20bericht.docx')
  })
})
