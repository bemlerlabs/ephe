/**
 * W1 (built-in browser, native path): inside the Tauri shell an external page
 * opens in a child WebView above the frame — not in an iframe that reports an
 * empty box for google.com as "ready" (measured 2026-10-06: region 419×646 px,
 * content empty, status line gone).
 *
 * The bridge is simulated here (window.__TAURI__), the rest is the real code:
 * usesNativeBrowser(), useNativeBrowserPane(), previewTab.tsx.
 *
 * GIVEN  a pane with a measured frame and a simulated shell bridge
 * THEN   a) external http(s) addresses go to the shell as browser_open with
 *           bounds, and there is no iframe left,
 *        b) without a shell the iframe stays the only path (PWA unchanged),
 *        c) loopback (dev server with HMR, LAN proxy) stays with the iframe,
 *        d) the status line follows the load events of the shell,
 *        e) a mask over the pane hides the native page and lifts the hiding
 *           again.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

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

type Call = { cmd: string; args: Record<string, unknown> }
let calls: Call[] = []
let handlers: Record<string, (e: { payload: unknown }) => void> = {}

/** The measured frame region of the panel — without this stub jsdom sees 0×0 everywhere. */
const REGION = { x: 861, y: 125, width: 419, height: 675 }
let rectStub: () => DOMRect

function openUrl(url: string) {
  act(() => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url, tab: 'preview' } }))
  })
}

const browserCalls = (cmd: string) => calls.filter((c) => c.cmd === cmd)
// The geometry sync throttles to one frame — the flush has to await a real
// frame, not just a microtask.
const flush = async () => {
  await act(async () => {
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

describe('W1 — das native Browser-Pane', () => {
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
    calls = []
    handlers = {}
    rectStub = () => ({ ...REGION, toJSON: () => REGION }) as unknown as DOMRect
    Element.prototype.getBoundingClientRect = function () {
      return (this as HTMLElement).dataset.testid === 'preview-frame-region'
        ? rectStub()
        : ({ x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 } as DOMRect)
    }
  })

  afterEach(() => {
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
    document.body.innerHTML = ''
  })

  function simulateShell() {
    ;(window as unknown as { __TAURI__: unknown }).__TAURI__ = {
      core: {
        invoke: (cmd: string, args: Record<string, unknown>) => {
          calls.push({ cmd, args: args ?? {} })
          return Promise.resolve(null)
        },
      },
      event: {
        listen: (name: string, handler: (e: { payload: unknown }) => void) => {
          handlers[name] = handler
          return Promise.resolve(() => {})
        },
      },
    }
  }

  const emit = (name: string, payload: unknown) =>
    act(() => {
      handlers[name]?.({ payload })
    })

  it('externe Adresse geht an den Shell — ein iframe gibt es hier nicht mehr', async () => {
    simulateShell()
    render(<AgentPanel />)
    openUrl('https://google.com')
    await flush()

    const opened = browserCalls('browser_open')
    expect(opened).toHaveLength(1)
    expect(opened[0]!.args.url).toBe('https://google.com')
    expect(opened[0]!.args.bounds).toEqual(REGION)
    expect(screen.queryByTestId('preview-frame')).toBeNull()
    expect(screen.getByTestId('preview-frame-native')).toBeTruthy()
  })

  it('ohne Shell bleibt das iframe der einzige Weg', async () => {
    render(<AgentPanel />)
    openUrl('https://google.com')
    await flush()

    expect(calls).toHaveLength(0)
    expect(screen.getByTestId('preview-frame').getAttribute('src')).toBe('https://google.com')
    expect(screen.queryByTestId('preview-frame-native')).toBeNull()
  })

  it('Loopback behält den Dev-Server-Pfad (HMR am echten Origin)', async () => {
    simulateShell()
    render(<AgentPanel />)
    openUrl('http://localhost:5173/')
    await flush()

    expect(browserCalls('browser_open')).toHaveLength(0)
    expect(screen.getByTestId('preview-frame')).toBeTruthy()
  })

  it('die Statuszeile folgt den Ladeereignissen des Shells', async () => {
    simulateShell()
    render(<AgentPanel />)
    openUrl('https://example.com')
    await flush()
    expect(screen.getByTestId('preview-frame-status')).toBeTruthy()

    emit('browser:load', { phase: 'finished', url: 'https://example.com/' })
    await flush()
    expect(screen.queryByTestId('preview-frame-status')).toBeNull()

    emit('browser:load', { phase: 'started', url: 'https://example.com/x' })
    await flush()
    expect(screen.getByTestId('preview-frame-status')).toBeTruthy()

    emit('browser:title', { title: 'Example Domain' })
    await flush()
    expect(screen.getByTestId('preview-frame-native').textContent).toBe('Example Domain')
  })

  it('eine Maske über dem Pane versteckt die native Seite — und hebt es wieder auf', async () => {
    simulateShell()
    render(<AgentPanel />)
    openUrl('https://example.com')
    await flush()

    const mask = document.createElement('div')
    mask.setAttribute('role', 'dialog')
    mask.setAttribute('aria-modal', 'true')
    act(() => {
      document.body.appendChild(mask)
    })
    await flush()
    await flush()
    const hidden = browserCalls('browser_visible').filter((c) => c.args.visible === false)
    expect(hidden.length).toBeGreaterThan(0)

    act(() => {
      mask.remove()
    })
    await flush()
    await flush()
    const shown = browserCalls('browser_visible').filter((c) => c.args.visible === true)
    expect(shown.length).toBeGreaterThan(0)
  })

  it('Escape gehört der Maske: das Pane hinter einer offenen Palette bleibt stehen', async () => {
    const { unmount } = render(<AgentPanel />)
    openUrl('https://example.com')
    await flush()
    expect(screen.getByTestId('preview-frame-region')).toBeTruthy()

    const mask = document.createElement('div')
    mask.setAttribute('role', 'dialog')
    act(() => {
      document.body.appendChild(mask)
    })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByTestId('preview-frame-region')).toBeTruthy()

    act(() => {
      mask.remove()
    })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('preview-frame-region')).toBeNull()
    unmount()
  })

  it('ein fehlgeschlagenes Öffnen sagt den Grund, statt leer zu bleiben', async () => {
    ;(window as unknown as { __TAURI__: unknown }).__TAURI__ = {
      core: {
        invoke: (cmd: string, args: Record<string, unknown>) => {
          calls.push({ cmd, args: args ?? {} })
          return cmd === 'browser_open'
            ? Promise.reject(new Error('Hauptfenster nicht gefunden'))
            : Promise.resolve(null)
        },
      },
      event: {
        listen: () => Promise.resolve(() => {}),
      },
    }
    render(<AgentPanel />)
    openUrl('https://example.com')
    await flush()
    const status = screen.getByTestId('preview-frame-status')
    expect(status.getAttribute('data-state')).toBe('error')
    expect(status.textContent).toContain('Hauptfenster nicht gefunden')
  })
})
