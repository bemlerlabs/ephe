/**
 * W13 follow-up — the settings header's three controls at desktop width.
 *
 * GIVEN the full settings page rendered at a 1440 px viewport
 * WHEN the back button, the language pill and the ? icon are inspected
 * THEN each holds the 24 px floor (WCAG 2.5.8) in a class that carries no
 *      width guard, and the ? icon holds it on both axes.
 *
 * The floor had reached this header only behind `max-lg:`: `max-lg:min-h-6` on
 * the back button and the pill, `max-lg:min-w-6 max-lg:min-h-6` plus the
 * guarded centring trio on the ? icon. A width-guarded floor is the defect the
 * sibling repairs name (Sidebar.touchFloor.test.tsx,
 * ToolbarRow.touchFloor.test.tsx): the phone paid the floor, the desktop client
 * — the width this shell is built for — kept the violation. The verification
 * wave measured the three as 112.4 x 22, 59.5 x 20 and 17.6 x 26 px at 390 px
 * and reports them under 24 px on at least one axis at 1440 px.
 *
 * jsdom computes no box, so the contract held here is the class list: the floor
 * is asserted as the exact token, because `max-lg:min-h-6` answers for the
 * phone and must not be read as the desktop floor. The px values belong to the
 * walkthrough. The unconditional token gives the phone the same 24 px the
 * guard gave it, which is why the phone case below asserts the identical list.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({
    provider: { type: 'openai_compatible', model: 'm', endpoint: 'http://10.1.2.3:8000/v1' },
    memory_enabled: true,
    language: 'de',
    theme: 'dark',
  })),
  updateSettings: vi.fn(async () => ({})),
  healthCheck: vi.fn(async () => ({
    status: 'ok',
    ollama: false,
    models: [],
    active_tier: 'power',
    active_model: 'm',
    dgx_online: true,
    active_provider: 'openai_compatible',
    offline_capable: false,
    requires_internet: true,
    engine_online: true,
    engine_state: 'ok',
  })),
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
  getSchedulePresets: vi.fn(async () => ({ presets: [] })),
  getScheduleResults: vi.fn(async () => ({ results: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  getTasks: vi.fn(async () => []),
  fileUrl: (p: string) => p,
  getNetworkStatus: vi.fn(async () => ({
    bind_host: '127.0.0.1',
    bind_port: 8765,
    lan: false,
    setup_mode: false,
    token_required: false,
    file_roots: [],
    proxy_extra_ports: [],
    allow_private_fetches: false,
  })),
  getHooks: vi.fn(async () => ({
    enabled: true,
    path: '/Users/x/.ephe/hooks.json',
    exists: false,
    events: [],
    recent: [],
  })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
}))

import SettingsPanel from '../SettingsPanel'

/** The three controls of the settings header, in source order. */
const HEADER_CONTROLS = {
  back: 'settings-back',
  pill: 'settings-lang-pill',
  help: 'settings-help',
} as const

/** The class tokens of an element — Tailwind reads them one by one. */
function tokensOf(el: Element): string[] {
  return el.className.split(/\s+/)
}

/** Any token that buys size only below a breakpoint, e.g. `max-lg:min-h-6`. */
function guardedSizeTokens(tokens: string[]): string[] {
  return tokens.filter((tok) => /^max-(?:lg|md|sm):(?:min-[hw]|h-|w-)/.test(tok))
}

/**
 * A 1440 px desktop viewport. jsdom applies no media query, so what the stub
 * changes is the intent a reader sees, not the class list — the missing width
 * guard is the whole difference between the two cases below.
 */
function stubDesktopViewport(): void {
  vi.stubGlobal('innerWidth', 1440)
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('min-width: 1024px'),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

/** Every header control by its role in the row, once the page has mounted. */
type HeaderControls = { back: Element; pill: Element; help: Element }

async function renderHeader(): Promise<HeaderControls> {
  render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
  await screen.findByTestId('settings-page')
  return {
    back: screen.getByTestId(HEADER_CONTROLS.back),
    pill: screen.getByTestId(HEADER_CONTROLS.pill),
    help: screen.getByTestId(HEADER_CONTROLS.help),
  }
}

describe('settings header at desktop width (W13)', () => {
  beforeEach(() => {
    stubDesktopViewport()
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('the back button holds the floor in an unguarded class', async () => {
    const { back } = await renderHeader()
    expect(tokensOf(back), 'back height at desktop').toContain('min-h-6')
    expect(guardedSizeTokens(tokensOf(back)), 'back size guard').toEqual([])
  })

  it('the language pill holds the floor in an unguarded class', async () => {
    const { pill } = await renderHeader()
    expect(tokensOf(pill), 'pill height at desktop').toContain('min-h-6')
    expect(guardedSizeTokens(tokensOf(pill)), 'pill size guard').toEqual([])
  })

  it('the ? icon holds 24 x 24 and centres its glyph without a guard', async () => {
    const { help } = await renderHeader()
    const tokens = tokensOf(help)
    expect(tokens, 'help width at desktop').toContain('min-w-6')
    expect(tokens, 'help height at desktop').toContain('min-h-6')
    expect(tokens, 'help glyph centring').toContain('items-center')
    expect(tokens, 'help glyph centring').toContain('justify-center')
    expect(guardedSizeTokens(tokens), 'help size guard').toEqual([])
  })

  it('no header control buys its size only below a breakpoint', async () => {
    const header = await renderHeader()
    for (const [name, el] of Object.entries(header)) {
      expect(guardedSizeTokens(tokensOf(el)), name).toEqual([])
    }
  })
})

describe('settings header at phone width (W10 contract, unchanged)', () => {
  beforeEach(() => {
    vi.stubGlobal('innerWidth', 390)
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('the same unguarded tokens give the phone its 24 px floor', async () => {
    const { back, pill, help } = await renderHeader()
    expect(tokensOf(back), 'back height at phone').toContain('min-h-6')
    expect(tokensOf(pill), 'pill height at phone').toContain('min-h-6')
    expect(tokensOf(help), 'help width at phone').toContain('min-w-6')
    expect(tokensOf(help), 'help height at phone').toContain('min-h-6')
  })
})
