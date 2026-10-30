// W44 P1c — MCP settings tab: show the server list + save via PUT.
// The MCP core exists (GET/PUT /settings/mcp) but the SettingsPanel
// had no mcp entry. Pattern: SettingsPanel.skills.test.tsx.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mcpState = vi.hoisted(() => ({
  servers: ['http://localhost:3000/mcp'],
  saved: null as null | string[],
}))

const getMcpSettings = vi.fn(async () => ({
  servers: mcpState.servers,
  source: 'file',
  tools: ['tool_a'],
}))
const putMcpSettings = vi.fn(async (servers: string[]) => {
  mcpState.saved = servers
  mcpState.servers = servers
  return { servers, source: 'file', tools: ['tool_a'] }
})

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ provider: { type: 'local_ollama', model: 'gemma4:12b' } })),
  updateSettings: vi.fn(async () => ({})),
  healthCheck: vi.fn(async () => ({ ollama: true, models: [] })),
  getModelProviders: vi.fn(async () => ({
    active: { type: 'local_ollama', model: 'gemma4:12b' },
    providers: [],
    local_models: [],
    local_model_options: [],
  })),
  getMemoryStats: vi.fn(async () => ({ total: 0 })),
  getCapabilities: vi.fn(async () => ({
    subagent: { tools: [], tool_count: 9, max_iterations: 8, read_only: true },
    main_agent: { read_only: false, note: '' },
    mcp_sandbox: {
      platform: 'seatbelt',
      available: true,
      home_root: '/tmp/.ephe/mcp/homes',
      network_isolated: false,
      pid_isolated: false,
    },
  })),
  clearMemory: vi.fn(async () => ({ cleared: true })),
  getMobileQR: vi.fn(async () => ({
    url: '',
    qr_base64: '',
    mode: 'lan',
    is_public: false,
    requires_internet: false,
    lan_reachable: true,
    message: '',
  })),
  getMobileStatus: vi.fn(async () => ({ connected: false })),
  synthesizeSpeech: vi.fn(async () => ''),
  listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
  installSkill: vi.fn(async () => ({ installed: [], updated: [], skipped: [] })),
  installSkillFromUrl: vi.fn(async () => ({ installed: [], updated: [], skipped: [] })),
  disableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  enableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  deleteSkill: vi.fn(async () => ({ deleted: '' })),
  getImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  getPackIndex: vi.fn(async () => ({ version: 1, packs: [] })),
  exportPackUrl: vi.fn(() => '/api/skills/export-pack/core'),
  getSchedulePresets: vi.fn(async () => ({ presets: [] })),
  getScheduleResults: vi.fn(async () => ({ results: [] })),
  runScheduleJob: vi.fn(async () => ({
    job_id: '',
    task: '',
    executed_at: '',
    result: '',
    error: null,
  })),
  listMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  importMemory: vi.fn(async () => ({ imported: 0, total: 0 })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  getMcpSettings: (...a: unknown[]) => getMcpSettings(...(a as [])),
  putMcpSettings: (...a: unknown[]) => putMcpSettings(...(a as [string[]])),
  probeMcpHealth: vi.fn(async () => ({
    servers: [
      {
        spec: 'http://localhost:3000/mcp',
        status: 'ok',
        tool_count: 2,
        transport: 'http',
        latency_ms: 12,
        error: null,
      },
    ],
  })),
  getMcpCatalog: vi.fn(async () => ({
    entries: [
      {
        id: 'mcp-everything',
        name: 'Everything Server',
        description: 'Test server',
        category: 'testing',
        install_hint: 'npx -y @modelcontextprotocol/server-everything (stdio)',
        docs: 'https://example.com/mcp',
      },
    ],
  })),
  artifactExportUrl: vi.fn(() => '/api/artifacts/export'),
  saveImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  testImageEndpoint: vi.fn(async () => ({
    reachable: false,
    models: [],
    base_url_used: '',
    detail: '',
  })),
  getVoiceSettings: vi.fn(async () => ({
    enabled: true,
    voice: '',
    speed: 1,
    piper_available: false,
    installed_piper_voices: [],
  })),
  saveVoiceSettings: vi.fn(async () => ({
    enabled: true,
    voice: '',
    speed: 1,
    piper_available: false,
    installed_piper_voices: [],
  })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  createSchedule: vi.fn(async () => ({ job_id: 'x', message: '' })),
  deleteSchedule: vi.fn(async () => ({ status: 'ok', job_id: 'x' })),
  getTasks: vi.fn(async () => []),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getPersona: vi.fn(async () => ({})),
  updatePersona: vi.fn(async () => ({})),
  fileUrl: (p: string) => p,
}))

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => (
    <div data-testid="markdown">{String(children)}</div>
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: React.ReactNode }) => <pre>{children}</pre>,
}))
// Partial mock: the register's rows read `cn` from this module, so the real
// exports come back and only the clock is pinned.
vi.mock('@/lib/utils', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils')>()),
  formatTime: () => '12:00',
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  mcpState.saved = null
})

describe('SettingsPanel MCP-Tab (W44 P1c + E3c)', () => {
  it('zeigt die geladenen MCP-Server im mcp-Tab', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="mcp" />)
    const row = await screen.findByTestId('mcp-server-0')
    // The spec value sits in the <input value=…> (no textContent) — check the field.
    const input = row.querySelector('input') as HTMLInputElement
    expect(input.value).toBe('http://localhost:3000/mcp')
  })

  it('Save ruft putMcpSettings mit der Server-Liste', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="mcp" />)
    await screen.findByTestId('mcp-server-0')
    fireEvent.click(await screen.findByTestId('mcp-save'))
    await waitFor(() => expect(putMcpSettings).toHaveBeenCalled())
    expect(mcpState.saved).toContain('http://localhost:3000/mcp')
  })

  it('E3c: Health-Dot + Detailzeile nach der Probe', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="mcp" />)
    await screen.findByTestId('mcp-server-0')
    // Before the probe: dot grey (unknown)
    expect(screen.getByTestId('mcp-health-dot-0').className).toContain('bg-mist/40')
    fireEvent.click(screen.getByTestId('mcp-health-button'))
    await waitFor(() =>
      expect(screen.getByTestId('mcp-health-dot-0').className).toContain('bg-status-success'),
    )
    // Identity-t mock: the detail line shows the i18n key (no interpolation)
    expect(screen.getByTestId('mcp-health-detail-0').textContent).toContain('settings.mcpHealthOk')
  })
})
