/**
 * W1-b (reader view): the same address, two routes. An iframe can only show what
 * embedding permits; the reader view fetches the text through the server.
 *
 * GIVEN  the browser pane with an external address
 * THEN   a) the toggle only exists where there is something to read,
 *        b) it shows text instead of the frame and keeps the address,
 *        c) an empty text is a statement with a reason, not an empty box,
 *        d) the truncation is announced.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import type { Mock } from 'vitest'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { readUrl } from '@/lib/api/endpoints'
import type { ReaderResult } from '@/lib/api/endpoints'

// The reader view is the only reason to stub this route in the test.
vi.mock('@/lib/api/endpoints', async (orig) => ({
  ...((await orig()) as Record<string, unknown>),
  readUrl: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'defaultValue' in opts ? String(opts.defaultValue) : key,
  }),
}))

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  runShell: vi.fn(async () => ({ output: '' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'proj', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
}))

function openUrl(url: string) {
  act(() => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url, tab: 'preview' } }))
  })
}

function result(patch: Partial<ReaderResult>) {
  return {
    ok: true,
    reason: '',
    title: 'Titel der Seite',
    text: '# Zwischenüberschrift\nEin Absatz mit Inhalt.\n- erster Punkt',
    chars: 60,
    truncated: false,
    target: 'https://example.org/a',
    ...patch,
  } as ReaderResult
}

describe('W1-b — die Lese-Ansicht im Browser-Pane', () => {
  beforeEach(() => {
    localStorage.clear()
    if (!window.matchMedia) {
      window.matchMedia = vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      })) as unknown as typeof window.matchMedia
    }
    if (!globalThis.ResizeObserver) {
      globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
      } as unknown as typeof globalThis.ResizeObserver
    }
    ;(readUrl as Mock).mockReset()
  })

  it('der Umschalter existiert nur bei einer Adresse, die Text tragen kann', async () => {
    render(<AgentPanel />)
    expect(screen.queryByTestId('preview-reader-toggle')).toBeNull()

    openUrl('https://example.org/a')
    const toggle = await screen.findByTestId('preview-reader-toggle')
    expect(toggle.getAttribute('aria-pressed')).toBe('false')
  })

  it('Lesen zeigt Text statt Frame und behält die Adresse', async () => {
    ;(readUrl as Mock).mockResolvedValue(result({}))
    render(<AgentPanel />)
    openUrl('https://example.org/a')
    const toggle = await screen.findByTestId('preview-reader-toggle')

    fireEvent.click(toggle)
    await waitFor(() => expect(screen.getByTestId('reader-view')).toBeTruthy())

    expect(toggle.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('Titel der Seite')).toBeTruthy()
    expect(screen.getByText('Zwischenüberschrift')).toBeTruthy()
    expect(screen.getByText('· erster Punkt')).toBeTruthy()
    expect(screen.queryByTestId('preview-frame')).toBeNull()
    // The address bar stays, otherwise nobody knows which page the text came from.
    expect(screen.getByTestId('preview-url-input')).toBeTruthy()
  })

  it('ohne Text sagt die Fläche warum, statt leer zu bleiben', async () => {
    ;(readUrl as Mock).mockResolvedValue(
      result({ ok: false, text: '', chars: 0, reason: '[verweigert] loopback ist nicht erlaubt' }),
    )
    render(<AgentPanel />)
    openUrl('https://example.org/a')
    fireEvent.click(await screen.findByTestId('preview-reader-toggle'))

    const fehler = await screen.findByTestId('reader-error')
    expect(fehler.getAttribute('role')).toBe('alert')
    expect(fehler.textContent).toContain('loopback ist nicht erlaubt')
  })

  it('eine Kürzung wird gesagt', async () => {
    ;(readUrl as Mock).mockResolvedValue(result({ truncated: true }))
    render(<AgentPanel />)
    openUrl('https://example.org/a')
    fireEvent.click(await screen.findByTestId('preview-reader-toggle'))

    expect(await screen.findByTestId('reader-truncated')).toBeTruthy()
  })

  it('eine leere ÜberschriftZeile wird nicht zum Inhalt', async () => {
    // The server writes "# " for every heading — an empty one (image only, spacing
    // only) would otherwise be noise in the reading copy.
    ;(readUrl as Mock).mockResolvedValue(
      result({ text: '### \nEin echter Absatz.\n#### Zwischenüberschrift\n' }),
    )
    render(<AgentPanel />)
    openUrl('https://example.org/a')
    fireEvent.click(await screen.findByTestId('preview-reader-toggle'))

    const ansicht = await screen.findByTestId('reader-view')
    expect(ansicht.textContent).toContain('Ein echter Absatz.')
    expect(ansicht.textContent).toContain('Zwischenüberschrift')
    expect(ansicht.textContent).not.toMatch(/#{2,}/)
  })

  it('der Abruffehler des Clients landet als Grund, nicht als Stille', async () => {
    ;(readUrl as Mock).mockRejectedValue(new Error('Der Server antwortet nicht'))
    render(<AgentPanel />)
    openUrl('https://example.org/a')
    fireEvent.click(await screen.findByTestId('preview-reader-toggle'))

    expect(await screen.findByTestId('reader-error')).toBeTruthy()
    expect(screen.getByTestId('reader-error').textContent).toContain('Der Server antwortet nicht')
  })
})
