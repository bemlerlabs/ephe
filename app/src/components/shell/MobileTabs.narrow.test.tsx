/**
 * QA-E2E F7: at 320 px the fifth tab read "Einstellu…". Below 340 px the row
 * keeps the icon and both names that do not require width: aria-label and title.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true,
}))

import MobileTabs from './MobileTabs'
import { TAB_BAR_DESTINATIONS } from './shellNav'

describe('MobileTabs at the 320 px floor (F7)', () => {
  it('names every destination without relying on the truncated label', () => {
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <MobileTabs />
      </MemoryRouter>,
    )
    for (const dest of TAB_BAR_DESTINATIONS) {
      const link = screen.getByTestId(`mobile-tab-${dest.id}`)
      expect(link.getAttribute('aria-label')).toBe(dest.labelKey)
      expect(link.getAttribute('title')).toBe(dest.labelKey)
    }
  })

  it('folds the visible label away below 340 px while both names stay on the link', () => {
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <MobileTabs />
      </MemoryRouter>,
    )
    const label = screen.getByTestId('mobile-tab-settings').querySelector('span')
    expect(label?.className).toContain('hidden')
    expect(label?.textContent).toBe('shell.navSettings')
  })

  it('keeps the icon reachable and marks the active row', () => {
    render(
      <MemoryRouter initialEntries={['/tools']}>
        <MobileTabs />
      </MemoryRouter>,
    )
    const active = screen.getByTestId('mobile-tab-tools')
    expect(active.getAttribute('aria-current')).toBe('page')
    expect(active.querySelector('svg')).toBeTruthy()
  })
})
