import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { DeepSection } from '@/types'

const { getSettings, saveSections } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  saveSections: vi.fn(async () => ({})),
}))

vi.mock('@/lib/api', () => ({ getSettings, saveSections }))
vi.mock('@/store/chatStore', () => ({
  useChatStore: (selector: (s: unknown) => unknown) => selector({ currentSession: null }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))
vi.mock('framer-motion', async (importOriginal) => {
  const orig = await importOriginal<typeof import('framer-motion')>()
  return { ...(orig as object), useReducedMotion: () => false }
})

import WorkspaceCompanion from './WorkspaceCompanion'

const DEEP: DeepSection[] = [
  {
    key: 'appearance',
    fields: [
      {
        key: 'appearance.companion_enabled',
        type: 'bool',
        label: 'Begleiter',
        labelEn: 'Companion',
        default: false,
        value: true,
      },
      {
        key: 'appearance.companion_mode',
        type: 'select',
        label: 'Modus',
        labelEn: 'Mode',
        default: 'copilot',
        value: 'copilot',
      },
      {
        key: 'appearance.companion_sound',
        type: 'bool',
        label: 'Klang',
        labelEn: 'Sound',
        default: true,
        value: true,
      },
      {
        key: 'appearance.font_scale',
        type: 'number',
        label: 'Schriftgröße (%)',
        labelEn: 'Font scale (%)',
        default: 100,
        value: 100,
        min: 80,
        max: 150,
      },
    ],
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  getSettings.mockResolvedValue({ deep: DEEP })
  seedDeepSettings(DEEP)
})

afterEach(() => seedDeepSettings(null))

async function openPanel() {
  render(<WorkspaceCompanion runState="working" hasMessages />)
  fireEvent.click(screen.getByTestId('companion-trigger'))
  return screen.getByTestId('companion-popover')
}

describe('companion quick panel', () => {
  it('opens on the actor with the current run word and the controls', async () => {
    const panel = await openPanel()
    expect(panel).toBeTruthy()
    expect(screen.getByTestId('companion-state-word').textContent).toBe('workbench.working')
    expect(screen.getByTestId('companion-popover-settings')).toBeTruthy()
    expect(screen.getByTestId('companion-popover-rest')).toBeTruthy()
    expect(screen.getByTestId('companion-popover-sound')).toBeTruthy()
  })

  it('writes only the sound key through the register endpoint', async () => {
    await openPanel()
    await act(async () => {
      fireEvent.click(screen.getByTestId('companion-popover-sound'))
    })
    expect(saveSections).toHaveBeenCalledTimes(1)
    expect(saveSections).toHaveBeenCalledWith({
      appearance: {
        'appearance.companion_enabled': true,
        'appearance.companion_mode': 'copilot',
        'appearance.companion_sound': false,
        'appearance.font_scale': 100,
      },
    })
  })

  it('lists the three co-pilot modes and writes the chosen one', async () => {
    await openPanel()
    expect(screen.getByTestId('companion-mode-perch')).toBeTruthy()
    expect(screen.getByTestId('companion-mode-scout')).toBeTruthy()
    expect(screen.getByTestId('companion-mode-copilot')).toBeTruthy()
    expect(screen.getByTestId('companion-mode-copilot').getAttribute('aria-pressed')).toBe('true')
    await act(async () => {
      fireEvent.click(screen.getByTestId('companion-mode-scout'))
    })
    expect(saveSections).toHaveBeenCalledWith({
      appearance: {
        'appearance.companion_enabled': true,
        'appearance.companion_mode': 'scout',
        'appearance.companion_sound': true,
        'appearance.font_scale': 100,
      },
    })
  })

  it('rests for the session and wakes again without a write', async () => {
    await openPanel()
    const rest = screen.getByTestId('companion-popover-rest')
    fireEvent.click(rest)
    expect(rest.getAttribute('aria-pressed')).toBe('true')
    expect(rest.textContent).toBe('settings.companionWake')
    fireEvent.click(rest)
    expect(rest.getAttribute('aria-pressed')).toBe('false')
    expect(rest.textContent).toBe('settings.companionRest')
    expect(saveSections).not.toHaveBeenCalled()
  })

  it('hands the settings request to the panel and closes', async () => {
    const seen: string[] = []
    let tab = ''
    const onOpen = () => seen.push('open')
    const onTab = (event: Event) => {
      tab = (event as CustomEvent<{ tab?: string }>).detail?.tab ?? ''
    }
    window.addEventListener('ephe:open-settings', onOpen)
    window.addEventListener('ephe:settings-tab', onTab)
    try {
      await openPanel()
      fireEvent.click(screen.getByTestId('companion-popover-settings'))
    } finally {
      window.removeEventListener('ephe:open-settings', onOpen)
      window.removeEventListener('ephe:settings-tab', onTab)
    }
    expect(seen).toEqual(['open'])
    expect(tab).toBe('appearance')
    expect(screen.queryByTestId('companion-popover')).toBeNull()
  })

  it('closes on Escape and returns the focus to the actor', async () => {
    const panel = await openPanel()
    expect(document.activeElement).toBe(screen.getByTestId('companion-popover-settings'))
    fireEvent.keyDown(panel, { key: 'Escape' })
    expect(screen.queryByTestId('companion-popover')).toBeNull()
    expect(document.activeElement).toBe(screen.getByTestId('companion-trigger'))
  })
})
