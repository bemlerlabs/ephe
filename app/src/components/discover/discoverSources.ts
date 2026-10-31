/** What `/discover` loads: the bootstrap frame plus the two slower reads. */
import { getDiscoverBootstrap, getMcpSettings, probeMcpHealth } from '@/lib/api'
import type { DiscoverSources } from './discoverModel'

/** The bootstrap frame carries everything but the slow health probes. */
export async function loadSources(): Promise<{ sources: DiscoverSources; failed: string[] }> {
  const [boot, mcp, health] = await Promise.all([
    getDiscoverBootstrap().catch(() => null),
    getMcpSettings().catch(() => null),
    probeMcpHealth().catch(() => null),
  ])
  const failed: string[] = []
  const note = (key: string, ok: boolean) => {
    if (!ok) failed.push(key)
  }
  note('skills', boot !== null)
  note('connectors', boot !== null)
  note('addons', boot !== null)
  return {
    sources: {
      skills: boot?.skills ?? [],
      mcp,
      health: health?.servers ?? [],
      catalog: boot?.catalog ?? [],
      featured: boot?.featured ?? [],
      registry: boot?.curated ?? [],
      registryCount: boot?.registry_count ?? 0,
      presets: boot?.presets ?? [],
      home: boot?.home ?? null,
      index: boot?.index ?? null,
      installed: boot?.installed ?? [],
      usage: boot?.usage ?? null,
    },
    failed,
  }
}
