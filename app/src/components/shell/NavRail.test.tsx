/**
 * The frame's one column after register #107: the two verbs it took over from the task
 * column (New task, Search), and the Task row that is both a place and the door to the
 * register. The rail is the only permanent column of the left edge, so what it holds and
 * what it opens is the whole answer to "where do I start, where do I find".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const createSession = vi.fn()

vi.mock('@/store/chatStore', () => ({
  useChatStore: (selector: (store: { createSession: typeof createSession }) => unknown) =>
    selector({ createSession }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

import NavRail from './NavRail'
import { registerOpen, setRegisterOpen } from '@/lib/taskRegister'

function mount(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <NavRail />
    </MemoryRouter>,
  )
}

/** The palette answers a chord, so a click is measured by the key it asks for. */
function catchKeydown(run: () => void): KeyboardEvent[] {
  const seen: KeyboardEvent[] = []
  const catcher = (e: KeyboardEvent) => seen.push(e)
  window.addEventListener('keydown', catcher)
  try {
    run()
  } finally {
    window.removeEventListener('keydown', catcher)
  }
  return seen
}

beforeEach(() => {
  createSession.mockReset()
  localStorage.clear()
  setRegisterOpen(true)
})

describe('NavRail', () => {
  it('starts the task and asks for the palette, the two verbs the column used to hold', () => {
    mount('/discover')
    fireEvent.click(screen.getByTestId('new-session'))
    expect(createSession).toHaveBeenCalledTimes(1)

    const keys = catchKeydown(() => fireEvent.click(screen.getByTestId('nav-rail-search')))
    expect(keys.find((e) => e.metaKey && e.key === 'k')).toBeTruthy()
  })

  it('the Task row opens and closes the register where it stands', () => {
    mount('/')
    const row = screen.getByTestId('nav-rail-task')
    expect(row.getAttribute('aria-expanded')).toBe('true')
    expect(row.getAttribute('aria-controls')).toBe('chat-sidebar')

    fireEvent.click(row)
    expect(registerOpen()).toBe(false)
    expect(screen.getByTestId('nav-rail-task').getAttribute('aria-expanded')).toBe('false')

    fireEvent.click(screen.getByTestId('nav-rail-task'))
    expect(registerOpen()).toBe(true)
  })

  it('from another place the same row goes to the chat and shows what it holds', () => {
    setRegisterOpen(false)
    mount('/tools')
    fireEvent.click(screen.getByTestId('nav-rail-task'))
    expect(registerOpen()).toBe(true)
    // The row is not the current page here, so it names no panel it cannot control.
    expect(screen.getByTestId('nav-rail-task').getAttribute('aria-controls')).toBeNull()
  })

  it('a place keeps its own row lit and the register out of it', () => {
    mount('/discover')
    expect(screen.getByTestId('nav-rail-discover').getAttribute('data-active')).toBe('true')
    expect(screen.getByTestId('nav-rail-settings')).toBeTruthy()
  })
})
