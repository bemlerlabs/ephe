import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@/i18n'

const api = vi.hoisted(() => ({ steerTurn: vi.fn(), getCapabilities: vi.fn() }))
vi.mock('@/lib/api', () => ({
  steerTurn: api.steerTurn,
  getCapabilities: api.getCapabilities,
}))
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

beforeEach(() => {
  api.steerTurn.mockReset()
  api.getCapabilities.mockReset()
  api.getCapabilities.mockResolvedValue({
    subagent: { tools: ['read_file'], tool_count: 9, max_iterations: 8, read_only: true },
    main_agent: { read_only: false, note: '' },
  })
})

describe('the swarm deck', () => {
  it('names the phase and seals the helpers read-only', async () => {
    render(<SwarmDeck activities={swarm} />)
    const deck = screen.getByTestId('swarm-deck')
    expect(deck.getAttribute('data-phase')).toBe('executing')
    expect(screen.getByTestId('swarm-deck-phase').textContent).toBe('Helpers at work')
    const seal = screen.getByTestId('swarm-deck-seal')
    expect(seal.textContent).toContain('READ-ONLY SANDBOX')
    // the count is the guard's, not a number in a locale file
    await waitFor(() => expect(seal.textContent).toContain('(9 tools)'))
    expect(screen.getByTestId('swarm-agent-a')).toBeTruthy()
    expect(screen.getByTestId('swarm-agent-b')).toBeTruthy()
  })

  it('leaves the count blank when the guard cannot be asked', async () => {
    api.getCapabilities.mockRejectedValue(new Error('offline'))
    render(<SwarmDeck activities={swarm} />)
    await waitFor(() =>
      expect(screen.getByTestId('swarm-deck-seal').textContent).toContain('(— tools)'),
    )
  })

  it('folds away on a click', () => {
    render(<SwarmDeck activities={swarm} />)
    fireEvent.click(screen.getByTestId('swarm-deck-toggle'))
    expect(screen.queryByTestId('swarm-deck-agents')).toBeNull()
  })

  it('carries a steer field on a running helper', async () => {
    api.steerTurn.mockResolvedValue({ queued: true })
    render(<SwarmDeck activities={swarm} sessionId="s1" turnId="t1" />)
    const field = screen.getByTestId('swarm-steer-a')
    fireEvent.change(field, { target: { value: 'look at the tests first' } })
    fireEvent.click(screen.getByTestId('swarm-steer-send-a'))
    await waitFor(() => {
      expect(api.steerTurn).toHaveBeenCalledWith({
        sessionId: 's1',
        turnId: 't1',
        text: 'look at the tests first',
        agentId: 'a',
      })
    })
    await waitFor(() => {
      expect(screen.getByTestId('swarm-agent-state-a').textContent).toBe('steered')
    })
  })

  it('reports a steer that found no running turn', async () => {
    api.steerTurn.mockRejectedValue(new Error('no running turn for this session'))
    render(<SwarmDeck activities={swarm} sessionId="s1" turnId="t1" />)
    fireEvent.change(screen.getByTestId('swarm-steer-b'), { target: { value: 'stop that' } })
    fireEvent.click(screen.getByTestId('swarm-steer-send-b'))
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('no running turn')
    })
  })

  it('stays out of the way when no agent ran', () => {
    render(<SwarmDeck activities={[{ label: 'Reading', status: 'done' }]} />)
    expect(screen.queryByTestId('swarm-deck')).toBeNull()
  })
})
