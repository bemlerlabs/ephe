// I7-4: the plugin store after the rebuild — groups only when they have something
// to say, and the orphan row has a producer in the core.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { ApiError } from '@/lib/api'
import { renderPlugins } from './sections-plugins'
import type { SettingsModel } from './types'
import type { PluginEntry, PluginView } from '@/lib/api'

const surfaceMocks = vi.hoisted(() => ({
  show: vi.fn(async () => ({
    opened: true,
    side: 'overlay' as const,
    created: true,
    handle: 'overlay:countdown',
    unmet: [],
    note: '',
    message: '',
  })),
  hide: vi.fn(async () => true),
  isOpen: vi.fn(() => false),
}))

vi.mock('@/lib/pluginDisplay', () => ({
  showPluginSurface: surfaceMocks.show,
  hidePluginSurface: surfaceMocks.hide,
  isPluginSurfaceOpen: surfaceMocks.isOpen,
  canOpenNativeSurface: () => false,
}))

function entry(id: string, over: Partial<PluginEntry> = {}): PluginEntry {
  return {
    id,
    name: id,
    description: `${id} beschreibt sich selbst`,
    tags: [],
    example_prompts: [],
    enabled: true,
    ...over,
  } as PluginEntry
}

function model(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    deepSections: [],
    deepDraft: {},
    setDeepField: () => {},
    expandedPlugin: null,
    handlePluginMasterToggle: () => {},
    handlePluginToggle: () => {},
    pluginQuery: '',
    setExpandedPlugin: () => {},
    setPluginQuery: () => {},
    pluginView: {
      version: 1,
      master_enabled: true,
      public: [entry('web-research'), entry('vision')],
      personal: [],
    } as PluginView,
    ...over,
  } as unknown as SettingsModel
}

describe('Plugin-Store (I7-4)', () => {
  it('eine leere Segment-Liste bekommt keinen Kasten', () => {
    render(renderPlugins(model()))
    expect(screen.getByTestId('plugins-section-global')).toBeTruthy()
    expect(screen.queryByTestId('plugins-section-session')).toBeNull()
  })

  it('Suche ohne Treffer sagt das, statt zwei leere Gruppen zu stapeln', () => {
    render(renderPlugins(model({ pluginQuery: 'dienst-nicht-da' })))
    expect(screen.queryByTestId('plugins-section-global')).toBeNull()
    expect(screen.queryByTestId('plugins-section-session')).toBeNull()
    expect(screen.getByText('settings.noResults')).toBeTruthy()
  })

  it('der Grundsatz ist eine Zeile mit Schalter', () => {
    const toggle = vi.fn()
    render(renderPlugins(model({ handlePluginMasterToggle: toggle })))
    const row = screen.getByTestId('plugins-master-row')
    expect(row.textContent).toContain('settings.pluginsMasterHint')
    fireEvent.click(screen.getByTestId('plugins-master-toggle'))
    expect(toggle).toHaveBeenCalledWith(false)
  })

  it('der Plugin-Schalter meldet die angeforderte Richtung', () => {
    const toggle = vi.fn()
    render(renderPlugins(model({ handlePluginToggle: toggle })))
    fireEvent.click(screen.getByTestId('plugin-toggle-web-research'))
    expect(toggle).toHaveBeenCalledWith('web-research', false)
  })

  it('shows the retired-master migration notice', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: true,
            public: [entry('web-research')],
            personal: [],
            notices: [{ code: 'legacy_master_bypass_retired' }],
          } as PluginView,
        }),
      ),
    )
    expect(screen.getByTestId('plugin-legacy-master-notice')).toBeTruthy()
  })

  it('Orphans aus der Registry erscheinen mit ihrer Erklaerung', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: true,
            public: [entry('web-research')],
            personal: [],
            orphans: ['altes-werkzeug'],
          } as PluginView,
        }),
      ),
    )
    expect(screen.getByText('altes-werkzeug')).toBeTruthy()
    expect(screen.getByText('settings.plugins.orphansHint')).toBeTruthy()
  })
})

describe('Plugin-Store read-only brake (FLAG-01)', () => {
  it('shows the read-only banner and disables every switch', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: true,
            read_only: true,
            public: [entry('web-research')],
            personal: [],
          } as PluginView,
        }),
      ),
    )

    expect(screen.getByTestId('plugin-read-only-notice').textContent).toBe(
      'settings.pluginReadOnly',
    )
    expect((screen.getByTestId('plugins-master-toggle') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByTestId('plugin-toggle-web-research') as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('shows the unproven banner and disables the switches', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: true,
            unproven: true,
            public: [entry('web-research', { enabled: false })],
            personal: [],
          } as PluginView,
        }),
      ),
    )

    expect(screen.getByTestId('plugin-state-unproven-notice').textContent).toBe(
      'settings.pluginStateUnproven',
    )
    expect((screen.getByTestId('plugin-toggle-web-research') as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('names the read-only refusal instead of the raw server sentence', async () => {
    const toggle = vi.fn(() =>
      Promise.reject(
        new ApiError('plugin lifecycle is read-only', 423, 'plugin_lifecycle_read_only'),
      ),
    )
    render(renderPlugins(model({ handlePluginToggle: toggle })))

    fireEvent.click(screen.getByTestId('plugin-toggle-web-research'))

    await waitFor(() =>
      expect(screen.getByTestId('plugin-toggle-error-web-research').textContent).toBe(
        'settings.pluginErrorReadOnly',
      ),
    )
  })
})

describe('Plugin surface row (W1-7)', () => {
  const surface = {
    type: 'floating-window',
    entry: 'ui/index.html',
    title: 'Countdown',
    width: 260,
    height: 132,
    transparent: true,
    always_on_top: true,
  }
  const view = (rows: PluginEntry[]) =>
    ({
      version: 1,
      master_enabled: true,
      public: rows,
      personal: [],
    }) as PluginView

  beforeEach(() => {
    surfaceMocks.show.mockClear()
    surfaceMocks.hide.mockClear()
    surfaceMocks.isOpen.mockReturnValue(false)
  })

  it('opens the declared surface through the display module with its descriptor', async () => {
    surfaceMocks.isOpen.mockReturnValue(false)
    render(
      renderPlugins(model({ pluginView: view([entry('countdown', { surface }) as PluginEntry]) })),
    )

    fireEvent.click(screen.getByTestId('plugin-surface-countdown'))
    await waitFor(() => expect(surfaceMocks.show).toHaveBeenCalledTimes(1))
    expect(surfaceMocks.show).toHaveBeenCalledWith(
      { pluginId: 'countdown', descriptor: expect.objectContaining({ entry: 'ui/index.html' }) },
      expect.any(Function),
    )
  })

  it('closes a standing surface through the same path and reopens it on the next click', async () => {
    surfaceMocks.isOpen.mockReturnValue(true)
    render(
      renderPlugins(model({ pluginView: view([entry('countdown', { surface }) as PluginEntry]) })),
    )

    fireEvent.click(screen.getByTestId('plugin-surface-countdown'))
    await waitFor(() =>
      expect(surfaceMocks.hide).toHaveBeenCalledWith('countdown', expect.any(Function)),
    )

    surfaceMocks.isOpen.mockReturnValue(false)
    fireEvent.click(screen.getByTestId('plugin-surface-countdown'))
    await waitFor(() => expect(surfaceMocks.show).toHaveBeenCalledTimes(1))
  })

  it('a bundle without a surface declares no button', () => {
    render(renderPlugins(model({ pluginView: view([entry('documents')]) })))
    expect(screen.queryByTestId('plugin-surface-documents')).toBeNull()
  })
})

describe('Plugin scope (task 99)', () => {
  const composed = entry('countdown', {
    enabled: false,
    scope: 'session',
    provided_by_modes: ['operator'],
    module: 'ui/index.html',
    configuration: '',
  })
  const namedAndOn = entry('web-research', {
    enabled: true,
    scope: 'session',
    provided_by_modes: ['operator'],
    module: 'tools/handlers.py:web_search',
    configuration: 'read, network',
  })
  const plainOff = entry('documents', {
    enabled: false,
    scope: 'global',
    provided_by_modes: [],
    module: '',
    configuration: '',
  })

  it('the badge appears only when the global switch is off and a mode names the bundle', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: true,
            public: [composed, namedAndOn, plainOff],
            personal: [],
          } as PluginView,
        }),
      ),
    )
    expect(screen.getByTestId('plugin-scope-badge-countdown')).toBeTruthy()
    expect(screen.queryByTestId('plugin-scope-badge-web-research')).toBeNull()
    expect(screen.queryByTestId('plugin-scope-badge-documents')).toBeNull()
    expect(screen.getByTestId('plugins-section-session')).toBeTruthy()
    expect(screen.getByTestId('plugins-section-global')).toBeTruthy()
  })

  it('pause-all hides the preset badge', () => {
    render(
      renderPlugins(
        model({
          pluginView: {
            version: 1,
            master_enabled: false,
            public: [composed],
            personal: [],
          } as PluginView,
        }),
      ),
    )
    expect(screen.queryByTestId('plugin-scope-badge-countdown')).toBeNull()
  })

  it('the detail sheet names the module and a read-only include list', () => {
    render(
      renderPlugins(
        model({
          expandedPlugin: 'countdown',
          pluginView: {
            version: 1,
            master_enabled: true,
            public: [composed],
            personal: [],
          } as PluginView,
        }),
      ),
    )
    expect(screen.getByTestId('plugin-detail-module-countdown').textContent).toContain(
      'ui/index.html',
    )
    expect(screen.getByTestId('plugin-detail-configuration-countdown').textContent).toContain(
      'settings.pluginDetailNone',
    )
    const include = screen.getByTestId('plugin-scope-include-countdown')
    const operator = include.querySelector('input[value="operator"]') as HTMLInputElement
    const analyst = include.querySelector('input[value="analyst"]') as HTMLInputElement
    expect(operator.checked).toBe(true)
    expect(operator.disabled).toBe(true)
    expect(analyst.checked).toBe(false)
    expect(analyst.disabled).toBe(true)
  })
})
