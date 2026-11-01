/**
 * Finding #61 — one frame, one rail, one tab bar.
 *
 * The rail is the part the reader learns to trust, so the tests hold the trust: it is there on
 * every page, it lights the place you are in (including a sub-page), the phone gets the same
 * places at the bottom, and first run gets no navigation at all.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

// The rail is the subject here; the pages behind it are stubs. NavRail imports the brand mark,
// which pulls the theme provider — a leaf render is enough to prove the column is mounted.
vi.mock('./EpheMark', () => ({ EpheMark: () => <span data-testid="rail-mark" /> }))

import AppShell from './AppShell'
import { SHELL_DESTINATIONS, TAB_BAR_DESTINATIONS, activeDestination } from './shellNav'

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell>
        <Routes>
          {SHELL_DESTINATIONS.map((dest) => (
            <Route
              key={dest.id}
              path={dest.path === '/' ? '/' : `${dest.path}/*`}
              element={<div>page for {dest.id}</div>}
            />
          ))}
          <Route path="*" element={<div>other</div>} />
        </Routes>
      </AppShell>
      ,
    </MemoryRouter>,
  )

describe('the frame', () => {
  it('mounts the rail, the page and the tab bar in one row', () => {
    renderAt('/discover')
    expect(screen.getByTestId('nav-rail')).toBeTruthy()
    expect(screen.getByTestId('shell-content').textContent).toContain('page for discover')
    expect(screen.getByTestId('mobile-tabs')).toBeTruthy()
  })

  it('lights the place the reader is in', () => {
    renderAt('/discover')
    const row = screen.getByTestId('nav-rail-discover')
    expect(row.getAttribute('aria-current')).toBe('page')
    expect(screen.getByTestId('nav-rail-tools').getAttribute('aria-current')).toBeNull()
    expect(screen.getByTestId('mobile-tab-discover').getAttribute('data-active')).toBe('true')
  })

  it('keeps the row lit on a sub-page of that place', () => {
    renderAt('/memory/writings')
    expect(screen.getByTestId('nav-rail-knowledge').getAttribute('aria-current')).toBe('page')
  })

  it('names the chat as the home place', () => {
    renderAt('/')
    expect(screen.getByTestId('nav-rail-task').getAttribute('aria-current')).toBe('page')
  })

  it('leaves first run without navigation', () => {
    render(
      <MemoryRouter initialEntries={['/setup']}>
        <AppShell>
          <div>the wizard</div>
        </AppShell>
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('nav-rail')).toBeNull()
    expect(screen.queryByTestId('mobile-tabs')).toBeNull()
    expect(screen.getByText('the wizard')).toBeTruthy()
  })

  it('gives every rail row a name, not only an icon', () => {
    renderAt('/tools')
    expect(screen.getByTestId('nav-rail-settings').getAttribute('aria-label')).toBe(
      'shell.navSettings',
    )
    // The rail and the tab bar are one navigation drawn for two viewports: same name, and a
    // device puts one of the two on screen (jsdom keeps both in the tree, hence the count).
    expect(screen.getAllByRole('navigation', { name: 'shell.navAria' })).toHaveLength(2)
  })
})

describe('the destination list', () => {
  it('carries the places a phone can reach in one thumb', () => {
    expect(TAB_BAR_DESTINATIONS.map((one) => one.id)).toEqual([
      'task',
      'tools',
      'discover',
      'knowledge',
      'settings',
    ])
  })

  it('answers nothing for a hash the app does not know', () => {
    // An unknown route is the shell's *content* problem (the notice names it); lighting a row
    // for it would claim the reader is somewhere they are not.
    expect(activeDestination('/nowhere')).toBeUndefined()
  })
})
