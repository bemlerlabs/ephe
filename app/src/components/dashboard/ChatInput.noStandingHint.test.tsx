import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ChatInput from '@/components/dashboard/ChatInput'

// F1: the composer used to carry a standing sentence about an empty draft above
// its action row. It is gone; the disabled send button and the field's own label
// still say what the control is, and nothing instructs the user in the meantime.

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

const ta = () => screen.getByTestId('chat-input') as HTMLTextAreaElement
const sendBtn = () => screen.getByTestId('send-btn') as HTMLButtonElement

describe('the composer keeps no standing instruction', () => {
  it('an empty draft disables send without a sentence above the actions', () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(sendBtn().disabled).toBe(true)
    expect(screen.queryByTestId('composer-empty-send-hint')).toBeNull()
    const actions = screen.getByTestId('composer-actions-row')
    expect(actions.previousElementSibling?.tagName).toBe('TEXTAREA')
  })

  it('both controls keep a name a screen reader can read', () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(ta().getAttribute('aria-label')).toBeTruthy()
    expect(sendBtn().getAttribute('aria-label')).toBeTruthy()
  })

  it('the first typed character arms the button', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: 'hello world' } })
    expect(sendBtn().disabled).toBe(false)
  })
})
