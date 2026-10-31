/** The one-roundtrip shelf read (Y1): `GET /api/discover/bootstrap`. */
import { request } from './http'
import type { McpCatalogEntry } from './endpoints'
import type { SkillSummary } from './types'
import type { MarketHome, MarketIndexBody, MarketInstalledRow, MarketSource } from './marketplace'
import type { ToolUsageView } from './usage'

/** One curated registry tier row; the full tier rides behind `?full=1`. */
export interface FeaturedEntry {
  id: string
  rank: number
  name: string
  publisher: string
  summary: string
  category: string
  transport: 'http' | 'stdio'
  install_hint: string
  docs: string
  icon: string
  why: string
  evidence?: string[]
}

export interface RegistryEntry {
  id: string
  name: string
  description: string
  category: string
  install_hint: string
  docs: string
  version: string
  published_at: string
  source: string
  curated_reason?: 'pick' | 'recent'
}

/** One of the two shelves that ship with the app; a preset is readable, not bought. */
export interface DiscoverPreset {
  id: string
  title: string
  kind: 'bundled' | 'mirror'
  url: string
  state: string
  count: number
}

export interface DiscoverBootstrap {
  skills: SkillSummary[]
  sources: MarketSource[]
  last_read: Record<string, string>
  last_error: Record<string, string>
  home: MarketHome
  index: MarketIndexBody | null
  catalog: McpCatalogEntry[]
  featured: FeaturedEntry[]
  curated: RegistryEntry[]
  registry_count: number
  presets: DiscoverPreset[]
  installed: MarketInstalledRow[]
  usage: ToolUsageView
}

export function getDiscoverBootstrap(): Promise<DiscoverBootstrap> {
  return request<DiscoverBootstrap>('/api/discover/bootstrap')
}

export interface DiscoverHit {
  id: string
  score: number
}

/** Y3 — intent search: the task a person types, answered from the committed index. */
export function searchDiscover(query: string, limit = 24): Promise<DiscoverHit[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  return request<{ query: string; entries: DiscoverHit[] }>(
    `/api/discover/search?${params.toString()}`,
  ).then((payload) => payload.entries)
}

export interface DryRunFinding {
  class: string
  severity: string
  file: string
  marker: string
}

export interface DryRunResult {
  verdict: 'checked-clean' | 'checked' | 'refused'
  findings: DryRunFinding[]
  mode: 'static'
}

/** Y2 — the rehearsal: scan one catalog entry before anything is downloaded. */
export function dryRunEntry(body: {
  name: string
  description?: string
  install_hint?: string
  spec?: string
}): Promise<DryRunResult> {
  return request<DryRunResult>('/api/discover/dry-run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
