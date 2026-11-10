// The plugin journey: status, capability, open, remove, empty and failure states.
// The copy comes from `locales/de.json` while the test runs, so a key that is not
// translated fails here instead of shipping a bare `settings.pluginStatusActive`.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { ApiError } from '@/lib/api'
import { renderPlugins } from './sections-plugins'
import type { SettingsModel } from './types'
import type { PluginCommandInfo, PluginEntry, PluginView } from '@/lib/api'

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

function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/de.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}

const DE = JSON.parse(readFileSync(resolve(findSrc(), 'locales/de.json'), 'utf8')) as {
  settings: Record<string, string>
}

/** The slice of i18next this surface needs: a namespaced key and `{{slot}}`. */
function t(key: string, options?: Record<string, unknown>): string {
  const dot = key.indexOf('.')
  const leaf = dot < 0 ? key : key.slice(dot + 1)
  const table = DE.settings
  const plural =
    typeof options?.count === 'number' && options.count === 1 ? `${leaf}_one` : `${leaf}_other`
  const template = table[plural] ?? table[leaf] ?? key
  return template.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(options?.[name] ?? ''))
}

function entry(id: string, over: Partial<PluginEntry> = {}): PluginEntry {
  return {
    id,
    name: id,
    description: `${id} describes itself`,
    tags: [],
    example_prompts: [],
    enabled: true,
    manifest: true,
    source: 'builtin',
    origin: 'first-party',
    ...over,
  } as PluginEntry
}

const surface = {
  type: 'floating-window',
  entry: 'ui/index.html',
  title: 'Countdown',
  width: 260,
  height: 132,
}

function commands(...plugins: [string, string[]][]): PluginCommandInfo[] {
  return plugins.flatMap(([plugin, names]) =>
    names.map((name) => ({ name: `/${name}`, description: `${name} tut`, template: '', plugin })),
  )
}

function model(over: Record<string, unknown> = {}) {
  return {
    t,
    i18n: { language: 'de' },
    deepSections: [],
    deepDraft: {},
    setDeepField: () => {},
    expandedPlugin: null,
    handlePluginMasterToggle: () => {},
    handlePluginToggle: () => {},
    handlePluginRemove: vi.fn(),
    pluginCommands: [],
    installedPlugins: [],
    pluginQuery: '',
    setExpandedPlugin: () => {},
    setPluginQuery: () => {},
    reloadPluginStore: vi.fn(),
    pluginLoadError: false,
    pluginView: {
      version: 1,
      master_enabled: true,
      public: [entry('web-research', { rail: 'worker', contributed_tools: 2 })],
      personal: [],
    } as PluginView,
    ...over,
  } as unknown as SettingsModel
}

function view(rows: PluginEntry[], over: Partial<PluginView> = {}): PluginView {
  return {
    version: 1,
    master_enabled: true,
    public: rows,
    personal: [],
    global: rows,
    session: [],
    ...over,
  } as PluginView
}

beforeEach(() => {
  surfaceMocks.show.mockClear()
  surfaceMocks.hide.mockClear()
  surfaceMocks.isOpen.mockReturnValue(false)
})

describe('plugin status', () => {
  it('marks an enabled bundle as active, a disabled one as inactive', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([
            entry('an', { rail: 'worker', contributed_tools: 2 }),
            entry('aus', { enabled: false, rail: 'worker', contributed_tools: 2 }),
          ]),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-status-an').textContent).toContain(
      DE.settings.pluginStatusActive,
    )
    expect(screen.getByTestId('plugin-status-aus').textContent).toContain(
      DE.settings.pluginStatusInactive,
    )
  })

  it('names a bundle whose manifest cannot be read as faulty, not as active', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([entry('kaputt', { enabled: true, rail: undefined })]),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-status-kaputt').textContent).toContain(
      DE.settings.pluginStatusFaulty,
    )
    expect(screen.getByTestId('plugin-faulty-hint-kaputt').textContent).toBe(
      DE.settings.pluginStatusFaultyHint,
    )
  })

  it('does not claim a manifest is broken when the catalog entry has none at all', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([entry('katalog', { manifest: false, enabled: false })]),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-status-katalog').textContent).toContain(
      DE.settings.pluginStatusInactive,
    )
    expect(screen.queryByTestId('plugin-faulty-hint-katalog')).toBeNull()
  })
})

describe('what a plugin can do, in the row', () => {
  it('shows its tools, its commands and its surface without opening the details', () => {
    render(
      renderPlugins(
        model({
          pluginCommands: commands(['web-research', ['research', 'cite']]),
          pluginView: view([
            entry('web-research', {
              rail: 'worker',
              contributed_tools: 2,
              module: 'tools/handlers.py:web_search',
            }),
          ]),
        }),
      ),
    )
    const strip = screen.getByTestId('plugin-capabilities-web-research')
    expect(strip.textContent).toContain('2 Werkzeuge')
    expect(strip.textContent).toContain('web_search')
    expect(strip.textContent).toContain('/research')
    expect(strip.textContent).toContain('/cite')
  })

  it('shows the surface it declares as an ability, not only as a button', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([entry('countdown', { rail: 'declarative', surface })]),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-capabilities-countdown').textContent).toContain(
      'Fläche: Countdown',
    )
  })

  it('keeps a command capability visible while the bundle is switched off', () => {
    render(
      renderPlugins(
        model({
          installedPlugins: [
            {
              name: 'browser-use',
              version: '1.2.0',
              description: 'browser',
              enabled: false,
              origin: 'bundled',
              components: ['tools', 'commands', 'skills'],
              permissions: { tool_families: ['browser'], data_roots: [] },
            },
          ],
          pluginCommands: [],
          pluginView: view([
            entry('browser-use', { enabled: false, rail: 'worker', contributed_tools: 8 }),
          ]),
        }),
      ),
    )
    const strip = screen.getByTestId('plugin-capabilities-browser-use')
    expect(strip.textContent).toContain(DE.settings.pluginCapCommandsOff)
    expect(strip.textContent).toContain('8 Werkzeuge')
  })

  it('says "no tools" for a declarative bundle instead of drawing a zero', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([entry('guide', { rail: 'declarative' })]),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-capabilities-guide').textContent).toContain(
      DE.settings.pluginCapNoTools,
    )
  })
})

describe('the row actions', () => {
  it('opens a surface with the action named "Öffnen"', async () => {
    render(renderPlugins(model({ pluginView: view([entry('countdown', { surface })]) })))
    const open = screen.getByTestId('plugin-surface-countdown')
    expect(open.textContent).toContain(DE.settings.pluginSurfaceShow)
    fireEvent.click(open)
    await waitFor(() => expect(surfaceMocks.show).toHaveBeenCalledTimes(1))
  })

  it('asks before removing an installed plugin and calls the remove path only on confirm', async () => {
    const remove = vi.fn(async () => {})
    render(
      renderPlugins(
        model({
          handlePluginRemove: remove,
          pluginView: view([entry('mein-plugin', { source: 'user' })]),
        }),
      ),
    )
    fireEvent.click(screen.getByTestId('plugin-remove-mein-plugin'))
    expect(screen.getByTestId('plugin-remove-confirm-mein-plugin').textContent).toContain(
      (DE.settings.pluginRemoveConfirmHint ?? '').replace('{{name}}', 'mein-plugin'),
    )
    expect(remove).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('plugin-remove-cancel-mein-plugin'))
    expect(screen.queryByTestId('plugin-remove-confirm-mein-plugin')).toBeNull()

    fireEvent.click(screen.getByTestId('plugin-remove-mein-plugin'))
    fireEvent.click(screen.getByTestId('plugin-remove-confirm-yes-mein-plugin'))
    await waitFor(() => expect(remove).toHaveBeenCalledWith('mein-plugin'))
  })

  it("says why a running plugin cannot be removed, in the reader's words", async () => {
    const remove = vi.fn(() =>
      Promise.reject(new ApiError('plugin enabled', 409, 'plugin_enabled')),
    )
    render(
      renderPlugins(
        model({
          handlePluginRemove: remove,
          pluginView: view([entry('mein-plugin', { source: 'user' })]),
        }),
      ),
    )
    fireEvent.click(screen.getByTestId('plugin-remove-mein-plugin'))
    fireEvent.click(screen.getByTestId('plugin-remove-confirm-yes-mein-plugin'))
    await waitFor(() =>
      expect(screen.getByTestId('plugin-remove-error-mein-plugin').textContent).toBe(
        DE.settings.pluginRemoveEnabled,
      ),
    )
  })

  it('offers no remove action for a bundled plugin', () => {
    render(
      renderPlugins(model({ pluginView: view([entry('web-research', { source: 'builtin' })]) })),
    )
    expect(screen.queryByTestId('plugin-remove-web-research')).toBeNull()
  })
})

describe('plugins installed without a catalog entry', () => {
  const installed = {
    name: 'mein-plugin',
    version: '0.3.0',
    description: 'Selbst gebaut',
    enabled: true,
    origin: 'user' as const,
    components: ['tools', 'commands'],
    permissions: { tool_families: ['read'], data_roots: [] },
  }

  it('becomes a row with status, abilities, source and the remove action', () => {
    const remove = vi.fn(async () => {})
    render(
      renderPlugins(
        model({
          handlePluginRemove: remove,
          installedPlugins: [installed],
          pluginView: view([], {
            public: [],
            personal: [],
            global: [],
            session: [],
            orphans: ['mein-plugin'],
          }),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-row-orphan-mein-plugin')).toBeTruthy()
    expect(screen.getByTestId('plugin-status-mein-plugin').textContent).toContain(
      DE.settings.pluginStatusActive,
    )
    expect(screen.getByTestId('plugin-capabilities-mein-plugin').textContent).toContain(
      'tools, commands',
    )
    expect(screen.getByTestId('plugin-source-mein-plugin').textContent).toContain(
      DE.settings.pluginSourceUser,
    )
    expect(screen.getByTestId('plugin-remove-mein-plugin')).toBeTruthy()
  })

  it('keeps its name visible when the installed inventory cannot be read', () => {
    render(
      renderPlugins(
        model({
          installedPlugins: null,
          pluginView: view([], {
            public: [],
            personal: [],
            global: [],
            session: [],
            orphans: ['mein-plugin'],
          }),
        }),
      ),
    )
    expect(screen.getByTestId('plugin-orphan-mein-plugin').textContent).toBe('mein-plugin')
    expect(screen.getByTestId('plugins-section-orphans')).toBeTruthy()
  })
})

describe('the empty and error states', () => {
  it('says how one gets a plugin instead of leaving an empty box', () => {
    render(
      renderPlugins(
        model({
          pluginView: view([], { public: [], personal: [], global: [], session: [] }),
        }),
      ),
    )
    const empty = screen.getByTestId('plugins-empty')
    expect(empty.textContent).toContain(DE.settings.pluginEmptyTitle)
    expect(empty.textContent).toContain(DE.settings.pluginEmptyBody)
    expect(screen.getByTestId('plugins-empty-discover')).toBeTruthy()
  })

  it('the empty state leads to the marketplace', () => {
    window.location.hash = ''
    render(
      renderPlugins(
        model({
          pluginView: view([], { public: [], personal: [], global: [], session: [] }),
        }),
      ),
    )
    fireEvent.click(screen.getByTestId('plugins-empty-discover'))
    expect(window.location.hash).toBe('#/discover')
  })

  it('an unreadable plugin list says so and offers a retry', () => {
    const reload = vi.fn()
    render(
      renderPlugins(model({ pluginView: null, pluginLoadError: true, reloadPluginStore: reload })),
    )
    expect(screen.getByTestId('plugins-load-error').textContent).toContain(
      DE.settings.pluginLoadError,
    )
    fireEvent.click(screen.getByTestId('plugins-load-retry'))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
