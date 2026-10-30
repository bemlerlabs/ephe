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
import type { UpdateState } from '@/lib/updateCheckRun'

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
        'update.mainChannel': '{{count}} new commits on main since your build.',
        'update.viewChanges': 'View changes',
        'update.applyNow': 'Update now',
        'update.applying': 'Pulling the newest commits and reinstalling.',
        'update.titleApplying': 'Updating',
        'update.applied': 'This installation runs the newest commits now.',
        'update.titleApplied': 'Updated',
        'update.stepPull': 'newest commits pulled',
        'update.stepInstall': 'environment and web app reinstalled',
        'update.reload': 'Reload',
        'update.getRelease': 'Get the release',
        'update.technical': 'Technical detail',
        'update.installFailed': 'The installation did not finish.',
        'update.blocked.not_a_checkout': 'Installed from a release; it updates by replacing the app.',
        'update.blocked.not_on_main': 'This checkout is on another branch.',
        'update.blocked.dirty_tree': 'This checkout has local changes.',
        'update.blocked.other': 'This build cannot pull by itself.',
      }
      const raw = map[key] ?? key
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, n: string) =>
        opts && opts[n] !== undefined ? String(opts[n]) : `{{${n}}}`,
      )
    },
  }),
}))

const noop = () => {}
const base = {
  open: true,
  onOpenChange: noop,
  onCheck: noop,
  onInstall: noop,
  onApply: noop,
  onRelaunch: noop,
}

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
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {
      core: { invoke: async () => undefined },
    }
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
    expect(screen.getByTestId('update-failed-sentence').textContent).toContain(
      'The installation did not finish.',
    )
    expect(screen.queryByText('update.checkFailed')).toBeNull()
    expect(screen.getByTestId('update-reason').textContent).toBe('the installer refused the bundle')
  })
})

describe('continuous channel — commits before the next tag', () => {
  const state: UpdateState = {
    phase: 'available',
    progress: null,
    channel: 'main',
    current: '0.6.0',
    commit: '2a1405a837f0',
    latest: 'deadbeefcafe',
    commitsBehind: 3,
    url: 'https://github.com/bemlerlabs/ephe/compare/2a1405a837f0...main',
    notes: 'fix(chat): quieter tool rows',
  }

  it('names the commit range and leads to the comparison instead of an install', () => {
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByTestId('update-state').textContent).toContain('3')
    expect(screen.getByTestId('update-stage').textContent).toContain('2a1405a837f0')
    expect(screen.getByTestId('update-stage').textContent).toContain('deadbeefcafe')
    expect(screen.getByTestId('update-main-link').getAttribute('href')).toBe(state.url)
    expect(screen.getByTestId('update-main-link').textContent).toBe('View changes')
  })

  it('offers neither an installer nor a release page', () => {
    render(<UpdateDialog {...base} state={state} releasesUrl="https://github.com/x/y/releases" />)
    expect(screen.queryByTestId('update-install')).toBeNull()
    expect(screen.queryByTestId('update-browser-note')).toBeNull()
  })
})

describe('applying a merge that has no release yet', () => {
  const found: UpdateState = {
    phase: 'available',
    progress: null,
    channel: 'main',
    commitsBehind: 2,
    commit: '2a1405a8',
    latest: 'deadbeef',
    url: 'https://github.com/bemlerlabs/ephe/compare/2a1405a8...main',
  }

  it('offers one button that takes the commits', () => {
    const onApply = vi.fn()
    render(<UpdateDialog {...base} state={found} onApply={onApply} />)
    fireEvent.click(screen.getByTestId('update-apply'))
    expect(onApply).toHaveBeenCalledTimes(1)
  })

  it('names the steps and offers the relaunch once it landed', () => {
    const state: UpdateState = {
      phase: 'applied',
      progress: null,
      restart: true,
      current: 'deadbeef',
      steps: [
        { name: 'pull', ok: true, detail: '' },
        { name: 'install', ok: true, detail: '' },
      ],
    }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByText('Updated')).toBeTruthy()
    expect(screen.getByTestId('update-steps').textContent).toContain('newest commits pulled')
    expect(screen.getByTestId('update-apply-relaunch')).toBeTruthy()
  })
})

describe('the commit path states its own closure', () => {
  const found: UpdateState = {
    phase: 'available',
    progress: null,
    channel: 'main',
    commitsBehind: 2,
    commit: '2a1405a8',
    latest: 'deadbeef',
    url: 'https://github.com/bemlerlabs/ephe/compare/2a1405a8...main',
    releaseUrl: 'https://github.com/bemlerlabs/ephe/releases/latest',
  }

  it('offers no pull when the backend cannot pull, and says why', () => {
    render(<UpdateDialog {...base} state={{ ...found, applyBlocked: 'not_a_checkout' }} />)
    expect(screen.queryByTestId('update-apply')).toBeNull()
    expect(screen.getByTestId('update-apply-blocked').textContent).toContain(
      'Installed from a release',
    )
    expect(screen.getByTestId('update-release-link').getAttribute('href')).toBe(found.releaseUrl)
  })

  it('keeps the pull when the backend answered that it can run it', () => {
    render(<UpdateDialog {...base} state={found} />)
    expect(screen.getByTestId('update-apply')).toBeTruthy()
    expect(screen.queryByTestId('update-apply-blocked')).toBeNull()
  })

  it('a structural refusal ends the retry loop instead of repeating it', () => {
    const state: UpdateState = {
      phase: 'failed',
      progress: null,
      failedAt: 'install',
      reasonCode: 'not_on_main',
      reason: 'this checkout is on a development branch, not on main',
      releaseUrl: 'https://github.com/bemlerlabs/ephe/releases/latest',
    }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByTestId('update-failed-sentence').textContent).toContain(
      'This checkout is on another branch.',
    )
    expect(screen.queryByTestId('update-recheck')).toBeNull()
    expect(screen.getByTestId('update-release-link')).toBeTruthy()
    expect(screen.getByTestId('update-reason').textContent).toContain('development branch')
  })

  it('a dirty tree stays retryable: clearing it is up to the user', () => {
    const state: UpdateState = {
      phase: 'failed',
      progress: null,
      failedAt: 'install',
      reasonCode: 'dirty_tree',
      reason: 'this checkout has local changes',
    }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByTestId('update-failed-sentence').textContent).toContain(
      'This checkout has local changes.',
    )
    expect(screen.getByTestId('update-recheck')).toBeTruthy()
  })
})
