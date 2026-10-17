// I7-2: the audio section — row layout, and the auto-speak switch reports the change
// to every open tab (the old path only wrote localStorage).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const api = vi.hoisted(() => ({
  getSettings: vi.fn(async () => ({
    provider: { type: 'local_ollama', model: 'gemma4:12b' },
    memory_enabled: true,
    language: 'de',
    theme: 'dark',
  })),
  updateSettings: vi.fn(async () => ({})),
  healthCheck: vi.fn(async () => ({ ollama: true, models: [] })),
  getModelProviders: vi.fn(async () => ({ active: {}, providers: [], local_models: [] })),
  getMemoryStats: vi.fn(async () => ({ total: 0 })),
  getVoiceSettings: vi.fn(async () => ({
    tts_engine: 'auto',
    piper_voice: 'de_DE-thorsten-medium',
    edge_voice: 'de-DE-KatjaNeural',
    stt_model: 'base',
    stt_language: 'de',
    piper_available: false,
    installed_piper_voices: ['de_DE-thorsten-medium', 'en_US-amy-medium'],
  })),
  saveVoiceSettings: vi.fn(async (patch: Record<string, unknown>) => ({
    tts_engine: 'auto',
    piper_voice: 'de_DE-thorsten-medium',
    edge_voice: 'de-DE-KatjaNeural',
    stt_model: 'base',
    stt_language: 'de',
    piper_available: false,
    installed_piper_voices: ['de_DE-thorsten-medium', 'en_US-amy-medium'],
    ...patch,
  })),
  synthesizeSpeech: vi.fn(async () => '/audio/tts.mp3'),
  listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
  getPackIndex: vi.fn(async () => ({ packs: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  getTasks: vi.fn(async () => []),
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  fileUrl: (p: string) => p,
}))
// Partial mock: only the network functions are stubbed, the rest stays real —
// the panel builds every section in a single render.
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  ...api,
}))

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

async function openVoice() {
  render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="voice" />)
  return screen.findByTestId('voice-row-engine')
}

describe('SettingsPanel Audio (I7-2)', () => {
  it('jede Steuerung ist eine Zeile mit eigener Erklärung', async () => {
    await openVoice()
    for (const id of [
      'voice-row-engine',
      'voice-row-piper',
      'voice-row-installed',
      'voice-row-edge',
      'voice-row-autospeak',
      'voice-row-test',
      'voice-row-stt-model',
      'voice-row-stt-language',
    ]) {
      expect(screen.getByTestId(id)).toBeTruthy()
      expect(screen.getByTestId(`${id}-desc`)).toBeTruthy()
    }
  })

  it('ohne Piper sagt die Engine-Zeile, dass Auto in die Cloud geht', async () => {
    await openVoice()
    expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
      'settings.engineAutoNoPiper',
    )
    fireEvent.click(screen.getByTestId('voice-engine-piper'))
    await waitFor(() =>
      expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
        'settings.piperMissing',
      ),
    )
  })

  it('Umschalten der Engine geht an den Endpunkt und zurück in die Zeile', async () => {
    await openVoice()
    fireEvent.click(screen.getByTestId('voice-engine-edge'))
    await waitFor(() => expect(api.saveVoiceSettings).toHaveBeenCalledWith({ tts_engine: 'edge' }))
    await waitFor(() =>
      expect(screen.getByTestId('voice-engine-edge')).toHaveAttribute('aria-checked', 'true'),
    )
  })

  it('Auto-Vorlesen persistiert und benachrichtigt die anderen Reiter', async () => {
    await openVoice()
    const heard = vi.fn()
    window.addEventListener('ephe:autospeak-changed', heard)
    const toggle = screen.getByTestId('autospeak-toggle')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(localStorage.getItem('ephe.autospeak')).toBe('1')
    expect(heard).toHaveBeenCalled()
    window.removeEventListener('ephe:autospeak-changed', heard)
  })

  it('die installierten Stimmen setzen die Piper-Zeile', async () => {
    await openVoice()
    fireEvent.click(screen.getByTestId('voice-piper-chip-en_US-amy-medium'))
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ piper_voice: 'en_US-amy-medium' }),
    )
  })
})
