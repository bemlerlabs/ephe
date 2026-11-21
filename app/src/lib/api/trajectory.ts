/** P5: model trajectory (backend: core/trajectory.py + routes/trajectory.py). */
import { request } from './http'

export interface TrajUsage {
  in: number | null
  out: number | null
  model: string
}

export interface TrajStep {
  n: number
  type: string
  title: string
  ms: number
  state: string
  usage?: TrajUsage
  /** P6: text body (user prompt, reasoning, assistant reply, tool output). */
  text?: string
}

/** G7 provenance: one stored fact the prompt of a turn carried. */
export interface TrajMemory {
  id: string
  text: string
  score: number
  source: string
}

export interface TrajTurn {
  sid: string
  /** A3 backwards: the same id the job is filed under in the artefact index.
   *  Cards predating the chain do not carry it — absent reads as empty. */
  turn_id?: string
  model: string
  ts: number | null
  duration_ms: number | null
  steps: TrajStep[]
  /** The memories injected into this turn's prompt (G7 provenance). Absent/[] = none. */
  memories?: TrajMemory[]
}

export function getTrajectory(session: string): Promise<{ turns: TrajTurn[] }> {
  return request<{ turns: TrajTurn[] }>(`/api/trajectory?session=${encodeURIComponent(session)}`)
}

export interface TurnDelta {
  index: number
  din: number | null
  dout: number | null
}

function usageTotals(t: TrajTurn): { i: number; o: number } | null {
  let i = 0
  let o = 0
  let seen = false
  for (const s of t.steps) {
    if (s.usage) {
      seen = true
      i += s.usage.in ?? 0
      o += s.usage.out ?? 0
    }
  }
  return seen ? { i, o } : null
}

/** N5 (C3): IN/OUT deltas between consecutive turns — a pure frontend
 *  derivation, the backend stays unchanged. Turns without a usage step and the
 *  first turn yield null (no invented default). */
export function diffTurns(turns: TrajTurn[]): TurnDelta[] {
  const totals = turns.map(usageTotals)
  return turns.map((_, index) => {
    const cur = totals[index]
    const prev = index > 0 ? totals[index - 1] : null
    if (!cur || !prev) return { index, din: null, dout: null }
    return { index, din: cur.i - prev.i, dout: cur.o - prev.o }
  })
}
