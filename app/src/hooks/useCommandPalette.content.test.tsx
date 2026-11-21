/**
 * R25: the "content:…" full-text search inside the command palette hook.
 *
 * GIVEN  the backend /api/search returns FTS5 hits
 * WHEN   the query starts with "content:" (debounced)
 * THEN   contentResults land as commands in the "Message content" section;
 *        without the prefix it stays the ordinary command filter.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const api = vi.hoisted(() => ({
  searchSessionContent: vi.fn(),
  fileUrl: vi.fn((p: string) => `/api/file?path=${encodeURIComponent(p)}`),
}))
vi.mock('@/lib/api', () => api)

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

import { useCommandPalette } from './useCommandPalette'

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

const RESULTS = [
  {
    session_id: 'abc123',
    session_title: 'API-Setup',
    role: 'user' as const,
    snippet: '‹user› Wo ist der ‹API› ‹Key›?',
    content: 'Wo ist der API Key?',
    updated_at: '',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  api.searchSessionContent.mockResolvedValue({
    query: 'api',
    results: RESULTS,
    total: 1,
    elapsed_ms: 1.2,
  })
})

describe('useCommandPalette content search (R25)', () => {
  it('fills contentResults for "content:" queries after debounce', async () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })

    act(() => {
      result.current.setOpen(true)
      result.current.setQuery('content:api')
    })

    await waitFor(() => {
      expect(api.searchSessionContent).toHaveBeenCalledWith('api', 12, expect.any(AbortSignal))
    })
    await waitFor(() => {
      expect(result.current.contentResults).toHaveLength(1)
      expect(result.current.contentMode).toBe(true)
    })
    const section = Object.keys(result.current.grouped).find((s) => s.includes('content'))
    expect(section).toBeTruthy()
    const items = result.current.grouped[section!] ?? []
    const first = items[0]
    expect(first).toBeDefined()
    expect(first!.label).toBe('API-Setup')
    expect(first!.id).toBe('content-abc123-user')
  })

  it('does not trigger content search without the prefix', async () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })

    act(() => {
      result.current.setOpen(true)
      result.current.setQuery('api')
    })

    await new Promise((r) => setTimeout(r, 350))
    expect(api.searchSessionContent).not.toHaveBeenCalled()
    expect(result.current.contentMode).toBe(false)
  })

  it('ignores short terms (<2 chars) without a network call', async () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })

    act(() => {
      result.current.setOpen(true)
      result.current.setQuery('content:a')
    })

    await new Promise((r) => setTimeout(r, 350))
    expect(api.searchSessionContent).not.toHaveBeenCalled()
    expect(result.current.contentResults).toEqual([])
  })

  // P1 item 10: the 250 ms debounce only called clearTimeout. A fast typist's
  // earlier request was still in flight and could land after the newer one.
  it('cancels the in-flight content search on a new keystroke (AbortSignal)', async () => {
    const signals: AbortSignal[] = []
    api.searchSessionContent.mockImplementation(
      (_q: string, _limit: number, signal?: AbortSignal) => {
        if (signal) signals.push(signal)
        return new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        })
      },
    )

    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    act(() => {
      result.current.setOpen(true)
      result.current.setQuery('content:api')
    })

    await waitFor(() => expect(api.searchSessionContent).toHaveBeenCalled())
    expect(signals).toHaveLength(1)
    expect(signals[0]!.aborted).toBe(false)

    // The next keystroke supersedes the query → the earlier request must abort.
    act(() => {
      result.current.setQuery('content:apix')
    })
    await waitFor(() => expect(signals[0]!.aborted).toBe(true))
  })
})
