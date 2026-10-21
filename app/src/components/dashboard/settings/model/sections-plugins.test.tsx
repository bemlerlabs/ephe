// I7-4: the plugin store after the rebuild — groups only when they have something
// to say, and the orphan row has a producer in the core.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { ApiError } from '@/lib/api'
import { renderPlugins } from './sections-plugins'
import type { SettingsModel } from './types'
import type { PluginEntry, PluginView } from '@/lib/api'

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
    expect(screen.getByTestId('plugins-section-public')).toBeTruthy()
    expect(screen.queryByTestId('plugins-section-personal')).toBeNull()
  })

  it('Suche ohne Treffer sagt das, statt zwei leere Gruppen zu stapeln', () => {
    render(renderPlugins(model({ pluginQuery: 'dienst-nicht-da' })))
    expect(screen.queryByTestId('plugins-section-public')).toBeNull()
    expect(screen.queryByTestId('plugins-section-personal')).toBeNull()
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
