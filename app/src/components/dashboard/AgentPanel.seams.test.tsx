/**
 * I4-1: the seams of the agent panel are contract, not implementation.
 *
 * GIVEN  the pane with dock/resize, the tab registry, preview navigation and the
 *        PREVIEW_OPEN_EVENT listener without dependencies
 * THEN   a) the dock toggle driven by the window event flips in BOTH directions
 *           (the listener deliberately hangs on no deps list — a frozen closure
 *           would always set the same side),
 *        b) drag-resize persists the width and keeps the 360px … 60vw bounds,
 *        c) the []-listener reads refs: after state flips (tab open/closed, pane
 *           closed) it still toggles instead of computing against stale state,
 *        d) the late focus move after 60 ms stays out as soon as the keyboard is
 *           already inside the pane,
 *        e) the five localStorage keys and the hard data-testids stay reachable,
 *           and the PANEL_STATE_EVENT payload carries width/dock (the content
 *           column reports the width back as padding).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT, PANEL_STATE_EVENT } from '@/lib/panelEvents'

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  runShell: vi.fn(async () => ({ command: 'ls', output: 'a', ok: true })),
  runShellPty: vi.fn(async () => ({ command: 'ls', output: 'a', ok: true })),
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'p', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  synthesizeSpeech: vi.fn(async () => ''),
  fileUrl: vi.fn((p: string) => `/api/file?path=${p}`),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('./agent/LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

const P = (type: string, x: number) =>
  Object.assign(new Event(type, { bubbles: true }), { clientX: x })

function openPane() {
  act(() => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
  })
}

function openTab(tab: string) {
  act(() => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
  })
}

beforeEach(() => {
  localStorage.clear()
  window.matchMedia = vi.fn((q: string) => ({
    matches: false,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver
})

describe('I4-1 Naht Dock/Geometrie', () => {
  it('der Fenster-Umschalter flippt right -> left -> right und persistiert', async () => {
    render(<AgentPanel />)
    openPane()
    await screen.findByTestId('panel-resize-handle')
    expect(localStorage.getItem('ephe.panel.dock') ?? 'right').toBe('right')
    act(() => {
      window.dispatchEvent(new CustomEvent('ephe:panel-dock-toggle'))
    })
    expect(localStorage.getItem('ephe.panel.dock')).toBe('left')
    // Second throw: a frozen closure would set 'left' again here.
    act(() => {
      window.dispatchEvent(new CustomEvent('ephe:panel-dock-toggle'))
    })
    expect(localStorage.getItem('ephe.panel.dock')).toBe('right')
  })

  it('Drag an der Innenkante persistiert die gemessene Breite', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    openPane()
    const handle = await screen.findByTestId('panel-resize-handle')
    // Right dock: dragging to the left makes it wider (420 + 40).
    fireEvent(handle, P('pointerdown', 400))
    fireEvent(window, P('pointermove', 360))
    fireEvent(window, P('pointerup', 360))
    expect(localStorage.getItem('ephe.panel.width')).toBe('460')
  })

  it('Drag haelt die Untergrenze 360px', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    openPane()
    const handle = await screen.findByTestId('panel-resize-handle')
    fireEvent(handle, P('pointerdown', 10))
    fireEvent(window, P('pointermove', 900))
    fireEvent(window, P('pointerup', 900))
    expect(localStorage.getItem('ephe.panel.width')).toBe('360')
  })

  it('Drag haelt die Obergrenze 60vw', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    openPane()
    const handle = await screen.findByTestId('panel-resize-handle')
    fireEvent(handle, P('pointerdown', 900))
    fireEvent(window, P('pointermove', 0))
    fireEvent(window, P('pointerup', 0))
    expect(localStorage.getItem('ephe.panel.width')).toBe(
      String(Math.round(window.innerWidth * 0.6)),
    )
  })

  it('Left-Dock misst die Sidebar-Breite als linken Versatz', async () => {
    localStorage.setItem('ephe.panel.dock', 'left')
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    const sidebar = document.createElement('div')
    sidebar.setAttribute('data-testid', 'chat-sidebar')
    sidebar.getBoundingClientRect = () =>
      ({
        width: 288,
        height: 800,
        top: 0,
        left: 0,
        right: 288,
        bottom: 800,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect
    document.body.appendChild(sidebar)
    try {
      render(<AgentPanel />)
      openPane()
      const pane = await screen.findByTestId('panel-resize-handle')
      const aside = pane.parentElement as HTMLElement
      await vi.waitFor(() => expect(aside.style.left).toBe('288px'))
    } finally {
      sidebar.remove()
    }
  })
})

describe('I4-1 Naht Tab-Registry + Persistenz', () => {
  it('alle harten data-testids bleiben erreichbar', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'git']))
    render(<AgentPanel />)
    openPane()
    for (const id of [
      'panel-resize-handle',
      'panel-collapse-pane',
      'panel-add-tab',
      'panel-tab-pill-preview',
      'panel-tab-close-preview',
    ]) {
      expect(await screen.findByTestId(id), id).toBeTruthy()
    }
    // The "opened" rows live in the +-menu — open it first, then check.
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    expect(await screen.findByTestId('panel-add-menu')).toBeTruthy()
    expect(screen.getByTestId('panel-tab-search')).toBeTruthy()
    expect(screen.getByTestId('panel-new-tab-item-browser')).toBeTruthy()
    expect(screen.getByTestId('panel-open-tab-row-preview')).toBeTruthy()
    expect(screen.getByTestId('panel-open-tab-close-preview')).toBeTruthy()
  })

  it('der Leerzustand traegt die Offnen-Karten', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify([]))
    render(<AgentPanel />)
    openPane()
    expect(await screen.findByTestId('panel-empty-state')).toBeTruthy()
    expect(screen.getByTestId('panel-tab-card-preview')).toBeTruthy()
    fireEvent.click(screen.getByTestId('panel-tab-card-git'))
    expect(await screen.findByTestId('panel-tab-pill-git')).toBeTruthy()
  })

  it('die fuenf Schluessel werden geschrieben: tabs/activeTab/recent/dock/width', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'git']))
    render(<AgentPanel />)
    openPane()
    await screen.findByTestId('panel-tab-pill-git')
    fireEvent.click(screen.getByTestId('panel-tab-close-git'))
    expect(JSON.parse(localStorage.getItem('ephe.panel.tabs')!)).toEqual(['preview'])
    expect(JSON.parse(localStorage.getItem('ephe.panel.activeTab')!)).toBe('preview')
    const recent = JSON.parse(localStorage.getItem('ephe.panel.recent')!) as { tab: string }[]
    expect(recent[0]?.tab).toBe('git')
    // Restore via "last closed" in the +-menu.
    fireEvent.click(screen.getByTestId('panel-add-tab'))
    fireEvent.click(await screen.findByTestId('panel-recent-git'))
    expect(JSON.parse(localStorage.getItem('ephe.panel.tabs')!)).toEqual(['preview', 'git'])
    expect(localStorage.getItem('ephe.panel.recent')).toBe('[]')
    act(() => {
      window.dispatchEvent(new CustomEvent('ephe:panel-dock-toggle'))
    })
    expect(localStorage.getItem('ephe.panel.dock')).toBe('left')
    fireEvent.doubleClick(screen.getByTestId('panel-resize-handle'))
    expect(localStorage.getItem('ephe.panel.width')).toBe('420')
  })

  it('persistiertes browser alias-t auf das preview-Pane', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['browser']))
    localStorage.setItem('ephe.panel.activeTab', '"browser"')
    render(<AgentPanel />)
    openPane()
    expect(await screen.findByTestId('panel-tab-pill-preview')).toBeTruthy()
    expect(screen.queryByTestId('panel-tab-pill-browser')).toBeNull()
  })
})

describe('I4-1 Naht Preview-Listener (keine Deps, nur Refs)', () => {
  it('toggle oeffnet und schliesst ueber Zustandsumzuege hinweg', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    const { container } = render(<AgentPanel />)
    openPane()
    expect(await screen.findByTestId('panel-tab-pill-preview')).toBeTruthy()
    openTab('git')
    expect(await screen.findByTestId('panel-tab-pill-git')).toBeTruthy()
    // Pane closed (chevron), then toggled again: the []-listener has to read the
    // current state from the ref, not the one from the first render.
    fireEvent.click(screen.getByTestId('panel-collapse-pane'))
    await vi.waitFor(() => expect(container.textContent).toBe(''))
    openPane()
    expect(await screen.findByTestId('panel-tab-pill-git')).toBeTruthy()
    expect(screen.getByTestId('panel-tab-pill-preview')).toBeTruthy()
    openPane()
    await vi.waitFor(() => expect(container.textContent).toBe(''))
  })

  it('der Fokus-Nachzug ueberholt niemanden, der schon im Pane steht', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    openPane()
    const collapse = await screen.findByTestId('panel-collapse-pane')
    ;(collapse as HTMLElement).focus()
    expect(document.activeElement).toBe(collapse)
    act(() => {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: 'https://example.com/x' } }),
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    expect(document.activeElement).toBe(collapse)
    expect(screen.getByDisplayValue('https://example.com/x')).toBeTruthy()
  })

  it('von ausserhalb zieht der Fokus in die Adressleiste', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel />)
    openPane()
    await screen.findByTestId('panel-tab-pill-preview')
    act(() => {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: 'https://example.com/y' } }),
      )
    })
    const input = await screen.findByTestId('preview-url-input')
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200))
    })
    expect(document.activeElement).toBe(input)
  })
})

describe('I4-1 Naht PANEL_STATE_EVENT', () => {
  it('der Payload traegt open/tab/tabs/width/dock', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    localStorage.setItem('ephe.panel.width', '560')
    localStorage.setItem('ephe.panel.dock', 'left')
    const seen: Record<string, unknown>[] = []
    const listener = (e: Event) => seen.push((e as CustomEvent).detail ?? {})
    window.addEventListener(PANEL_STATE_EVENT, listener)
    try {
      render(<AgentPanel />)
      openTab('git')
      await screen.findByTestId('panel-tab-pill-git')
      // The panel also announces state on its own (mount, restore), so the last
      // event is not necessarily the one this action produced: on a loaded runner
      // one of those lands afterwards and the assertion read 'terminal'. The
      // event to check is therefore the one that carries the git payload.
      const opened = [...seen].reverse().find((e) => e.tab === 'git')
      expect(opened).toBeDefined()
      expect(opened!.open).toBe(true)
      expect(opened!.tabs).toEqual(expect.arrayContaining(['preview', 'git']))
      expect(opened!.width).toBe(560)
      expect(opened!.dock).toBe('left')
    } finally {
      window.removeEventListener(PANEL_STATE_EVENT, listener)
    }
  })
})
