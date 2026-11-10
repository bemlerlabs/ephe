/**
 * #39 — the measured symptom, at the pane: every persisted panel key holds valid
 * JSON of the wrong shape and the boot still comes up on the documented defaults.
 *
 * GIVEN  ephe.panel.tabs/recent/activeTab behind an object, a null entry and an
 *        object again, ephe.panel.dock 'middle', ephe.panel.width 'Infinity'
 * WHEN   the panel mounts (nothing else)
 * THEN   no exception is thrown and the first PANEL_STATE_EVENT carries the
 *        default pane: open=false, tab 'preview', tabs ['preview'], width 420,
 *        dock 'right' — the same values a fresh profile gets.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PANEL_STATE_EVENT } from '@/lib/panelEvents'

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  runShell: vi.fn(async () => ({ output: '' })),
  runShellPty: vi.fn(async () => ({ command: 'ls', output: '', ok: true })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  listArtifacts: vi.fn(async () => ({ artifacts: [] })),
  listFs: vi.fn(async () => ({ entries: [] })),
  listChangeSets: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'p', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  gitAdd: vi.fn(async () => ({ success: true })),
  gitCommit: vi.fn(async () => ({ success: true, hash: 'abc1234' })),
  gitApplyPatch: vi.fn(async () => ({ success: true })),
  fileUrl: vi.fn((p: string) => `/api/file?path=${p}`),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('ephe.panel.tabs', '{"a":1}')
  localStorage.setItem('ephe.panel.recent', '[null]')
  localStorage.setItem('ephe.panel.activeTab', '{"a":1}')
  localStorage.setItem('ephe.panel.dock', 'middle')
  localStorage.setItem('ephe.panel.width', 'Infinity')
  window.matchMedia = vi.fn((q: string) => ({
    matches: false,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver
})

describe('panel boot — every persisted key has valid JSON of the wrong shape', () => {
  it('comes up on the default pane without an exception', () => {
    const seen: Record<string, unknown>[] = []
    const listener = (e: Event) => seen.push((e as CustomEvent).detail ?? {})
    window.addEventListener(PANEL_STATE_EVENT, listener)
    try {
      expect(() => render(<AgentPanel />)).not.toThrow()
    } finally {
      window.removeEventListener(PANEL_STATE_EVENT, listener)
    }
    expect(seen.length).toBeGreaterThan(0)
    expect(seen[seen.length - 1]).toMatchObject({
      open: false,
      tab: 'preview',
      tabs: ['preview'],
      width: 420,
      dock: 'right',
    })
  })
})
