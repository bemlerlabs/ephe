// R1-9 / R2-0: the browser edge follows the canvas token, and only when it can
// actually resolve that token.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { applyTheme } from './theme'

function metaTag(content = '#050505') {
  document.head.querySelector('meta[name="theme-color"]')?.remove()
  const meta = document.createElement('meta')
  meta.name = 'theme-color'
  meta.content = content
  document.head.append(meta)
  return meta
}

function resolved(color: string) {
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    color,
  } as unknown as CSSStyleDeclaration)
}

describe('theme-color-Sync', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.head.querySelector('meta[name="theme-color"]')?.remove()
  })

  it('schreibt den aufgelösten Farbton', () => {
    const meta = metaTag()
    resolved('rgb(240, 240, 230)')
    applyTheme('light')
    expect(meta.content).toBe('rgb(240, 240, 230)')
  })

  it('schreibt kein rohes var() in das Attribut', () => {
    const meta = metaTag()
    resolved('var(--color-canvas)')
    applyTheme('dark')
    expect(meta.content).toBe('#050505')
  })

  it('wirft nicht, wenn das Attribut gar nicht hängt', () => {
    metaTag().remove()
    resolved('rgb(21, 18, 15)')
    expect(() => applyTheme('light')).not.toThrow()
  })

  it('setzt die Theme-Klasse am <html>', () => {
    metaTag()
    resolved('rgb(21, 18, 15)')
    applyTheme('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    applyTheme('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
  })
})
