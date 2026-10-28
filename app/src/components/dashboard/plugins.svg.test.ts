/**
 * The plugin icon constitution.
 *
 * Every first-party plugin ships one hand-built SVG in the warm-ink palette, and no
 * two plugins wear the same picture: a shared icon is how two different products
 * become one row in the store. The gate reads the shipped files, not a fixture.
 */
import { describe, expect, it } from 'vitest'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const PLUGINS = join(dirname(fileURLToPath(import.meta.url)), '../../../../plugins')

const icons = readdirSync(PLUGINS, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => ({ plugin: entry.name, path: join(PLUGINS, entry.name, 'icon.svg') }))
  .filter(({ path }) => {
    try {
      readFileSync(path)
      return true
    } catch {
      return false
    }
  })
  .map(({ plugin, path }) => ({ plugin, svg: readFileSync(path, 'utf8') }))

const digest = (svg: string) => createHash('sha256').update(svg).digest('hex')

describe('plugin icons', () => {
  it('ships one icon for every first-party plugin', () => {
    expect(icons.length).toBe(16)
  })

  it('never lets two plugins share a picture', () => {
    const byHash = new Map<string, string[]>()
    for (const { plugin, svg } of icons) {
      const hash = digest(svg)
      byHash.set(hash, [...(byHash.get(hash) ?? []), plugin])
    }
    const shared = [...byHash.values()].filter((names) => names.length > 1)
    expect(shared).toEqual([])
  })

  it('carries no trace of the retired forest palette', () => {
    const legacy = icons.filter(({ svg }) => /#0f2418|#5eed93|#1d3b28/i.test(svg))
    expect(legacy.map(({ plugin }) => plugin)).toEqual([])
  })

  it('draws every icon on the warm-ink ground with its primary stroke', () => {
    for (const { plugin, svg } of icons) {
      expect(svg, plugin).toContain('viewBox="0 0 96 96"')
      expect(svg, plugin).toContain('fill="#1D1917"')
      expect(svg, plugin).toContain('stroke="#F2EFE8"')
      expect(svg, plugin).toContain('stroke-width="3.5"')
      expect(svg, plugin).toContain('stroke="#2E2926"')
    }
  })
})
