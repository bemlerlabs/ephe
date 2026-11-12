/**
 * Wave 3 (web intake): the verdict under a research answer.
 *
 * The card never rewrites or hides the answer; it states how many claims a
 * stored source carried and names the ones it did not.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
  }),
}))

import { CitationCheck } from './CitationCheck'

afterEach(cleanup)

describe('CitationCheck', () => {
  it('renders nothing without a check', () => {
    const { container } = render(<CitationCheck />)
    expect(container).toBeEmptyDOMElement()
  })

  it('states the count when every claim is backed', () => {
    render(<CitationCheck check={{ runId: 'r_1', checked: 3, verified: 3, unverified: [] }} />)
    const card = screen.getByTestId('citation-check')
    expect(card.getAttribute('data-verdict')).toBe('verified')
    expect(card.textContent).toContain('chat.research.citationAll')
    expect(card.textContent).toContain('"checked":3')
  })

  it('names the claims no stored source carried', () => {
    render(
      <CitationCheck
        check={{
          runId: 'r_1',
          checked: 3,
          verified: 1,
          unverified: ['The moon is made of cheese.', 'Tides are caused by wind.'],
        }}
      />,
    )
    const card = screen.getByTestId('citation-check')
    expect(card.getAttribute('data-verdict')).toBe('unverified')
    expect(card.textContent).toContain('chat.research.citationMissing')
    expect(card.textContent).toContain('"missing":2')
    expect(screen.getByText('The moon is made of cheese.')).toBeInTheDocument()
    expect(screen.getByText('Tides are caused by wind.')).toBeInTheDocument()
  })
})
