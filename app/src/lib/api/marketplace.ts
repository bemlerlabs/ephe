/** Marketplace client: sources, index, installed view, updates and actions. */
import { apiUrl, request } from './http'

export interface MarketSource {
  id: string
  title: string
  kind: 'bundled' | 'local' | 'https'
  url: string
  trust: string
  removable: boolean
}

export interface MarketHome {
  sources: MarketSource[]
  last_read: Record<string, string>
  last_error: Record<string, string>
}

export interface MarketPermissionDelta {
  tool_families_added: string[]
  tool_families_removed: string[]
  data_roots_added: string[]
  data_roots_removed: string[]
  digest: string
}

export interface MarketVersion {
  version: string
  publishTimestamp: number
  source: {
    type: string
    url: string
    sha256: string
    signature?: Record<string, unknown>
  }
  engines: { ephe: string }
  permissions: { tool_families?: string[]; data_roots?: string[] }
  components: string[]
  revoked?: boolean
  revocation_reason?: string
}

export interface MarketMeasurement {
  provider?: string
  model?: string
  cases?: number
  runs?: number
  pass3?: string
  date?: string
  commit?: string
  dirty?: boolean
}

export interface MarketPlugin {
  name: string
  displayName: string
  description: string | Record<string, string>
  publisher: { name: string; verified?: boolean }
  trust: string
  kind?: 'plugin' | 'skill-pack'
  quality_label?: 'plugin' | 'capability-preset' | 'bundled'
  provenance?: string
  measurement?: MarketMeasurement | null
  tiers?: { A?: number; B?: number; C?: number } | null
  categories: string[]
  icon?: Record<string, string>
  versions: MarketVersion[]
}

export interface MarketIndexBody {
  format: number
  name: string
  owner: { name: string }
  metadata?: Record<string, unknown>
  plugins: MarketPlugin[]
}

export interface MarketIndexResponse {
  status: 'ok' | 'error'
  source: MarketSource
  index: MarketIndexBody | null
  error: string
}

export interface MarketInstalledRow {
  name: string
  version: string
  description: string
  enabled: boolean
  origin: 'bundled' | 'user'
  components: string[]
  permissions: { tool_families: string[]; data_roots: string[] }
}

export interface MarketUpdate {
  name: string
  version: string
  installed_version: string
  trust: string
  source_id: string
  source_title: string
}

export interface MarketPlan {
  status: 'ready' | 'permission_review' | 'refused' | 'already_installed'
  code?: string
  error?: string
  name: string
  version: string
  installed_version?: string
  sha256?: string
  url?: string
  trust?: string
  signature?: Record<string, unknown> | null
  permissions?: Record<string, unknown>
  components?: string[]
  delta?: MarketPermissionDelta
  approved_delta?: string
  local_trust_required?: boolean
  displayName?: string
  description?: string | Record<string, string>
  publisher?: { name: string }
  categories?: string[]
}

export interface MarketInstallResult {
  status: string
  name: string
  version?: string
  trust?: string
  error?: string
  code?: string
  warning?: string
  permissions?: { tool_families: string[]; data_roots: string[] }
  enabled?: boolean
  activation_error?: string
  lockfile_error?: string
}

export function getMarketHome(): Promise<MarketHome> {
  return request<MarketHome>('/api/market')
}

export function getMarketIndex(): Promise<MarketIndexResponse> {
  return request<MarketIndexResponse>('/api/market/index')
}

export function getMarketInstalled(): Promise<{ plugins: MarketInstalledRow[] }> {
  return request<{ plugins: MarketInstalledRow[] }>('/api/market/installed')
}

export function getMarketUpdates(): Promise<{
  updates: MarketUpdate[]
  errors: { source: string; error: string }[]
}> {
  return request('/api/market/updates')
}

export function planMarketInstall(
  sourceId: string,
  name: string,
  version: string,
  options: { approvePermissions?: boolean; allowLocalTrust?: boolean } = {},
): Promise<MarketPlan> {
  return request<MarketPlan>('/api/market/plan', {
    method: 'POST',
    body: JSON.stringify({
      source_id: sourceId,
      name,
      version,
      approve_permissions: Boolean(options.approvePermissions),
      allow_local_trust: Boolean(options.allowLocalTrust),
    }),
    timeoutMs: 120_000,
  })
}

export function installMarketPlan(plan: MarketPlan): Promise<MarketInstallResult> {
  return request<MarketInstallResult>('/api/market/install', {
    method: 'POST',
    body: JSON.stringify({ plan }),
    timeoutMs: 180_000,
  })
}

export function switchMarketPlugin(body: {
  name: string
  enabled: boolean
  sourceId?: string
  version?: string
  approvePermissions?: boolean
  allowLocalTrust?: boolean
}): Promise<MarketInstallResult & { phase?: string }> {
  return request<MarketInstallResult & { phase?: string }>('/api/market/switch', {
    method: 'POST',
    body: JSON.stringify({
      name: body.name,
      enabled: body.enabled,
      source_id: body.sourceId ?? 'bundled',
      version: body.version ?? '',
      approve_permissions: Boolean(body.approvePermissions),
      allow_local_trust: Boolean(body.allowLocalTrust),
    }),
    timeoutMs: 180_000,
  })
}

export function rollbackMarketPlugin(name: string): Promise<MarketInstallResult> {
  return request<MarketInstallResult>('/api/market/rollback', {
    method: 'POST',
    body: JSON.stringify({ name }),
    timeoutMs: 60_000,
  })
}

export function removeMarketPlugin(name: string, deleteData = false): Promise<MarketInstallResult> {
  return request<MarketInstallResult>('/api/market/remove', {
    method: 'POST',
    body: JSON.stringify({ name, delete_data: deleteData }),
    timeoutMs: 60_000,
  })
}

export function marketIconUrl(name: string): string {
  return apiUrl(`/api/market/icon/${encodeURIComponent(name)}`)
}
