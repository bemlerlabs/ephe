// W3b — Skills tab: pack export link, file install and URL install (pins).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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

const installSkill = vi.fn(async (_f: unknown, _force?: boolean) => ({
  installed: [{ name: 'a', version: '1', trigger: '/a' }],
  updated: [],
  skipped: [],
}))
const installSkillFromUrl = vi.fn(async (_url: string, _force?: boolean) => ({
  installed: [{ name: 'b', version: '1', trigger: '/b' }],
  updated: [],
  skipped: [],
}))
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
  listSkills: vi.fn(async () => ({
    skills: [{ name: 'alpha', description: 'd', trigger: '/alpha' }],
    total: 1,
  })),
  installSkill: (...args: unknown[]) => installSkill(...(args as [File, boolean?])),
  installSkillFromUrl: (...args: unknown[]) => installSkillFromUrl(...(args as [string, boolean?])),
  disableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  enableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  deleteSkill: vi.fn(async () => ({ deleted: '' })),
  getImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  getPackIndex: vi.fn(async () => ({
    version: 1,
    packs: [
      {
        id: 'core',
        title: 'Core',
        description: 'Grundpack',
        skills: [{ name: 'alpha', installed: true, trigger: '/alpha' }],
        complete: true,
      },
    ],
  })),
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
  getTelegramStatus: vi.fn(async () => ({
    token_configured: false,
    token_masked: null,
    running: false,
    bot_username: null,
    paired_count: 0,
    session_count: 0,
    last_error: null,
  })),
  saveTelegramToken: vi.fn(async () => ({ mode: 'file_0600', masked: '…abcd (47 Zeichen)' })),
  deleteTelegramToken: vi.fn(async () => ({ ok: true })),
  startTelegramChannel: vi.fn(async () => ({ running: true })),
  stopTelegramChannel: vi.fn(async () => ({ running: false })),
  createTelegramPairing: vi.fn(async () => ({
    deep_link: 'x',
    qr_base64: 'QUJD',
    issued_at: 1,
    expires_at: 601,
    ttl_seconds: 600,
  })),
  listTelegramDevices: vi.fn(async () => []),
  revokeTelegramDevice: vi.fn(async () => ({ ok: true })),
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

import SettingsPanel from './SettingsPanel'

beforeEach(() => localStorage.clear())

describe('SettingsPanel Skills-Tab (W3b)', () => {
  it('Pack-Export-Link nutzt exportPackUrl (data-testid pack-export-core)', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="skills" />)
    const link = await screen.findByTestId('pack-export-core')
    expect(link).toHaveAttribute('href', '/api/skills/export-pack/core')
  })
})
