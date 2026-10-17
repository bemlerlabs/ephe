// I7-4: the plugin store after the rebuild — groups only when they have something
// to say, and the orphan row has a producer in the core.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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
