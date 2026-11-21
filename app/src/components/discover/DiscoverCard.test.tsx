/** The card marks which language an entry's own words are in when that is not
 *  the reader's language. The words themselves are never touched here. */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

import { DiscoverCard } from './DiscoverCard'
import type { DiscoverItem } from './discoverModel'

const skillItem = (over: Partial<DiscoverItem>): DiscoverItem => ({
  id: 'skill:award-audit',
  kind: 'skill',
  name: 'award-audit',
  title: 'award-audit',
  summary: 'Descriptive words the author shipped with the skill.',
  origin: 'local',
  categories: ['skills'],
  installed: true,
  enabled: true,
  ...over,
})

const actions = { onAdd: () => undefined, onToggle: () => undefined }

describe('discover author language mark', () => {
  it('labels an entry whose words are not in the reader language', () => {
    render(<DiscoverCard {...actions} item={skillItem({ language: 'de' })} />)
    const mark = screen.getByTestId('discover-language-skill:award-audit')
    expect(mark.textContent).toBe('de')
    expect(mark.getAttribute('lang')).toBe('de')
  })

  it('stays silent when the entry already answers in the reader language', () => {
    render(<DiscoverCard {...actions} item={skillItem({ language: 'en' })} />)
    expect(screen.queryByTestId('discover-language-skill:award-audit')).toBeNull()
  })

  it('carries the author words verbatim into the summary and tags them', () => {
    render(<DiscoverCard {...actions} item={skillItem({ language: 'de' })} />)
    const summary = screen.getByTestId('discover-summary-skill:award-audit')
    expect(summary.textContent).toBe('Descriptive words the author shipped with the skill.')
    expect(summary.getAttribute('lang')).toBe('de')
  })
})
