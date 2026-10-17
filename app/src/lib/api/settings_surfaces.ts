/**
 * I6-4 / I6-6: the API of the Hooks and Network settings surfaces.
 *
 * Both endpoints only read (writing happens through the tab), and both
 * bring a larger type block along. They live here rather than in endpoints.ts
 * so that the API file does not keep growing past the
 * file boundary with every new surface — index.ts exports both as a matter of course.
 */
import { request } from './http'
// ── I6-4: User hooks (GET /settings/hooks) ─────────────────────────────────

export interface HookSpec {
  command: string
  match: string
  priority: number
}

export interface HookEvent {
  key: string
  /** false = the core fires this event nowhere at all (no call site). */
  live: boolean
  hooks: HookSpec[]
}

export interface HookRun {
  ts: string
  tool: string
  status: string
  detail: string
}

export interface HooksView {
  enabled: boolean
  path: string
  exists: boolean
  events: HookEvent[]
  recent: HookRun[]
}

/** The read side of the hooks — hooks.json is written on the device, not here. */
export function getHooks(): Promise<HooksView> {
  return request<HooksView>('/api/settings/hooks')
}

// ── I6-6: Network as it really binds (GET /network/status) ─────────────────

export interface NetworkStatus {
  bind_host: string
  bind_port: number
  lan: boolean
  setup_mode: boolean
  token_required: boolean
  file_roots: string[]
  proxy_extra_ports: string[]
  allow_private_fetches: boolean
}

/** What the server really binds and releases — none of it is a slider here. */
export function getNetworkStatus(): Promise<NetworkStatus> {
  return request<NetworkStatus>('/api/network/status')
}
