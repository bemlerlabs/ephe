/**
 * The consent surface needs the two reads the guard already answers.
 *
 * `80e3852f` landed `core/tools/creator_guard.py` and `GET|PUT
 * /api/creator/consent`, and the refusal it writes tells the model to "ask the
 * user to grant it" — a sentence no surface in the app could answer yet. These
 * are the client bindings, pinned against the three promises the store makes:
 * the key is the session, a write replaces the whole set rather than adding to
 * it, and the names are the closed three the guard knows.
 *
 * The route answers with both the closed set and what one session holds, so the
 * dialog can render three rows and check the held ones without a second read.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { CREATOR_PRIVILEGES, getCreatorConsent, putCreatorConsent } from './index'

const ok = (body: unknown) =>
  ({ ok: true, status: 200, statusText: 'OK', json: async () => body }) as Response

const ANSWER = {
  session_id: 'sess-1',
  privileges: ['code', 'files', 'network'],
  held: ['code'],
  mode: 'creator',
}

describe('the creator consent client', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('offers exactly the three permissions the guard stores', () => {
    expect([...CREATOR_PRIVILEGES].sort()).toEqual(['code', 'files', 'network'])
  })

  it('reads one session by its key and answers with what it holds', async () => {
    fetchMock.mockResolvedValueOnce(ok(ANSWER))

    const answer = await getCreatorConsent('sess-1')

    expect(answer.held).toEqual(['code'])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/creator/consent')
    expect(decodeURIComponent(String(url))).toContain('session_id=sess-1')
    expect(init.method ?? 'GET').toBe('GET')
  })

  it('writes the whole set the user chose, for the session it names', async () => {
    fetchMock.mockResolvedValueOnce(ok({ ...ANSWER, held: ['code', 'network'] }))

    await putCreatorConsent('sess-1', ['code', 'network'])

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/creator/consent')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: 'sess-1',
      privileges: ['code', 'network'],
    })
  })

  it('escapes a session key instead of pasting it into the query', async () => {
    fetchMock.mockResolvedValue(ok(ANSWER))

    await getCreatorConsent('a/b?c')

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).not.toContain('a/b?c')
    expect(String(url)).toContain('a%2Fb%3Fc')
  })
})
