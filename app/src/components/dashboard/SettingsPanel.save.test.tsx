// I6-1: the two save buttons are one. The footer button serves both storage
// areas — first the register (settings.json), then the main block (engine.json)
// — and reports each error separately. The saved confirmation appears only once
// both of them have gone through.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const { calls, toastError, toastSuccess, api } = vi.hoisted(() => {
  const calls: string[] = []
  const api = {
    getSettings: vi.fn(async () => ({
      provider: { type: 'local_ollama', model: 'gemma4:e4b' },
      memory_enabled: true,
      language: 'de',
      theme: 'dark',
      deep: [
        {
          key: 'appearance',
          fields: [
            {
              key: 'appearance.animations_enabled',
              type: 'bool',
              label: 'Animationen aktiv',
              labelEn: 'Animations enabled',
              default: true,
              value: true,
            },
            {
              key: 'appearance.font_scale',
              type: 'number',
              label: 'Schriftgroesse (%)',
              labelEn: 'Font scale (%)',
              default: 100,
              value: 100,
              min: 80,
              max: 150,
              step: 1,
            },
          ],
        },
      ],
    })),
    updateSettings: vi.fn(async () => {
      calls.push('settings')
      return {}
    }),
    saveSections: vi.fn(async () => {
      calls.push('sections')
      return {}
    }),
    healthCheck: vi.fn(async () => ({
      status: 'ok',
      active_model: 'gemma4:e4b',
      active_provider: 'local_ollama',
      engine_state: 'ok',
    })),
    getModelProviders: vi.fn(async () => ({
      active: {},
      providers: [],
      local_models: [],
      local_model_options: [],
    })),
    getMemoryStats: vi.fn(async () => ({ total: 0 })),
    listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
    getPackIndex: vi.fn(async () => ({ packs: [] })),
    listSchedules: vi.fn(async () => ({ jobs: [] })),
    getTasks: vi.fn(async () => []),
    getSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
    saveSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
  }
  return { calls, api, toastError: vi.fn(), toastSuccess: vi.fn() }
})

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

vi.mock('@/lib/toast', () => ({
  toastBus: { info: vi.fn(), error: toastError, success: toastSuccess },
  toast: { info: vi.fn(), error: toastError, success: toastSuccess },
}))

// Partial mock: only the network functions are sealed off. The panel layer builds
// all 17 areas in one render, so a full mock would have to supply every render-
// time function — URL builders such as exportMemoryUrl therefore stay real.
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  ...api,
}))

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  calls.length = 0
  toastError.mockClear()
  toastSuccess.mockClear()
  // The write mocks keep their implementation (mockClear, not mockReset), so a
  // test never reads the call counter of the one that ran before it.
  api.saveSections.mockClear()
  api.updateSettings.mockClear()
})

async function openAppearance() {
  render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="appearance" />)
  await screen.findByTestId('deep-row-appearance.animations_enabled')
}

/** Call order of two mocks: the last invocation number decides. */
function wroteFirst(a: { mock: { invocationCallOrder: number[] } }, b: typeof a) {
  const last = (m: { mock: { invocationCallOrder: number[] } }) =>
    m.mock.invocationCallOrder[m.mock.invocationCallOrder.length - 1] ?? 0
  return last(a) < last(b)
}

describe('eine Save-Flaeche (I6-1)', () => {
  it('der Bereich zeigt keinen eigenen Speichern-Knopf mehr', async () => {
    await openAppearance()
    expect(screen.queryByTestId('deep-save')).toBeNull()
    expect(screen.queryByTestId('deep-changed-count')).toBeNull()
    expect(screen.getByTestId('settings-save')).toBeTruthy()
  })

  it('der Fuss-Zaehler zaehlt nur die ungespeicherten Register-Aenderungen', async () => {
    await openAppearance()
    expect(screen.queryByTestId('settings-save-changed')).toBeNull()
    fireEvent.click(screen.getByTestId('setting-switch-appearance.animations_enabled'))
    expect(screen.getByTestId('settings-save-changed').textContent).toBe('1')
    fireEvent.change(screen.getByTestId('setting-number-appearance.font_scale'), {
      target: { value: '120' },
    })
    expect(screen.getByTestId('settings-save-changed').textContent).toBe('2')
  })

  it('ein Klick speichert erst das Register, dann den Hauptblock', async () => {
    await openAppearance()
    fireEvent.click(screen.getByTestId('setting-switch-appearance.animations_enabled'))
    fireEvent.click(screen.getByTestId('settings-save'))
    await screen.findByText('settings.saved')
    expect(calls).toEqual(['sections', 'settings'])
    expect(wroteFirst(api.saveSections, api.updateSettings)).toBe(true)
    expect(toastSuccess).toHaveBeenCalled()
  })

  it('ohne Register-Aenderung bleibt settings.json unberuehrt', async () => {
    await openAppearance()
    fireEvent.click(screen.getByTestId('settings-save'))
    await screen.findByText('settings.saved')
    expect(calls).toEqual(['settings'])
    expect(api.saveSections).not.toHaveBeenCalled()
  })

  it('scheitert das Register, wird der Hauptblock trotzdem gespeichert — und es heisst nicht gespeichert', async () => {
    await openAppearance()
    api.saveSections.mockRejectedValueOnce(new Error('settings.json nicht schreibbar'))
    fireEvent.click(screen.getByTestId('setting-switch-appearance.animations_enabled'))
    fireEvent.click(screen.getByTestId('settings-save'))
    await vi.waitFor(() => expect(calls).toEqual(['settings']))
    expect(api.saveSections).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('settings.saved')).toBeNull()
    expect(toastSuccess).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith(
      'settings.deepSaveFailed',
      'settings.json nicht schreibbar',
    )
  })

  it('Register und Hauptblock melden ihren Fehler getrennt', async () => {
    await openAppearance()
    api.saveSections.mockRejectedValueOnce(new Error('register kaputt'))
    api.updateSettings.mockRejectedValueOnce(new Error('block kaputt'))
    fireEvent.click(screen.getByTestId('setting-switch-appearance.animations_enabled'))
    fireEvent.click(screen.getByTestId('settings-save'))
    await vi.waitFor(() => expect(toastError).toHaveBeenCalledTimes(2))
    const titles = toastError.mock.calls.map((c) => c[0])
    expect(titles).toContain('settings.deepSaveFailed')
    expect(titles).toContain('settings.saveFailed')
    expect(toastError).toHaveBeenCalledWith(expect.anything(), 'register kaputt')
    expect(toastError).toHaveBeenCalledWith(expect.anything(), 'block kaputt')
  })
})
