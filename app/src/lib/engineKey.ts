type TauriBridge = {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

function bridgeInvoke(cmd: string, args: Record<string, unknown>): Promise<unknown> | null {
  const bridge = (window as { __TAURI__?: TauriBridge }).__TAURI__
  if (!bridge?.core?.invoke) return null
  return bridge.core.invoke(cmd, args)
}

/**
 * The engine access token, per surface (AGENTS.md: no silent default, one variable).
 *
 * POST /api/settings writes a typed key into the env of the server process that answers,
 * which dies with it. On the desktop that is not enough: the app starts its own backend
 * from a launchd environment that carries no `EPHE_` variable at all, so a keyed engine
 * chosen in the app stopped authenticating at the next start. The shell therefore stores
 * the value in `~/.ephe/engine.key` (owner-only, one line) and the spawn hands that file
 * to the backend it starts.
 *
 * In a browser there is no shell to ask, and this module says so: 'session-only' is the
 * honest answer rather than a claim about a device the page cannot write to.
 */
export type EngineKeyResult = 'stored' | 'session-only' | 'removed' | 'no-shell'

export async function storeEngineKey(value: string): Promise<EngineKeyResult> {
  const call = bridgeInvoke('save_engine_key', { value })
  if (!call) return 'session-only'
  await call
  return 'stored'
}

export async function clearEngineKey(): Promise<EngineKeyResult> {
  const call = bridgeInvoke('clear_engine_key', {})
  if (!call) return 'no-shell'
  await call
  return 'removed'
}

/** Whether a token is stored. Existence only — the value never crosses into the page. */
export async function engineKeyStored(): Promise<boolean> {
  const call = bridgeInvoke('engine_key_state', {})
  if (!call) return false
  return (await call) === true
}

/** Is this the desktop surface, where a stored key survives the next start? */
export function engineKeyStoreAvailable(): boolean {
  return Boolean((window as { __TAURI__?: TauriBridge }).__TAURI__?.core?.invoke)
}
