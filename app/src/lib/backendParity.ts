import { healthCheck } from '@/lib/api'
import { IS_DESKTOP_SHELL } from '@/lib/desktopBaseUrl'
import { requestSettingsOpen } from '@/lib/openSettings'
import { relaunchApp, restartGuardNow } from '@/lib/restartGuard'
import { toastBus } from '@/lib/toast'

export interface BackendParity {
  verdict: string
  shell: string
  backend: string
  note: string
}

export interface BuildParity {
  verdict: 'match' | 'mismatch' | 'unknown'
  build: string
  backend: string
}

type Translate = (key: string, options?: Record<string, unknown>) => string

/** The shell's command channel, reachable while the app runs with `withGlobalTauri`. */
type TauriBridge = {
  core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

async function invokeParity(): Promise<BackendParity> {
  const bridge = (window as unknown as { __TAURI__?: TauriBridge }).__TAURI__
  const invoke = bridge?.core?.invoke
  if (typeof invoke !== 'function') throw new Error('no shell command channel')
  return (await invoke('backend_parity')) as BackendParity
}

/**
 * The updater replaces the `.app` and nothing else, so the Python backend can
 * still be running the version before the shell's. The shell compares the two
 * when it starts the backend, moves the checkout when they disagree and asks
 * that backend to refresh the environment around the tree it just moved; this
 * reads what the shell found and says it out loud.
 *
 * Only a measured disagreement is reported. `unknown` and `no_backend` stay
 * silent because there is nothing there to name — an older shell without the
 * command, or a machine where the app is not the one that starts a backend.
 */
export async function announceBackendParity(t: Translate): Promise<BackendParity | null> {
  let status: BackendParity
  try {
    status = await invokeParity()
  } catch {
    return null
  }
  report(status, t)
  if (status.verdict === 'updated_reinstalling') followRefresh(t)
  return status
}

/** One verdict, in the user's words.
 *
 * The shell's own note stays out of the restart branch on purpose: it names a
 * git state in the shell's language, and what a person needs here is the action.
 * The mismatch keeps its note because that sentence is the reason nothing moved.
 */
function report(status: BackendParity, t: Translate): void {
  if (status.verdict === 'mismatch') {
    toastBus.error(
      t('chat.backendMismatch', { shell: status.shell, backend: status.backend }),
      status.note,
    )
    return
  }
  if (status.verdict === 'updated_reinstalling') {
    toastBus.info(t('chat.backendReinstalling'), undefined, undefined, 'backend-parity')
    return
  }
  if (status.verdict !== 'updated_restart') return
  const block = restartGuardNow()
  if (block.blocked) {
    toastBus.info(
      t('chat.backendUpdated'),
      t(block.reason === 'running' ? 'update.restartBlockedRunning' : 'update.restartBlockedDraft'),
      undefined,
      'backend-parity',
    )
    return
  }
  toastBus.info(
    t('chat.backendUpdated'),
    undefined,
    { label: t('update.relaunchNow'), onClick: () => void relaunchApp() },
    'backend-parity',
  )
}

/** The shell waits on the installer it asked for; the surface waits on the
 * shell. The same bound, read at the same distance, and a start that comes
 * later re-reads the verdict on its own. */
const REFRESH_POLL_MS = 30_000
const REFRESH_POLLS = 60

let followTimer: ReturnType<typeof setTimeout> | undefined

function followRefresh(t: Translate): void {
  if (followTimer) clearTimeout(followTimer)
  let left = REFRESH_POLLS
  const step = async (): Promise<void> => {
    followTimer = undefined
    let next: BackendParity
    try {
      next = await invokeParity()
    } catch {
      return
    }
    if (next.verdict === 'updated_reinstalling') {
      left -= 1
      if (left > 0) followTimer = setTimeout(step, REFRESH_POLL_MS)
      return
    }
    report(next, t)
  }
  followTimer = setTimeout(step, REFRESH_POLL_MS)
}

/** The commit this bundle was built from. Empty in a development build whose define
 * was not stamped, which reads as "nothing measured" rather than as a match. */
export function frontendBuildSha(): string {
  return typeof __EPHE_BUILD_SHA__ === 'string' ? __EPHE_BUILD_SHA__ : ''
}

/** Where a dismissed shell update is remembered — per pair, so a genuinely newer
 *  build asks once more and the same pair does not come back on every reload. */
const BUILD_ACK_KEY = 'ephe.build-parity.ack'

function buildPair(mine: string, backend: string): string {
  return `${mine}->${backend}`
}

function acknowledgedBuildPair(): string {
  try {
    return window.localStorage.getItem(BUILD_ACK_KEY) ?? ''
  } catch {
    return ''
  }
}

function acknowledgeBuildPair(pair: string): void {
  try {
    window.localStorage.setItem(BUILD_ACK_KEY, pair)
  } catch {
    /* private mode — the toast stays per page life, which is the honest fallback */
  }
}

/**
 * F10, second half: the shell and the backend are shipped by different mechanisms,
 * so the *bundle* has to know its own commit. The version string cannot separate two
 * builds of one number — a `dist` a day older than the tree serving it looks current
 * and quietly lacks the new UI. The build SHA is stamped by `vite.config.ts` and
 * compared with the backend's `git_sha`; only a measured disagreement is reported,
 * and `unknown` on either side stays silent because there is nothing to name.
 *
 * A browser build is deliberately silent here. The page is served by the same tree
 * that answers `/api/health`, so reloading a stale `dist` re-reads the stale files;
 * only a *waiting service worker* is a new version a reload can actually load, and
 * `registerSW.ts` owns that banner. A toast on every task mount promised an action
 * the surface could not perform (measured 2026-11-10: dist 75384975, backend
 * c47ba078 — the banner reappeared after every reload and covered the header).
 */
export async function announceBuildParity(
  t: Translate,
  health?: { git_sha?: string } | null,
  build: string = frontendBuildSha(),
  inShell: boolean = IS_DESKTOP_SHELL,
): Promise<BuildParity | null> {
  let info = health
  if (info === undefined) {
    try {
      info = await healthCheck()
    } catch {
      return null
    }
  }
  const mine = build.trim()
  const backend = String(info?.git_sha ?? '').trim()
  if (!mine || mine === 'unknown' || !backend) {
    return { verdict: 'unknown', build: mine, backend }
  }
  if (mine === backend) return { verdict: 'match', build: mine, backend }
  if (!inShell) {
    // Nothing this page can do: the dist it loaded is the dist the server ships.
    // The service-worker banner is the one that names a reloadable new version.
    return { verdict: 'mismatch', build: mine, backend }
  }
  // The interface is frozen into the `.app`, so reloading the window re-reads the same
  // files and the newer one stays where it is. Only the app update brings it — so the
  // shell names the update and opens the page that runs it. The tab is asked for first:
  // the panel reads a named request as the tab of the open it arrives with.
  const pair = buildPair(mine, backend)
  if (acknowledgedBuildPair() === pair) return { verdict: 'mismatch', build: mine, backend }
  toastBus.error(
    t('chat.buildMismatchShell'),
    undefined,
    {
      label: t('update.applyNow'),
      onClick: () => {
        window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'about' } }))
        requestSettingsOpen()
      },
    },
    // One row for one pair: a page that remounts the task view cannot stack copies,
    // and closing it writes the acknowledgement so a reload stays quiet.
    'build-parity',
    { onDismiss: () => acknowledgeBuildPair(pair) },
  )
  return { verdict: 'mismatch', build: mine, backend }
}
