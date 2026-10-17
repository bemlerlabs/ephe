/**
 * Ephe — desktop wave: BASE_URL resolution (pin tests)
 *
 * GIVEN the desktop shell (Tauri) serves the UI from tauri://localhost
 * WHEN the API base URL gets resolved
 * THEN: VITE_API_URL always wins; without that env the Tauri shell points at
 *     the local product server (127.0.0.1:8765) while the browser stays
 *     same-origin. Without it /api fetches went nowhere (empty chat,
 *     "offline") — release mode was never wired end to end.
 */
import { describe, it, expect } from 'vitest'
import { resolveBaseUrl, TAURI_BACKEND_DEFAULT } from './desktopBaseUrl'

describe('resolveBaseUrl', () => {
  it('VITE_API_URL gewinnt immer (auch in der Tauri-Shell)', () => {
    expect(resolveBaseUrl('http://192.168.1.50:8765', true)).toBe('http://192.168.1.50:8765')
    expect(resolveBaseUrl('http://192.168.1.50:8765', false)).toBe('http://192.168.1.50:8765')
  })

  it('Tauri-Shell ohne Env → lokaler Produktserver', () => {
    expect(resolveBaseUrl(undefined, true)).toBe(TAURI_BACKEND_DEFAULT)
    expect(resolveBaseUrl('', true)).toBe(TAURI_BACKEND_DEFAULT)
  })

  it('Browser ohne Env → same-origin (leer)', () => {
    expect(resolveBaseUrl(undefined, false)).toBe('')
    expect(resolveBaseUrl('', false)).toBe('')
  })

  it('Standard-Endpunkt ist localhost (kein Fremd-Host, kein LAN-Default)', () => {
    expect(TAURI_BACKEND_DEFAULT.startsWith('http://127.0.0.1:')).toBe(true)
  })
})
