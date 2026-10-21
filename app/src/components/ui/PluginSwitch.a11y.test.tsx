import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import PluginSwitch from './PluginSwitch'

const labels = {
  on: 'On',
  off: 'Off',
  enabling: 'Enabling',
  disabling: 'Disabling',
  failed: 'Toggle failed',
}

describe('PluginSwitch accessibility (A11Y-01..03)', () => {
  it('names the role, state and pending verb', () => {
    render(
      <PluginSwitch
        name="Acme Research"
        checked={false}
        onToggle={() => new Promise(() => {})}
        labels={labels}
        testid="acme-switch"
      />,
    )
    const control = screen.getByRole('switch', { name: 'Acme Research, Off' })
    expect(control.getAttribute('aria-checked')).toBe('false')
    expect(control.getAttribute('aria-busy')).toBe('false')
    fireEvent.click(control)
    expect(control.getAttribute('aria-label')).toBe('Acme Research, On, Enabling')
    expect(control.getAttribute('aria-busy')).toBe('true')
  })

  it('toggles from Space and Enter, keeps focus, and carries the target and reduced-motion classes', async () => {
    const onToggle = vi.fn()
    render(
      <PluginSwitch
        name="Acme Research"
        checked={false}
        onToggle={onToggle}
        labels={labels}
        testid="acme-switch"
      />,
    )
    const control = screen.getByTestId('acme-switch')
    control.focus()
    fireEvent.keyDown(control, { key: ' ' })
    await waitFor(() => expect(onToggle).toHaveBeenCalledTimes(1))
    expect(onToggle).toHaveBeenCalledWith(true)
    fireEvent.keyDown(control, { key: 'Enter' })
    await waitFor(() => expect(onToggle).toHaveBeenCalledTimes(2))
    expect(document.activeElement).toBe(control)
    expect(control.className).toContain('after:-inset-2.5')
    expect(control.className).toContain('motion-reduce:transition-none')
  })

  it('announces the server failure reason in the visible row', async () => {
    const onToggle = vi.fn(() => Promise.reject(new Error('dependency base-pack is off')))
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
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.getByRole('alert').textContent).toContain('dependency base-pack is off')
    expect(screen.getByTestId('acme-switch').getAttribute('aria-checked')).toBe('false')
  })
})
