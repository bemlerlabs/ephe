/**
 * R2-U: the update path has to state its own condition — including the bad one.
 *
 * The previous state was a banner that only existed for an available update,
 * plus a type without an `error` field: when the check failed (404, no backend),
 * the surface answered "no update available". That is an assertion about a
 * condition that was never measured. These cases hold the state machine.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UpdateDialog } from './UpdateDialog'
import type { UpdateState } from '@/lib/useUpdateCheck'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'update.title': 'Updates',
        'update.titleCurrent': 'Du bist aktuell',
        'update.titleFailed': 'Prüfung nicht möglich',
        'update.titleAvailable': 'Neue Version verfügbar',
        'update.titleReady': 'Bereit zum Neustart',
        'update.checkFailed':
          'Die Release-Quelle war nicht erreichbar. Die Fläche behauptet deshalb nicht, dass du aktuell bist — sie weiß es gerade nicht.',
        'update.isCurrent': 'Ephe {{version}} ist die neueste Version.',
        'update.availableBody': 'Ephe {{from}} → {{to}}',
        'update.downloading': 'Lade Ephe {{version}} herunter…',
        'update.installAndRestart': 'Installieren & neu starten',
        'update.viewReleases': 'Releases ansehen',
      }
      const raw = map[key] ?? key
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, n: string) =>
        opts && opts[n] !== undefined ? String(opts[n]) : `{{${n}}}`,
      )
    },
  }),
}))

const noop = () => {}
const base = { open: true, onOpenChange: noop, onCheck: noop, onInstall: noop, onRelaunch: noop }

describe('R2-U — der Update-Dialog sagt, was er weiß', () => {
  it('ein fehlgeschlagener Check heißt Prüfung nicht möglich — nicht „aktuell"', () => {
    const state: UpdateState = { phase: 'failed', progress: null, reason: '404 Not Found' }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByText('Prüfung nicht möglich')).toBeTruthy()
    expect(screen.getByTestId('update-reason').textContent).toBe('404 Not Found')
    expect(screen.queryByText(/neueste Version/)).toBeNull()
    expect(screen.getByTestId('update-recheck')).toBeTruthy()
  })

  it('aktuell nennt die Version, die geprüft wurde', () => {
    const state: UpdateState = { phase: 'current', progress: null, current: '1.1.0' }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByTestId('update-state').textContent).toContain('1.1.0')
    expect(screen.queryByTestId('update-install')).toBeNull()
  })

  it('im Browser gibt es nichts zu installieren — der Weg führt zu den Releases', () => {
    const state: UpdateState = {
      phase: 'available',
      progress: null,
      current: '1.1.0',
      latest: '1.2.0',
      url: 'https://github.com/bemlerlabs/ephe/releases',
    }
    render(<UpdateDialog {...base} state={state} releasesUrl={state.url} />)
    expect(screen.getByTestId('update-install').textContent).toBe('Releases ansehen')
    expect(screen.getByTestId('update-releases-link').getAttribute('href')).toBe(state.url)
  })

  it('der Download zeigt eine Zahl, keine angedeutete Fortschrittssimulation', () => {
    const state: UpdateState = { phase: 'downloading', progress: 0.4, latest: '1.2.0' }
    render(<UpdateDialog {...base} state={state} />)
    const bar = screen.getByTestId('update-progress')
    expect(bar.getAttribute('role')).toBe('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('40')
  })

  it('installiert heißt bereit zum Neustart — und der Neustart ist die Handlung', () => {
    // The restart button belongs in the desktop build: in the browser there is
    // nothing the surface could restart. So the Tauri channel is put in place.
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {}
    const onRelaunch = vi.fn()
    const state: UpdateState = { phase: 'ready', progress: 1, latest: '1.2.0' }
    render(<UpdateDialog {...base} onRelaunch={onRelaunch} state={state} />)
    fireEvent.click(screen.getByTestId('update-relaunch'))
    expect(onRelaunch).toHaveBeenCalled()
    delete (window as unknown as Record<string, unknown>).__TAURI__
  })

  it('ohne Tauri-Kanal bleibt der Dialog bedienbar (Prüfung auslösen)', async () => {
    const onCheck = vi.fn()
    render(<UpdateDialog {...base} onCheck={onCheck} state={{ phase: 'idle', progress: null }} />)
    fireEvent.click(screen.getByTestId('update-recheck'))
    await waitFor(() => expect(onCheck).toHaveBeenCalled())
  })
})

describe('R2-U — die Zustandsmaschine', () => {
  const realFetch = global.fetch

  beforeEach(() => {
    vi.resetModules()
  })
  afterEach(() => {
    global.fetch = realFetch
  })

  it('ein error-Feld der Prüfung wird zu failed, nicht zu current', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        enabled: true,
        available: false,
        current: '1.1.0',
        error: 'HTTP Error 404: Not Found',
      }),
    })) as unknown as typeof fetch
    const { useUpdateCheck } = await import('@/lib/useUpdateCheck')
    let captured: UpdateState | undefined
    const Probe = () => {
      captured = useUpdateCheck().state
      return null
    }
    render(<Probe />)
    await waitFor(() => expect(captured?.phase).toBe('failed'))
    expect(captured?.reason).toContain('404')
  })

  it('antwortete die Quelle wirklich, ist current eine Aussage, keine Lücke', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ enabled: true, available: false, current: '1.1.0' }),
    })) as unknown as typeof fetch
    const { useUpdateCheck } = await import('@/lib/useUpdateCheck')
    let captured: UpdateState | undefined
    const Probe = () => {
      captured = useUpdateCheck().state
      return null
    }
    render(<Probe />)
    await waitFor(() => expect(captured?.phase).toBe('current'))
    expect(captured?.reason).toBeUndefined()
  })
})

describe('U-3 — the running phases read as themselves', () => {
  it('installing names the installation, not the download, and keeps the bar full', () => {
    const state: UpdateState = { phase: 'installing', progress: 1, latest: '1.2.0' }
    render(<UpdateDialog {...base} state={state} />)
    // No locale map for these two keys on purpose: the key that came out of
    // t() is the assertion, and no German product copy enters this file.
    expect(screen.getByText('update.titleInstalling')).toBeTruthy()
    expect(screen.queryByText('update.titleDownloading')).toBeNull()
    const bar = screen.getByTestId('update-progress')
    expect(bar.getAttribute('aria-valuenow')).toBe('100')
    expect(bar.getAttribute('data-indeterminate')).toBeNull()
    expect(screen.getByTestId('update-percent').textContent).toBe('update.percent')
  })

  it('a source that reports no total gets the band and claims no number', () => {
    const state: UpdateState = { phase: 'downloading', progress: null, latest: '1.2.0' }
    render(<UpdateDialog {...base} state={state} />)
    const bar = screen.getByTestId('update-progress')
    expect(bar.getAttribute('aria-valuenow')).toBeNull()
    expect(bar.getAttribute('data-indeterminate')).toBe('true')
    expect(screen.getByTestId('update-progress-fill').className).toContain('update-progress-sweep')
    expect(screen.queryByTestId('update-percent')).toBeNull()
  })

  it('a refused installer carries its own sentence in its own place', () => {
    const state: UpdateState = {
      phase: 'failed',
      progress: null,
      reason: 'the installer refused the bundle',
      failedAt: 'install',
    }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByText('update.titleInstallFailed')).toBeTruthy()
    expect(screen.getByText('update.installFailed')).toBeTruthy()
    expect(screen.queryByText('update.checkFailed')).toBeNull()
    expect(screen.getByTestId('update-reason').textContent).toBe('the installer refused the bundle')
  })
})
