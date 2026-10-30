/** The one-roundtrip shelf read (Y1): `GET /api/discover/bootstrap`. */
import { request } from './http'
import type { McpCatalogEntry } from './endpoints'
import type { SkillSummary } from './types'
import type { MarketHome, MarketIndexBody, MarketInstalledRow, MarketSource } from './marketplace'
import type { ToolUsageView } from './usage'

/** One curated registry tier row; the full tier rides behind `?full=1`. */
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

export interface DiscoverBootstrap {
  skills: SkillSummary[]
  sources: MarketSource[]
  last_read: Record<string, string>
  last_error: Record<string, string>
  home: MarketHome
  index: MarketIndexBody | null
  catalog: McpCatalogEntry[]
  curated: RegistryEntry[]
  registry_count: number
  installed: MarketInstalledRow[]
  usage: ToolUsageView
}

export function getDiscoverBootstrap(): Promise<DiscoverBootstrap> {
  return request<DiscoverBootstrap>('/api/discover/bootstrap')
}
