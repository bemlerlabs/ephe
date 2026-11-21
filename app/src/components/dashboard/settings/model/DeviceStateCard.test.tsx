/**
 * F2 — the device card: it renders the declaration as the route answers it,
 * names what is protected, offers the clear only as a second click, and never
 * renders an empty area: loading, failure with a retry, and the honest
 * "nothing here yet" each get words.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const getDeviceState = vi.fn()
const forgetDevice = vi.fn()

vi.mock('@/lib/api', () => ({
  getDeviceState: () => getDeviceState(),
  forgetDevice: (body: unknown) => forgetDevice(body),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o ? `${k} ${JSON.stringify(o)}` : k),
    i18n: { language: 'en' },
  }),
}))

import { DeviceStateCard } from './DeviceStateCard'

/** The route's answer over a folder that ran: one file, one dir, one kept row, one leftover. */
const STATE = {
  root: '<home>/.ephe',
  declared: 57,
  present: 3,
  forgettable: 2,
  entries: [
    {
      name: 'sessions',
      kind: 'dir',
      holds: 'the task history and every transcript in it',
      writer: 'core/session.py',
      forgettable: true,
      present: true,
      bytes: 2048,
    },
    {
      name: 'settings.json',
      kind: 'file',
      holds: 'every setting saved in the app',
      writer: 'core/settings_schema.py',
      forgettable: true,
      present: true,
      bytes: 512,
    },
    {
      name: 'audit.log',
      kind: 'file',
      holds: 'every tool call, approval and refusal, append-only',
      writer: 'core/audit_log.py',
      forgettable: false,
      present: true,
      bytes: 128,
    },
  ],
  total_bytes: 2688,
  unnamed: ['engine.json.bak-2'],
}

beforeEach(() => {
  getDeviceState.mockReset()
  forgetDevice.mockReset()
  getDeviceState.mockResolvedValue(STATE)
})

describe('DeviceStateCard', () => {
  it('renders the listing with each entry, its hold and the measured total', async () => {
    render(<DeviceStateCard />)
    const row = await screen.findByTestId('device-entry-sessions')
    expect(row.textContent).toContain('the task history and every transcript in it')
    expect(screen.getByTestId('device-entry-settings.json')).toBeTruthy()
    expect(screen.getByTestId('device-entry-size-sessions').textContent).toContain('2 KB')
    expect(screen.getByTestId('device-state-total').textContent).toContain('2.7 KB')
    expect(screen.getByTestId('device-state-row').textContent).toContain('"declared":"57"')
  })

  it('marks the protected row and explains the keep', async () => {
    render(<DeviceStateCard />)
    const kept = await screen.findByTestId('device-entry-audit.log')
    expect(kept.textContent).toContain('settings.deviceStateProtected')
    expect(screen.getByTestId('device-state-protected-note').textContent).toContain(
      'settings.deviceStateProtectedHint',
    )
    // The leftover nobody declared is counted, and it is never a clear target.
    expect(screen.getByTestId('device-state-unnamed').textContent).toContain('"count":1')
  })

  it('clears only after the second click, and that click states what stays', async () => {
    forgetDevice.mockResolvedValue({
      removed: ['sessions', 'settings.json'],
      kept: ['audit.log'],
      unnamed: ['engine.json.bak-2'],
      root: '<home>/.ephe',
      dry_run: false,
    })
    render(<DeviceStateCard />)
    await screen.findByTestId('device-state-clear-row')

    fireEvent.click(screen.getByTestId('device-state-clear'))
    expect(forgetDevice).not.toHaveBeenCalled()
    // The confirm panel states both halves of the promise before it acts.
    const confirm = await screen.findByTestId('device-state-confirm')
    expect(screen.getByTestId('device-state-clear-row').textContent).toContain(
      'settings.deviceStateWillStay',
    )

    fireEvent.click(confirm)
    await waitFor(() => expect(forgetDevice).toHaveBeenCalledWith({ dry_run: false }))
    const outcome = await screen.findByTestId('device-state-outcome')
    expect(outcome.textContent).toContain('settings.deviceStateDone')
    expect(outcome.textContent).toContain('"kept":"1"')
    // The card re-reads the folder after the run: the third GET is the answer.
    await waitFor(() => expect(getDeviceState).toHaveBeenCalledTimes(2))
  })

  it('shows the loading words before the route answers', () => {
    getDeviceState.mockReturnValue(new Promise(() => {}))
    render(<DeviceStateCard />)
    expect(screen.getByTestId('device-state-loading').textContent).toContain(
      'settings.deviceStateLoading',
    )
  })

  it('refuses to render an empty area when the read failed, and offers a retry', async () => {
    getDeviceState.mockRejectedValue(new Error('down'))
    render(<DeviceStateCard />)
    await waitFor(() => expect(screen.getByTestId('device-state-failed')).toBeTruthy())
    expect(screen.getByTestId('device-state-failed').textContent).toContain(
      'settings.deviceStateFailed',
    )
    getDeviceState.mockResolvedValue(STATE)
    fireEvent.click(screen.getByTestId('device-state-retry'))
    await waitFor(() => expect(screen.getByTestId('device-state-total')).toBeTruthy())
  })

  it('says nothing here yet for a folder with no declared entry on disk', async () => {
    getDeviceState.mockResolvedValue({
      ...STATE,
      present: 0,
      entries: [],
      total_bytes: 0,
      unnamed: [],
    })
    render(<DeviceStateCard />)
    await waitFor(() =>
      expect(screen.getByTestId('device-state-row').textContent).toContain(
        'settings.deviceStateEmpty',
      ),
    )
    expect(screen.queryByTestId('device-state-clear')).toBeNull()
  })
})
