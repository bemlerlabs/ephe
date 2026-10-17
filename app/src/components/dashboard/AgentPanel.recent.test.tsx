import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

// W2-2 (2026-09-09): the "recently opened" list in the preview tab — the last
// 8 URLs from the tab history as chips; a click jumps back to that entry.

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

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

function baseStubs() {
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
}

describe('W2 — Preview-Recent-Liste', () => {
  beforeEach(() => {
    localStorage.clear()
    baseStubs()
  })

  it('nach zwei oeffneten Dateien listet der Tab beide als Chips (neueste zuerst)', async () => {
    render(<AgentPanel messages={[]} />)
    // P2-A: internal paths (not http(s) — the panel routes those into the
    // browser tab), so the preview recent list stays covered by this test.
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/a.md' } }),
    )
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/b.md' } }),
    )
    const list = await screen.findByTestId('preview-recent')
    const items = Array.from(list.querySelectorAll('[data-testid^="preview-recent-"]'))
    expect(items.length).toBe(2)
    expect(items[0]!.textContent).toContain('/tmp/b.md')
    expect(items[1]!.textContent).toContain('/tmp/a.md')
  })

  it('Chip-Klick setzt die URL zurueck ins Adressfeld', async () => {
    render(<AgentPanel messages={[]} />)
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/a.md' } }),
    )
    window.dispatchEvent(
      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: '/api/file?path=/tmp/b.md' } }),
    )
    const chip = await screen.findByTestId('preview-recent-0')
    fireEvent.click(chip)
    const input = screen.getByTestId('preview-url-input') as HTMLInputElement
    // Chip 0 carries the newest file (b.md) — clicking puts it back into the
    // address field, which shows prettifyUrl → the file name.
    expect(input.value).toContain('b.md')
  })

  it('nach 9 Dateien: die Liste haelt maximal 8 Eintraege', async () => {
    render(<AgentPanel messages={[]} />)
    for (let i = 1; i <= 9; i += 1) {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: `/api/file?path=/tmp/h${i}.md` } }),
      )
    }
    const list = await screen.findByTestId('preview-recent')
    expect(Array.from(list.querySelectorAll('[data-testid^="preview-recent-"]')).length).toBe(8)
  })
})
