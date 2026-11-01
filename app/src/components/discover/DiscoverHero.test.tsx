/** The hero is the largest surface on the shelf, so its proof is the mark:
 *  the publisher's own icon when one is named, the subject glyph otherwise,
 *  and the same plate either way so a turn between picks moves nothing. */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

import { DiscoverHero } from './DiscoverHero'
import type { DiscoverItem } from './discoverModel'

const pick = (over: Partial<DiscoverItem>): DiscoverItem => ({
  id: 'connector:featured:featured-nimbus',
  kind: 'connector',
  name: 'Nimbus',
  title: 'Nimbus',
  summary: 'Cloud operations as tools.',
  origin: 'featured',
  categories: ['cloud'],
  installed: false,
  enabled: false,
  ...over,
})

const actions = { busy: false, onAdd: () => undefined, onToggle: () => undefined }

describe('discover hero mark', () => {
  it('shows the publisher icon where the eyebrow glyph sat', () => {
    render(<DiscoverHero {...actions} item={pick({ icon: '/api/discover/icon/github' })} />)
    const img = screen.getByTestId('discover-hero-icon')
    expect(img.getAttribute('src')).toBe('/api/discover/icon/github')
    expect(img.getAttribute('alt')).toBe('')
  })

  it('keeps the subject glyph when the item carries no icon', () => {
    render(<DiscoverHero {...actions} item={pick({})} />)
    expect(screen.queryByTestId('discover-hero-icon')).toBeNull()
    expect(screen.getByTestId('discover-hero-plate').querySelector('svg')).toBeTruthy()
  })

  it('holds one plate size across the rotation, icon or not', () => {
    const withIcon = render(<DiscoverHero {...actions} item={pick({ icon: 'x' })} />)
    const sized = withIcon.getByTestId('discover-hero-plate').className
    withIcon.unmount()
    render(<DiscoverHero {...actions} item={pick({})} />)
    expect(screen.getByTestId('discover-hero-plate').className).toBe(sized)
  })
})
