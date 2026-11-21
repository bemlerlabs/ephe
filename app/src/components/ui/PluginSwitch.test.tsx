import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import PluginSwitch from './PluginSwitch'

const labels = {
  on: 'On',
  off: 'Off',
  enabling: 'Enabling',
  disabling: 'Disabling',
  failed: 'Toggle failed',
}

function deferred() {
  let resolve!: () => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('PluginSwitch (P1)', () => {
  it('acknowledges immediately, follows the requested state while busy, and ignores a second click', async () => {
    const pending = deferred()
    const onToggle = vi.fn(() => pending.promise)
    render(
      <PluginSwitch
        name="Acme Research"
        checked={false}
        onToggle={onToggle}
        labels={labels}
        testid="acme-switch"
      />,
    )
    const control = screen.getByRole('switch', { name: 'Acme Research, Off' })
    fireEvent.click(control)
    fireEvent.click(control)

    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(control.getAttribute('aria-label')).toBe('Acme Research, On, Enabling')
    expect(control.getAttribute('aria-checked')).toBe('true')
    expect(control.getAttribute('aria-busy')).toBe('true')
    expect(screen.getByText('Enabling')).toBeTruthy()

    pending.resolve()
    await waitFor(() => expect(control.getAttribute('aria-busy')).toBe('false'))
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText('On')).toBeTruthy()
    expect(control.getAttribute('aria-checked')).toBe('true')
  })

  it('stays on after the parent commits a successful toggle', async () => {
    function Stateful() {
      const [checked, setChecked] = useState(false)
      return (
        <PluginSwitch
          name="Acme Research"
          checked={checked}
          onToggle={async (next) => {
            await Promise.resolve()
            setChecked(next)
          }}
          labels={labels}
          testid="acme-switch"
        />
      )
    }
    render(<Stateful />)
    const control = screen.getByTestId('acme-switch')
    fireEvent.click(control)

    await waitFor(() => expect(control.getAttribute('aria-busy')).toBe('false'))
    expect(screen.getByText('On')).toBeTruthy()
    expect(control.getAttribute('aria-checked')).toBe('true')
  })

  it('reverts the knob and announces the reason when activation fails', async () => {
    const pending = deferred()
    const onToggle = vi.fn(() => pending.promise)
    render(
      <PluginSwitch
        name="Acme Research"
        checked={false}
        onToggle={onToggle}
        labels={labels}
        testid="acme-switch"
        errorTestid="acme-switch-error"
      />,
    )
    fireEvent.click(screen.getByTestId('acme-switch'))
    pending.reject(new Error('activation failed'))

    await waitFor(() => expect(screen.getByTestId('acme-switch-error')).toBeTruthy())
    const control = screen.getByTestId('acme-switch')
    expect(control.getAttribute('aria-checked')).toBe('false')
    expect(control.getAttribute('aria-busy')).toBe('false')
    expect(screen.getByRole('alert').textContent).toContain('activation failed')
  })

  it('does not call the backend while disabled', () => {
    const onToggle = vi.fn()
    render(
      <PluginSwitch
        name="Acme Research"
        checked={true}
        onToggle={onToggle}
        labels={labels}
        testid="acme-switch"
        disabled
      />,
    )
    fireEvent.click(screen.getByTestId('acme-switch'))
    expect(onToggle).not.toHaveBeenCalled()
  })
})
