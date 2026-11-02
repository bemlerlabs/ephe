/**
 * The shelf's marks are files the backend serves, so their address has to be
 * the backend's. In the PWA a root-relative `/api/...` resolves against the same
 * origin and works; in the desktop shell the page lives on `tauri://localhost`,
 * and the same string asks the bundle for a file it never carried — measured as
 * "the icons are there in the PWA and missing in the app".
 */
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { render, screen } from '@testing-library/react'

vi.mock('@/lib/api/http', () => ({
  apiUrl: (path: string) => `http://127.0.0.1:8765${path}`,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

describe('shelf icon address', () => {
  it('asks the backend for the mark, not the bundle', () => {
    render(<DiscoverHero {...actions} item={pick({ icon: '/api/discover/icon/github' })} />)
    expect(screen.getByTestId('discover-hero-icon').getAttribute('src')).toBe(
      'http://127.0.0.1:8765/api/discover/icon/github',
    )
  })

  it('leaves no plate reaching for a root-relative icon of its own', () => {
    for (const file of ['DiscoverHero.tsx', 'DiscoverCard.tsx', 'DiscoverDetail.tsx']) {
      const source = readFileSync(`src/components/discover/${file}`, 'utf8')
      expect(source, file).toContain('src={apiUrl(item.icon)}')
      expect(source.match(/src=\{item\.icon\}/g) ?? [], file).toHaveLength(0)
    }
  })
})
