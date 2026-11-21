/**
 * The settings tab a caller asked for before the register was mounted.
 *
 * The register mounts on its first open request and the callers that name a tab
 * dispatch `ephe:open-settings` and `ephe:settings-tab` in one tick, so the tab
 * arrives before the register's own listener exists and the open falls back to
 * the default tab. The listener here is installed at app start; the register
 * takes the request once on mount, and a live listener clears it so a request
 * cannot leak into a later open.
 */
export interface SettingsIntent {
  tab?: string
  query?: string
}

let pending: SettingsIntent | null = null

export function pendingSettingsIntent(): SettingsIntent | null {
  return pending
}

export function takeSettingsIntent(): SettingsIntent | null {
  const taken = pending
  pending = null
  return taken
}

export function clearSettingsIntent(): void {
  pending = null
}

if (typeof window !== 'undefined') {
  window.addEventListener('ephe:settings-tab', (event) => {
    const detail = (event as CustomEvent<SettingsIntent | undefined>).detail
    if (!detail) return
    pending = { ...(pending ?? {}), ...detail }
  })
}
