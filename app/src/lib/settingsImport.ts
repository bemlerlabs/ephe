import { apiUrl } from '@/lib/api/http'
import { tauriInvoke } from '@/lib/tauriBridge'

export interface ImportOutcome {
  skills: number
  servers: number
  persona: boolean
}

/**
 * M2: the same path the first-run tour takes. The shell picks a folder and hands
 * back a one-time token, so no local path travels through the page or the
 * request. Returns null where there is no shell — a browser tab has no picker.
 */
export async function importPickedFolder(): Promise<ImportOutcome | null> {
  const invoke = tauriInvoke()
  if (!invoke) return null
  const token = await invoke('pick_folder')
  if (typeof token !== 'string' || !token) return null
  const response = await fetch(apiUrl('/api/import'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, apply: true }),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const data = (await response.json()) as {
    applied?: { persona?: boolean; skills?: unknown[]; mcp_servers?: unknown[] }
  }
  const applied = data.applied ?? {}
  return {
    skills: Array.isArray(applied.skills) ? applied.skills.length : 0,
    servers: Array.isArray(applied.mcp_servers) ? applied.mcp_servers.length : 0,
    persona: applied.persona === true,
  }
}
