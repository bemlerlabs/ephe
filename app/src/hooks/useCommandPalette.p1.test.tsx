/**
 * P1 [F5]: a palette with an action per result — artifacts of the active session
 * (click → preview) and settings sub-pages (ephe:open-settings + tab).
 *
 * W10 (FINDINGS 2026-10-12, medium): the settings list has to BE the panel's
 * navigation (settings/model.tsx NAV) and reach a control, not only a tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const api = vi.hoisted(() => ({
  searchSessionContent: vi.fn(),
  fileUrl: vi.fn((p: string) => `/api/file?path=${encodeURIComponent(p)}`),
}))
vi.mock('@/lib/api', () => api)

// The shell's only working way out of the app window (src/lib/nativeBrowser.ts).
const native = vi.hoisted(() => ({ openExternally: vi.fn(async () => {}) }))
vi.mock('@/lib/nativeBrowser', () => native)

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
import { SETTINGS_NAV_KEYS } from './paletteExtraItems'
import { useChatStore } from '@/store/chatStore'
import { NAV } from '@/components/dashboard/settings/model'
import { ROW_INDEX } from '@/components/dashboard/settings/model/rowIndex'
import type { Session, ChatMessage } from '@/types'

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

const ART_MSG: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: '',
  timestamp: Date.now(),
  artifacts: [
    {
      id: 'art1',
      artifact_type: 'file',
      content: '',
      language: '',
      title: 'report.pdf',
      filename: 'report.pdf',
    },
  ],
}
const SESSION: Session = {
  id: 's1',
  title: 'Artefakt-Session',
  createdAt: Date.now(),
  messages: [ART_MSG],
}

beforeEach(() => {
  vi.clearAllMocks()
  useChatStore.setState({ sessions: [SESSION], activeSessionId: 's1', currentSession: SESSION })
})

function settingsEntries(grouped: Record<string, { id: string; label: string }[]>) {
  return Object.values(grouped)
    .flat()
    .filter((c) => c.id.startsWith('settings-'))
}

describe('useCommandPalette Aktionen (P1 [F5])', () => {
  it('listet Artefakte der aktiven Session; Aktion öffnet die Preview-URL', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const artifactSection = Object.values(result.current.grouped)
      .flat()
      .find((c) => c.id === 'artifact-report.pdf')
    expect(artifactSection).toBeTruthy()
    expect(artifactSection!.label).toBe('report.pdf')

    const seen: CustomEvent[] = []
    const catcher = (e: Event) => seen.push(e as CustomEvent)
    window.addEventListener('ephe:preview-open', catcher)
    try {
      act(() => {
        artifactSection!.action()
      })
    } finally {
      window.removeEventListener('ephe:preview-open', catcher)
    }
    expect(String((seen[0]!.detail as { url?: string }).url)).toContain('report.pdf')
  })

  it('Settings-Unterseiten: settings-engine-Eintrag dispatcht open-settings + Tab', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const all = Object.values(result.current.grouped).flat()
    const engineEntry = all.find((c) => c.id === 'settings-engine')
    expect(engineEntry).toBeTruthy()

    const seen: Array<{ type: string; detail?: unknown }> = []
    const catcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:open-settings', catcher)
    window.addEventListener('ephe:settings-tab', catcher)
    try {
      act(() => {
        engineEntry!.action()
      })
    } finally {
      window.removeEventListener('ephe:open-settings', catcher)
      window.removeEventListener('ephe:settings-tab', catcher)
    }
    expect(seen.map((s) => s.type)).toEqual(['ephe:open-settings', 'ephe:settings-tab'])
    expect((seen[1]!.detail as { tab?: string }).tab).toBe('engine')
  })
})

describe('useCommandPalette: the palette carries the real settings navigation', () => {
  it('derives its tab rows from NAV — one entry per tab, same order', () => {
    expect(SETTINGS_NAV_KEYS).toEqual(NAV.map((n) => n.key))
  })

  it('exposes an entry for every NAV tab, so a nav that grows can never outrun it', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const ids = settingsEntries(result.current.grouped).map((c) => c.id)
    expect(ids.slice().sort()).toEqual(NAV.map((n) => `settings-${n.key}`).sort())
  })

  it('carries no phantom key: every entry names a tab the panel can render', () => {
    const navKeys = NAV.map((n) => n.key as string)
    for (const key of SETTINGS_NAV_KEYS) {
      expect(navKeys).toContain(key as string)
    }
    expect(SETTINGS_NAV_KEYS as readonly string[]).not.toContain('deep')
  })
})

describe('useCommandPalette: a control is reachable by name', () => {
  it('offers the panel row index as entries once a query names a control', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    // No query: the curated list stays as it is — the row index would drown it.
    expect(
      settingsEntries(result.current.grouped).every((c) => !c.id.startsWith('settings-row-')),
    ).toBe(true)

    act(() => result.current.setQuery('privacyProfileRow'))
    const hits = Object.values(result.current.grouped)
      .flat()
      .map((c) => c.id)
    expect(hits).toContain('settings-row-behaviour-settings.privacyProfileRow')
  })

  it('a control entry opens the row tab AND hands the row name to the panel search', () => {
    const row = ROW_INDEX.find((r) => r.key === 'settings.privacyProfileRow')
    expect(row).toBeTruthy()

    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    act(() => result.current.setQuery('privacyProfileRow'))
    const entry = Object.values(result.current.grouped)
      .flat()
      .find((c) => c.id === 'settings-row-behaviour-settings.privacyProfileRow')
    expect(entry).toBeTruthy()

    const seen: Array<{ type: string; detail?: unknown }> = []
    const catcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:settings-tab', catcher)
    try {
      act(() => {
        entry!.action()
      })
    } finally {
      window.removeEventListener('ephe:settings-tab', catcher)
    }
    const detail = seen[0]?.detail as { tab?: string; query?: string }
    expect(detail?.tab).toBe(row!.tab)
    expect(detail?.query).toBe('settings.privacyProfileRow')
  })
})

describe('useCommandPalette: the two external entries leave through the shell', () => {
  it('routes GitHub and the docs through openExternally, never window.open', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const all = Object.values(result.current.grouped).flat()
    const github = all.find((c) => c.id === 'github')
    const docs = all.find((c) => c.id === 'docs')
    expect(github).toBeTruthy()
    expect(docs).toBeTruthy()

    // A Tauri shell has no window to open into; raw window.open is a no-op there.
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    try {
      act(() => github!.action())
      act(() => docs!.action())
    } finally {
      openSpy.mockRestore()
    }
    expect(native.openExternally).toHaveBeenCalledWith('https://github.com/bemlerlabs/ephe')
    expect(native.openExternally).toHaveBeenCalledWith('https://ephe.app/docs')
    expect(openSpy).not.toHaveBeenCalled()
  })
})
