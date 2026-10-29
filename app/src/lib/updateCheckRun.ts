/**
 * Ephe — the update check as a function, apart from the hook that drives it.
 *
 * Both checks answer the same shape. The browser reads the backend, which
 * compares against the release feed and the default branch's tip; the desktop
 * asks the signed updater as well, because the release the bundle will replace
 * is the only comparison that decides an install.
 */
import { apiUrl } from '@/lib/api/http'
import { readAsset, readManifestNotes, readPlatform } from '@/lib/updateDetails'

export interface UpdateCheckInfo {
  enabled: boolean
  available: boolean
  current?: string
  latest?: string
  url?: string
  notes?: string
  /** The reason the check could not run. Without a reader in the surface this
   *  value used to be lost — which is why it said "no update" on a 404. */
  error?: string
  /** Which source answered: a tagged release, or merges that reached the
   *  default branch before the next tag. */
  channel?: 'release' | 'main'
  /** Commits between this build and the branch tip, on the main channel. */
  commitsBehind?: number
  /** The commit this build runs on, when the backend knows it. */
  commit?: string
}

/** What the app's own update did, step by step. */
export interface ApplyResult {
  ok: boolean
  reason?: string
  detail?: string
  steps?: Array<{ name: string; ok: boolean; detail: string }>
  before?: string
  after?: string
  restart?: boolean
}

export type UpdatePhase =
  | 'idle'
  | 'checking'
  | 'current'
  | 'failed'
  | 'available'
  | 'downloading'
  | 'installing'
  | 'ready'
  | 'applying'
  | 'applied'
  | 'unsupported'

export interface UpdateState {
  phase: UpdatePhase
  current?: string
  latest?: string
  notes?: string
  url?: string
  /** The size the transfer reported, when it reported one — the Details line
   *  shows it in bytes the reader can compare. */
  sizeBytes?: number
  /** The package the updater resolved for this platform, when it named one. */
  asset?: string
  /** The host platform the shell runs on. */
  platform?: string
  /** The publish date the release feed named, when it named one. */
  date?: string
  /** 0..1, only during `downloading`; null when the source reports nothing. */
  progress: number | null
  reason?: string
  /** Which step carried the failure. An installer that refused used to be
   *  reported with the sentence about an unreachable release source. */
  failedAt?: 'check' | 'install'
  /** Which source answered the check (see UpdateCheckInfo). */
  channel?: 'release' | 'main'
  /** Commits between this build and the default branch tip. */
  commitsBehind?: number
  /** The commit this build runs on, when the backend knows it. */
  commit?: string
  /** The steps an applied update ran, in order. */
  steps?: Array<{ name: string; ok: boolean; detail: string }>
  /** True when the update moved the checkout, so a relaunch is owed. */
  restart?: boolean
}

/** True inside the Ephe desktop shell (Tauri IPC available). */
export function isDesktopShell(): boolean {
  return !!(window as unknown as Record<string, unknown>).__TAURI__
}

/** The running bundle's version, read from the shell. */
async function shellVersion(): Promise<string | undefined> {
  const app = (window as { __TAURI__?: { app?: { getVersion?: () => Promise<string> } } }).__TAURI__
    ?.app
  try {
    return await app?.getVersion?.()
  } catch {
    return undefined
  }
}

/**
 * The desktop check. The local backend owns the opt-out and the release notes;
 * the signed updater compares the release against the bundle it will replace,
 * which is the only comparison that decides an install.
 */
async function runDesktopCheck(force: boolean): Promise<UpdateState> {
  let local: UpdateCheckInfo | undefined
  try {
    const r = await fetch(apiUrl(force ? '/api/update/check?force=1' : '/api/update/check'))
    if (r.ok) local = (await r.json()) as UpdateCheckInfo
  } catch {
    /* the updater below answers on its own */
  }
  if (local && !local.enabled) {
    return { phase: 'unsupported', progress: null, current: local.current, reason: 'disabled' }
  }
  const updater = await import('@tauri-apps/plugin-updater')
  const [current, update] = await Promise.all([shellVersion(), updater.check()])
  // A tagged release is the only thing the signed updater can install. Merges
  // the backend reports on the main channel are still news the user can take,
  // and the dialog points at the comparison instead of offering an install.
  const main = !update?.available && local?.channel === 'main' ? local : undefined
  const base = {
    current: current ?? update?.currentVersion ?? local?.current,
    latest: update?.version ?? main?.latest ?? current ?? local?.latest,
    notes: readManifestNotes(update?.body) ?? local?.notes,
    platform: readPlatform(),
    asset: readAsset(update?.rawJson),
    date: update?.date,
    channel: update?.available ? ('release' as const) : main ? ('main' as const) : undefined,
    commitsBehind: main?.commitsBehind,
    commit: main?.commit,
    url: main?.url,
  }
  return update?.available || main
    ? { phase: 'available', progress: null, ...base }
    : { phase: 'current', progress: null, ...base }
}

/**
 * The check path itself — once for a live question, once for the click from
 * the menu or the dialog. `force` is what makes the backend skip its TTL
 * cache, so every caller here passes true except the tests.
 */
export async function runCheck(force = false): Promise<UpdateState> {
  try {
    if (isDesktopShell()) return await runDesktopCheck(force)
    const r = await fetch(apiUrl(force ? '/api/update/check?force=1' : '/api/update/check'))
    if (!r.ok) {
      return { phase: 'failed', progress: null, reason: `HTTP ${r.status}`, failedAt: 'check' }
    }
    const info = (await r.json()) as UpdateCheckInfo
    if (!info.enabled) {
      return { phase: 'unsupported', progress: null, current: info.current, reason: 'disabled' }
    }
    if (info.error) {
      return {
        phase: 'failed',
        progress: null,
        current: info.current,
        reason: String(info.error),
        failedAt: 'check',
      }
    }
    const base = {
      current: info.current,
      latest: info.latest,
      notes: info.notes,
      url: info.url,
      channel: info.channel,
      commitsBehind: info.commitsBehind,
      commit: info.commit,
    }
    return info.available && info.latest
      ? { phase: 'available', progress: null, ...base }
      : { phase: 'current', progress: null, ...base }
  } catch (e) {
    return {
      phase: 'failed',
      progress: null,
      reason: e instanceof Error ? e.message : String(e),
      failedAt: 'check',
    }
  }
}

/**
 * Take the newest commits: the same pull and installer `ephe update` runs,
 * behind one click. The backend refuses a dirty tree, another branch or a
 * second click, and says why.
 */
export async function applyUpdate(): Promise<ApplyResult> {
  try {
    const r = await fetch(apiUrl('/api/update/apply'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: 'update' }),
    })
    if (!r.ok) return { ok: false, reason: `HTTP ${r.status}` }
    return (await r.json()) as ApplyResult
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : String(e) }
  }
}
