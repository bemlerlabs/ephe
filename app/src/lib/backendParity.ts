import { healthCheck } from '@/lib/api'
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
 * when it starts the backend; this reads what it found and says it out loud.
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
  if (status.verdict === 'mismatch') {
    toastBus.error(
      t('chat.backendMismatch', { shell: status.shell, backend: status.backend }),
      status.note,
    )
  } else if (status.verdict === 'updated_restart') {
    toastBus.info(t('chat.backendUpdated'), undefined, undefined, 'backend-parity')
  }
  return status
}

/** The commit this bundle was built from. Empty in a development build whose define
 * was not stamped, which reads as "nothing measured" rather than as a match. */
export function frontendBuildSha(): string {
  return typeof __EPHE_BUILD_SHA__ === 'string' ? __EPHE_BUILD_SHA__ : ''
}

/**
 * F10, second half: the shell and the backend are shipped by different mechanisms,
 * so the *bundle* has to know its own commit. The version string cannot separate two
 * builds of one number — a `dist` a day older than the tree serving it looks current
 * and quietly lacks the new UI. The build SHA is stamped by `vite.config.ts` and
 * compared with the backend's `git_sha`; only a measured disagreement is reported,
 * and `unknown` on either side stays silent because there is nothing to name.
 */
export async function announceBuildParity(
  t: Translate,
  health?: { git_sha?: string } | null,
  build: string = frontendBuildSha(),
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
  toastBus.error(t('chat.buildMismatch'))
  return { verdict: 'mismatch', build: mine, backend }
}
