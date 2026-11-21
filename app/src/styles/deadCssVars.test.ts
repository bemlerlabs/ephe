/**
 * A custom property written from code must have a reader.
 *
 * jsdom applies no CSS and the browser suite measures pixels, not declarations, so
 * nothing in the suite otherwise sees the one contract this file checks: a
 * `style.setProperty('--x', …)` that no `var(--x)` ever reads is a write the frame
 * pays for and the user never sees. Two of these reached main — `--chat-reading-width`
 * (removed in #327) and `--look-y` (given its nod in this branch) — and both were
 * invisible to every other test. The source of a stylesheet is not normally a seam;
 * here it is the only one there is.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { extname, join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

// vitest runs from `app/`, but a runner started one level up must still measure the
// same tree, so the root is whichever candidate actually holds `src/`.
function appRoot(): string {
  for (const candidate of [process.cwd(), join(process.cwd(), 'app')]) {
    if (statSync(join(candidate, 'src'), { throwIfNoEntry: false })?.isDirectory()) return candidate
  }
  throw new Error(`no app root (src/) below ${process.cwd()}`)
}

const APP_ROOT = appRoot()
const SCAN_ROOTS = [join(APP_ROOT, 'src'), join(APP_ROOT, 'src-tauri', 'src')]
const EXTRA_FILES = [join(APP_ROOT, 'index.html')]
const SKIP_DIRS = new Set(['node_modules', 'target', 'dist', '.git'])
const EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.css', '.html', '.json', '.rs'])

function sources(): string[] {
  const found: string[] = []
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry)
      if (statSync(path).isDirectory()) {
        if (!SKIP_DIRS.has(entry)) walk(path)
      } else if (EXTENSIONS.has(extname(entry))) {
        found.push(path)
      }
    }
  }
  for (const root of SCAN_ROOTS) {
    if (statSync(root, { throwIfNoEntry: false })?.isDirectory()) walk(root)
  }
  return found.concat(EXTRA_FILES.filter((p) => statSync(p, { throwIfNoEntry: false })?.isFile()))
}

const WRITE = /setProperty\(\s*['"`](--[a-z0-9-]+)['"`]/g
const READ = /var\(\s*(--[a-z0-9-]+)|getPropertyValue\(\s*['"`](--[a-z0-9-]+)['"`]/g

describe('the custom properties the app writes', () => {
  it('each one is read by a stylesheet, a script or the shell', () => {
    const written = new Map<string, string>()
    const read = new Set<string>()
    for (const path of sources()) {
      const text = readFileSync(path, 'utf8')
      // Specs are neither side of the contract: a spec that names a property in an
      // assertion is not a stylesheet that applies it, and counting one as a reader
      // would let a dead write pass. Only product code may write and only product
      // code, a stylesheet or the shell may read.
      if (/(\.test|\.spec)\.[cm]?[jt]sx?$/.test(path)) continue
      const from = relative(APP_ROOT, path)
      for (const match of text.matchAll(WRITE)) {
        if (match[1]) written.set(match[1], from)
      }
      for (const match of text.matchAll(READ)) {
        const name = match[1] ?? match[2]
        if (name) read.add(name)
      }
    }
    const dead = [...written]
      .filter(([name]) => !read.has(name))
      .map(([name, where]) => `${name} written at ${where}`)
    expect(dead, `dead custom-property write(s): ${dead.join('; ')}`).toEqual([])
    expect(written.size).toBeGreaterThan(0)
  })
})
