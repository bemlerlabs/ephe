/**
 * Ephe — the native file windows (R4/A1, W5).
 *
 * „Übernehmen" (English: "Adopt") means: the copy goes where the user wants it. On // language-gate: ignore — quoted rendered label, locales/de.json artifacts.adopt
 * the desktop that is a real window, not a text field — hence this module on
 * top of `tauri-plugin-dialog`. In the browser the window does not exist
 * (Safari and Firefox cannot ask for the destination at all); there
 * the same gesture falls back to the ordinary download, and the surface says so.
 * The same plugin also opens the picker („Öffnen", English "Open") — for years the gesture in // language-gate: ignore — quoted rendered label, locales/de.json toast.open
 * the composer called a command the shell never registered.
 *
 * Encapsulated via tauriBridge: without the bridge `pickSaveTarget` is simply null,
 * and the caller decides — no throwing, no try/catch ritual.
 */
import { tauriInvoke } from './tauriBridge'

export type SaveTarget = { path: string; name: string }

function asPath(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  // v2 delivers a FilePath; depending on the source as a string or { path }
  if (value && typeof value === 'object') {
    const p = (value as { path?: unknown }).path
    if (typeof p === 'string' && p.trim()) return p.trim()
  }
  return null
}

/**
 * Opens the native "save as…" dialog. Null means: cancelled, or there is
 * no shell (PWA) — for the caller both mean "ask another way".
 */
export async function pickSaveTarget(
  defaultName: string,
  title = 'Übernehmen',
): Promise<SaveTarget | null> {
  const invoke = tauriInvoke()
  if (!invoke) return null
  const name = defaultName || 'ephe-artifact'
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : ''
  try {
    const result = await invoke('plugin:dialog|save', {
      options: {
        title,
        defaultPath: name,
        canCreateDirectories: true,
        filters: ext ? [{ name: ext.toUpperCase(), extensions: [ext] }] : [],
      },
    })
    const path = asPath(result)
    if (!path) return null
    return { path, name: path.slice(path.lastIndexOf('/') + 1) }
  } catch {
    // A dialog that does not answer is not a user error.
    return null
  }
}
