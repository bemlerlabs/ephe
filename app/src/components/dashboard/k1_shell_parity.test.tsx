import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import Sidebar from '@/components/dashboard/Sidebar'
import AgentPanel from '@/components/dashboard/AgentPanel'
import MessageBubble from '@/components/dashboard/MessageBubble'
import type { ChatMessage } from '@/types'

// K1 (2026-09-08): parity gaps from the E2 inventory — sidebar drag-resize
// with px persistence, double-click-to-fit on both dividers, "In Panel offnen" // language-gate: ignore — the German label this gap names, quoted from the product UI
// in the stream.

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))

const P = (type: string, x: number) =>
  Object.assign(new Event(type, { bubbles: true }), { clientX: x })

beforeEach(() => {
  localStorage.clear()
  // Force the desktop path explicitly (isDesktop = '(min-width: 1024px)').
  window.matchMedia = vi.fn((query: string) => ({
    matches: query.includes('min-width'),
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver
})

describe('K1 Sidebar drag-resize + Persistenz', () => {
  const sidebarProps = {
    isOpen: true,
    onClose: () => {},
    onOpenSettings: () => {},
    collapsed: false,
    onToggleCollapsed: () => {},
  }

  it('seeded width wird als inline-Pixelbreite gerendert', () => {
    localStorage.setItem('ephe.sidebar.width', '320')
    render(<Sidebar {...sidebarProps} />)
    expect(screen.getByTestId('chat-sidebar').style.width).toBe('320px')
  })

  it('Drag ueber den Henkel persistiert die neue Breite', () => {
    localStorage.setItem('ephe.sidebar.width', '288')
    render(<Sidebar {...sidebarProps} />)
    const handle = screen.getByTestId('sidebar-resize-handle')
    fireEvent(handle, P('pointerdown', 300))
    fireEvent(handle, P('pointermove', 340))
    fireEvent(handle, P('pointerup', 340))
    expect(localStorage.getItem('ephe.sidebar.width')).toBe('328')
  })

  it('Double-Click am Henkel = fit (Default 288)', () => {
    localStorage.setItem('ephe.sidebar.width', '430')
    render(<Sidebar {...sidebarProps} />)
    fireEvent.doubleClick(screen.getByTestId('sidebar-resize-handle'))
    expect(localStorage.getItem('ephe.sidebar.width')).toBe('288')
    expect(screen.getByTestId('chat-sidebar').style.width).toBe('288px')
  })

  it('Rail-Modus: keine Breite uebersteuert, Henkel entfaellt', () => {
    localStorage.setItem('ephe.sidebar.width', '320')
    render(<Sidebar {...sidebarProps} collapsed />)
    expect(screen.getByTestId('chat-sidebar').style.width).toBe('')
    expect(screen.queryByTestId('sidebar-resize-handle')).toBeNull()
  })
})

describe('K1 Panel-Trenner Double-Click-to-Fit', () => {
  it('Doppelklick auf die Panel-Kante setzt die Fit-Breite 420', () => {
    localStorage.setItem('ephe.panel.width', '720')
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    act(() => {
      window.dispatchEvent(new CustomEvent('ephe:preview-open', { detail: { tab: 'preview' } }))
    })
    fireEvent.doubleClick(screen.getByTestId('panel-resize-handle'))
    expect(localStorage.getItem('ephe.panel.width')).toBe('420')
  })
})

describe('K1 In-Panel-Links im Stream', () => {
  it('Artefakt-Karte traegt einen "In Panel offnen"-Knopf mit URL-Payload', () => {
    const seen: unknown[] = []
    const onOpen = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener('ephe:preview-open', onOpen)
    const msg: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: 'ok',
      timestamp: 1,
      artifacts: [
        {
          id: 'x',
          artifact_type: 'code_py',
          content: 'print(1)',
          language: 'python',
          title: 'demo.py',
          filename: 'demo.py',
        },
      ],
    }
    render(<MessageBubble message={msg} />)
    fireEvent.click(screen.getByTestId('artifact-open-panel'))
    window.removeEventListener('ephe:preview-open', onOpen)
    expect(seen.length).toBe(1)
    expect((seen[0] as { url: string }).url).toContain('demo.py')
  })
})
