// WS-E 47 — the panel-level keyboard walk: close the last pill and the keyboard
// must land on the empty state, not on <body>. The unit test in
// panelEmptyState.test.tsx proves the component; this one proves it through the
// panel's AnimatePresence swap.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

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
}))

vi.mock('./LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const openPane = () =>
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

describe('AgentPanel — keyboard walk into the empty state (WS-E 47)', () => {
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

  it('closing the last pill hands focus to the first open-card', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(
      <MemoryRouter>
        <AgentPanel />
      </MemoryRouter>,
    )
    openPane()
    const close = await screen.findByTestId('panel-tab-close-preview')
    close.focus()
    fireEvent.click(close)

    const card = await screen.findByTestId('panel-tab-card-preview')
    await vi.waitFor(() => expect(document.activeElement).toBe(card))
  })
})
