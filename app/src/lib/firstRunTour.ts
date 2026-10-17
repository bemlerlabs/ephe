/**
 * The first open's four questions, as a device-level marker.
 *
 * The marker lives in `~/.ephe/tour.json` (server route `/api/tour`), not in
 * localStorage: the answers span the PWA and the desktop app, and a per-browser
 * flag would replay the tour in a second browser while the engine already
 * answers. `shouldOpenTour` is the one decision the surface and its tests share.
 */
import { apiUrl } from '@/lib/api/http'

export type TourUsage = 'code' | 'research' | 'documents' | 'mix'
export type TourCarry = 'fresh' | 'imported'

export interface TourActivate {
  memory: boolean
  skills: boolean
  web: boolean
}

export interface TourAnswers {
  usage?: TourUsage
  engine?: string
  activate?: TourActivate
  carry?: TourCarry
}

export interface TourMarker {
  version: number
  step: number
  walked: boolean
  skipped: boolean
  answers: TourAnswers
  exists: boolean
}

export const TOUR_VERSION = 1
/** The four question stops; the greeting and the desk frame them. */
export const TOUR_QUESTION_COUNT = 4
export const TOUR_DESK_STEP = 5

const EMPTY: TourMarker = {
  version: TOUR_VERSION,
  step: 0,
  walked: false,
  skipped: false,
  answers: {},
  exists: false,
}

function normalize(raw: unknown): TourMarker {
  if (!raw || typeof raw !== 'object') return EMPTY
  const data = raw as Partial<TourMarker>
  return {
    version: typeof data.version === 'number' ? data.version : TOUR_VERSION,
    step: typeof data.step === 'number' ? Math.min(TOUR_DESK_STEP, Math.max(0, data.step)) : 0,
    walked: data.walked === true,
    skipped: data.skipped === true,
    answers: data.answers && typeof data.answers === 'object' ? data.answers : {},
    exists: data.exists === true,
  }
}

/** The marker, or the defaults when the file is absent or the backend is down. */
export async function loadTourMarker(): Promise<TourMarker> {
  try {
    const response = await fetch(apiUrl('/api/tour'))
    if (!response.ok) return EMPTY
    return normalize(await response.json())
  } catch {
    return EMPTY
  }
}

/** Writes the whole marker atomically through the server route. */
export async function writeTourMarker(marker: TourMarker): Promise<TourMarker> {
  const body = {
    version: TOUR_VERSION,
    step: marker.step,
    walked: marker.walked,
    skipped: marker.skipped,
    answers: marker.answers,
  }
  const response = await fetch(apiUrl('/api/tour'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return { ...marker, ...normalize(await response.json()), exists: true }
}

/** Clears the walked marker so the next load opens the tour again. */
export async function resetTourMarker(): Promise<void> {
  const response = await fetch(apiUrl('/api/tour'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      version: TOUR_VERSION,
      step: 0,
      walked: false,
      skipped: false,
      answers: {},
    }),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
}

/**
 * Whether this load opens the tour.
 *
 * A returning configured install has no tour; an interrupted one resumes at its
 * step; a fresh install starts at the greeting. `?tour=1` replays it on demand.
 */
export function shouldOpenTour(
  marker: TourMarker,
  gate: { ready: boolean; configured: boolean; skipped: boolean },
  force: boolean,
): boolean {
  if (force) return true
  if (!gate.ready) return false
  if (marker.walked || marker.skipped) return false
  if (marker.exists) return true
  return !gate.configured
}

/** The replay trigger: `/?tour=1` or a hash carrying the same query. */
export function tourForceFromUrl(): boolean {
  if (typeof window === 'undefined') return false
  const query = new URLSearchParams(window.location.search).get('tour') === '1'
  return query || window.location.hash.includes('tour=1')
}
