/**
 * Ephe — EphemeralWordmark (the brand moment in the empty chat state)
 *
 * GIVEN the brand name
 * WHEN the component renders
 * THEN the text stays one contiguous node (the `hero-brand` textContent pin)
 *      and no dot trail follows it — QD-014 B3: the breathing dots read as a
 *      loading animation while the agent waited in `Ready`.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EphemeralWordmark from './EphemeralWordmark'

describe('EphemeralWordmark', () => {
  it('renders the name as one text node', () => {
    render(<EphemeralWordmark text="Ephe Agent" />)
    const wm = screen.getByTestId('ephemeral-wordmark')
    expect(wm.textContent).toBe('Ephe Agent')
    expect(wm.children.length).toBe(0)
  })

  it('carries no dot trail', () => {
    const { container } = render(<EphemeralWordmark text="Ephe" />)
    expect(container.querySelector('.ephemeral-dot')).toBeNull()
    expect(screen.queryByTestId('ephemeral-dot-0')).toBeNull()
  })
})
