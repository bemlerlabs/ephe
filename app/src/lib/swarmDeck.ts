/**
 * C1: the orchestra, read from what the stream already says.
 *
 * `streamActions` files every swarm and helper event as an activity line with a
 * fixed shape (`Agent <id>`, `SubAgent <id> (<role>)`, `Swarm: N Agents`). This
 * turns those lines back into agent cards and one phase, so the deck needs no
 * second event channel and cannot disagree with the feed above the transcript.
 */
export interface DeckActivity {
  label: string
  status: string
  detail?: string
}

export interface DeckAgent {
  id: string
  role: string | null
  task: string | null
  status: 'running' | 'done' | 'failed'
}

export interface SwarmDeckState {
  count: number | null
  agents: DeckAgent[]
}

export type DeckPhase = 'planning' | 'spawning' | 'executing' | 'synthesizing' | 'done'

const AGENT = /^Agent (.+)$/
const HELPER = /^SubAgent (\S+)(?: \((.+)\))?$/
const SPAWNED = /^Swarm: (\d+) Agents$/

function statusOf(raw: string): DeckAgent['status'] {
  if (raw === 'done') return 'done'
  if (raw === 'failed' || raw === 'error') return 'failed'
  return 'running'
}

export function deckFromActivities(activities: readonly DeckActivity[]): SwarmDeckState {
  const agents = new Map<string, DeckAgent>()
  let count: number | null = null
  for (const activity of activities) {
    const spawned = SPAWNED.exec(activity.label)
    if (spawned) {
      count = Number(spawned[1])
      continue
    }
    const helper = HELPER.exec(activity.label)
    if (helper) {
      agents.set(helper[1]!, {
        id: helper[1]!,
        role: helper[2] ?? null,
        task: activity.detail ?? null,
        status: statusOf(activity.status),
      })
      continue
    }
    const member = AGENT.exec(activity.label)
    if (member) {
      agents.set(member[1]!, {
        id: member[1]!,
        role: null,
        task: activity.detail ?? null,
        status: statusOf(activity.status),
      })
    }
  }
  return { count, agents: [...agents.values()] }
}

/** PLANNING → SPAWNING → EXECUTING → SYNTHESIZING → DONE, from counts alone. */
export function deckPhase(state: SwarmDeckState): DeckPhase | null {
  if (state.count == null && state.agents.length === 0) return null
  if (state.count == null) return 'planning'
  if (state.agents.length === 0) return 'spawning'
  const running = state.agents.filter((agent) => agent.status === 'running').length
  if (running > 0) return 'executing'
  return state.agents.length >= state.count ? 'synthesizing' : 'spawning'
}

export function deckDone(state: SwarmDeckState): boolean {
  return (
    state.count != null &&
    state.agents.length >= state.count &&
    state.agents.every((agent) => agent.status !== 'running')
  )
}
