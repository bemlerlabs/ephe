import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import SettingsPage from './SettingsPage'

vi.mock('@/components/dashboard/SettingsPanel', () => ({
  default: ({ isOpen, initialTab }: { isOpen: boolean; initialTab: string }) => (
    <div data-testid="settings-panel">{`${initialTab}:${String(isOpen)}`}</div>
  ),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/:tab" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SettingsPage', () => {
  it('opens the section named by the route', () => {
    renderAt('/settings/teams')
    expect(screen.getByTestId('settings-panel').textContent).toBe('teams:true')
  })

  it('falls back to the engine section for an unknown route', () => {
    renderAt('/settings/does-not-exist')
    expect(screen.getByTestId('settings-panel').textContent).toBe('engine:true')
  })

  it('opens the engine section at /settings', () => {
    renderAt('/settings')
    expect(screen.getByTestId('settings-panel').textContent).toBe('engine:true')
  })
})
