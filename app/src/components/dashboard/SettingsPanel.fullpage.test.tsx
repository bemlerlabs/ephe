// P6 B6 (ref-16/17/18/20) — full settings page: master-detail with the four
// groups (Everyday / Capabilities / Data / Advanced) and About as the dashed
// closing card, ← Back to workspace, H1 + language pill + ?-icon.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const changeLanguage = vi.fn()

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage },
    }),
  }
})

vi.mock('@/lib/api', () => ({
  getCapabilities: vi.fn(async () => ({
    subagent: { tools: ['read_file'], tool_count: 1, max_iterations: 8, read_only: true },
    main_agent: { read_only: false, note: 'all tools' },
  })),
  getSettings: vi.fn(async () => ({
    provider: {
      type: 'openai_compatible',
      model: 'my-served-model',
      endpoint: 'http://10.1.2.3:8000/v1',
    },
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
    active_model: 'my-served-model',
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

import SettingsPanel from './SettingsPanel'
import { ABOUT_KEYS, NAV, NAV_GROUPS } from './settings/model'

beforeEach(() => {
  localStorage.clear()
  changeLanguage.mockClear()
})

describe('Settings-Vollseite (P6 B6, ref-16/17/18/20)', () => {
  it('Vollseite mit Back-Zeile — Klick auf Back ruft onClose', async () => {
    const onClose = vi.fn()
    render(<SettingsPanel isOpen onClose={onClose} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    const back = screen.getByTestId('settings-back')
    expect(back.textContent).toContain('settings.back')
    fireEvent.click(back)
    expect(onClose).toHaveBeenCalled()
  })

  it('Nav-Gruppen nach Schema und alle NAV-Einträge als Pillen-Zeilen', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    for (const id of ['models', 'look', 'work', 'trust', 'system']) {
      expect(screen.getByTestId(`settings-nav-group-${id}`)).toBeInTheDocument()
    }
    for (const n of NAV) {
      const row = screen.getByTestId(`settings-nav-${n.key}`)
      expect(row).toBeInTheDocument()
      // One 16 px glyph per row on the 1.5 px stroke raster; a group head carries none.
      expect(row.querySelectorAll('svg')).toHaveLength(1)
      expect(row.querySelector('svg')?.getAttribute('class')).toContain('h-4')
      expect(row.querySelector('svg')?.getAttribute('stroke-width')).toBe('1.5')
    }
    for (const group of NAV_GROUPS) {
      const id = `settings-nav-group-${group.groupKey.replace('settings.group', '').toLowerCase()}`
      // A group head carries no 16 px row glyph; its only svg is the 12 px fold chevron.
      expect(screen.getByTestId(id).querySelector('svg.h-4')).toBeNull()
    }
    // 1:1 — every group matches the NAV keys, no entry missing or doubled
    const groupKeys = [...NAV_GROUPS.flatMap((g) => g.keys), ...ABOUT_KEYS]
    expect([...groupKeys].sort()).toEqual(NAV.map((n) => n.key).sort())
  })

  it('a folded group stays folded when the register opens again', async () => {
    const first = render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    fireEvent.click(screen.getByTestId('settings-fold-models'))
    expect(
      screen.getByTestId('settings-fold-models').getAttribute('aria-expanded'),
    ).toBe('false')
    expect(screen.getByTestId('settings-group-rows-models').className).toContain('hidden')
    first.unmount()
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    expect(
      screen.getByTestId('settings-fold-models').getAttribute('aria-expanded'),
    ).toBe('false')
  })

  // I5-4: the save footer belongs only on tabs whose form writes the settings.
  // On cron/artifacts/tasks it saved the engine while the user was editing jobs,
  // artefacts or hooks there — a dead, dangerous button (DD-24 already knew the
  // rule; three tabs were missing it).
  it('Speichern-Fuss nur auf Tabs mit Settings-Formular', async () => {
    // I7-3: cron is no longer a read-only area — the four schedule controls sit
    // in that tab and need the same footer button as the others.
    for (const tab of ['engine', 'behaviour', 'cron'] as const) {
      const { unmount } = render(<SettingsPanel isOpen onClose={vi.fn()} initialTab={tab} />)
      await screen.findByTestId('settings-page')
      expect(screen.queryByText('settings.save')).toBeInTheDocument()
      unmount()
    }
    for (const tab of [
      // Appearance rows persist on change; the section's own status line replaces
      // the footer while no other section is dirty.
      'appearance',
      'artifacts',
      'tasks',
      'about',
      'language',
      'shortcuts', // a read board in the browser; the desktop shell saves its global opt-in
      'network',
    ] as const) {
      const { unmount } = render(<SettingsPanel isOpen onClose={vi.fn()} initialTab={tab} />)
      await screen.findByTestId('settings-page')
      expect(screen.queryByText('settings.save')).toBeNull()
      unmount()
    }
  })

  it('aktiver Nav-Eintrag an der 2px-Regel der linken Kante erkennbar', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    // Wave 2 (register grouping): the fill is gone. A nav row says where you
    // are through a 2 px hairline on its left edge and an ink step, so the one
    // accent stays for what is running now.
    expect(screen.getByTestId('settings-nav-engine')).toHaveClass('border-l-hairline-strong')
    expect(screen.getByTestId('settings-nav-engine')).toHaveClass('text-ink')
    expect(screen.getByTestId('settings-nav-language')).not.toHaveClass('border-l-hairline-strong')
    expect(screen.getByTestId('settings-nav-language')).not.toHaveClass('bg-brand/10')
  })

  it('H1 + Sprach-Pill: Pill zeigt aktive Sprache, Klick schaltet de→en', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    expect(screen.getByTestId('settings-title-h1')).toBeInTheDocument()
    const pill = screen.getByTestId('settings-lang-pill')
    expect(pill.textContent).toContain('Deutsch')
    fireEvent.click(pill)
    expect(changeLanguage).toHaveBeenCalledWith('en')
  })

  it('?-Icon toggelt die Detail-Zeile (kein totes Control)', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    expect(screen.queryByTestId('settings-help-hint')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('settings-help'))
    expect(screen.getByTestId('settings-help-hint')).toHaveTextContent('engine')
  })

  // W10 g8: at 390 px the header controls measured 22 / 20 / 17.6 x 26 px, all
  // under the 24 px floor. jsdom has no box, so the class contract is pinned
  // here and the px value is measured by the persona-07 walkthrough spec.
  // W13: the floor is unconditional now — `min-h-6`, plus `min-w-6` on the help
  // icon. The `max-lg:` guard it used to travel with is what let the desktop
  // client keep the violation; that width is held by
  // settings/index.touchFloor.test.tsx, this block holds the phone value.
  it('the header controls carry the phone touch floor', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('settings-page')
    const tokens = (testid: string) => screen.getByTestId(testid).className.split(/\s+/)
    expect(tokens('settings-back')).toContain('min-h-6')
    expect(tokens('settings-lang-pill')).toContain('min-h-6')
    expect(tokens('settings-help')).toContain('min-h-6')
    expect(tokens('settings-help')).toContain('min-w-6')
  })
})
