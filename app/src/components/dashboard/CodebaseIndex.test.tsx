import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import CodebaseStatusBarPill from './CodebaseStatusBarPill'
import CodebaseIndexDialog from './CodebaseIndexDialog'
import { indexProgress, type CodebaseIndexStatus } from '@/lib/codebaseIndex'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}:${JSON.stringify(opts)}` : key,
    i18n: { language: 'en' },
  }),
}))

const idle: CodebaseIndexStatus = { state: 'idle', files: 0, symbols: 0, indexed: 0, total: 0 }
const indexing: CodebaseIndexStatus = {
  state: 'indexing',
  files: 0,
  symbols: 0,
  indexed: 160,
  total: 320,
}
const ready: CodebaseIndexStatus = {
  state: 'ready',
  files: 320,
  symbols: 4821,
  indexed: 320,
  total: 320,
}

function statusResponse(body: CodebaseIndexStatus) {
  return { ok: true, json: async () => body } as Response
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CodebaseStatusBarPill', () => {
  it('names the symbol count once the index is ready', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => statusResponse(ready)))
    render(<CodebaseStatusBarPill />)
    const pill = await screen.findByTestId('codebase-pill')
    expect(pill).toHaveAttribute('data-state', 'ready')
    expect(pill.textContent).toContain('codebase.pillReady')
    expect(pill.textContent).toContain('4821')
  })

  it('opens the dialog on click', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => statusResponse(ready)))
    const onOpen = vi.fn()
    render(<CodebaseStatusBarPill onOpen={onOpen} />)
    fireEvent.click(await screen.findByTestId('codebase-pill'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('reads a refused status request as idle, not as a failed index', async () => {
    // The defect this case pins: with no answer to read (no workspace chosen, the
    // server not up yet, a refused port), the pill used to paint the danger tone and
    // claim an index had failed. Nothing had run, so nothing had failed.
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('fetch failed') }))
    render(<CodebaseStatusBarPill />)
    const pill = await screen.findByTestId('codebase-pill')
    expect(pill).toHaveAttribute('data-state', 'idle')
    expect(pill.textContent).toContain('codebase.pillIdle')
  })

  it('names the failure the route itself reports', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => statusResponse({ ...idle, state: 'error' })))
    render(<CodebaseStatusBarPill />)
    const pill = await screen.findByTestId('codebase-pill')
    expect(pill).toHaveAttribute('data-state', 'error')
    expect(pill.textContent).toContain('codebase.pillError')
  })
})

describe('CodebaseIndexDialog', () => {
  it('renders nothing while closed', () => {
    render(<CodebaseIndexDialog open={false} onClose={() => {}} />)
    expect(screen.queryByTestId('codebase-dialog')).toBeNull()
  })

  it('shows the file progress of a running index', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => statusResponse(indexing)))
    render(<CodebaseIndexDialog open onClose={() => {}} />)
    const dialog = await screen.findByTestId('codebase-dialog')
    expect(dialog.textContent).toContain('codebase.title')
    const bar = await screen.findByTestId('codebase-progress')
    expect(bar.style.width).toBe('50%')
    expect(screen.getByTestId('codebase-start')).toBeDisabled()
  })

  it('starts the index and shows the finished symbol count', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(idle))
      .mockResolvedValueOnce(statusResponse(ready))
    vi.stubGlobal('fetch', fetchMock)
    render(<CodebaseIndexDialog open onClose={() => {}} />)

    const button = await screen.findByTestId('codebase-start')
    fireEvent.click(button)

    expect(await screen.findByTestId('codebase-count')).toHaveTextContent('4821')
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toContain('/api/project/index')
    expect(init.method).toBe('POST')
  })

  it('names a failed index request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    )
    render(<CodebaseIndexDialog open onClose={() => {}} />)
    fireEvent.click(await screen.findByTestId('codebase-start'))
    expect(await screen.findByTestId('codebase-error')).toHaveTextContent('HTTP 500')
  })
})

describe('indexProgress', () => {
  it('is the indexed share while running and complete when ready', () => {
    expect(indexProgress(indexing)).toBe(50)
    expect(indexProgress(ready)).toBe(100)
    expect(indexProgress(idle)).toBe(0)
  })
})
