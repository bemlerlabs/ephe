/**
 * QA-E2E F6: the first screen after a cold open was the previous run's failed
 * tool bodies. This card is what stands in for that transcript until the reader
 * opens it or starts a new task.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import RestoredConversation from './RestoredConversation'

describe('RestoredConversation', () => {
  it('names the restored conversation and both ways on', () => {
    render(<RestoredConversation onShow={vi.fn()} onNewTask={vi.fn()} />)
    const card = screen.getByTestId('restored-conversation')
    expect(card.textContent).toContain('chat.restoredConversationTitle')
    expect(card.textContent).toContain('chat.restoredConversationBody')
    expect(screen.getByTestId('restored-conversation-show').textContent).toBe(
      'chat.restoredConversationShow',
    )
    expect(screen.getByTestId('restored-conversation-new').textContent).toContain('sidebar.newChat')
  })

  it('opens the transcript on request', () => {
    const onShow = vi.fn()
    render(<RestoredConversation onShow={onShow} onNewTask={vi.fn()} />)
    fireEvent.click(screen.getByTestId('restored-conversation-show'))
    expect(onShow).toHaveBeenCalledTimes(1)
  })

  it('offers the new task instead of the old failure', () => {
    const onNewTask = vi.fn()
    render(<RestoredConversation onShow={vi.fn()} onNewTask={onNewTask} />)
    fireEvent.click(screen.getByTestId('restored-conversation-new'))
    expect(onNewTask).toHaveBeenCalledTimes(1)
  })
})
