/**
 * Version & Updates on the About page: the status word, the facts the answer
 * carries, the one button that asks again, and the sheet the rest of the update
 * lives in — the page that names the version has to open it too.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { UpdateSection } from './UpdateSection'

const check = vi.fn()
const install = vi.fn()
const apply = vi.fn()
const relaunch = vi.fn()
let state: Record<string, unknown> = {}

vi.mock('@/lib/useUpdateCheck', () => ({
  useUpdateCheck: () => {
    const [open, setOpen] = useState(false)
    return { state, open, setOpen, check, install, apply, relaunch, restartBlocked: null }
  },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

describe('UpdateSection', () => {
  it('names the state and shows the commit, and asks again on click', () => {
    state = { phase: 'current', current: '0.5.1', commit: 'b7c9b576', channel: 'release' }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.titleCurrent')
    expect(screen.getByText('b7c9b576')).toBeTruthy()

    fireEvent.click(screen.getByTestId('settings-updates-check'))
    expect(check).toHaveBeenCalled()
  })

  it('reports the main channel with its distance instead of a release', () => {
    state = { phase: 'available', current: '0.5.1', channel: 'main', commitsBehind: 3 }
    render(<UpdateSection />)

    expect(screen.getByTestId('settings-updates-status').textContent).toBe('update.mainChannel')
    // A build without a commit names none — no empty row.
    expect(screen.queryByText('update.detailsCommit')).toBeNull()
  })

  it('opens the update sheet from the page that names the version', () => {
    state = {
      phase: 'available',
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
})
