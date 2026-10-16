/**
 * Ephe — desktop wave: BASE_URL resolution for the Tauri shell.
 *
 * The Tauri app serves the UI from tauri://localhost — same-origin /api
 * fetches come back empty there. The browser (PWA from the product server)
 * stays same-origin; without env the shell points at the local
 * product server. VITE_API_URL always overrides (remote setups).
 */
export const TAURI_BACKEND_DEFAULT = 'http://127.0.0.1:8765'

export function resolveBaseUrl(envUrl: string | undefined, hasTauri: boolean): string {
  if (envUrl) return envUrl
  return hasTauri ? TAURI_BACKEND_DEFAULT : ''
}

const hasTauri =
  typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window)

/** The surface knows whether it runs in a real browser or in the shell window.
 *  That decides which formats need a viewer in the browser —
 *  see `previewShowsInFrame`. */
export const IS_DESKTOP_SHELL = hasTauri

export const DESKTOP_BASE_URL = resolveBaseUrl(import.meta.env.VITE_API_URL, hasTauri)
