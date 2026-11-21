/**
 * #96 — the Extensions row says which rail a bundle runs on.
 *
 * The switch says a plugin is on. It did not say what kind of on: a version 1 bundle turns
 * tools Ephe implements on, and a version 2 bundle carries entries of its own that the
 * confined worker resolves and runs. A reader who is told both are "a plugin" is being told
 * something untrue, so the row names the rail the manifest actually declares.
 *
 * The copy is read from `locales/en.json` while the test runs, so a chip that renders with no
 * key behind it fails here instead of shipping a bare `settings.pluginRail.worker`.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { renderPlugins } from './sections-plugins'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/en.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}
const SRC = findSrc()
const EN = JSON.parse(readFileSync(resolve(SRC, 'locales/en.json'), 'utf8')) as {
  settings: Record<string, string>
}

/** The slice of i18next this surface needs: a namespaced key, one plural form, `{{slot}}`. */
function t(key: string, options?: Record<string, unknown>): string {
  const dot = key.indexOf('.')
  const namespace = dot < 0 ? '' : key.slice(0, dot)
  const leaf = dot < 0 ? key : key.slice(dot + 1)
  const table = (EN as unknown as Record<string, Record<string, string>>)[namespace] ?? {}
  const plural =
    typeof options?.count === 'number' && options.count === 1 ? `${leaf}_one` : `${leaf}_other`
  const template = table[plural] ?? table[leaf] ?? String(options?.defaultValue ?? key)
  return template.replace(/\{\{(\w+)\}\}/g, (_match: string, name: string) =>
    String(options?.[name] ?? ''),
  )
}

type Entry = Record<string, unknown>

function row(entry: Entry) {
  const model = {
    t,
    pluginQuery: '',
    setPluginQuery: () => {},
    expandedPlugin: entry.id,
    setExpandedPlugin: () => {},
    handlePluginToggle: () => {},
    handlePluginMasterToggle: () => {},
    deepSections: [],
    pluginView: {
      public: [entry],
      personal: [],
      master_enabled: true,
      read_only: false,
      unproven: false,
      notices: [],
    },
  } as never
  return render(renderPlugins(model))
}

const BASE = {
  id: 'demo',
  name: 'Demo',
  description: 'a bundle',
  tags: [],
  example_prompts: [],
  enabled: true,
  source: 'builtin',
  permissions: [],
}

describe('the plugin row states the rail its manifest declares', () => {
  it('names the confined worker and its own entries', () => {
    row({
      ...BASE,
      rail: 'worker',
      contributed_tools: 2,
      activated_tools: 0,
    })
    const chip = screen.getByTestId('plugin-rail-demo')
    expect(chip.textContent).toContain(EN.settings['pluginRail.worker'])
    expect(chip.textContent).toContain('2 tools named')
  })

  it('names the kernel rail and the tools it switches on', () => {
    row({ ...BASE, rail: 'kernel', contributed_tools: 0, activated_tools: 8 })
    const chip = screen.getByTestId('plugin-rail-demo')
    expect(chip.textContent).toContain(EN.settings['pluginRail.kernel'])
    expect(chip.textContent).toContain('8 tools named')
    expect(chip.textContent).not.toContain(EN.settings['pluginRail.worker'])
  })

  /** A declarative bundle contributes no tool at all, so a count would be a lie of zero. */
  it('names the declarative rail without inventing a tool count', () => {
    row({ ...BASE, rail: 'declarative', contributed_tools: 0, activated_tools: 0 })
    const chip = screen.getByTestId('plugin-rail-demo')
    expect(chip.textContent).toContain(EN.settings['pluginRail.declarative'])
    expect(chip.textContent).not.toMatch(/\d+ tools? named/)
  })

  it('leaves the chip out when no manifest behind the entry could be read', () => {
    row({ ...BASE })
    expect(screen.queryByTestId('plugin-rail-demo')).toBeNull()
  })

  it('reads one singular where the rail names a single tool', () => {
    expect(EN.settings['pluginRailTools_one']).toContain('{{count}}')
    row({ ...BASE, rail: 'worker', contributed_tools: 1 })
    expect(screen.getByTestId('plugin-rail-demo').textContent).toContain('1 tool named')
  })
})
