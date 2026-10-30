/**
 * The page is where the seven loads meet the grid, so the proof is about what the
 * user can act on: the counts in the tabs, the bench drawn from the audit log, and
 * the one write a click is allowed to make.
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
  listSkills: vi.fn(),
  getMcpSettings: vi.fn(),
  probeMcpHealth: vi.fn(),
  getMcpCatalog: vi.fn(),
  getMarketHome: vi.fn(),
  getMarketIndex: vi.fn(),
  getMarketInstalled: vi.fn(),
  getToolUsage: vi.fn(),
  enableSkill: vi.fn(),
  disableSkill: vi.fn(),
  putMcpSettings: vi.fn(),
  setPluginEnabled: vi.fn(),
  planMarketInstall: vi.fn(),
  installMarketPlan: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

import DiscoverPage from './DiscoverPage'

const emptyIndex = { format: 1, name: 'c', owner: { name: 'Ephe' }, plugins: [] }

function seed() {
  api.listSkills.mockResolvedValue({
    skills: [{ name: 'pdf', trigger: 'document', description: 'Reads PDFs', is_builtin: true }],
    total: 1,
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
  api.getMcpCatalog.mockResolvedValue({
    entries: [
      {
        id: 'maps',
        name: 'maps',
        description: 'Karten',
        description_en: 'Maps',
        category: 'geo',
        spec: 'npx:mcp-maps',
      },
    ],
  })
  api.getMarketHome.mockResolvedValue({
    sources: [
      { id: 'main', title: 'Main', kind: 'https', url: 'u', trust: 'signed', removable: false },
    ],
    last_read: {},
    last_error: {},
  })
  api.getMarketIndex.mockResolvedValue({
    status: 'ok',
    source: { id: 'main' },
    index: emptyIndex,
    error: '',
  })
  api.getMarketInstalled.mockResolvedValue({ plugins: [] })
  api.getToolUsage.mockResolvedValue({
    tools: [{ tool: 'pdf', calls: 12, ok: 10, errors: 2, blocked: 1, last_ts: 'ts' }],
    population: 12,
    window: 500,
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
})

describe('discover page', () => {
  it('shows the band, the counted tabs and the measured bench', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-grid')).toBeTruthy())
    expect(screen.getByTestId('discover-band')).toBeTruthy()
    expect(screen.getByTestId('discover-tab-all').textContent).toContain('3')
    expect(screen.getByTestId('discover-tab-connector').textContent).toContain('2')
    expect(screen.getByTestId('discover-card-skill:pdf')).toBeTruthy()
    expect(screen.getByTestId('discover-bench-row-pdf').textContent).toContain('12')
    expect(screen.getByTestId('discover-bench-reach').textContent).toContain('12')
    // One card is presented large, and it is the one already on the machine.
    expect(screen.getByTestId('discover-card-skill:pdf').getAttribute('data-hero')).toBe('true')
  })

  it('adds a suggested connector by rewriting the server list', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-card-connector:maps')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-act-connector:maps'))
    await waitFor(() => expect(api.putMcpSettings).toHaveBeenCalledTimes(1))
    expect(api.putMcpSettings.mock.calls[0]?.[0]).toEqual(['npx:mcp-weather', 'npx:mcp-maps'])
    expect(screen.getByTestId('discover-notice').textContent).toContain('discover.added')
  })

  it('switches a skill off through its own route', async () => {
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-card-skill:pdf')).toBeTruthy())
    fireEvent.click(screen.getByTestId('discover-act-skill:pdf'))
    await waitFor(() => expect(api.disableSkill).toHaveBeenCalledWith('pdf'))
  })

  it('names the lists that did not answer', async () => {
    api.getMarketIndex.mockRejectedValue(new Error('offline'))
    render_()
    await waitFor(() => expect(screen.getByTestId('discover-failed')).toBeTruthy())
    expect(screen.getByTestId('discover-fail-addons')).toBeTruthy()
  })
})
