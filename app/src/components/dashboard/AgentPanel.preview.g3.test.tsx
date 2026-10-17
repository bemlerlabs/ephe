/**
 * G3 (built-in browser): the URL pane has to be honest about what the iframe does —
 * and the sandbox has to be real control rather than an exit.
 *
 * GIVEN  the browser pane with a loaded URL
 * THEN   a) the sandbox has no escape case (popups-to-escape-sandbox cancels the
 *           whole sandbox: a window.open takes the freedom with it),
 *        b) while loading a role="status" line is alive (a screen reader learns
 *           the progress), and it disappears after 'load',
 *        c) if the load never comes, the line switches to the honest
 *           "blocked/reachable" hint after the time budget (for cross-origin the
 *           browser cannot report an error — an invented error message would be a
 *           lie),
 *        d) the border/contrast toggles are exposed as a pressed state,
 *        e) the overflow menu item receives focus and gives it back.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, act, waitFor } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { FRAME_SLOW_MS } from '@/components/dashboard/agent/previewUrl'

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

describe('G3 — Browser-Pane: sandbox, Ladezustand, Accessibility', () => {
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
  })

  it('sandbox ohne Escape-Fall: kein allow-popups-to-escape-sandbox', async () => {
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    const frame = (await screen.findByTestId('preview-frame')) as HTMLIFrameElement
    const tokens = (frame.getAttribute('sandbox') ?? '').split(/\s+/).filter(Boolean)
    expect(tokens).not.toContain('allow-popups-to-escape-sandbox')
    // Popups stay allowed — just without the escape clause.
    expect(tokens).toContain('allow-popups')
    // A frame with no sandbox directive at all would be worse than before.
    expect(tokens.length).toBeGreaterThan(1)
  })

  it('role="status" meldet das Laden und verschwindet nach load; aria-busy folgt', async () => {
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    const status = await screen.findByTestId('preview-frame-status')
    expect(status.getAttribute('role')).toBe('status')
    expect(status.textContent).toBeTruthy()
    const region = (await screen.findByTestId('preview-frame-region')) as HTMLElement
    expect(region.getAttribute('aria-busy')).toBe('true')
    const frame = (await screen.findByTestId('preview-frame')) as HTMLIFrameElement
    act(() => {
      fireEvent.load(frame)
    })
    expect(screen.queryByTestId('preview-frame-status')).toBeNull()
    expect(region.getAttribute('aria-busy')).toBe('false')
  })

  it('bleibt der load aus, wechselt die Zeile nach dem Zeitbudget auf slow + Retry', async () => {
    vi.useFakeTimers()
    try {
      render(<AgentPanel />)
      openUrl('https://example.com/slow')
      const status = screen.getByTestId('preview-frame-status')
      expect(status.getAttribute('data-state')).toBe('loading')
      expect(screen.queryByTestId('preview-frame-retry')).toBeNull()
      act(() => {
        vi.advanceTimersByTime(FRAME_SLOW_MS + 50)
      })
      expect(screen.getByTestId('preview-frame-status').getAttribute('data-state')).toBe('slow')
      // The honest text stays a hint, not an invented error message — and it
      // offers an action: retry, because the most common case is a dev server
      // that is only just starting.
      expect(screen.getByTestId('preview-frame-retry')).toBeTruthy()
      expect(screen.queryByRole('alert')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('Retry aus dem slow-Zustand laedt neu und nimmt den Ladezustand wieder auf', async () => {
    vi.useFakeTimers()
    try {
      render(<AgentPanel />)
      openUrl('https://example.com/slow')
      act(() => {
        vi.advanceTimersByTime(FRAME_SLOW_MS + 50)
      })
      fireEvent.click(screen.getByTestId('preview-frame-retry'))
      const status = screen.getByTestId('preview-frame-status')
      expect(status.getAttribute('data-state')).toBe('loading')
      // No dangling slow hint after the reload: the deadline runs again.
      act(() => {
        vi.advanceTimersByTime(FRAME_SLOW_MS + 50)
      })
      expect(screen.getByTestId('preview-frame-status').getAttribute('data-state')).toBe('slow')
    } finally {
      vi.useRealTimers()
    }
  })

  it('Rahmenbreite und Kontrast sind als aria-pressed exponiert', async () => {
    // R2-P1: the two secondary switches live in the ⋯ menu, so the address bar
    // does not shrink to 23 characters in a 420 px pane.
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    fireEvent.click(await screen.findByTestId('preview-overflow'))
    const menu = await screen.findByTestId('preview-menu')
    const device = within(menu).getByTestId('preview-device')
    const contrast = within(menu).getByTestId('preview-contrast')
    expect(device.getAttribute('aria-pressed')).toBe('false')
    expect(contrast.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(device)
    fireEvent.click(await screen.findByTestId('preview-overflow'))
    const menu2 = await screen.findByTestId('preview-menu')
    expect(within(menu2).getByTestId('preview-device').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(within(menu2).getByTestId('preview-contrast'))
    fireEvent.click(await screen.findByTestId('preview-overflow'))
    const menu3 = await screen.findByTestId('preview-menu')
    expect(within(menu3).getByTestId('preview-contrast').getAttribute('aria-pressed')).toBe('true')
  })

  it('Adressleiste ist eine URL-Leiste: inputMode, keine Autovervollstaetigung, keine Korrektur', async () => {
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    const input = (await screen.findByTestId('preview-url-input')) as HTMLInputElement
    expect(input.getAttribute('inputmode')).toBe('url')
    expect(input.getAttribute('autocomplete')).toBe('off')
    expect(input.getAttribute('autocorrect')).toBe('off')
    expect(input.getAttribute('autocapitalize')).toBe('none')
    expect(input.getAttribute('spellcheck')).toBe('false')
  })

  it('Ueberlauf-Menue: Fokus faehrt in den Menuepunkt und nach Escape zurueck', async () => {
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    const trigger = await screen.findByTestId('preview-overflow')
    fireEvent.click(trigger)
    const menu = await screen.findByTestId('preview-menu')
    const item = within(menu).getAllByRole('menuitem')[0]!
    await waitFor(() => expect(document.activeElement).toBe(item))
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(screen.queryByTestId('preview-menu')).toBeNull()
    expect(document.activeElement).toBe(trigger)
    // The finding of this wave: the panel listens to the same window Escape and
    // used to close the whole panel as soon as only the menu should have closed.
    expect(screen.getByTestId('preview-frame-region')).toBeTruthy()
  })

  it('Ein spaeter eintreffender URL-Fokus ueberholt ein geoeffnetes Menue nicht', async () => {
    render(<AgentPanel />)
    openUrl('https://example.com/article')
    const trigger = await screen.findByTestId('preview-overflow')
    fireEvent.click(trigger)
    const menu = await screen.findByTestId('preview-menu')
    const item = within(menu).getAllByRole('menuitem')[0]!
    await waitFor(() => expect(document.activeElement).toBe(item))
    // The agent streams a new URL while the keyboard is already in the menu.
    // panel.tsx focuses the address bar with a delay — that late move must not
    // overtake anyone who is already inside the panel.
    openUrl('https://example.com/naechste')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    expect(document.activeElement).toBe(item)
    expect(screen.getByDisplayValue('https://example.com/naechste')).toBeTruthy()
    // ... and the trigger is still alive: the returned focus is not a dead corner.
    expect(trigger.isConnected).toBe(true)
  })

  it('Von ausserhalb zieht der URL-Fokus in die Adressleiste — die Goldener-Pfad-Haelfte', async () => {
    render(<AgentPanel />)
    // The user is in the chat (here: outside the panel) and opens a source. The
    // guard above must not switch off this late move, otherwise the address bar is
    // not typeable after opening without clicking into it first.
    openUrl('https://example.com/article')
    const input = await screen.findByTestId('preview-url-input')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    expect(document.activeElement).toBe(input)
  })

  it('Datei-Vorschau (kein Frame) zeigt keine Frame-Statuszeile — sie hat ihre eigene', async () => {
    render(<AgentPanel />)
    openUrl('/api/file?path=/tmp/notes.md')
    // The markdown/code preview reads via fetch and has its own states for that
    // (aria-busy + role="alert" in FilePreviewBody) — the frame line must not show
    // up here on top, since it describes an iframe.
    expect(await screen.findByTestId('preview-url-input')).toBeTruthy()
    expect(screen.queryByTestId('preview-frame-status')).toBeNull()
    expect(screen.queryByTestId('preview-frame-region')).toBeNull()
  })
})
