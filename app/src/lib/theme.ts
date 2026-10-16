// Theme mode of the app. The forest is the product's own register and the default:
// dark canvas, warm light, the mark's glow as the one warm source. A paper theme
// exists as a user choice (`html.light` bends the same tokens) and is no longer what
// a first launch shows — the paper register was tried as the default and rejected by
// the owner on 2026-10-16: 'we are not doing this paper style, only the forest.'
// Deliberately no 'system': one button, two states, and this file owns the
// persistence and the class toggle on the <html> element.
export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'ephe.theme'

export function getStoredTheme(): ThemeMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

/** The browser edge follows the canvas token, not a second color declaration:
 *  the value is resolved through the DOM so it already reflects the current class
 *  (light/dark) and arrives in the syntax every parser knows. */
function syncThemeColor(): void {
  const root = document.head.querySelector('meta[name="theme-color"]')
  if (!root || !document.body) return
  const probe = document.createElement('span')
  probe.style.color = 'var(--color-canvas)'
  document.body.append(probe)
  const resolved = getComputedStyle(probe).color
  probe.remove()
  // jsdom and old parsers like to return the raw `var(...)` here — that does
  // not belong in a meta attribute.
  if (/^(rgba?\(|#)/.test(resolved)) root.setAttribute('content', resolved)
}

export function applyTheme(mode: ThemeMode): void {
  document.documentElement.classList.toggle('light', mode === 'light')
  syncThemeColor()
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    /* Private mode: the theme stays in effect for the session */
  }
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = getStoredTheme() === 'light' ? 'dark' : 'light'
  applyTheme(next)
  return next
}
