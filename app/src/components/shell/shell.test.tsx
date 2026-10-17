/**
 * Ephe — S wave: app-shell building blocks (pin tests)
 *
 * GIVEN PageHeader / SearchInput / Section as shell primitives
 * WHEN they render
 * THEN their data-testid contracts and aria labels are right (every
 *      content page is built on them — the Ephemora look, docs/BRAND.md).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import PageHeader from './PageHeader'
import SearchInput from './SearchInput'
import Section from './Section'

describe('PageHeader', () => {
  it('rendert Titel + Untertitel + Aktions-Slot mit Testids', () => {
    render(
      <PageHeader
        title="Plugin Store"
        subtitle="Extend Ephe"
        actions={<button data-testid="action-x">Add</button>}
      />,
    )
    expect(screen.getByTestId('page-title').textContent).toBe('Plugin Store')
    expect(screen.getByTestId('page-subtitle').textContent).toBe('Extend Ephe')
    expect(screen.getByTestId('page-actions')).toBeTruthy()
  })

  it('Untertitel optional', () => {
    render(<PageHeader title="Nur Titel" />)
    expect(screen.getByTestId('page-title')).toBeTruthy()
    expect(screen.queryByTestId('page-subtitle')).toBeNull()
  })
})

describe('SearchInput', () => {
  it('hat page-search-Testid + Aria-Label und feuert onChange', () => {
    const onChange = vi.fn()
    render(
      <SearchInput value="" onChange={onChange} placeholder="Suchen" label="Plugins durchsuchen" />,
    )
    const input = screen.getByTestId('page-search') as HTMLInputElement
    expect(input.getAttribute('aria-label')).toBe('Plugins durchsuchen')
    fireEvent.change(input, { target: { value: 'git' } })
    expect(onChange).toHaveBeenCalledWith('git')
  })
})

describe('Section', () => {
  it('rendert Titel + Kinder + optionalen Testid', () => {
    render(
      <Section title="Installed" testid="section-installed">
        <p>Inhalt</p>
      </Section>,
    )
    expect(screen.getByText('Installed')).toBeTruthy()
    expect(screen.getByTestId('section-installed')).toBeTruthy()
  })
})
