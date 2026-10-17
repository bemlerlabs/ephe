/** The same surface, once inside the desktop window.
 *
 * The frame there is WebKit, and WebKit has no PDF viewer: the address answers
 * 200 with application/pdf and the field stays white (measured on the running
 * window, 2026-10-07). What the surface does then is give an answer — not an
 * empty rectangle, and not a claim that the file is gone.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import type { ArtifactEntry } from '@/lib/api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))
vi.mock('@/lib/desktopBaseUrl', async (io) => ({
  ...(await io<typeof import('@/lib/desktopBaseUrl')>()),
  IS_DESKTOP_SHELL: true,
}))

const { default: ArtifactPreviewPane } = await import('./preview')

const karte = (name: string, kind: string): ArtifactEntry =>
  ({
    id: 'k1',
    root_id: 'k1',
    version: 1,
    session_id: 's1',
    name,
    path: `/home/x/.ephe/artifacts/s1/${name}`,
    kind,
    size: 2048,
    topic: '',
    created_at: '2026-10-06T09:00:00+00:00',
    favorite: false,
    tags: [],
  }) as ArtifactEntry

afterEach(cleanup)

describe('Desktop-Fenster', () => {
  it('zeigt für ein PDF die Karte mit Auskunft, nicht das weiße Feld', () => {
    render(<ArtifactPreviewPane art={karte('bericht.pdf', 'pdf')} />)
    expect(document.querySelector('iframe')).toBeNull()
    expect(screen.getByText('bericht.pdf')).toBeTruthy()
    expect(screen.getByText('artifacts.preview.noViewer')).toBeTruthy()
  })

  it('lässt Markup im Rahmen — das kann WebKit', () => {
    render(<ArtifactPreviewPane art={karte('seite.html', 'html')} />)
    const frame = document.querySelector('iframe')
    expect(frame?.getAttribute('sandbox')).toBe('allow-popups')
    expect(screen.queryByText('artifacts.preview.noViewer')).toBeNull()
  })
})
