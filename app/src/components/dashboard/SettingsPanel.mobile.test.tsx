// P2-1/Mobile: the header QR button opens Settings straight on the Mobile tab (initialTab).
// The fix: SettingsPanel sets activeTab = initialTab when opening → the QR renders without a manual tab click.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

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
    url: 'http://x/mobile.html',
    qr_base64: 'QUJD',
    mode: 'lan',
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
  listMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  importMemory: vi.fn(async () => ({ imported: 0, total: 0 })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
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
    deep_link: 'https://t.me/ephe_bot?start=abc',
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

  listSchedules: vi.fn(async () => ({ jobs: [] })),
  createSchedule: vi.fn(async () => ({ job_id: 'x', message: '' })),
  deleteSchedule: vi.fn(async () => ({ status: 'ok', job_id: 'x' })),
  getTasks: vi.fn(async () => []),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  synthesizeSpeech: vi.fn(async () => '/audio/tts.mp3'),
  fileUrl: (p: string) => p,
}))

import SettingsPanel from './SettingsPanel'

describe('SettingsPanel initialTab', () => {
  it('GIVEN initialTab="mobile" WHEN offen THEN rendert QR ohne Tab-Klick', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="mobile" />)
    await waitFor(() => expect(screen.getByTestId('mobile-qr')).toBeInTheDocument())
  })

  it('GIVEN kein initialTab WHEN offen THEN Default model-Tab (kein QR)', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} />)
    await waitFor(() => expect(screen.queryByTestId('mobile-qr')).not.toBeInTheDocument())
  })

  it('I7-6: der Code steht in einer Gruppe, die erklaert, was er oeffnet', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="mobile" />)
    const group = await screen.findByTestId('mobile-group-pair')
    expect(group.textContent).toContain('mobileGroupPairHint')
    expect(group.querySelector('[data-testid="mobile-qr"]')).toBeInTheDocument()
  })
})
