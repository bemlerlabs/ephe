/**
 * Web app manifest installability.
 *
 * The install prompt only fires when the manifest meets the browser's criteria
 * (name, 192 px + 512 px icons, standalone display, a start_url in scope) and
 * every icon it names really exists — a 404 icon makes the app non-installable.
 * This pins both halves.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const publicDir = resolve(here, '../../public')
const manifest = JSON.parse(readFileSync(resolve(publicDir, 'manifest.json'), 'utf8')) as {
  name?: string
  short_name?: string
  start_url?: string
  scope?: string
  display?: string
  theme_color?: string
  icons?: { src: string; sizes: string; purpose?: string }[]
}

describe('web app manifest', () => {
  it('declares the fields the install criteria require', () => {
    expect(manifest.name).toBeTruthy()
    expect(manifest.short_name).toBeTruthy()
    expect(manifest.start_url).toBe('/')
    expect(manifest.scope).toBe('/')
    expect(manifest.display).toBe('standalone')
    expect(manifest.theme_color).toBeTruthy()
  })

  it('ships both required icon sizes plus a maskable variant', () => {
    const icons = manifest.icons ?? []
    const sizes = icons.map((i) => i.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
    expect(icons.some((i) => i.purpose === 'maskable')).toBe(true)
  })

  it('every icon src resolves to a file under public/', () => {
    const missing = (manifest.icons ?? []).filter((icon) => {
      try {
        readFileSync(resolve(publicDir, icon.src.replace(/^\//, '')))
        return false
      } catch {
        return true
      }
    })
    expect(missing.map((i) => i.src)).toEqual([])
  })
})
