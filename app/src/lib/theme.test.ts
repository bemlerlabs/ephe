import { beforeEach, describe, expect, it } from 'vitest'
import { applyTheme, getStoredTheme, toggleTheme } from './theme'

// The mode lives as the .light class on the <html> element and mirrors into
// localStorage. The forest is the default; a saved paper choice keeps paper.
describe('theme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('light')
  })

  it('opens on the forest when nothing is stored', () => {
    expect(getStoredTheme()).toBe('dark')
  })

  it('keeps a saved paper choice', () => {
    localStorage.setItem('ephe.theme', 'light')
    expect(getStoredTheme()).toBe('light')
  })

  it('applyTheme sets the class and persists the choice', () => {
    applyTheme('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
    expect(localStorage.getItem('ephe.theme')).toBe('dark')

    applyTheme('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('ephe.theme')).toBe('light')
  })

  it('toggleTheme switches there and back', () => {
    applyTheme('light')
    expect(toggleTheme()).toBe('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
    expect(toggleTheme()).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
  })
})
