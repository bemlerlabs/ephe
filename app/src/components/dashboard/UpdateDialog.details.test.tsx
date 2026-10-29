/**
 * U-4: the Details block names the package and repeats the release's own
 * words, and a restart with a running turn or an unsent draft is drawn as held
 * back instead of offered. The browser states what the surface can do there.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UpdateDialog } from './UpdateDialog'
import type { UpdateState } from '@/lib/updateCheckRun'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const noop = () => {}
const base = { open: true, onOpenChange: noop, onCheck: noop, onInstall: noop, onRelaunch: noop }

const available: UpdateState = {
  phase: 'available',
  progress: null,
  current: '0.1.0-beta.1',
  latest: '0.1.0-beta.2',
  notes: 'A release note the feed carried.',
}

describe('U-4 — Details carries what is being installed', () => {
  it('repeats the release notes in the words the feed used', () => {
    render(<UpdateDialog {...base} state={available} />)
    expect(screen.getByTestId('update-details-notes').textContent).toBe(
      'A release note the feed carried.',
    )
    expect(screen.getByTestId('update-details-version').textContent).toBe(
      '0.1.0-beta.1 → 0.1.0-beta.2',
    )
  })

  it('says the feed carried no notes instead of writing some', () => {
    render(<UpdateDialog {...base} state={{ ...available, notes: undefined }} />)
    expect(screen.getByTestId('update-details-notes').textContent).toBe('update.detailsNoNotes')
  })

  it('names the size and the package the transfer reported', () => {
    const state: UpdateState = {
      ...available,
      phase: 'downloading',
      progress: 0.5,
      sizeBytes: 4_000_000,
      asset: 'Ephe_0.1.0-beta.2_aarch64.app.tar.gz',
      platform: 'MacIntel',
    }
    render(<UpdateDialog {...base} state={state} />)
    expect(screen.getByTestId('update-details-size').textContent).toBe('4 MB')
    expect(screen.getByTestId('update-details-asset').textContent).toBe(
      'Ephe_0.1.0-beta.2_aarch64.app.tar.gz',
    )
    expect(screen.getByTestId('update-details-platform').textContent).toBe('MacIntel')
  })

  it('marks a value the source never reported', () => {
    render(<UpdateDialog {...base} state={available} />)
    expect(screen.getByTestId('update-details-size').textContent).toBe('update.detailsUnknown')
    expect(screen.getByTestId('update-details-asset').textContent).toBe('update.detailsUnknown')
  })

  it('keeps the details out of a state that has no release to describe', () => {
    render(
      <UpdateDialog {...base} state={{ phase: 'current', progress: null, current: '1.0.0' }} />,
    )
    expect(screen.queryByTestId('update-details')).toBeNull()
  })
})

describe('U-4 — a restart that would cost work', () => {
  it('holds the restart back while a turn runs, and says so', () => {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {}
    const state: UpdateState = { phase: 'ready', progress: 1, latest: '0.1.0-beta.2' }
    render(<UpdateDialog {...base} state={state} restartBlocked="running" />)
    expect(screen.getByTestId('update-relaunch').hasAttribute('disabled')).toBe(true)
    expect(screen.getByTestId('update-restart-blocked').textContent).toBe(
      'update.restartBlockedRunning',
    )
    delete (window as unknown as Record<string, unknown>).__TAURI__
  })

  it('offers the restart when nothing holds it', () => {
    ;(window as unknown as Record<string, unknown>).__TAURI__ = {}
    const state: UpdateState = { phase: 'ready', progress: 1, latest: '0.1.0-beta.2' }
    render(<UpdateDialog {...base} state={state} restartBlocked={null} />)
    expect(screen.getByTestId('update-relaunch').hasAttribute('disabled')).toBe(false)
    expect(screen.queryByTestId('update-restart-blocked')).toBeNull()
    delete (window as unknown as Record<string, unknown>).__TAURI__
  })
})

describe('U-4 — the browser states its own limit', () => {
  it('names what this surface can do and where the install happens', () => {
    render(
      <UpdateDialog {...base} state={available} releasesUrl="https://example.invalid/releases" />,
    )
    expect(screen.getByTestId('update-browser-note').textContent).toBe('update.browserNote')
    expect(screen.getByTestId('update-install').textContent).toBe('update.viewReleases')
    expect(screen.queryByTestId('update-relaunch')).toBeNull()
  })
})
