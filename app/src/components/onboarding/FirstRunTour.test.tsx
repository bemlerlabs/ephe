/**
 * The first open's three questions: workspace, engine, what runs on its own.
 *
 * The assertions read the shipped English copy instead of key names, so the
 * promise the tour makes is the thing under test: the engine stop says that
 * nothing is sent without a choice, the desk names AGENTS.md and /context, and
 * the workspace stop writes the folder the picker returned.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import en from '@/locales/en.json'

const {
  skipSetupGate,
  writeTourMarker,
  skipSetup,
  markerStep,
  gateState,
  motion,
  listFs,
  updateSettings,
  getSettings,
  saveSections,
} = vi.hoisted(() => ({
  skipSetupGate: vi.fn(async () => {}),
  writeTourMarker: vi.fn(async (marker: unknown) => marker),
  skipSetup: vi.fn(),
  markerStep: { value: 0 },
  gateState: { snapshot: { ready: true, configured: false, skipped: false } },
  motion: { reduced: true },
  listFs: vi.fn(),
  updateSettings: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({ deep: [] })),
  saveSections: vi.fn(async () => ({})),
}))

vi.mock('framer-motion', () => ({ useReducedMotion: () => motion.reduced }))
vi.mock('@/lib/deepSettings', () => ({ useDeepBool: () => false }))
vi.mock('@/lib/setupGate', () => ({
  gateSnapshot: () => gateState.snapshot,
  subscribeGate: () => () => {},
  loadSetupGate: async () => {},
  markSetupIntent: () => {},
  skipSetupGate,
  readSetupGateHint: () => null,
}))
vi.mock('@/lib/firstRunTour', () => ({
  TOUR_VERSION: 1,
  loadTourMarker: async () => ({
    version: 1,
    step: markerStep.value,
    walked: false,
    skipped: false,
    answers: {},
    exists: true,
  }),
  shouldOpenTour: () => true,
  tourForceFromUrl: () => false,
  writeTourMarker,
}))
vi.mock('@/lib/api', () => ({
  createWorkspaceFolder: vi.fn(),
  disableSkill: vi.fn(),
  enableSkill: vi.fn(),
  getPlugins: vi.fn(async () => ({ public: [], personal: [] })),
  getSettings,
  listFs,
  listSkills: vi.fn(async () => ({ skills: [] })),
  saveSections,
  setPluginEnabled: vi.fn(),
  skipSetup,
  updateSettings,
}))
vi.mock('@/lib/api/http', () => ({ apiUrl: (path: string) => path }))

function translate(key: string, vars?: Record<string, unknown>): string {
  const raw = key
    .split('.')
    .reduce<unknown>(
      (node, part) => (node as Record<string, unknown> | undefined)?.[part],
      en as unknown,
    )
  if (typeof raw !== 'string') return key
  return raw.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(vars?.[name] ?? ''))
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate, i18n: { language: 'en' } }),
}))

import FirstRunTour, { TOUR_STEPS, TOUR_DESK } from './FirstRunTour'

function listing(workspace: string, set: boolean) {
  return {
    path: workspace,
    parent: null,
    home: '/Users/you',
    workspace,
    workspace_set: set,
    entries: [],
  }
}

beforeEach(() => {
  skipSetupGate.mockClear()
  writeTourMarker.mockClear()
  updateSettings.mockClear()
  saveSections.mockClear()
  motion.reduced = true
  markerStep.value = 0
  gateState.snapshot = { ready: true, configured: false, skipped: false }
  getSettings.mockResolvedValue({ deep: [] })
  listFs.mockResolvedValue(listing('/Users/you/Ephe', false))
})

describe('FirstRunTour — the first open', () => {
  it('asks three questions, then opens the desk', () => {
    expect(TOUR_STEPS).toBe(3)
    expect(TOUR_DESK).toBe(4)
  })

  it('records the setup skip when the tour is skipped without an engine', async () => {
    render(<FirstRunTour />)
    const skip = await screen.findByTestId('tour-skip')
    fireEvent.click(skip)
    await waitFor(() => expect(skipSetupGate).toHaveBeenCalledTimes(1))
  })

  it('numbers the questions against three', async () => {
    render(<FirstRunTour />)
    fireEvent.click(await screen.findByTestId('tour-start'))
    expect(await screen.findByText('1 of 3')).toBeTruthy()
  })

  it('shows the workspace the server resolved, and writes a picked folder', async () => {
    markerStep.value = 1
    render(<FirstRunTour />)
    const current = await screen.findByTestId('tour-workspace-current')
    expect(current.textContent).toContain('/Users/you/Ephe')
    expect(current.textContent).toContain('No folder chosen yet')

    fireEvent.click(screen.getByTestId('tour-workspace-choose'))
    const choose = await screen.findByText('Use this folder')
    fireEvent.click(choose)
    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ workspace_dir: '/Users/you/Ephe' }),
    )
  })

  it('states that nothing is sent without a choice, with the terminal door', async () => {
    markerStep.value = 2
    render(<FirstRunTour />)
    expect(await screen.findByText(/chat stays read-only/)).toBeTruthy()
    expect(screen.getByText('ephe configure')).toBeTruthy()
    expect(screen.getByText(/Settings → Engine/)).toBeTruthy()
  })

  it('lets the engine stop pass without a choice, with the skip recorded', async () => {
    markerStep.value = 2
    render(<FirstRunTour />)
    fireEvent.click(await screen.findByTestId('tour-engine-skip'))
    await waitFor(() => expect(skipSetupGate).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('tour-panel').getAttribute('data-step')).toBe('3')
  })

  it('shows the interactive approval preview on the activation stop', async () => {
    markerStep.value = 3
    render(<FirstRunTour />)
    const toggle = await screen.findByTestId('tour-guard-toggle')
    fireEvent.click(toggle)
    expect(await screen.findByTestId('tour-approval-card')).toBeTruthy()
    fireEvent.click(screen.getByTestId('tour-guard-allow'))
    await waitFor(() => expect(screen.queryByTestId('tour-approval-card')).toBeNull())
  })

  it('puts the moth glyph in the engine core', async () => {
    markerStep.value = 2
    render(<FirstRunTour />)
    await screen.findByTestId('tour-engine-core')
    expect(screen.getByTestId('paper-moth-glyph')).toBeTruthy()
  })

  it('names AGENTS.md and /context on the closing desk', async () => {
    markerStep.value = TOUR_DESK
    render(<FirstRunTour />)
    const rules = await screen.findByTestId('tour-rules')
    expect(rules.textContent).toContain('AGENTS.md')
    expect(rules.textContent).toContain('/context')
    fireEvent.click(screen.getByTestId('tour-finish'))
    await waitFor(() => expect(writeTourMarker).toHaveBeenCalled())
  })

  it('resumes a four-question marker on the desk instead of a stop it does not render', async () => {
    markerStep.value = 5
    render(<FirstRunTour />)
    expect(await screen.findByTestId('tour-rules')).toBeTruthy()
    expect(screen.getByTestId('tour-panel').getAttribute('data-step')).toBe('4')
  })

  it('stands the keyframe scene behind the card', async () => {
    render(<FirstRunTour />)
    await screen.findByTestId('tour-panel')
    const frame = document.querySelector('img.tour-stage-frame')
    expect(frame?.getAttribute('src')).toBe('/onboarding/scene-1-ignition.jpg')
  })
})
