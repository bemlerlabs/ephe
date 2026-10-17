import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TaskDock } from './TaskDock'
import { useChatStore } from '@/store/chatStore'
import type { ChatMessage } from '@/types'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

let wideScreen = true

const message = () => ({ id: 'm1', role: 'user', content: 'hello', timestamp: 1 }) as ChatMessage
const session = (id: string, title: string, count = 1) => ({
  id,
  title,
  messages: Array.from({ length: count }, message),
  createdAt: 1,
})

describe('TaskDock', () => {
  beforeEach(() => {
    wideScreen = true
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: wideScreen,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    }))
    const first = session('s1', 'First task')
    const second = session('s2', 'Second task')
    useChatStore.setState({
      sessions: [first, second],
      currentSession: first,
      activeSessionId: first.id,
    })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    act(() => {
      useChatStore.setState({ sessions: [], currentSession: null, activeSessionId: null })
    })
  })

  it('stays away until the chat has messages', () => {
    render(<TaskDock messages={[]} />)
    expect(screen.queryByTestId('task-dock')).toBeNull()
  })

  it('lists the tasks once the chat starts and switches on a row', async () => {
    render(<TaskDock messages={[message()]} />)
    expect(screen.getByTestId('task-dock')).toBeTruthy()
    expect(screen.getByTestId('task-dock-row-s1')).toBeTruthy()
    fireEvent.click(screen.getByTestId('task-dock-row-s2'))
    await waitFor(() => expect(useChatStore.getState().activeSessionId).toBe('s2'))
  })

  it('shows the plan steps and the project branch when they exist', () => {
    render(
      <TaskDock
        messages={[message()]}
        plan={{ items: [{ status: 'active', text: 'Step one' }], done: 0, total: 1 }}
        headerMeta={{ git: true, branch: 'main' }}
      />,
    )
    expect(screen.getByText('Step one')).toBeTruthy()
    expect(screen.getByText('main')).toBeTruthy()
  })

  it('collapses into a pill and dismisses for the session', () => {
    render(<TaskDock messages={[message()]} />)
    fireEvent.click(screen.getByTestId('task-dock-collapse'))
    expect(screen.getByTestId('task-dock-pill')).toBeTruthy()
    fireEvent.click(screen.getByTestId('task-dock-pill'))
    fireEvent.click(screen.getByTestId('task-dock-dismiss'))
    expect(screen.queryByTestId('task-dock')).toBeNull()
  })

  it('starts as a pill on a narrow column', () => {
    wideScreen = false
    render(<TaskDock messages={[message()]} />)
    expect(screen.getByTestId('task-dock-pill')).toBeTruthy()
    expect(screen.queryByTestId('task-dock')).toBeNull()
  })

  it('keeps the collapsed choice when the task changes', () => {
    render(<TaskDock messages={[message()]} />)
    fireEvent.click(screen.getByTestId('task-dock-collapse'))
    act(() => {
      const second = useChatStore.getState().sessions.find((s) => s.id === 's2')!
      useChatStore.setState({ currentSession: second, activeSessionId: second.id })
    })
    expect(screen.getByTestId('task-dock-pill')).toBeTruthy()
    expect(screen.queryByTestId('task-dock')).toBeNull()
  })

  it('opens a panel destination', () => {
    const listener = vi.fn()
    window.addEventListener('ephe:preview-open', listener)
    render(<TaskDock messages={[message()]} />)
    fireEvent.click(screen.getByTestId('task-dock-tool-files'))
    const detail = (listener.mock.calls[0]![0] as CustomEvent).detail
    expect(detail.tab).toBe('files')
    window.removeEventListener('ephe:preview-open', listener)
  })
})
