// WS3-18: the nav search as a flow. The hit list reports how much it found, and a
// click scrolls its landing spot into view instead of dropping the user at the top
// of a fresh section. The Escape close is held here too: it used to sit in two
// effects with their own window listeners, so one key press ran onClose twice.
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

const getSettings = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({
  getSettings: (...args: unknown[]) => getSettings(...args),
  updateSettings: vi.fn(async () => ({})),
  healthCheck: vi.fn(async () => ({ ollama: false, models: [] })),
  getModelProviders: vi.fn(async () => ({
    active: {},
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
  getPackIndex: vi.fn(async () => ({ version: 1, packs: [] })),
  getPlugins: vi.fn(async () => ({ plugins: [], installed: [] })),
  getDeepSettings: vi.fn(async () => ({ sections: [] })),
  putDeepSettings: vi.fn(async () => ({ sections: [] })),
  getTasks: vi.fn(async () => []),
  listMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  synthesizeSpeech: vi.fn(async () => '/audio/tts.mp3'),
  fileUrl: (p: string) => p,
}))

import SettingsPanel from './SettingsPanel'

// jsdom has no layout, so scrollIntoView is replaced and the calls are collected.
const scrolled: Element[] = []

async function openSettings(onClose = vi.fn()) {
  render(<SettingsPanel isOpen onClose={onClose} />)
  return (await screen.findByTestId('settings-search')) as HTMLInputElement
}

function search(box: HTMLInputElement, query: string) {
  fireEvent.change(box, { target: { value: query } })
}

const landedOn = (testid: string) =>
  scrolled.some((el) => el.getAttribute('data-testid') === testid)

beforeEach(() => {
  localStorage.clear()
  scrolled.length = 0
  ;(
    Element.prototype as unknown as { scrollIntoView: (options?: unknown) => void }
  ).scrollIntoView = function (this: Element) {
    scrolled.push(this)
  }
  getSettings.mockResolvedValue({
    provider: { type: 'local_ollama', model: 'gemma4:12b' },
    deep: [
      {
        key: 'advanced',
        fields: [
          {
            key: 'advanced.api_timeout',
            type: 'number',
            label: 'Tempolimit',
            labelEn: 'Timeout',
            default: 120,
            value: 120,
          },
        ],
      },
    ],
  })
})

describe('nav search reports its yield', () => {
  it('counts the areas and the settings separately', async () => {
    const box = await openSettings()
    search(box, 'engine')
    expect((await screen.findByTestId('settings-search-tabs-count')).textContent).toBe('1')
    // The yield badge agrees with the rows the list actually shows (the engine
    // string also sits in the audio row, so the number is not a constant here).
    const settings = screen.getAllByTestId(/^settings-search-(field|row)-/)
    expect(screen.getByTestId('settings-search-fields-count').textContent).toBe(
      String(settings.length),
    )
  })
})

describe('a search hit lands where it points', () => {
  it('scrolls the register group of a field hit into view', async () => {
    const box = await openSettings()
    search(box, 'tempolimit')
    fireEvent.click(await screen.findByTestId('settings-search-field-advanced-Tempolimit'))
    expect(screen.getByTestId('settings-title-h1').textContent).toBe('settings.engine')
    await waitFor(() => expect(landedOn('deep-section-advanced')).toBe(true))
  })

  it('scrolls the content column to the top for an area hit', async () => {
    const box = await openSettings()
    search(box, 'about')
    fireEvent.click(await screen.findByTestId('settings-search-tab-about'))
    expect(screen.getByTestId('settings-title-h1').textContent).toBe('settings.about')
    await waitFor(() => expect(landedOn('settings-panel')).toBe(true))
  })
})

describe('Escape closes the settings dialog once', () => {
  it('calls onClose a single time per key press', async () => {
    const onClose = vi.fn()
    await openSettings(onClose)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
