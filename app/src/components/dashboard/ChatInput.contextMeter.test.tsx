import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ChatInput from '@/components/dashboard/ChatInput'

// F3 wiring: the composer owns no context data of its own, so this checks that
// what the chat surface hands down reaches the meter and the compact action.

vi.mock('@/lib/api', () => ({
  getModelProviders: () => Promise.reject(new Error('offline')),
  getSetupStatus: () => Promise.reject(new Error('offline')),
  getSettings: () => Promise.resolve({ workspace_dir: '/tmp/ws' }),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
  listSkills: () => Promise.resolve({ skills: [] }),
}))

describe('the composer context meter', () => {
  it('renders the handed-down fill', () => {
    render(
      <ChatInput
        onSend={vi.fn()}
        contextPercent={22}
        contextTokens={{ used: 1840, window: 8192 }}
      />,
    )
    expect(screen.getByTestId('composer-context-numbers').textContent).toBe(
      '22% · 1,840 / 8,192 tok',
    )
  })

  it('sends /compact through the slash channel, not as a message', () => {
    const onSend = vi.fn()
    const onSlashCommand = vi.fn()
    render(
      <ChatInput
        onSend={onSend}
        onSlashCommand={onSlashCommand}
        contextPercent={22}
        contextTokens={{ used: 1840, window: 8192 }}
      />,
    )
    fireEvent.click(screen.getByTestId('composer-compact'))
    expect(onSlashCommand).toHaveBeenCalledWith('/compact')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows no meter while the composer has no occupancy', () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.queryByTestId('composer-context-meter')).toBeNull()
  })
})
