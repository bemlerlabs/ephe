import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { CustodySeal } from './CustodySeal'

describe('CustodySeal', () => {
  it('ties both knots and says so', () => {
    render(<CustodySeal />)
    const seal = screen.getByTestId('custody-seal')
    expect(seal.getAttribute('data-sealed')).toBe('true')
    expect(seal.textContent).toContain('custody.sealed')
    expect(seal.querySelectorAll('.moth-knot').length).toBe(2)
  })
})
