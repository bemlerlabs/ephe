/**
 * G3 (remote case): a phone reached through the QR link does not see the dev
 * server's loopback — Ephe fetches the body server-side via /api/proxy. When
 * THAT request fails Ephe really knows: the frame row has to render as
 * role="alert" instead of guessing "still loading".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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
  LAN_TOKEN: 'test-token',
  proxyFetch: vi.fn(async () => {
    throw new Error('upstream unreachable')
  }),
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

describe('G3 — Frame-Fehler im Remote-Fall (Proxy-Request fehlgeschlagen)', () => {
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

  it('gescheiterter Loopback-Proxy meldet error (role=alert) statt ewig zu laden', async () => {
    render(<AgentPanel />)
    act(() => {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, {
          detail: { url: 'http://localhost:5173/', tab: 'preview' },
        }),
      )
    })
    const status = await screen.findByTestId('preview-frame-status')
    // the proxy request has already been rejected before the test can read on —
    // so what is asserted is the final state, never an intermediate one.
    await vi.waitFor(() => expect(status.getAttribute('data-state')).toBe('error'))
    expect(status.getAttribute('role')).toBe('alert')
    expect(screen.getByTestId('preview-frame-retry')).toBeTruthy()
    fireEvent.click(screen.getByTestId('preview-frame-retry'))
    expect(screen.getByTestId('preview-frame-status').getAttribute('data-state')).toBe('loading')
  })
})
