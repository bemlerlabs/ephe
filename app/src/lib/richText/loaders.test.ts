/**
 * The load-on-demand seam itself.
 *
 * The entry chunk is the number this seam protects: a static import of KaTeX
 * would put its parser and font metrics in front of every user, which is the
 * mistake `i18n.ts` makes with the two locale files. These tests pin the two
 * properties the seam relies on — one fetch per session, and no cache of a
 * failure.
 */
import { describe, it, expect, vi } from 'vitest'
import { loadKatex } from './loadKatex'
import { loadMermaid } from './loadMermaid'

describe('loadKatex', () => {
  it('hands every caller the same in-flight promise', () => {
    const first = loadKatex()
    expect(loadKatex()).toBe(first)
    return first.then((katex) => {
      expect(typeof katex.renderToString).toBe('function')
      expect(loadKatex()).toBe(first)
    })
  })
})

describe('loadMermaid', () => {
  it('hands every caller the same in-flight promise', async () => {
    const first = loadMermaid()
    expect(loadMermaid()).toBe(first)
    const mermaid = await first
    expect(typeof mermaid.render).toBe('function')
  })
})

describe('a failed load', () => {
  it('is not cached, so a later formula can still render', async () => {
    vi.resetModules()
    // The factory itself has to resolve; what fails is the module's own shape, so
    // the rejection happens inside the loader's chain, where the cache is cleared.
    vi.doMock('katex', () => ({
      get default(): never {
        throw new Error('chunk unavailable')
      },
    }))
    const fresh = await import('./loadKatex')
    const first = fresh.loadKatex()
    await expect(first).rejects.toThrow('chunk unavailable')
    const second = fresh.loadKatex()
    expect(second).not.toBe(first)
    await expect(second).rejects.toThrow('chunk unavailable')
    vi.doUnmock('katex')
    vi.resetModules()
  })
})
