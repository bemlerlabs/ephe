/**
 * The frame's one column after register #107: the two verbs it took over from the task
 * column (New task, Search), and the Task row that is both a place and the door to the
 * register. The rail is the only permanent column of the left edge, so what it holds and
 * what it opens is the whole answer to "where do I start, where do I find".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const createSession = vi.fn()

vi.mock('@/store/chatStore', () => ({
  useChatStore: (selector: (store: { createSession: typeof createSession }) => unknown) =>
    selector({ createSession }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

import NavRail from './NavRail'
import { SHELL_DESTINATIONS } from './shellNav'
import { registerOpen, setRegisterOpen } from '@/lib/taskRegister'

const catalog = (locale: 'en' | 'de'): Record<string, Record<string, string>> =>
  JSON.parse(readFileSync(join(process.cwd(), 'src/locales', `${locale}.json`), 'utf8'))

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

  it('every rail control carries a name and the same tooltip', () => {
    mount('/')
    const rows = Array.from(document.querySelectorAll<HTMLElement>('[data-tooltip]'))
    // +, search, task, tools, discover, workspaces, artifacts, knowledge, settings.
    expect(rows).toHaveLength(9)
    for (const row of rows) {
      const label = row.getAttribute('aria-label')
      expect(label && label.length).toBeGreaterThan(0)
      expect(row.getAttribute('data-tooltip')).toBe(label)
    }
  })

  it('names all nine rows in both shipped catalogs', () => {
    const en = catalog('en')
    const de = catalog('de')
    const keys = [
      ...SHELL_DESTINATIONS.map((d) => d.labelKey),
      'sidebar.newChat',
      'sidebar.actionSearch',
    ]
    for (const key of keys) {
      const [ns, leaf] = key.split('.') as [string, string]
      expect(en[ns]?.[leaf], `en ${key}`).toBeTruthy()
      expect(de[ns]?.[leaf], `de ${key}`).toBeTruthy()
    }
    // The places a German reader acts on are German words, not the English ones.
    expect(de.shell?.navTask).toBe('Aufgabe')
    expect(de.shell?.navSettings).toBe('Einstellungen')
    expect(de.shell?.navWorkspaces).toBe('Arbeitsbereiche')
  })

  it('a place keeps its own row lit and the register out of it', () => {
    mount('/discover')
    expect(screen.getByTestId('nav-rail-discover').getAttribute('data-active')).toBe('true')
    expect(screen.getByTestId('nav-rail-settings')).toBeTruthy()
  })
})
