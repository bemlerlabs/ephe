/**
 * `window.__epheStore` — the dev handle, pinned in both directions.
 *
 * The handle is the switch that decides whether fifteen Playwright specs run or
 * skip: they seed real state through it (a 120-message session, a message with
 * thinking blocks and tool calls) and each one guards with `hasDevHandle(page)`
 * from tests/playwright/helpers.ts. Remove the guarded assignment at the end of
 * chatStore.ts and those fifteen do not fail — they skip, the run stays green,
 * and the coverage is gone. That is the state register #68 found the tree in, and
 * why a check over tests/, app/src/**\/*.test.*, app/tests/ and app/e2e found
 * nothing pinning the assignment.
 *
 * The pin has two halves, in two places, because each can only be proven in one
 * of them:
 *
 *   dev build, handle present — this file. The source assertions fail when the
 *   assignment or its guard goes; the behaviour check imports the store in jsdom
 *   and reads the handle off `window` the way the specs do, so it also fails if
 *   the branch stops executing. No browser involved.
 *
 *   production build, handle absent — NOT this file. `import.meta.env.DEV` is
 *   the mode vitest runs in, and that mode is dev, so nothing here can reach the
 *   false branch: a test that stubbed the flag would assert the stub. The
 *   artefact that answers the question is the bundle, so that half lives in
 *   `app/scripts/dev_handle_check.py`, which CI runs against `dist/` right after
 *   `pnpm run build`.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// Paths are relative to app/, the cwd vitest runs with. jsdom rewrites
// import.meta.url to an http URL, so fileURLToPath is not available here —
// globals.deadTokens.test.ts resolves its tree the same way, and the anchor test
// below fails loudly if the cwd is ever something else.
const STORE = 'src/store/chatStore.ts'
const SRC = 'src'
const SPECS_DIR = 'tests/playwright'
const HELPERS = 'tests/playwright/helpers.ts'

const EXTS = ['.ts', '.tsx']
// The name in each assignment shape a refactor could take — `__epheStore =`,
// `window['__epheStore'] =`, `window["__epheStore"] =`.
const ASSIGN = /__epheStore['"]?\]?\s*=(?!=)/

function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (EXTS.some((e) => p.endsWith(e)) && !/\.(test|spec)\./.test(p)) out.push(p)
  }
  return out
}

/** Source without comments — prose about the handle is not the handle. */
function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

function lastIfAbove(lines: string[], from: number): number {
  for (let i = from; i >= 0; i--) if (/^\s*if\s*\(/.test(lines[i]!)) return i
  return -1
}

describe('the dev store handle in chatStore.ts', () => {
  it('is anchored on the app root (a wrong cwd fails instead of scanning nothing)', () => {
    expect(existsSync(STORE)).toBe(true)
    expect(existsSync(HELPERS)).toBe(true)
  })

  it('assigns it behind the DEV guard, and nowhere else in the file', () => {
    const lines = withoutComments(readFileSync(STORE, 'utf8')).split('\n')
    const assignments = lines
      .map((line, i) => ({ line, i }))
      .filter(({ line }) => ASSIGN.test(line))

    expect(assignments, 'chatStore.ts no longer assigns window.__epheStore').toHaveLength(1)

    const at = assignments[0]!.i
    const guard = lastIfAbove(lines, at)
    expect(
      guard,
      'the assignment now sits outside any if, so a build ships it',
    ).toBeGreaterThanOrEqual(0)
    expect(lines[guard], 'the guard is no longer import.meta.env.DEV').toMatch(
      /import\.meta\.env\.DEV/,
    )
    // Nothing closes the guard between it and the assignment: the two are one block.
    expect(lines.slice(guard + 1, at).join('\n')).not.toContain('}')
  })

  it('is assigned in no other file under src/', () => {
    const files = walk(SRC)
    // Guards against a silently empty walk (globals.deadTokens.test.ts does the same).
    expect(files.length).toBeGreaterThan(50)
    const holders = files.filter((f) => ASSIGN.test(withoutComments(readFileSync(f, 'utf8'))))
    expect(holders, 'a second assignment site sits outside the DEV guard').toEqual([STORE])
  })

  it('wears the name the specs ask for', () => {
    const helpers = readFileSync(HELPERS, 'utf8')
    expect(helpers, 'hasDevHandle no longer probes the property chatStore.ts sets').toMatch(
      /'__epheStore'\s*in\s*window/,
    )
    const guarded = readdirSync(SPECS_DIR)
      .filter((f) => f.endsWith('.spec.ts'))
      .filter((f) => readFileSync(join(SPECS_DIR, f), 'utf8').includes('hasDevHandle'))
    expect(guarded, 'no spec guards on hasDevHandle anymore').not.toEqual([])
  })

  it('runs: importing the store sets the live handle on window', async () => {
    // False here would make the rest of this test say nothing — fail instead of
    // slipping into a skip, which is the failure this file exists to stop.
    expect(import.meta.env.DEV, 'vitest must run in dev mode for this check to mean anything').toBe(
      true,
    )

    const mod = await import('./chatStore')
    const handle = (window as unknown as { __epheStore?: typeof mod.useChatStore }).__epheStore

    expect(handle, 'chatStore.ts did not set window.__epheStore on import').toBe(mod.useChatStore)
    // The two capabilities the specs use on it.
    expect(typeof handle!.getState).toBe('function')
    expect(typeof handle!.setState).toBe('function')
    expect(Array.isArray(handle!.getState().sessions)).toBe(true)
  })
})
