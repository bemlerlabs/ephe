/**
 * Version & Updates on the About page: the status word, the facts the answer
 * carries, and the one button that asks again.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UpdateSection } from './UpdateSection'

const check = vi.fn()
const setOpen = vi.fn()
let state: Record<string, unknown> = {}

vi.mock('@/lib/useUpdateCheck', () => ({
  useUpdateCheck: () => ({ state, setOpen, check }),
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
})
