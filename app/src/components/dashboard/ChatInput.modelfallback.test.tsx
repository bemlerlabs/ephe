// N9 — model chip fallback: when /api/model/providers returns no units,
// the chip merges the environment-scan findings (the mirror's `preferred` row
// leads, dedupe over the scrubbed triple); a click sets provider kind + model
// via setModelProvider.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChatInput, { buildScanEntries } from '@/components/dashboard/ChatInput'

const scanEnv = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api/environment', () => ({
  scanEnvironment: (...a: unknown[]) => scanEnv(...a),
}))

const apiMocks = vi.hoisted(() => ({
  getModelProviders: vi.fn(async () => ({
    active: { model: 'm1', offline_capable: false },
    providers: [] as unknown[],
    local_models: [],
    local_model_options: [],
  })),
  getSetupStatus: vi.fn(async () => ({ configured: true })),
  setModelProvider: vi.fn(async () => ({ active: { model: 'Sample-4-70' } })),
  transcribeAudio: vi.fn(async () => ''),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws' })),
  listFs: vi.fn(async () => ({
    path: '/tmp/ws',
    parent: null,
    home: '/tmp',
    workspace: '/tmp/ws',
    entries: [],
  })),
  listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
}))
vi.mock('@/lib/api', () => apiMocks)
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: Record<string, unknown>) =>
      typeof opts?.defaultValue === 'string' ? opts.defaultValue : key,
  }),
}))

const TOOLS = [
  {
    tool: 'sample',
    installed: true,
    config_path: '~/.example-tool/config.json',
    providers: ['https://api.example.test/v1?k=sk-secret'],
    models: ['Sample-4-70'],
    auth_present: true,
    // The mirror marks the row the product is built around; the chip ranks on
    // this flag and never on the tool name (see the decoupling test below).
    preferred: true,
  },
  {
    tool: 'opencode',
    installed: true,
    config_path: '~/.opencode.json',
    providers: ['http://127.0.0.1:11434'],
    models: ['gemma4:12b', 'gemma4:12b'],
    auth_present: true,
  },
  {
    tool: 'cursor',
    installed: true,
    config_path: '~/.cursor',
    providers: [],
    models: ['gpt-4o'],
    auth_present: false,
  },
]

describe('Modell-Chip-Fallback (N9)', () => {
  it('leere Provider-Tabelle → Scan-Eintraege erscheinen im Menu (die preferred-Zeile zuerst)', async () => {
    scanEnv.mockResolvedValue({ tools: TOOLS, summary: { installed: 2, with_models: [] } })
    render(<ChatInput onSend={() => {}} />)
    fireEvent.click(await screen.findByTestId('model-chip'))
    const sample = await screen.findByTestId('model-chip-option-sample:Sample-4-70')
    expect(sample.textContent).toContain('Sample · Sample-4-70')
    // Endpoint scrubbed: query parameters (keys) never show up in the label
    expect(sample.textContent).toContain('https://api.example.test/v1')
    expect(sample.textContent).not.toContain('sk-secret')
    expect(screen.getByTestId('model-chip-option-opencode:gemma4:12b')).toBeTruthy()
    // cursor without an endpoint: no entry
    expect(screen.queryByTestId('model-chip-option-cursor:gpt-4o')).toBeNull()
  })

  it('Klick auf die bevorzugte Option setzt Kind + Modell + gescrubbter Endpunkt', async () => {
    scanEnv.mockResolvedValue({ tools: TOOLS, summary: { installed: 2, with_models: [] } })
    render(<ChatInput onSend={() => {}} />)
    fireEvent.click(await screen.findByTestId('model-chip'))
    fireEvent.click(await screen.findByTestId('model-chip-option-sample:Sample-4-70'))
    await vi.waitFor(() =>
      expect(apiMocks.setModelProvider).toHaveBeenCalledWith(
        'openai_compatible',
        'Sample-4-70',
        'https://api.example.test/v1',
      ),
    )
  })

  it('buildScanEntries: Dedupe, die preferred-Zeile zuerst, Endpoint ueber Bruecke zum PUT', () => {
    const out = buildScanEntries(TOOLS as never)
    expect(out.map((e) => e.id)).toEqual(['sample:Sample-4-70', 'opencode:gemma4:12b'])
    expect(out[1]?.kind).toBe('custom_ollama')
    expect(out[0]?.endpoint).toBe('https://api.example.test/v1')
    expect(out[1]?.endpoint).toBe('http://127.0.0.1:11434')
  })

  // Decision (n19): the mirror's `preferred` flag decides the ranking; a tool
  // name decides nothing. A row spelled like the reference harness without the
  // flag does not lead. The label shows the reported name, first letter up.
  it('the preferred flag decides the order, a tool name does not', () => {
    const named = {
      tool: 'sample',
      installed: true,
      config_path: '~/.example-tool/config.json',
      providers: ['https://api.example.test/v1'],
      models: ['Sample-4-70'],
      auth_present: true,
    }
    const flagged = {
      tool: 'opencode',
      installed: true,
      config_path: '~/.opencode.json',
      providers: ['https://api.example.test/v2'],
      models: ['gemma4:12b'],
      auth_present: true,
      preferred: true,
    }
    const out = buildScanEntries([named, flagged] as never)
    expect(out.map((e) => e.id)).toEqual(['opencode:gemma4:12b', 'sample:Sample-4-70'])
    expect(out.map((e) => e.label)).toEqual(['Opencode · gemma4:12b', 'Sample · Sample-4-70'])
  })
})
