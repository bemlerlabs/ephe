/**
 * The tour's four audit fixes: the skip reaches the setup gate, the carry step has
 * an honest footer, the guard step shows the approval card, and the stage is the
 * keyframe scene rather than a second drawing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const { skipSetupGate, writeTourMarker, skipSetup, markerStep, gateState } = vi.hoisted(() => ({
  skipSetupGate: vi.fn(async () => {}),
  writeTourMarker: vi.fn(async (marker: unknown) => marker),
  skipSetup: vi.fn(),
  markerStep: { value: 4 },
  gateState: { snapshot: { ready: true, configured: false, skipped: false } },
}))

vi.mock('framer-motion', () => ({ useReducedMotion: () => true }))
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
  TOUR_QUESTION_COUNT: 4,
  TOUR_DESK_STEP: 5,
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
  disableSkill: vi.fn(),
  enableSkill: vi.fn(),
  getPlugins: vi.fn(async () => ({ plugins: [] })),
  getSettings: vi.fn(async () => ({ deep: [] })),
  listSkills: vi.fn(async () => ({ skills: [] })),
  saveSections: vi.fn(),
  setPluginEnabled: vi.fn(),
  skipSetup,
}))
vi.mock('@/lib/api/http', () => ({ apiUrl: (path: string) => path }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

import FirstRunTour from './FirstRunTour'

beforeEach(() => {
  skipSetupGate.mockClear()
  writeTourMarker.mockClear()
})

describe('FirstRunTour — audit fixes', () => {
  it('records the setup skip when the tour is skipped without an engine', async () => {
    render(<FirstRunTour />)
    const skip = await screen.findByTestId('tour-skip')
    fireEvent.click(skip)
    await waitFor(() => expect(skipSetupGate).toHaveBeenCalledTimes(1))
  })

  it('offers an honest next button on the carry step, without an import', async () => {
    render(<FirstRunTour />)
    const next = await screen.findByTestId('tour-next')
    expect(next).not.toBeDisabled()
    expect(next.textContent).toBe('tour.carry.fresh')
    fireEvent.click(next)
    await waitFor(() => expect(writeTourMarker).toHaveBeenCalled())
  })

  it('shows the interactive approval preview on the activation step', async () => {
    markerStep.value = 3
    render(<FirstRunTour />)
    const toggle = await screen.findByTestId('tour-guard-toggle')
    fireEvent.click(toggle)
    expect(await screen.findByTestId('tour-approval-card')).toBeTruthy()
    fireEvent.click(screen.getByTestId('tour-guard-allow'))
    await waitFor(() => expect(screen.queryByTestId('tour-approval-card')).toBeNull())
    markerStep.value = 4
  })

  it('stands the keyframe scene behind the card', async () => {
    render(<FirstRunTour />)
    await screen.findByTestId('tour-panel')
    const frame = document.querySelector('img.tour-stage-frame')
    expect(frame?.getAttribute('src')).toBe('/onboarding/scene-1-ignition.jpg')
  })
})
