/**
 * SW precache regression.
 *
 * cache.addAll() is atomic: a single 404 (e.g. /favicon.svg, which does not
 * exist) makes the install event fail → the Service Worker never installs →
 * the offline shell AND the SKIP_WAITING update flow are dead. This suite
 * checks statically that every precached path is either a server route
 * ('/', '/index.html') or a file that exists under public/.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const swPath = resolve(here, '../../public/service-worker.js')
const publicDir = resolve(here, '../../public')

const swSource = readFileSync(swPath, 'utf8')

function extractPrecachePaths(src: string): string[] {
  const match = src.match(/const ASSETS_TO_CACHE\s*=\s*\[([\s\S]*?)\]/)
  const body = match?.[1]
  if (body == null) throw new Error('ASSETS_TO_CACHE array not found in service-worker.js')
  return [...body.matchAll(/['"]([^'"]+)['"]/g)]
    .map((m) => m[1])
    .filter((p): p is string => typeof p === 'string' && p.length > 0)
}

// Paths routed by the server that do not exist as files under public/.
const SERVER_ROUTES = new Set(['/', '/index.html'])

describe('service worker precache manifest', () => {
  it('parses a non-empty ASSETS_TO_CACHE list', () => {
    const paths = extractPrecachePaths(swSource)
    expect(paths.length).toBeGreaterThan(0)
  })

  it('precaches only routes or files that actually exist under public/', () => {
    const missing = extractPrecachePaths(swSource).filter((p) => {
      if (SERVER_ROUTES.has(p)) return false
      const rel = p.replace(/^\//, '')
      try {
        readFileSync(resolve(publicDir, rel))
        return false
      } catch {
        return true
      }
    })
    expect(
      missing,
      `precached paths that 404 (break atomic addAll → SW install): ${missing.join(', ')}`,
    ).toEqual([])
  })
})
