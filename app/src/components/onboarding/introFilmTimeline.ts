/**
 * The first-open film's clock: five camera cuts, the spark's spline through the
 * clearing and the bee's birth. Everything here is a pure function of time, which is
 * what lets `__epheIntroSeek(ms)` render the same frame the live loop shows.
 */
export const FILM_MS = 12_800
export const IMPACT_MS = 700
export const CHASE_AT = 2200
export const GATHER_AT = 5200
export const VORTEX_AT = 6600
export const AWAKEN_AT = 9400
export const MORPH_AT = 7400
export const WINGS_AT = 8000
export const SHOCK_AT = 8000

/** The five camera setups. Returns 1-5 for a timestamp in ms. */
export function shotAt(t: number): 1 | 2 | 3 | 4 | 5 {
  if (t < CHASE_AT) return 1
  if (t < GATHER_AT) return 2
  if (t < VORTEX_AT) return 3
  if (t < AWAKEN_AT) return 4
  return 5
}

export interface Seed {
  a: number
  b: number
  c: number
  d: number
}

interface PathPoint {
  t: number
  x: number
  y: number
}

const CHASE: PathPoint[] = [
  { t: 2200, x: 0.5, y: 0.62 },
  { t: 2600, x: 0.34, y: 0.68 },
  { t: 3000, x: 0.22, y: 0.7 },
  { t: 3300, x: 0.4, y: 0.6 },
  { t: 3600, x: 0.66, y: 0.55 },
  { t: 3900, x: 0.78, y: 0.54 },
  { t: 4200, x: 0.62, y: 0.62 },
  { t: 4550, x: 0.38, y: 0.68 },
  { t: 4800, x: 0.3, y: 0.66 },
  { t: 4950, x: 0.46, y: 0.58 },
  { t: 5200, x: 0.5, y: 0.5 },
]

export const clamp = (value: number, low = 0, high = 1) => Math.min(high, Math.max(low, value))

export const smooth = (from: number, to: number, value: number) => {
  const x = clamp((value - from) / (to - from))
  return x * x * (3 - 2 * x)
}

export const easeOutCubic = (x: number) => 1 - (1 - clamp(x)) ** 3
export const easeOutBack = (x: number) => {
  const c = 1.70158
  const p = clamp(x) - 1
  return 1 + (c + 1) * p ** 3 + c * p ** 2
}

export function seeded(count: number, seed: number): Seed[] {
  let state = seed >>> 0
  const next = () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return Array.from({ length: count }, () => ({ a: next(), b: next(), c: next(), d: next() }))
}

function catmull(p0: PathPoint, p1: PathPoint, p2: PathPoint, p3: PathPoint, u: number) {
  const u2 = u * u
  const u3 = u2 * u
  return {
    x:
      0.5 *
      (2 * p1.x +
        (-p0.x + p2.x) * u +
        (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * u2 +
        (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * u3),
    y:
      0.5 *
      (2 * p1.y +
        (-p0.y + p2.y) * u +
        (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * u2 +
        (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * u3),
  }
}

export function chaseAt(t: number) {
  const first = CHASE[0]!
  if (t <= first.t) return { x: first.x, y: first.y }
  for (let i = 1; i < CHASE.length; i += 1) {
    const p1 = CHASE[i - 1]!
    const p2 = CHASE[i]!
    if (t <= p2.t) {
      const p0 = CHASE[Math.max(0, i - 2)]!
      const p3 = CHASE[Math.min(CHASE.length - 1, i + 1)]!
      const u = (t - p1.t) / (p2.t - p1.t)
      const point = catmull(p0, p1, p2, p3, u)
      return { x: clamp(point.x, 0.12, 0.88), y: clamp(point.y, 0.3, 0.78) }
    }
  }
  const last = CHASE[CHASE.length - 1]!
  return { x: last.x, y: last.y }
}

/** The spark's path in viewport fractions; null once the bee owns the frame. */
export function sparkAt(t: number): { x: number; y: number } | null {
  if (t < IMPACT_MS) {
    const u = easeOutCubic(t / IMPACT_MS)
    const a = { x: 0.68, y: -0.05 }
    const b = { x: 0.82, y: 0.22 }
    const c = { x: 0.5, y: 0.62 }
    const v = 1 - u
    return {
      x: v * v * a.x + 2 * v * u * b.x + u * u * c.x,
      y: v * v * a.y + 2 * v * u * b.y + u * u * c.y,
    }
  }
  if (t < CHASE_AT) {
    const age = (t - IMPACT_MS) * 0.003
    return { x: 0.5 + Math.sin(age) * 0.012, y: 0.62 + Math.cos(age * 0.8) * 0.014 }
  }
  if (t < GATHER_AT) return chaseAt(t)
  if (t < VORTEX_AT) {
    // The spark brakes in front of the lens: a small breath, not a path.
    const age = (t - GATHER_AT) * 0.003
    return { x: 0.5 + Math.sin(age) * 0.008, y: 0.5 + Math.cos(age * 0.9) * 0.01 }
  }
  if (t < AWAKEN_AT) {
    const p = clamp((t - VORTEX_AT) / (AWAKEN_AT - VORTEX_AT))
    const radius = 0.19 * (1 - p * 0.93)
    const angle = (t - VORTEX_AT) * 0.018
    return {
      x: 0.5 + Math.cos(angle) * radius * 0.72,
      y: 0.52 - p * 0.2 + Math.sin(angle) * radius * 0.55,
    }
  }
  return null
}
