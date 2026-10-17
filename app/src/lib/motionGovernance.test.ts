/**
 * Motion governance (R4): the operating system's reduce-motion rule applies once,
 * centrally — not file by file.
 *
 * Four surfaces animated without ever knowing `useReducedMotion` (Settings,
 * Shortcuts, Sidebar, type indicator). Demanding per-file helpers would be the
 * fourth copy of the same intent; it is fixed at the top instead, with
 * `MotionConfig reducedMotion="user"`. This test pins exactly that down and
 * forbids a surface from switching the rule off again afterwards.
 */
import { describe, it, expect } from 'vitest'

const sources = import.meta.glob<string>('../**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const TEST_FILE = /\/[^/]+\.(test|spec)\.[tm]sx?$/
const app = sources['../App.tsx']

describe('reducedMotion wird zentral gesetzt', () => {
  it('der Wurzelbaum steckt in einer MotionConfig mit Ruheregel', () => {
    expect(app).toBeDefined()
    expect(app).toContain('reducedMotion="user"')
    expect(app).toMatch(/<MotionConfig[^>]*reducedMotion="user"[\s\S]*<Router>/)
  })

  it('keine Fläche schaltet die Ruheregel wieder aus', () => {
    const contradicting = Object.entries(sources)
      .filter(([path, raw]) => !TEST_FILE.test(path) && /reducedMotion="never"/.test(raw))
      .map(([path]) => path)
    expect(contradicting).toEqual([])
  })

  it('Flächen ohne eigene Ruheregel existieren nur, weil die zentrale gilt', () => {
    const animating = Object.entries(sources).filter(
      ([path, raw]) => !TEST_FILE.test(path) && /from 'framer-motion'/.test(raw),
    )
    expect(animating.length).toBeGreaterThan(4)
    // A surface that steers its own jumps may well do without the central rule;
    // one that does not know it falls back on it. Both are fine, both are here.
    const perFile = animating.filter(([, raw]) => raw.includes('useReducedMotion'))
    expect(perFile.length).toBeGreaterThan(0)
  })
})
