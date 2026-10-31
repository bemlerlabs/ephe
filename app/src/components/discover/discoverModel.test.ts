/**
 * The mapping is where a wrong number would land, so it is tested on its own:
 * a card may only carry what the endpoint sent, and a filter may only narrow.
 */
import { describe, expect, it } from 'vitest'
import {
  buildItems,
  categoryFacets,
  countByTab,
  facetValues,
  filterItems,
  heroOf,
  prettyName,
  publisherOf,
  specName,
  type DiscoverSources,
} from './discoverModel'

const base: DiscoverSources = {
  skills: [],
  mcp: null,
  health: [],
  catalog: [],
  featured: [],
  registry: [],
  registryCount: 0,
  presets: [],
  home: null,
  index: null,
  installed: [],
  usage: null,
}

describe('discover spec name', () => {
  it('reads the name out of a launch spec', () => {
    expect(specName('npx:@modelcontextprotocol/server-filesystem')).toBe('server-filesystem')
    expect(specName('uvx:mcp-search@1.2')).toBe('mcp-search')
    expect(specName('plain')).toBe('plain')
  })
})

describe('discover build', () => {
  it('keeps the three kinds apart and carries only measured facts', () => {
    const items = buildItems({
      ...base,
      skills: [
        {
          name: 'pdf',
          trigger: 'document',
          description: 'Reads PDFs',
          is_builtin: true,
          disabled: true,
        },
      ],
      mcp: { servers: ['npx:mcp-weather'], source: 'file', tools: [] },
      health: [
        {
          spec: 'npx:mcp-weather',
          status: 'ok',
          tool_count: 3,
          transport: 'stdio',
          latency_ms: 42,
          error: null,
        },
      ],
      catalog: [
        {
          id: 'maps',
          name: 'maps',
          description: 'Karten',
          description_en: 'Maps',
          category: 'geo',
          spec: 'npx:mcp-maps',
        },
      ],
      index: {
        format: 1,
        name: 'catalog',
        owner: { name: 'Ephe' },
        plugins: [
          {
            name: 'spreadsheets',
            displayName: 'Spreadsheets',
            description: { en: 'Turns tables' },
            publisher: { name: 'Ephe', verified: true },
            trust: 'signed',
            categories: ['office'],
            versions: [
              {
                version: '1.1.0',
                publishTimestamp: 0,
                source: { type: 'https', url: 'u', sha256: 'd' },
                engines: { ephe: '>=0.1' },
                permissions: {},
                components: [],
              },
            ],
          },
        ],
      },
      installed: [
        {
          name: 'spreadsheets',
          version: '1.0.0',
          description: 'Turns tables',
          enabled: false,
          origin: 'bundled',
          components: [],
          permissions: { tool_families: [], data_roots: [] },
        },
      ],
      usage: {
        tools: [{ tool: 'pdf', calls: 12, ok: 10, errors: 2, blocked: 1, last_ts: 't' }],
        population: 12,
        window: 500,
      },
    })

    const pdf = items.find((one) => one.id === 'skill:pdf')
    expect(pdf).toMatchObject({
      kind: 'skill',
      installed: true,
      enabled: false,
      calls: 12,
      origin: 'bundled',
    })

    const weather = items.find((one) => one.id === 'connector:mcp-weather')
    expect(weather).toMatchObject({
      installed: true,
      enabled: true,
      toolCount: 3,
      latencyMs: 42,
      spec: 'npx:mcp-weather',
    })

    // A catalog entry the health probe never saw stays a suggestion.
    const maps = items.find((one) => one.id === 'connector:maps')
    expect(maps).toMatchObject({ installed: false, enabled: false, spec: 'npx:mcp-maps' })

    // The version on the card is the one the index published.
    expect(items.find((one) => one.id === 'plugin:spreadsheets')).toMatchObject({
      installed: true,
      enabled: false,
      version: '1.1.0',
      origin: 'Ephe',
    })
    expect(countByTab(items)).toEqual({ all: 4, skill: 1, connector: 2, plugin: 1 })
  })

  it('offers only facets the items carry', () => {
    const items = buildItems({
      ...base,
      catalog: [{ id: 'a', name: 'a', description: '', category: 'geo' }],
    })
    expect(facetValues(items, (one) => one.categories)).toEqual(['geo'])
    expect(facetValues(items, (one) => [one.origin])).toEqual(['catalog'])
  })
})

describe('discover featured tier', () => {
  const linear = {
    id: 'featured-linear',
    rank: 12,
    name: 'Linear',
    publisher: 'Linear',
    summary: 'Issues and projects as tools',
    category: 'productivity',
    transport: 'http' as const,
    install_hint: 'https://mcp.linear.app/mcp (streamable-http)',
    docs: 'https://linear.app/docs',
    icon: 'linear',
    why: 'Official Linear endpoint',
    evidence: ['https://linear.app/docs/mcp'],
  }
  const legacy = {
    id: 'app-linear-linear',
    name: 'app.linear/linear',
    description: 'Older SSE endpoint',
    category: 'productivity',
    install_hint: 'https://mcp.linear.app/sse (sse)',
    docs: '',
    version: '1',
    published_at: '',
    source: 'registry',
  }

  it('lists one product once and ranks it into the hero', () => {
    const items = buildItems({ ...base, featured: [linear], registry: [legacy] })
    const row = items.find((one) => one.id === 'connector:featured:featured-linear')
    expect(row).toMatchObject({
      kind: 'connector',
      origin: 'featured',
      featured: 12,
      icon: '/api/discover/icon/linear',
      why: 'Official Linear endpoint',
      spec: 'https://mcp.linear.app/mcp',
      docs: 'https://linear.app/docs',
      sources: ['https://linear.app/docs/mcp'],
    })
    expect(items.some((one) => one.id === 'connector:registry:app-linear-linear')).toBe(false)
    expect(heroOf(items)?.id).toBe('connector:featured:featured-linear')
  })

  it('reads an attached featured endpoint from the machine state', () => {
    const items = buildItems({
      ...base,
      featured: [linear],
      mcp: { servers: ['https://mcp.linear.app/mcp'], source: 'file', tools: [] },
      health: [
        {
          spec: 'https://mcp.linear.app/mcp',
          status: 'ok',
          tool_count: 4,
          transport: 'http',
          latency_ms: 30,
          error: null,
        },
      ],
    })
    expect(items[0]).toMatchObject({ installed: true, enabled: true })
  })
})

describe('discover names', () => {
  it('reads a registry id as a name and keeps its namespace', () => {
    expect(prettyName('com.ainetcafe/netcafe-memory')).toBe('Netcafe Memory')
    expect(prettyName('ai.takara/miru')).toBe('Miru')
    expect(prettyName('Memory Server')).toBe('Memory Server')
    expect(publisherOf('ai.takara/miru')).toBe('ai.takara')
    expect(publisherOf('Filesystem Server')).toBeUndefined()
  })

  it('orders subjects by the shelf order, not the alphabet', () => {
    const items = buildItems({
      ...base,
      skills: [{ name: 'pdf', trigger: 'document', description: '' }],
      catalog: [{ id: 'a', name: 'a', description: '', category: 'web' }],
      registry: [
        {
          id: 'r',
          name: 'ai.takara/miru',
          description: '',
          category: 'code',
          install_hint: 'npx -y miru',
          docs: '',
          version: '1',
          published_at: '',
          source: 'registry',
        },
      ],
    })
    expect(categoryFacets(items)).toEqual(['skills', 'code', 'web'])
    expect(items.find((one) => one.id === 'connector:registry:r')?.title).toBe('Miru')
  })
})

describe('discover query', () => {
  const items = buildItems({
    ...base,
    skills: [
      { name: 'pdf', trigger: 'document', description: 'Reads PDFs' },
      { name: 'maps', trigger: 'geo', description: 'Finds places' },
    ],
  })

  it('narrows by tab, chip and word', () => {
    expect(
      filterItems(items, { tab: 'skill', query: '', category: null, origin: null }),
    ).toHaveLength(2)
    expect(
      filterItems(items, { tab: 'plugin', query: '', category: null, origin: null }),
    ).toHaveLength(0)
    expect(
      filterItems(items, { tab: 'all', query: 'place', category: null, origin: null }).map(
        (one) => one.name,
      ),
    ).toEqual(['maps'])
    expect(
      filterItems(items, { tab: 'all', query: '', category: 'skills', origin: null }),
    ).toHaveLength(2)
    expect(
      filterItems(items, { tab: 'all', query: '', category: null, origin: 'local' }),
    ).toHaveLength(2)
  })

  it('presents an installed item before a suggestion', () => {
    expect(heroOf(items)?.id).toBe('skill:pdf')
    expect(heroOf([])).toBeNull()
  })
})
