/**
 * Issues #202 and #203: the status surfaces may not claim a state they cannot know.
 *
 * #202: the pill said "Ready" while the engine was offline — a readiness claim about a
 *       moment that is not ready. #203: the usage row showed a bare token count where a
 *       cost figure belongs, with the explanation reachable only through a title tooltip.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentStatusButton from './AgentStatusButton'

vi.mock('@/hooks/useTasks', () => ({ useTasks: () => ({ tasks: [], loading: false }) }))

describe('the status pill tells the truth about the engine', () => {
  it('shows Offline when the engine is unreachable', () => {
    render(<AgentStatusButton messages={[]} engineOnline={false} />)
    expect(screen.getByTestId('agent-status-offline')).toBeTruthy()
    expect(screen.queryByText(/ready/i)).toBeNull()
  })

  it('keeps the idle word when the engine is reachable', () => {
    render(<AgentStatusButton messages={[]} engineOnline />)
    expect(screen.queryByTestId('agent-status-offline')).toBeNull()
  })
})
