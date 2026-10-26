import { toastBus } from '@/lib/toast'

export interface BackendParity {
  verdict: string
  shell: string
  backend: string
  note: string
}

type Translate = (key: string, options?: Record<string, unknown>) => string

/** The shell's command channel, reachable while the app runs with `withGlobalTauri`. */
type TauriBridge = { core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> } }

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
