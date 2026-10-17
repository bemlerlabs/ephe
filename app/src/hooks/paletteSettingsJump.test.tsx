/**
 * W10 — the command palette's settings jump (FINDINGS 2026-10-12, medium).
 *
 * The walkthrough measured: every settings entry landed on Engine whatever its
 * label, because the palette sends `ephe:open-settings` and `ephe:settings-tab` in
 * one handler while the panel's open-effect (useSettingsCore) lands on
 * `initialTab ?? 'engine'`. This drives the real pair — palette events plus the
 * panel's own model — so the assertion is about the surface, not about one hook.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as React from 'react'
import { render, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The settings model reads a dozen endpoints; every function export becomes an
// async stub so this test is about the tab race and not about the network. Every
// name stays exported, so the module graph of the panel still loads unchanged.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(actual)) {
    out[key] = typeof value === 'function' ? vi.fn(async () => ({})) : value
  }
  return out
})

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'en', changeLanguage: vi.fn(async () => {}) },
    }),
  }
})

import { useCommandPalette, type CommandItem } from '@/hooks/useCommandPalette'
import { useSettingsPanelModel } from '@/components/dashboard/settings/model'
import { useChatStore } from '@/store/chatStore'

type PanelModel = ReturnType<typeof useSettingsPanelModel>

let palette: ReturnType<typeof useCommandPalette> | null = null
let panel: PanelModel | null = null

function Probe({ isOpen }: { isOpen: boolean }) {
  // The shell passes `initialTab` too (chat/index.tsx maps the store's settingsTab,
  // default 'engine') — the entry's tab still has to win over that default.
  panel = useSettingsPanelModel({ isOpen, onClose: () => {}, initialTab: 'engine' })
  return null
}

function Harness() {
  const [open, setOpen] = React.useState(false)
  palette = useCommandPalette()
  React.useEffect(() => {
    // The ChatLayout listener (chat/model.ts) — the app's real open path.
    const onOpen = () => setOpen(true)
    window.addEventListener('ephe:open-settings', onOpen)
    return () => window.removeEventListener('ephe:open-settings', onOpen)
  }, [])
  return <Probe isOpen={open} />
}

beforeEach(() => {
  vi.clearAllMocks()
  palette = null
  panel = null
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null })
})

function renderHarness() {
  return render(
    <MemoryRouter>
      <Harness />
    </MemoryRouter>,
  )
}

function entries(): CommandItem[] {
  return Object.values(palette?.grouped ?? {}).flat()
}

describe('command palette → settings: the tab the user asked for', () => {
  it('lands on the named tab for every settings entry (privacy, appearance, hooks, about)', async () => {
    const tabs = ['privacy', 'appearance', 'hooks', 'about'] as const
    for (const tab of tabs) {
      const view = renderHarness()
      const entry = entries().find((c) => c.id === `settings-${tab}`)
      expect(entry, `palette entry settings-${tab}`).toBeTruthy()
      await act(async () => {
        entry!.action()
      })
      expect(panel!.activeTab, `settings-${tab} landed on`).toBe(tab)
      view.unmount()
    }
  })

  it('the same entry from an already open panel switches the tab as well', async () => {
    renderHarness()
    await act(async () => {
      entries()
        .find((c) => c.id === 'settings-engine')!
        .action()
    })
    expect(panel!.activeTab).toBe('engine')
    await act(async () => {
      entries()
        .find((c) => c.id === 'settings-mobile')!
        .action()
    })
    expect(panel!.activeTab).toBe('mobile')
  })
})

describe('command palette → settings: reaching a control, not only the tab', () => {
  it('a control entry lands on the row tab and hands the row name to the panel', async () => {
    renderHarness()
    await act(async () => {
      palette!.setQuery('privacyProfileRow')
    })
    const row = entries().find((c) => c.id === 'settings-row-privacy-settings.privacyProfileRow')
    expect(row, 'palette entry for the approval-profile row').toBeTruthy()
    await act(async () => {
      row!.action()
    })
    expect(panel!.activeTab).toBe('privacy')
    // The panel's own search now names the control the user asked for.
    expect(panel!.settingsQuery).toBe('settings.privacyProfileRow')
  })
})
