/**
 * Version & Updates on the About page: the status word, the facts the answer
 * carries, the one button that asks again, and the action the answer leads to —
 * the page that names the version takes the update the header takes, in the same
 * words, because both read `updateActionOf`. A state with nothing to click is
 * spoken for too: the page names the reason and the next step.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { UpdateSection } from './UpdateSection'
import { updateActionOf } from '@/lib/useUpdateCheck'
import type { UpdateState } from '@/lib/updateCheckRun'

const check = vi.fn()
const install = vi.fn()
const apply = vi.fn()
const relaunch = vi.fn()
let state: UpdateState = { phase: 'idle', progress: null }

vi.mock('@/lib/useUpdateCheck', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/useUpdateCheck')>()),
  useUpdateCheck: () => {
    const [open, setOpen] = useState(false)
    return { state, open, setOpen, check, install, apply, relaunch, restartBlocked: null }
  },
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

/** The answer the header's sheet acts on: merges on the default branch the
 *  backend said it can pull. */
const pullable: UpdateState = {
  phase: 'available',
  progress: null,
  current: '0.5.7',
  commit: '2a1405a8',
  latest: 'deadbeef',
  channel: 'main',
  commitsBehind: 3,
  url: 'https://example.invalid/compare/2a1405a8...main',
}

describe('UpdateSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    state = { phase: 'idle', progress: null }
  })

  it('names the state and shows the commit, and asks again on click', () => {
    state = {
      phase: 'current',
      progress: null,
      current: '0.5.1',
      commit: 'b7c9b576',
      channel: 'release',
    }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleCurrent')
    expect(screen.getByText('b7c9b576')).toBeTruthy()

    fireEvent.click(screen.getByTestId('settings-updates-check'))
    expect(check).toHaveBeenCalled()
  })

  it('reports the main channel with its distance instead of a release', () => {
    state = {
      phase: 'available',
      progress: null,
      current: '0.5.1',
      channel: 'main',
      commitsBehind: 3,
    }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.mainChannel')
    // A build without a commit names none — no empty row.
    expect(screen.queryByText('update.detailsCommit')).toBeNull()
  })

  it('opens the update sheet from the page that names the version', () => {
    state = {
      phase: 'available',
      progress: null,
      current: '0.5.1',
      latest: '0.5.2',
      channel: 'release',
      url: 'https://example.invalid/releases',
    }
    render(<UpdateSection />)
    expect(screen.queryByTestId('update-install')).toBeNull()

    fireEvent.click(screen.getByTestId('settings-updates-details'))

    // The sheet lives on this page now: a button that sets open state on a
    // dialog mounted elsewhere answers with nothing at all.
    expect(screen.getByTestId('update-install')).toBeTruthy()
  })

  it('says it is asking while the machine holds no answer', () => {
    state = { phase: 'idle', progress: null }
    render(<UpdateSection />)

    // The page used to print its own title here, which reads as an answer.
    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.checking')
    expect(screen.queryByTestId('settings-updates-apply')).toBeNull()
  })

  it('takes the update the header takes, in the header word, and names the run', () => {
    state = pullable
    const view = render(<UpdateSection />)
    const action = updateActionOf(pullable)

    expect(action).not.toBeNull()
    const button = screen.getByTestId('settings-updates-apply')
    expect(button.textContent).toBe(action?.labelKey)

    fireEvent.click(button)
    expect(apply).toHaveBeenCalledTimes(1)
    expect(install).not.toHaveBeenCalled()

    // The machine owns the answer for every surface: what it moves is what this
    // page says, and the button that started the run stands down while it runs.
    state = { ...pullable, phase: 'applying' }
    view.rerender(<UpdateSection />)
    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleApplying')
    expect(screen.queryByTestId('settings-updates-apply')).toBeNull()

    state = { ...pullable, phase: 'applied', current: 'deadbeef', restart: true }
    view.rerender(<UpdateSection />)
    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleApplied')
    expect(screen.queryByText('update.mainChannel')).toBeNull()
  })

  it('offers the sheet the same action the row offers, from one contract', () => {
    state = pullable
    render(<UpdateSection />)

    fireEvent.click(screen.getByTestId('settings-updates-details'))

    expect(screen.getByTestId('update-apply').textContent).toBe(
      screen.getByTestId('settings-updates-apply').textContent,
    )
    fireEvent.click(screen.getByTestId('update-apply'))
    expect(apply).toHaveBeenCalledTimes(1)
  })

  it('names the reason and the next step where no update can be taken', () => {
    state = { ...pullable, applyBlocked: 'not_a_checkout' }
    render(<UpdateSection />)

    expect(screen.queryByTestId('settings-updates-apply')).toBeNull()
    expect(screen.getByTestId('settings-updates-notice').textContent).toBe(
      'update.blocked.not_a_checkout',
    )
  })

  it('speaks for a refused run instead of going back to quiet', () => {
    state = {
      phase: 'failed',
      progress: null,
      failedAt: 'install',
      reasonCode: 'dirty_tree',
      reason: 'this checkout has local changes',
    }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleFailed')
    expect(screen.getByTestId('settings-updates-notice').textContent).toBe(
      'update.blocked.dirty_tree',
    )
  })

  it('points the browser surface at the release it cannot install', () => {
    state = {
      phase: 'available',
      progress: null,
      current: '0.5.7',
      latest: '0.5.8',
      channel: 'release',
      url: 'https://example.invalid/releases',
    }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleAvailable')
    expect(screen.getByTestId('settings-updates-notice').textContent).toBe('update.browserNote')
    expect(screen.queryByTestId('settings-updates-apply')).toBeNull()
  })
})
