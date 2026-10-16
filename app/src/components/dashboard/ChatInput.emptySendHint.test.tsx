import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ChatInput from '@/components/dashboard/ChatInput'

// Walkthrough finding: an empty or a whitespace-only draft turns the send
// button off and says nothing about why. The composer now carries the reason
// itself, as a status line a screen reader also reaches.

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

const EMPTY_SEND_HINT = 'Type a message first — sending stays off while the draft is empty'

const ta = () => screen.getByTestId('chat-input') as HTMLTextAreaElement
const sendBtn = () => screen.getByTestId('send-btn') as HTMLButtonElement
const hint = () => screen.queryByTestId('composer-empty-send-hint')

describe('the composer explains a disabled send', () => {
  it('an empty draft names the reason instead of leaving the dead button silent', () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(sendBtn().disabled).toBe(true)
    expect(hint()).toBeTruthy()
    expect(hint()!.getAttribute('role')).toBe('status')
    expect(hint()!.textContent).toBe(EMPTY_SEND_HINT)
  })

  it('a whitespace-only draft reads the same sentence', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '   ' } })
    expect(sendBtn().disabled).toBe(true)
    expect(hint()).toBeTruthy()
  })

  it('the first typed character clears it and the button goes live', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: 'hello world' } })
    expect(hint()).toBeNull()
    expect(sendBtn().disabled).toBe(false)
  })

  it('during a turn the placeholder carries the state, so the hint stays quiet', () => {
    render(<ChatInput onSend={vi.fn()} streaming />)
    expect(hint()).toBeNull()
  })

  it('a composer blocked for another reason does not invite typing', () => {
    render(<ChatInput onSend={vi.fn()} disabled />)
    expect(sendBtn().disabled).toBe(true)
    expect(hint()).toBeNull()
  })
})
