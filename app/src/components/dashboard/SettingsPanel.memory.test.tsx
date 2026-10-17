/**
 * R2-A: the Settings section now only tunes thresholds and shows the scope.
 * The list itself (real document id on delete, metadata on the row, reload on
 * the real path) moved to the Memory page (product title "What stays") and
 * its checks live on there, src/pages/MemoryPage.test.tsx. What stays here is
 * the single sentence this section can still tell on its own: which collection
 * is actually read, and which store the holdings belong to.
 */
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

const api = vi.hoisted(() => ({
  searchMemory: vi.fn(),
  listMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  updateMemoryEntry: vi.fn(async () => ({ updated: '' })),
  getMemoryStats: vi.fn(async () => ({ total: 7, scope: 'ephe_memory_3f2a1b90c4d5' })),
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
  clearMemory: vi.fn(async () => ({ cleared: true })),
  getMobileQR: vi.fn(async () => ({
    url: '',
    qr_base64: '',
    mode: 'local',
    is_public: false,
    requires_internet: false,
    lan_reachable: true,
    message: '',
  })),
  getMobileStatus: vi.fn(async () => ({ connected: false })),
  listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
  installSkill: vi.fn(async () => ({ installed: [], updated: [], skipped: [] })),
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
  getSchedulePresets: vi.fn(async () => ({ presets: [] })),
  getScheduleResults: vi.fn(async () => ({ results: [] })),
  runScheduleJob: vi.fn(async () => ({
    job_id: '',
    task: '',
    executed_at: '',
    result: '',
    error: null,
  })),
  importMemory: vi.fn(async () => ({ imported: 0, total: 0 })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
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
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  createSchedule: vi.fn(async () => ({ job_id: 'x', message: '' })),
  deleteSchedule: vi.fn(async () => ({ status: 'ok', job_id: 'x' })),
  getTasks: vi.fn(async () => []),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  synthesizeSpeech: vi.fn(async () => '/audio/tts.mp3'),
  fileUrl: (p: string) => p,
  ...api,
}))

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  vi.clearAllMocks()
  api.getMemoryStats.mockResolvedValue({ total: 7, scope: 'ephe_memory_3f2a1b90c4d5' })
})

describe('SettingsPanel Memory — Regler und Umfang, nicht der Bestand', () => {
  it('GIVEN stats.scope WHEN Memory lädt THEN ist die Collection sichtbar', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="memory" />)
    const scope = await screen.findByTestId('settings-memory-scope')
    expect(scope).toHaveTextContent('ephe_memory_3f2a1b90c4d5')
  })

  it('führt den Bestand auf seine Seite und listet ihn nicht selbst', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="memory" />)
    const link = await screen.findByTestId('memory-open-page')
    expect(link.querySelector('a')?.getAttribute('href')).toBe('#/memory')
    expect(screen.queryByTestId('settings-memory-search')).toBeNull()
  })
})
