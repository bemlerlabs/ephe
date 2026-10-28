import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import EngineStatusPill from './EngineStatusPill'

// B1/B2: the engine state has one home — the top bar — and its click is the way
// to the settings that can change it.

describe('the engine status pill', () => {
  it('names the state it is in', () => {
    render(<EngineStatusPill state="online" onClick={vi.fn()} />)
    const pill = screen.getByTestId('engine-status-pill')
    expect(pill.getAttribute('data-engine-state')).toBe('online')
    expect(pill.getAttribute('aria-label')).toBeTruthy()
    expect(pill.textContent).toBeTruthy()
  })

  it('sticks to the edge of the header on phones', () => {
    render(<EngineStatusPill state="offline" onClick={vi.fn()} />)
    expect(screen.getByTestId('engine-status-pill').className).toContain('hidden')
    expect(screen.getByTestId('engine-status-pill').className).toContain('lg:inline-flex')
  })

  it('opens the engine settings on click', () => {
    const onClick = vi.fn()
    render(<EngineStatusPill state="checking" onClick={onClick} />)
    fireEvent.click(screen.getByTestId('engine-status-pill'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
