// P4 — privacy tab: the auto-read-aloud switch (localStorage) + deleting local chats
// (confirmation overlay, dbClearAll) + history bubbles staying silent on auto-speak.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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

const dbClearAll = vi.fn(async () => {})
vi.mock('@/lib/db', () => ({ dbClearAll: () => dbClearAll() }))

const synthesizeSpeech = vi.fn((_text: string) => Promise.resolve('/audio/tts.mp3'))
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
  synthesizeSpeech: (...args: unknown[]) => synthesizeSpeech(...(args as [string])),
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
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),

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
import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/types'

beforeEach(() => localStorage.clear())

describe('SettingsPanel P4 Datenschutz', () => {
  it('privacy-Tab: die Auto-Speak-Zeile ist nach Audio umgezogen', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="privacy" />)
    await screen.findByTestId('privacy-profile')
    expect(screen.queryByTestId('autospeak-toggle')).toBeNull()
  })

  it('privacy-Tab: Löschen braucht Bestätigung, dann dbClearAll', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="privacy" />)
    fireEvent.click(await screen.findByTestId('clear-local-data'))
    fireEvent.click(await screen.findByTestId('confirm-clear-local'))
    await waitFor(() => expect(dbClearAll).toHaveBeenCalled())
  })

  it('MessageBubble: History-Bubble (streaming=false ab Mount) spricht NICHT automatisch', async () => {
    localStorage.setItem('ephe.autospeak', '1')
    render(
      <MessageBubble
        message={
          {
            id: 'a1',
            role: 'assistant',
            content: 'Antwort',
            timestamp: 0,
            streaming: false,
          } as ChatMessage
        }
      />,
    )
    await new Promise((r) => setTimeout(r, 50))
    expect(synthesizeSpeech).not.toHaveBeenCalled()
  })

  it('MessageBubble: Stream-ENDE mit autospeak=1 löst Vorlesen aus', async () => {
    localStorage.setItem('ephe.autospeak', '1')
    const { rerender } = render(
      <MessageBubble
        message={
          {
            id: 'a1',
            role: 'assistant',
            content: 'Antwort',
            timestamp: 0,
            streaming: true,
          } as ChatMessage
        }
      />,
    )
    rerender(
      <MessageBubble
        message={
          {
            id: 'a1',
            role: 'assistant',
            content: 'Antwort',
            timestamp: 0,
            streaming: false,
          } as ChatMessage
        }
      />,
    )
    await waitFor(() => expect(synthesizeSpeech).toHaveBeenCalledWith('Antwort'))
  })
})
