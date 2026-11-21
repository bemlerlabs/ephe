// The store's writes go through the routes the product already has: the lifecycle
// switch for on/off and the marketplace's remove for an install on this device.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

import { ApiError } from '@/lib/api'
import type { PluginView } from '@/lib/api'

const api = vi.hoisted(() => ({
  getPlugins: vi.fn(),
  getSettings: vi.fn(),
  getMarketInstalled: vi.fn(),
  getPluginCommands: vi.fn(),
  setPluginEnabled: vi.fn(),
  setPluginMaster: vi.fn(),
  removeMarketPlugin: vi.fn(),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  getTasks: vi.fn(async () => []),
  createSchedule: vi.fn(),
  createTask: vi.fn(),
  deleteSchedule: vi.fn(),
  deleteTask: vi.fn(),
  updateTask: vi.fn(),
  saveSections: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, ...api }
})

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
vi.mock('@/lib/toast', () => ({ toastBus: toast }))

import { useSettingsLists } from './useSettingsLists'

const VIEW = {
  version: 1,
  master_enabled: true,
  public: [
    {
      id: 'web-research',
      name: 'web-research',
      description: 'research',
      tags: [],
      example_prompts: [],
      enabled: true,
      source: 'builtin',
      manifest: true,
      rail: 'worker',
      contributed_tools: 2,
    },
  ],
  personal: [],
  global: [],
  session: [],
  orphans: [],
} as unknown as PluginView

function state(over: Record<string, unknown> = {}) {
  return {
    activeTab: 'plugins',
    isOpen: true,
    deepDraft: {},
    deepSections: null,
    setDeepDraft: vi.fn(),
    setDeepSections: vi.fn(),
    setPluginView: vi.fn(),
    setPluginCommands: vi.fn(),
    setInstalledPlugins: vi.fn(),
    setPluginLoadError: vi.fn(),
    setScheduleJobs: vi.fn(),
    setTasks: vi.fn(),
    t: (key: string) => key,
    ...over,
  } as never
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getPlugins.mockResolvedValue(VIEW)
  api.getSettings.mockResolvedValue({ deep: [] })
  api.getMarketInstalled.mockResolvedValue({ plugins: [] })
  api.getPluginCommands.mockResolvedValue({ commands: [] })
  api.setPluginEnabled.mockResolvedValue({})
  api.removeMarketPlugin.mockResolvedValue({ status: 'removed', name: 'mein-plugin' })
})

describe('plugin store routes', () => {
  it('loads the catalog, the command list and the installed inventory together', async () => {
    api.getPluginCommands.mockResolvedValue({
      commands: [{ name: '/research', description: '', template: '', plugin: 'web-research' }],
    })
    api.getMarketInstalled.mockResolvedValue({
      plugins: [{ name: 'mein-plugin', version: '1.0.0', enabled: true, origin: 'user' }],
    })
    const s = state()
    renderHook(() => useSettingsLists(s))

    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(1))
    expect(
      (s as unknown as { setPluginView: ReturnType<typeof vi.fn> }).setPluginView,
    ).toHaveBeenCalledWith(VIEW)
    expect(
      (s as unknown as { setPluginCommands: ReturnType<typeof vi.fn> }).setPluginCommands,
    ).toHaveBeenCalledWith([
      { name: '/research', description: '', template: '', plugin: 'web-research' },
    ])
    expect(
      (s as unknown as { setInstalledPlugins: ReturnType<typeof vi.fn> }).setInstalledPlugins,
    ).toHaveBeenCalledTimes(1)
  })

  it('switching a plugin calls the lifecycle route and re-reads the store', async () => {
    const s = state()
    const { result } = renderHook(() => useSettingsLists(s))
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(1))

    await act(async () => {
      await result.current.handlePluginToggle('web-research', false)
    })

    expect(api.setPluginEnabled).toHaveBeenCalledWith('web-research', false)
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(2))
  })

  it('a refused switch keeps the committed list and says the reason', async () => {
    api.setPluginEnabled.mockRejectedValue(
      new ApiError('dependency blocked', 409, 'dependency_blocked'),
    )
    const s = state()
    const { result } = renderHook(() => useSettingsLists(s))
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(1))

    await act(async () => {
      await expect(result.current.handlePluginToggle('web-research', true)).rejects.toBeInstanceOf(
        ApiError,
      )
    })

    expect(toast.error).toHaveBeenCalledWith('settings.pluginToggleFailed')
    // The rejection path re-reads the truth instead of leaving the knob where the
    // failed request wanted it.
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(2))
  })

  it('removing an installed plugin calls the marketplace route and re-reads the store', async () => {
    const s = state()
    const { result } = renderHook(() => useSettingsLists(s))
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(1))

    await act(async () => {
      await result.current.handlePluginRemove('mein-plugin')
    })

    expect(api.removeMarketPlugin).toHaveBeenCalledWith('mein-plugin', false)
    expect(toast.success).toHaveBeenCalledWith('settings.pluginRemoveDone')
    await waitFor(() => expect(api.getPlugins).toHaveBeenCalledTimes(2))
  })

  it('an unreadable store becomes the error state, not an endless loading row', async () => {
    api.getPlugins.mockRejectedValue(new ApiError('offline', 500))
    const s = state()
    renderHook(() => useSettingsLists(s))

    await waitFor(() =>
      expect(
        (s as unknown as { setPluginLoadError: ReturnType<typeof vi.fn> }).setPluginLoadError,
      ).toHaveBeenCalledWith(true),
    )
  })
})
