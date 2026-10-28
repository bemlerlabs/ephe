import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import { SwarmDeck } from './SwarmDeck'
import { deckDone, deckFromActivities, deckPhase } from '@/lib/swarmDeck'

// The labels below are the ones `streamActions` writes for swarm and helper
// events; the deck reads that contract rather than a second channel.
const swarm = [
  { label: 'Swarm: 2 Agents', status: 'done', detail: 'a, b' },
  { label: 'Agent a', status: 'running', detail: 'search the docs' },
  { label: 'Agent b', status: 'running', detail: 'write the patch' },
]

describe('the swarm deck model', () => {
  it('turns the feed into agent cards and a count', () => {
    const state = deckFromActivities(swarm)
    expect(state.count).toBe(2)
    expect(state.agents.map((agent) => agent.id)).toEqual(['a', 'b'])
    expect(state.agents[0]!.task).toBe('search the docs')
  })

  it('walks the phases as the run advances', () => {
    expect(deckPhase({ count: null, agents: [] })).toBeNull()
    expect(deckPhase(deckFromActivities([swarm[0]!]))).toBe('spawning')
    expect(deckPhase(deckFromActivities(swarm))).toBe('executing')
    const finished = deckFromActivities([
      ...swarm.slice(0, 1),
      { label: 'Agent a', status: 'done' },
      { label: 'Agent b', status: 'done' },
    ])
    expect(deckPhase(finished)).toBe('synthesizing')
    expect(deckDone(finished)).toBe(true)
  })

  it('reads a helper with its role', () => {
    const state = deckFromActivities([
      { label: 'SubAgent h1 (researcher)', status: 'running', detail: 'find sources' },
    ])
    expect(state.agents[0]).toMatchObject({ id: 'h1', role: 'researcher', task: 'find sources' })
  })
})

describe('the swarm deck', () => {
  it('names the phase and seals the helpers read-only', () => {
    render(<SwarmDeck activities={swarm} />)
    const deck = screen.getByTestId('swarm-deck')
    expect(deck.getAttribute('data-phase')).toBe('executing')
    expect(screen.getByTestId('swarm-deck-phase').textContent).toBe('Helpers at work')
    expect(screen.getByTestId('swarm-deck-seal').textContent).toContain('READ-ONLY HELPERS')
    expect(screen.getByTestId('swarm-agent-a')).toBeTruthy()
    expect(screen.getByTestId('swarm-agent-b')).toBeTruthy()
  })

  it('folds away on a click', () => {
    render(<SwarmDeck activities={swarm} />)
    fireEvent.click(screen.getByTestId('swarm-deck-toggle'))
    expect(screen.queryByTestId('swarm-deck-agents')).toBeNull()
  })

  it('stays out of the way when no agent ran', () => {
    render(<SwarmDeck activities={[{ label: 'Reading', status: 'done' }]} />)
    expect(screen.queryByTestId('swarm-deck')).toBeNull()
  })
})
