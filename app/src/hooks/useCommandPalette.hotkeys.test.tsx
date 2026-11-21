/**
 * P2 area A: palette hotkeys and the browser entry.
 *
 * GIVEN  the global keydown handler of the command palette hook
 * WHEN   ⌥⌘B / Ctrl+Alt+B arrives (with no focused input)
 * THEN   it dispatches PREVIEW_OPEN_EVENT with detail {toggle:true} — the same
 *        toggle path as ⌘⇧O; inside the input/textarea guard nothing happens.
 * AND    the palette entry "panel-browser" opens the browser tab.
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TAB_KEYS } from '@/components/dashboard/agent/primitives'

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
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

function catchPreviewOpen() {
  const seen: Array<{ detail?: unknown }> = []
  const catcher = (e: Event) => seen.push({ detail: (e as CustomEvent).detail })
  window.addEventListener(PREVIEW_OPEN_EVENT, catcher)
  return { seen, stop: () => window.removeEventListener(PREVIEW_OPEN_EVENT, catcher) }
}

describe('useCommandPalette ⌥⌘B Panel-Toggle (P2-A)', () => {
  it('⌥⌘B dispatches the panel toggle event', () => {
    renderHook(() => useCommandPalette(), { wrapper })
    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        window.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'b', metaKey: true, altKey: true, bubbles: true }),
        )
      })
    } finally {
      stop()
    }
    expect(seen).toHaveLength(1)
    expect((seen[0]!.detail as { toggle?: boolean }).toggle).toBe(true)
  })

  it('Ctrl+Alt+B dispatches as well (Windows/Linux parity)', () => {
    renderHook(() => useCommandPalette(), { wrapper })
    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        window.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'B', ctrlKey: true, altKey: true, bubbles: true }),
        )
      })
    } finally {
      stop()
    }
    expect(seen).toHaveLength(1)
    expect((seen[0]!.detail as { toggle?: boolean }).toggle).toBe(true)
  })

  it('guard: nothing happens in a focused input (no toggle)', () => {
    renderHook(() => useCommandPalette(), { wrapper })
    const input = document.createElement('input')
    document.body.appendChild(input)
    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        input.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'b', metaKey: true, altKey: true, bubbles: true }),
        )
      })
    } finally {
      stop()
      input.remove()
    }
    expect(seen).toHaveLength(0)
  })

  it('⌘B without alt does not toggle (conflict-free with the sidebar binding)', () => {
    renderHook(() => useCommandPalette(), { wrapper })
    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        window.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'b', metaKey: true, bubbles: true }),
        )
      })
    } finally {
      stop()
    }
    expect(seen).toHaveLength(0)
  })
})

describe('useCommandPalette ⌘1 to ⌘9 panel tab binding (P0-2, single source)', () => {
  it("⌘1 dispatches exactly one event {tab:'preview', toggle:true}", () => {
    renderHook(() => useCommandPalette(), { wrapper })
    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        window.dispatchEvent(
          new KeyboardEvent('keydown', { key: '1', metaKey: true, bubbles: true }),
        )
      })
    } finally {
      stop()
    }
    // Single source of truth: no duplicate listener → exactly one event.
    expect(seen).toHaveLength(1)
    expect(seen[0]!.detail).toEqual({ tab: 'preview', toggle: true })
  })

  it('⌘9 and ⌘0 together cover TAB_KEYS, no tab without a key', () => {
    // WP5 let TAB_KEYS grow; the digit keys did not. So the binding must not be
    // written as "the ninth entry" — it has to come out of the list itself.
    expect(TAB_KEYS.length).toBeLessThanOrEqual(10)
    renderHook(() => useCommandPalette(), { wrapper })
    const press = (key: string) => {
      const caught = catchPreviewOpen()
      try {
        act(() => {
          window.dispatchEvent(new KeyboardEvent('keydown', { key, metaKey: true, bubbles: true }))
        })
      } finally {
        caught.stop()
      }
      expect(caught.seen).toHaveLength(1)
      return (caught.seen[0]!.detail as { tab?: string }).tab
    }
    expect(press('9')).toBe(TAB_KEYS[8])
    expect(press('0')).toBe(TAB_KEYS[TAB_KEYS.length - 1])
  })
})

describe('useCommandPalette panel-browser entry (P2-A)', () => {
  it("the palette lists panel-browser; the action dispatches tab:'browser'", () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const entry = Object.values(result.current.grouped)
      .flat()
      .find((c) => c.id === 'panel-browser')
    expect(entry).toBeTruthy()

    const { seen, stop } = catchPreviewOpen()
    try {
      act(() => {
        entry!.action()
      })
    } finally {
      stop()
    }
    expect(seen).toHaveLength(1)
    expect((seen[0]!.detail as { tab?: string }).tab).toBe('browser')
  })
})
