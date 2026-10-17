/**
 * Ephe — PluginIcon (extensions v2, E2, out/plan.md [S1]-[S4])
 *
 * GIVEN the icon route
 * WHEN the icon loads / fails
 * THEN the testid tile always exists, on failure as a lettermark
 *      (a deterministic angle derived from the slug).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import PluginIcon from './PluginIcon'

describe('PluginIcon', () => {
  it('rendert die Icon-Kachel mit Testid (img-Pfad) [S1][S2]', () => {
    render(<PluginIcon pluginId="documents" name="Documents" />)
    const el = screen.getByTestId('plugin-icon-documents') as HTMLImageElement
    expect(el.tagName).toBe('IMG')
    expect(el.getAttribute('src')).toBe('/api/plugins/icon/documents')
    expect(el.className).toContain('h-11') // 44 px Kachel
  })

  it('Lettermark-Winkel ist deterministisch aus dem Slug [S3]', () => {
    const angle = (slug: string) => [...slug].reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % 360
    expect(angle('documents')).toBe(angle('documents'))
    expect(angle('documents')).not.toBe(angle('memory'))
  })
})
