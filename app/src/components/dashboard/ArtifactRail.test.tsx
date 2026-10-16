// P2-1 ArtifactRail: portal pop-up — only with artifacts, preview types, the ✕ path.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import ArtifactRail from './ArtifactRail'
import type { ChatMessage } from '@/types'

beforeEach(() => {
  document.body.innerHTML = ''
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const msg = (activities: ChatMessage['activities']): ChatMessage =>
  ({ id: 'm1', role: 'assistant', content: '', timestamp: 0, activities }) as ChatMessage

const TWO = [
  msg([
    { id: 'a0', label: 'html', status: 'done', path: '/tmp/seite.html', fileType: 'html' },
    { id: 'a1', label: 'chart', status: 'done', path: '/tmp/chart.svg', fileType: 'svg' },
    { id: 'a2', label: 'pdf', status: 'done', path: '/tmp/a.pdf', fileType: 'pdf' },
  ]),
]

describe('ArtifactRail', () => {
  it('render nichts ohne Artefakte', () => {
    const { container } = render(
      <ArtifactRail messages={[msg([{ id: 'a', label: 'x', status: 'done' }])]} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('listet Artefakte mit path und isoliert die Vorschau nach Format', () => {
    render(<ArtifactRail messages={TWO} />)
    expect(screen.getByText('chart.svg')).toBeTruthy()
    expect(screen.getByText('a.pdf')).toBeTruthy()
    // the last one (a2, pdf) is selected -> iframe; is a2 an img? img only for a selected img artifact
    const frame = document.querySelector('iframe')
    expect(frame?.getAttribute('src')).toContain('/api/file?path=%2Ftmp%2Fa.pdf')
    // Finding 2026-10-02: model-generated artifacts (html/pdf/deck) used to render
    // without a sandbox in the same origin — scripts inside the artifact had full
    // app access. Guard: no preview frame gets allow-scripts, and a
    // markup format (html/deck) stays without an origin.
    //
    // For PDF the directive may not just allow the origin, it must not appear at
    // all: the viewer is a browser extension, and that works in
    // no sandboxed frame. Measured in real Chrome (both variants with the
    // attribute → sad-document, without the attribute → the page). The
    // isolation of a format that cannot render anyway is carried by the assertion itself.
    const VALID_SANDBOX = new Set([
      'allow-scripts',
      'allow-same-origin',
      'allow-forms',
      'allow-popups',
      'allow-modals',
      'allow-orientation-lock',
      'allow-pointer-lock',
      'allow-presentation',
      'allow-popups-to-escape-sandbox',
      'allow-downloads',
      'allow-storage-access-by-user-activation',
    ])
    const tokensFor = (el: Element | null) =>
      (el?.getAttribute('sandbox') ?? '').split(/\s+/).filter(Boolean)
    expect(frame?.hasAttribute('sandbox')).toBe(false)

    // The same surface, a markup artifact: in a dense frame, without an origin.
    fireEvent.click(screen.getByText('seite.html'))
    const htmlFrame = document.querySelector('iframe')
    const htmlTokens = tokensFor(htmlFrame)
    expect(htmlTokens.length).toBeGreaterThan(0)
    expect(htmlTokens).not.toContain('allow-scripts')
    expect(htmlTokens).not.toContain('allow-same-origin')
    expect(htmlTokens.filter((tk) => !VALID_SANDBOX.has(tk))).toEqual([])
  })

  it('img-Vorschau fuer selected svg', () => {
    render(
      <ArtifactRail
        messages={[
          msg([{ id: 'a1', label: 'c', status: 'done', path: '/tmp/c.svg', fileType: 'svg' }]),
        ]}
      />,
    )
    const img = document.querySelector('img')
    expect(img?.getAttribute('src')).toContain('/api/file?path=%2Ftmp%2Fc.svg')
  })

  // The same finding as on the workbench page: a card whose bytes are gone
  // (404) used to leave a broken image symbol standing. The surface now says what is missing.
  it('benennt eine fehlende Datei, statt ein kaputtes Bild zu zeigen', () => {
    render(
      <ArtifactRail
        messages={[
          msg([{ id: 'a1', label: 'c', status: 'done', path: '/tmp/qr.png', fileType: 'png' }]),
        ]}
      />,
    )
    expect(screen.queryByTestId('artifact-preview-missing')).toBeNull()
    fireEvent.error(document.querySelector('img') as HTMLImageElement)
    expect(screen.getByTestId('artifact-preview-missing').textContent).toBe(
      'artifacts.preview.missing',
    )
    expect(document.querySelector('img')).toBeNull()
  })

  it('gesteuert: ✕ schliesst das Pop-up, und zu bleibt zu', () => {
    const onClose = vi.fn()
    const { rerender, container } = render(
      <ArtifactRail messages={TWO} libraryOpen onCloseLibrary={onClose} />,
    )
    fireEvent.click(screen.getByTestId('artifact-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
    rerender(<ArtifactRail messages={TWO} onCloseLibrary={onClose} />)
    expect(container.innerHTML).toBe('')
  })

  // The review pass caught this: the dialog carried aria-modal but could not be
  // closed with Escape, because the handler was registered only in the *uncontrolled*
  // case. It stayed on top of the chat and swallowed every click.
  it('gesteuert offen: Escape schliesst das Fenster', () => {
    const onClose = vi.fn()
    render(<ArtifactRail messages={TWO} libraryOpen onCloseLibrary={onClose} />)
    expect(screen.getByTestId('artifact-modal')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('registriert den Escape-Weg nur, solange das Fenster offen ist', () => {
    const onClose = vi.fn()
    const { rerender } = render(<ArtifactRail messages={TWO} onCloseLibrary={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    rerender(<ArtifactRail messages={TWO} libraryOpen onCloseLibrary={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('öffnet sich nicht von selbst, nur weil die Aufgabe Karten hat', () => {
    // The old state: one flag meant both — "show the rail" and "open the
    // library". The pop-up stood over the chat without anyone calling it, and it
    // could not be clicked away because the parent already held it closed.
    const { container } = render(
      <ArtifactRail messages={TWO} sessionId="s1" onCloseLibrary={() => {}} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('gesteuert geschlossen: kein Dialog mehr im Baum (Flag alone selig)', () => {
    const { container } = render(
      <ArtifactRail messages={[]} onCloseLibrary={() => {}} libraryOpen={false} />,
    )
    expect(container.innerHTML).toBe('')
    expect(screen.queryByTestId('artifact-modal')).toBeNull()
  })

  // R4-A2: the library is a page. The pop-up does not build a second shelf —
  // it hands over via a link. Calling the library is a navigation, not a
  // self-triggered jump out of the window.
  it('übergibt den Bibliotheks-Ruf an die Seite, statt sie nachzubauen', () => {
    const before = window.location.hash
    render(<ArtifactRail messages={TWO} libraryOpen onCloseLibrary={() => {}} />)
    // The window stays where it is: it shows the cards and links over there.
    expect(window.location.hash).toBe(before)
    expect(screen.getByTestId('artifact-open-page').getAttribute('href')).toBe('#/artifacts')
    // The call hands over; it builds no second shelf: search and the retention
    // notice now only exist on the page.
    expect(screen.queryByPlaceholderText('artifacts.searchPlaceholder')).toBeNull()
    expect(screen.queryByTestId('artifact-expiry')).toBeNull()
  })

  it('zeigt in der Aufgabe einen Link in die Werkbank', () => {
    render(<ArtifactRail messages={TWO} />)
    const link = screen.getByTestId('artifact-open-page')
    expect(link.getAttribute('href')).toBe('#/artifacts')
    // no search field, no retention notice, no export — all of that belongs to the page
    expect(screen.queryByPlaceholderText('artifacts.searchPlaceholder')).toBeNull()
    expect(screen.queryByTestId('artifact-expiry')).toBeNull()
    expect(screen.queryByTestId('artifact-export')).toBeNull()
  })
})

// A0: a card with an id asks for its bytes via the id. The path stays the fallback
// for sessions from before the id — it was the reason a preview could pick up
// a different file.
describe('ArtifactRail — Bytes über die id', () => {
  const WITH_ID = [
    {
      id: 'm2',
      role: 'assistant',
      content: '',
      timestamp: 0,
      activities: [
        {
          id: 'a1',
          label: 'pdf',
          status: 'done',
          path: '/tmp/alt.pdf',
          fileType: 'pdf',
          artifactId: 'f00d',
        },
      ],
    },
  ] as unknown as ChatMessage[]

  it('nutzt die id für Vorschau und Download', () => {
    render(<ArtifactRail messages={WITH_ID} />)
    expect(document.querySelector('iframe')?.getAttribute('src')).toContain(
      '/api/artifacts/f00d/file',
    )
    const link = document.querySelector('a[download]')
    expect(link?.getAttribute('href')).toContain('/api/artifacts/f00d/file?download=1')
  })

  it('fällt ohne id (Sessions von vorher) auf den Pfad zurück', () => {
    render(<ArtifactRail messages={TWO} />)
    expect(document.querySelector('iframe')?.getAttribute('src')).toContain(
      '/api/file?path=%2Ftmp%2Fa.pdf',
    )
  })
})

// R4 (A3): the way out of the pop-up leads via the task, never via a path.
const born = [
  {
    id: 'm2',
    role: 'assistant',
    content: '',
    timestamp: 0,
    turnId: 'turn-7',
    activities: [{ id: 'a9', label: 'pdf', status: 'done', path: '/tmp/a.pdf', fileType: 'pdf' }],
  },
  {
    id: 'm3',
    role: 'assistant',
    content: '',
    timestamp: 0,
    activities: [{ id: 'a8', label: 'pdf', status: 'done', path: '/tmp/b.pdf', fileType: 'pdf' }],
  },
] as unknown as ChatMessage[]

describe('Weg in die Werkbank (R4 A3)', () => {
  it('scoped eine Karte auf ihren Auftrag, eine ohne Turn auf die Sitzung', () => {
    render(<ArtifactRail messages={born} sessionId="s9" />)
    expect(
      document.querySelector('[data-testid="artifact-row-workbench-a9"]')?.getAttribute('href'),
    ).toBe('#/artifacts?turn=turn-7')
    expect(
      document.querySelector('[data-testid="artifact-row-workbench-a8"]')?.getAttribute('href'),
    ).toBe('#/artifacts?session=s9')
  })

  it('der Kopflink bleibt bei der Sitzung, nicht bei einem einzelnen Auftrag', () => {
    render(<ArtifactRail messages={born} sessionId="s9" />)
    expect(screen.getByTestId('artifact-open-page').getAttribute('href')).toBe(
      '#/artifacts?session=s9',
    )
  })

  it('ohne Sitzung führt der Link in die Bibliothek statt auf ein leeres ?session=', () => {
    render(<ArtifactRail messages={born} />)
    expect(screen.getByTestId('artifact-open-page').getAttribute('href')).toBe('#/artifacts')
  })
})

// Wave 10 (persona 06, measured): the pop-up declares role=dialog aria-modal and
// did not honour it — the Tab walk left it after 10 stops into the toolbar behind
// it, and nothing behind it was inert. Live proof:
// e2e/walkthrough/persona-06-tastatur.spec.ts cases (d2) and (b).

/** The rail's own Tab stops, exactly what the walkthrough spec counts. */
const railStops = (modal: HTMLElement): HTMLElement[] =>
  Array.from(
    modal.querySelectorAll<HTMLElement>('a[href],button,input,select,textarea,[tabindex]'),
  ).filter((el) => el.tabIndex >= 0)

describe('ArtifactRail — aria-modal contract (Wave 10)', () => {
  it('takes focus on open, keeps Tab inside and unreaches the shell behind it', () => {
    render(
      <>
        <button data-testid="shell">shell</button>
        <ArtifactRail messages={TWO} />
      </>,
    )
    const modal = screen.getByTestId('artifact-modal')
    expect(modal.getAttribute('tabindex')).toBe('-1')

    const stops = railStops(modal)
    expect(stops.length).toBeGreaterThan(2)
    expect(document.activeElement).toBe(stops[0])

    // The toolbar behind the pop-up used to be the very next stop (measured:
    // Tab #1 → [toolbar-files]). The shell it lives in is inert now, so it
    // cannot be reached at all.
    const shell = screen.getByTestId('shell')
    const shellRegion = shell.closest('[inert]')
    expect(shellRegion).not.toBeNull()
    expect(shellRegion?.getAttribute('aria-hidden')).toBe('true')

    const last = stops[stops.length - 1]!
    last.focus()
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(false)
    expect(document.activeElement).toBe(stops[0])
  })

  it('Escape closes, lifts the inert and hands focus back to the toggle that opened it', () => {
    function Host() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button data-testid="toggle" onClick={() => setOpen(true)}>
            toggle
          </button>
          <ArtifactRail messages={TWO} libraryOpen={open} onCloseLibrary={() => setOpen(false)} />
        </>
      )
    }
    render(<Host />)
    const toggle = screen.getByTestId('toggle')
    toggle.focus()
    fireEvent.click(toggle)
    expect(screen.getByTestId('artifact-modal')).toBeTruthy()
    // The portal sits in <body>, so the whole app shell around the toggle is inert.
    expect(toggle.closest('[inert]')).not.toBeNull()

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(screen.queryByTestId('artifact-modal')).toBeNull()
    expect(toggle.closest('[inert]')).toBeNull()
    expect(document.activeElement).toBe(toggle)
    expect(document.activeElement).not.toBe(document.body)
  })
})
