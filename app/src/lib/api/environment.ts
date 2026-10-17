/**
 * Environment Mirror — opt-in scan of the agent tools already installed (B-wave B2/B3).
 *
 * POST /api/environment/scan reads the configs of known tools in the home
 * directory (read-only, secret-free). Deliberately NOT a GET: the scan is
 * privacy-relevant and it runs only on an explicit user click.
 */
import { BASE_URL, LAN_TOKEN } from './http'

export interface MirrorTool {
  tool: string
  installed: boolean
  config_path: string
  providers: string[]
  models: string[]
  auth_present: boolean
  /** Models carrying a Free suffix ('-free'/':free'), or every local Ollama model. */
  free_models?: string[]
  /** The models the tool REALLY used last (its own session DB), newest first. */
  last_used?: string[]
  /** Model → real API endpoint from the provider catalog (models.dev 'api'). */
  model_endpoints?: Record<string, string>
  /** The row the product is built around (its own reference harness) — the model
   *  chip lists its entries first. Comes from the mirror; never inferred from the
   *  tool's name here. */
  preferred?: boolean
}

export interface EnvironmentScanResponse {
  tools: MirrorTool[]
  summary: { installed: number; with_models: string[] }
}

export async function scanEnvironment(): Promise<EnvironmentScanResponse> {
  const headers: Record<string, string> = {}
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const res = await fetch(`${BASE_URL}/api/environment/scan`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return (await res.json()) as EnvironmentScanResponse
}
