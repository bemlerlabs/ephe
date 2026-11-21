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
    stt_allow_download: false,
    stt_model_cached: false,
    piper_available: false,
    installed_piper_voices: ['de_DE-thorsten-medium', 'en_US-amy-medium'],
    supertonic_voice: 'M1',
    supertonic_lang: 'de',
    supertonic_steps: 8,
    supertonic_package: false,
    supertonic_assets: false,
    local_rungs: [] as string[],
  })),
  saveVoiceSettings: vi.fn(async (patch: Record<string, unknown>) => ({
    tts_engine: 'auto',
    piper_voice: 'de_DE-thorsten-medium',
    edge_voice: 'de-DE-KatjaNeural',
    stt_model: 'base',
    stt_language: 'de',
    stt_allow_download: false,
    stt_model_cached: false,
    piper_available: false,
    installed_piper_voices: ['de_DE-thorsten-medium', 'en_US-amy-medium'],
    supertonic_voice: 'M1',
    supertonic_lang: 'de',
    supertonic_steps: 8,
    supertonic_package: false,
    supertonic_assets: false,
    local_rungs: [] as string[],
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

describe('SettingsPanel audio (I7-2)', () => {
  it('every control is a row with its own explanation', async () => {
    await openVoice()
    for (const id of [
      'voice-row-engine',
      'voice-row-piper',
      'voice-row-installed',
      'voice-row-supertonic',
      'voice-row-rungs',
      'voice-row-edge',
      'voice-row-autospeak',
      'voice-row-test',
      'voice-row-stt-model',
      'voice-row-stt-download',
      'voice-row-stt-language',
    ]) {
      expect(screen.getByTestId(id)).toBeTruthy()
      expect(screen.getByTestId(`${id}-desc`)).toBeTruthy()
    }
  })

  it('without Piper the engine row says that Auto goes to the cloud', async () => {
    await openVoice()
    expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
      'settings.engineAutoNoLocal',
    )
    fireEvent.click(screen.getByTestId('voice-engine-piper'))
    await waitFor(() =>
      expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
        'settings.piperMissing',
      ),
    )
  })

  it('switching the engine reaches the endpoint and comes back to the row', async () => {
    await openVoice()
    fireEvent.click(screen.getByTestId('voice-engine-edge'))
    await waitFor(() => expect(api.saveVoiceSettings).toHaveBeenCalledWith({ tts_engine: 'edge' }))
    await waitFor(() =>
      expect(screen.getByTestId('voice-engine-edge')).toHaveAttribute('aria-checked', 'true'),
    )
  })

  it('auto read-aloud persists and notifies the other tabs', async () => {
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

  it('the installed voices drive the Piper row', async () => {
    await openVoice()
    fireEvent.click(screen.getByTestId('voice-piper-chip-en_US-amy-medium'))
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ piper_voice: 'en_US-amy-medium' }),
    )
  })

  it('the download switch reports a missing model and writes the consent', async () => {
    await openVoice()
    expect(screen.getByTestId('voice-row-stt-download-desc').textContent).toContain(
      'settings.sttDownloadHint',
    )
    const toggle = screen.getByTestId('voice-stt-allow-download')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ stt_allow_download: true }),
    )
  })

  it('a cached model is reported as present', async () => {
    api.getVoiceSettings.mockResolvedValueOnce({
      tts_engine: 'auto',
      piper_voice: 'de_DE-thorsten-medium',
      edge_voice: 'de-DE-KatjaNeural',
      stt_model: 'base',
      stt_language: 'de',
      stt_allow_download: true,
      stt_model_cached: true,
      piper_available: false,
      installed_piper_voices: [],
      supertonic_voice: 'M1',
      supertonic_lang: 'de',
      supertonic_steps: 8,
      supertonic_package: false,
      supertonic_assets: false,
      local_rungs: [] as string[],
    })
    await openVoice()
    expect(screen.getByTestId('voice-row-stt-download-desc').textContent).toContain(
      'settings.sttDownloadCached',
    )
    expect(screen.getByTestId('voice-stt-allow-download')).toHaveAttribute('aria-checked', 'true')
  })
  it('a machine with both rungs shows who answers and in which order', async () => {
    api.getVoiceSettings.mockResolvedValueOnce({
      tts_engine: 'auto',
      piper_voice: 'de_DE-thorsten-medium',
      edge_voice: 'de-DE-KatjaNeural',
      stt_model: 'base',
      stt_language: 'de',
      stt_allow_download: false,
      stt_model_cached: false,
      piper_available: true,
      installed_piper_voices: ['de_DE-thorsten-medium'],
      supertonic_voice: 'M1',
      supertonic_lang: 'de',
      supertonic_steps: 8,
      supertonic_package: true,
      supertonic_assets: true,
      local_rungs: ['supertonic', 'piper'],
    })
    await openVoice()
    expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
      'settings.engineAutoHint',
    )
    expect(screen.getByTestId('voice-rung-supertonic').textContent).toContain('1.')
    expect(screen.getByTestId('voice-rung-piper').textContent).toContain('2.')
  })

  it('the supertonic row writes each of its three fields', async () => {
    await openVoice()
    fireEvent.change(screen.getByLabelText('settings.supertonicSteps'), { target: { value: '16' } })
    fireEvent.blur(screen.getByLabelText('settings.supertonicSteps'))
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ supertonic_steps: 16 }),
    )
    fireEvent.change(screen.getByLabelText('settings.supertonicVoice'), { target: { value: 'F2' } })
    fireEvent.blur(screen.getByLabelText('settings.supertonicVoice'))
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ supertonic_voice: 'F2' }),
    )
    fireEvent.change(screen.getByLabelText('settings.supertonicLang'), { target: { value: 'en' } })
    fireEvent.blur(screen.getByLabelText('settings.supertonicLang'))
    await waitFor(() =>
      expect(api.saveVoiceSettings).toHaveBeenCalledWith({ supertonic_lang: 'en' }),
    )
  })

  it('a half-installed second rung names the half that is missing', async () => {
    api.getVoiceSettings.mockResolvedValueOnce({
      tts_engine: 'supertonic',
      piper_voice: 'de_DE-thorsten-medium',
      edge_voice: 'de-DE-KatjaNeural',
      stt_model: 'base',
      stt_language: 'de',
      stt_allow_download: false,
      stt_model_cached: false,
      piper_available: true,
      installed_piper_voices: [],
      supertonic_voice: 'M1',
      supertonic_lang: 'de',
      supertonic_steps: 8,
      supertonic_package: true,
      supertonic_assets: false,
      local_rungs: [] as string[],
    })
    await openVoice()
    expect(screen.getByTestId('voice-row-supertonic-desc').textContent).toContain(
      'settings.supertonicAssetsMissing',
    )
    expect(screen.getByTestId('voice-rung-none')).toBeTruthy()
    expect(screen.getByTestId('voice-row-engine-desc').textContent).toContain(
      'settings.supertonicAssetsMissing',
    )
  })
})
