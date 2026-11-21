import { describe, it, expect } from 'vitest'
import { deckFromActivities } from './swarmDeck'

/**
 * D2: the steering frame is filed as `Steer <id>`; the card keeps the last
 * direction change that reached that agent. A miss carries no text, and an
 * unknown target never invents a card.
 */
describe('deckFromActivities — steering', () => {
  it('attaches the last landed steer to its agent', () => {
    const state = deckFromActivities([
      { label: 'Swarm: 1 Agents', status: 'done' },
      { label: 'Agent a1', status: 'running', detail: 'qwen · read the docs' },
      { label: 'Steer a1', status: 'done', detail: 'focus on tests' },
    ])
    expect(state.agents[0]!.steered).toBe('focus on tests')
  })

  it('ignores a steer the run never took up', () => {
    const state = deckFromActivities([
      { label: 'Agent a1', status: 'running', detail: 'task' },
      { label: 'Steer a1', status: 'failed', detail: 'unlanded' },
    ])
    expect(state.agents[0]!.steered).toBeUndefined()
  })

  it('never creates a card for an unknown agent', () => {
    const state = deckFromActivities([{ label: 'Steer ghost', status: 'done', detail: 'x' }])
    expect(state.agents).toHaveLength(0)
  })
})
