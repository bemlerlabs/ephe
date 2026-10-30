/**
 * The page is where the one bootstrap frame meets the grid, so the proof is about
 * what the user can act on: the counts in the tabs, the bento of our own items,
 * the bench drawn from the audit log, and the one write a click is allowed to make.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      `${key}${opts ? `:${JSON.stringify(opts)}` : ''}`,
  }),
}))

const api = vi.hoisted(() => ({
  getDiscoverBootstrap: vi.fn(),
  getMcpSettings: vi.fn(),
  probeMcpHealth: vi.fn(),
  enableSkill: vi.fn(),
  disableSkill: vi.fn(),
  putMcpSettings: vi.fn(),
  setPluginEnabled: vi.fn(),
  planMarketInstall: vi.fn(),
  installMarketPlan: vi.fn(),
  dryRunEntry: vi.fn(),
  searchDiscover: vi.fn(),
  declareMcpEnv: vi.fn(),
  getSecretStatus: vi.fn(),
  putSecret: vi.fn(),
  removeSecret: vi.fn(),
  addMarketSource: vi.fn(),
  removeMarketSource: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

import DiscoverPage from './DiscoverPage'

const emptyIndex = { format: 1, name: 'c', owner: { name: 'Ephe' }, plugins: [] }

function seed() {
  api.getDiscoverBootstrap.mockResolvedValue({
    skills: [{ name: 'pdf', trigger: 'document', description: 'Reads PDFs', is_builtin: true }],
    sources: [
      { id: 'main', title: 'Main', kind: 'https', url: 'u', trust: 'signed', removable: false },
    ],
    last_read: {},
    last_error: {},
    home: {
      sources: [
        { id: 'main', title: 'Main', kind: 'https', url: 'u', trust: 'signed', removable: false },
      ],
      last_read: {},
      last_error: {},
    },
    index: emptyIndex,
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
    curated: [
      {
        id: 'web-search',
        name: 'Web Search',
        description: 'Search the open web',
        category: 'web',
        install_hint: 'npx -y web-search (stdio)',
        docs: 'https://registry.example/v0/servers/web-search',
        version: '1.0.0',
        published_at: '2026-10-01T00:00:00Z',
        source: 'registry',
        curated_reason: 'recent',
        required_env: [{ name: 'WEB_SEARCH_KEY', secret: true }],
      },
    ],
    registry_count: 6606,
    presets: [
      { id: 'ephe-index', title: 'Ephe', kind: 'bundled', url: '', state: 'bundled', count: 2 },
      {
        id: 'mcp-registry',
        title: 'Registry',
        kind: 'mirror',
        url: 'https://registry.example/v0/servers',
        state: 'mirrored weekly',
        count: 6606,
      },
    ],
    installed: [],
    usage: {
      tools: [{ tool: 'pdf', calls: 12, ok: 10, errors: 2, blocked: 1, last_ts: 'ts' }],
      population: 12,
      window: 500,
    },
  })
  api.getMcpSettings.mockResolvedValue({ servers: ['npx:mcp-weather'], source: 'file', tools: [] })
  api.probeMcpHealth.mockResolvedValue({
    servers: [
      {
        spec: 'npx:mcp-weather',
        status: 'ok',
        tool_count: 3,
        transport: 'stdio',
        latency_ms: 40,
        error: null,
      },
    ],
  })
}

const render_ = () =>
  render(
    <MemoryRouter initialEntries={['/discover']}>
      <DiscoverPage />
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  seed()
  api.enableSkill.mockResolvedValue({ name: 'pdf', disabled: false })
  api.disableSkill.mockResolvedValue({ name: 'pdf', disabled: true })
  api.putMcpSettings.mockResolvedValue({ servers: [], source: 'file', tools: [] })
  api.getSecretStatus.mockResolvedValue([{ name: 'WEB_SEARCH_KEY', present: false, mode: '' }])
  api.putSecret.mockResolvedValue({ name: 'WEB_SEARCH_KEY', present: true, mode: 'keyring' })
  api.removeSecret.mockResolvedValue({ name: 'WEB_SEARCH_KEY', present: false, mode: '' })
  api.declareMcpEnv.mockResolvedValue({ servers: {}, declared: ['WEB_SEARCH_KEY'] })
  api.addMarketSource.mockResolvedValue({ source: { id: 'src-1', title: 'Mine' } })
  api.removeMarketSource.mockResolvedValue({ removed: true })
})

describe('discover page', () => {
  it('shows the featured pick, the counted tabs, the bento and the measured bench', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-sections')).toBeTruthy())
    expect(screen.getByTestId('discover-hero')).toBeTruthy()
    expect(screen.getByTestId('discover-bento')).toBeTruthy()
    expect(screen.getByTestId('discover-tab-all').textContent).toContain('4')
    expect(screen.getByTestId('discover-tab-connector').textContent).toContain('3')
    expect(screen.getByTestId('discover-card-skill:pdf')).toBeTruthy()
    expect(
      screen.getByTestId('discover-badge-connector:registry:web-search').textContent,
    ).toContain('discover.badge.recent')
    expect(screen.getByTestId('discover-bench-row-pdf').textContent).toContain('12')
    expect(screen.getByTestId('discover-bench-reach').textContent).toContain('12')
  })

  it('adds a suggested connector by rewriting the server list', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-card-connector:maps')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-act-connector:maps'))
    await waitFor(() => expect(api.putMcpSettings).toHaveBeenCalledTimes(1))
    expect(api.putMcpSettings.mock.calls[0]?.[0]).toEqual(['npx:mcp-weather', 'npx:mcp-maps'])
    expect(screen.getByTestId('discover-notice').textContent).toContain('discover.added')
  })

  it('attaches a curated registry connector through its launch line', async () => {
    render_()
    await waitFor(() =>
      expect(screen.getByTestId('discover-card-connector:registry:web-search')).toBeTruthy(),
    )
    fireEvent.click(screen.getByTestId('discover-act-connector:registry:web-search'))
    await waitFor(() => expect(api.putMcpSettings).toHaveBeenCalledTimes(1))
    expect(api.putMcpSettings.mock.calls[0]?.[0]).toEqual([
      'npx:mcp-weather',
      'stdio:npx -y web-search',
    ])
  })

  it('opens the centred detail surface from a card', async () => {
    render_()
    await waitFor(() =>
      expect(screen.getByTestId('discover-detail-open-connector:registry:web-search')).toBeTruthy(),
    )
    fireEvent.click(screen.getByTestId('discover-detail-open-connector:registry:web-search'))
    await waitFor(() => expect(screen.getByTestId('discover-detail-summary')).toBeTruthy())
    expect(screen.getByTestId('discover-detail-install').textContent).toContain('npx -y web-search')
    expect(screen.getByTestId('discover-detail-permissions').textContent).toContain(
      'discover.detailPermissionsReview',
    )
  })

  it('rehearses a catalog entry inside the detail surface', async () => {
    api.dryRunEntry.mockResolvedValue({ verdict: 'checked-clean', findings: [], mode: 'static' })
    render_()
    await waitFor(() =>
      expect(screen.getByTestId('discover-detail-open-connector:registry:web-search')).toBeTruthy(),
    )
    fireEvent.click(screen.getByTestId('discover-detail-open-connector:registry:web-search'))
    await waitFor(() => expect(screen.getByTestId('discover-detail-rehearse')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-detail-rehearse'))
    await waitFor(() => expect(api.dryRunEntry).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('discover-detail-verdict').textContent).toContain(
      'discover.verdict.checked-clean',
    )
  })

  it('takes a required credential in the sheet and never shows it back', async () => {
    render_()
    await waitFor(() =>
      expect(screen.getByTestId('discover-detail-open-connector:registry:web-search')).toBeTruthy(),
    )
    fireEvent.click(screen.getByTestId('discover-detail-open-connector:registry:web-search'))
    await waitFor(() => expect(screen.getByTestId('discover-credentials')).toBeTruthy())
    expect(screen.getByTestId('discover-credential-state-WEB_SEARCH_KEY').textContent).toContain(
      'discover.credentialMissing',
    )
    fireEvent.change(screen.getByTestId('discover-credential-input-WEB_SEARCH_KEY'), {
      target: { value: 'sk-test' },
    })
    fireEvent.click(screen.getByTestId('discover-credential-save-WEB_SEARCH_KEY'))
    await waitFor(() => expect(api.putSecret).toHaveBeenCalledWith('WEB_SEARCH_KEY', 'sk-test'))
    await waitFor(() =>
      expect(screen.getByTestId('discover-credential-state-WEB_SEARCH_KEY').textContent).toContain(
        'discover.credentialStored.keyring',
      ),
    )
    expect(screen.getByTestId('discover-credential-input-WEB_SEARCH_KEY')).toHaveProperty(
      'value',
      '',
    )
  })

  it('names the two preset shelves with their counts', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-sources')).toBeTruthy())
    expect(screen.getByTestId('discover-preset-ephe-index').textContent).toContain('2')
    expect(screen.getByTestId('discover-preset-mcp-registry').textContent).toContain('6,606')
  })

  it('adds a user source through the validated door', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-source-add')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-source-add'))
    fireEvent.change(screen.getByTestId('discover-source-title'), {
      target: { value: 'My index' },
    })
    fireEvent.change(screen.getByTestId('discover-source-url'), {
      target: { value: 'https://example.com/index.json' },
    })
    fireEvent.click(screen.getByTestId('discover-source-save'))
    await waitFor(() => expect(api.addMarketSource).toHaveBeenCalledTimes(1))
    expect(api.addMarketSource.mock.calls[0]?.[0]).toEqual({
      kind: 'https',
      title: 'My index',
      url: 'https://example.com/index.json',
    })
  })

  it('switches a skill off through its own route', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-card-skill:pdf')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-act-skill:pdf'))
    await waitFor(() => expect(api.disableSkill).toHaveBeenCalledWith('pdf'))
  })

  it('names the lists that did not answer', async () => {
    api.getDiscoverBootstrap.mockRejectedValue(new Error('offline'))
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-failed')).toBeTruthy())
    expect(screen.getByTestId('discover-fail-addons')).toBeTruthy()
  })

  it('finds a task entry whose words the card never carries', async () => {
    api.searchDiscover.mockResolvedValue([{ id: 'web-search', score: -3 }])
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-search')).toBeTruthy())
    fireEvent.change(screen.getByTestId('discover-search'), {
      target: { value: 'Nachricht senden' },
    })
    await waitFor(() => expect(api.searchDiscover).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.getByTestId('discover-card-connector:registry:web-search')).toBeTruthy(),
    )
    expect(screen.getByTestId('discover-result-count').textContent).toContain('1')
  })
})
