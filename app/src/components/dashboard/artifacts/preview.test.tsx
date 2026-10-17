/**
 * R5: the preview surface of a workbench card.
 *
 * Two findings from the review run on the live product, both measured with an
 * image:
 * 1. A PDF showed a white rectangle. The frame carried a sandbox directive, and
 *    the browser's viewer works in no sandboxed frame — so for dead formats the
 *    directive has to go.
 * 2. A card whose file had been cleared away (`ephe_github_qr.png`, HTTP 404)
 *    showed a broken-image glyph and said nothing. This file promises to emit
 *    nothing but an empty area — the image branch did not keep that.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ArtifactPreviewPane from './preview'
import type { ArtifactEntry } from '@/lib/api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

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

beforeEach(() => cleanup())
afterEach(() => cleanup())

describe('Vorschau-Rahmen', () => {
  it('lässt ein PDF ohne Direktive — mit jeder Variante blieb das Feld weiß', () => {
    render(<ArtifactPreviewPane art={karte('bericht.pdf', 'pdf')} />)
    const frame = screen.getByTitle('bericht.pdf')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame.hasAttribute('sandbox')).toBe(false)
    expect(frame.getAttribute('src')).toContain('#toolbar=0&navpanes=0&view=FitH')
  })

  it('hält Markup im dichten Rahmen', () => {
    render(<ArtifactPreviewPane art={karte('seite.html', 'html')} />)
    const frame = screen.getByTitle('seite.html')
    expect(frame.getAttribute('sandbox')).toBe('allow-popups')
  })
})

describe('fehlende Bytes', () => {
  it('zeigt eine Auskunft statt eines kaputten Bildes', () => {
    render(<ArtifactPreviewPane art={karte('qr.png', 'png')} />)
    const bild = screen.getByAltText('qr.png')
    expect(bild.tagName).toBe('IMG')
    fireEvent.error(bild)
    expect(screen.queryByAltText('qr.png')).toBeNull()
    expect(screen.getByText('artifacts.preview.missing')).toBeTruthy()
    expect(screen.getByText('qr.png')).toBeTruthy()
  })

  it('gilt ebenso für Ton und Video', () => {
    // jsdom does not know the ARIA roles of video/audio — measured on the element.
    const { unmount, container } = render(<ArtifactPreviewPane art={karte('clip.mp4', 'mp4')} />)
    const film = container.querySelector('video')
    expect(film).toBeTruthy()
    fireEvent.error(film as HTMLVideoElement)
    expect(screen.getByText('artifacts.preview.missing')).toBeTruthy()
    unmount()
    const zweiter = render(<ArtifactPreviewPane art={karte('sprache.mp3', 'audio')} />)
    const ton = zweiter.container.querySelector('audio')
    expect(ton).toBeTruthy()
    fireEvent.error(ton as HTMLAudioElement)
    expect(screen.getByText('artifacts.preview.missing')).toBeTruthy()
  })
})

// A5 edge: a source file used to answer `none` here — an unsupported card next
// to bytes the file endpoint serves fine. The code view reads them back.
describe('source code in the pane (A5 edge)', () => {
  const realFetch = global.fetch
  afterEach(() => {
    global.fetch = realFetch
  })

  it('shows a .ts card as source instead of an empty area', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      text: async () => 'export const zaehler = 1\n',
    })) as unknown as typeof fetch
    render(<ArtifactPreviewPane art={karte('modul.ts', 'ts')} />)
    expect(await screen.findByTestId('artifact-preview-code')).toBeTruthy()
    expect(screen.getByText('typescript')).toBeTruthy()
    expect(screen.getByText(/export const zaehler = 1/)).toBeTruthy()
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/artifacts/k1/file'))
  })

  it('answers a failed read with a message, not an empty area', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 404 })) as unknown as typeof fetch
    render(<ArtifactPreviewPane art={karte('modul.ts', 'ts')} />)
    const warning = await screen.findByRole('alert')
    expect(warning.textContent).toBe('artifacts.preview.failed')
    expect(screen.queryByTestId('artifact-preview-code')).toBeNull()
  })
})

// A5 edge: the failed read names the next step. The warning keeps the sentence,
// and a retry under it re-reads the same route instead of standing still.
describe('the failed read names the next step', () => {
  const realFetch = global.fetch
  afterEach(() => {
    global.fetch = realFetch
  })

  it('offers the retry under the source warning and re-reads the file', async () => {
    let calls = 0
    global.fetch = vi.fn(async () => {
      calls += 1
      if (calls === 1) return { ok: false, status: 404 }
      return { ok: true, text: async () => 'export const zaehler = 1\n' }
    }) as unknown as typeof fetch
    render(<ArtifactPreviewPane art={karte('modul.ts', 'ts')} />)
    const warning = await screen.findByRole('alert')
    expect(warning.textContent).toBe('artifacts.preview.failed')
    const retry = screen.getByTestId('artifact-preview-code-retry')
    expect(retry.textContent).toBe('agentPanel.retry')
    fireEvent.click(retry)
    expect(await screen.findByTestId('artifact-preview-code')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(calls).toBe(2)
  })

  it('offers the retry for a card the server reads back as content', async () => {
    let calls = 0
    global.fetch = vi.fn(async () => {
      calls += 1
      if (calls === 1)
        return {
          ok: false,
          status: 500,
          statusText: 'boom',
          json: async () => {
            throw new Error('no body')
          },
        }
      return { ok: true, json: async () => ({ mode: 'text', format: 'plain', text: 'inhalt' }) }
    }) as unknown as typeof fetch
    render(<ArtifactPreviewPane art={karte('tabelle.xlsx', 'xlsx')} />)
    const warning = await screen.findByRole('alert')
    expect(warning.textContent).toBe('artifacts.preview.failed')
    fireEvent.click(screen.getByTestId('artifact-preview-retry'))
    expect(await screen.findByText('inhalt')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(calls).toBe(2)
  })
})
