import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import ChatInput from '@/components/dashboard/ChatInput'

// getModelProviders → the backend is offline, the model badge keeps its default
vi.mock('@/lib/api', () => ({
  getModelProviders: () => Promise.reject(new Error('offline')),
  // W19: the setup status feeds the engine-chip re-entry (offline → unchanged)
  getSetupStatus: () => Promise.reject(new Error('offline')),
  // Round 14: @-mentions need getSettings (workspace dir) + listFs
  getSettings: () => Promise.resolve({ workspace_dir: '/tmp/ws' }),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
  // R34: skill triggers fill the slash menu (loadSkillSlashCommands)
  listSkills: () =>
    Promise.resolve({
      skills: [
        { trigger: '/factory', description: 'Build a complete project from one brief' },
        { trigger: '/pdf', description: 'Create a PDF document' },
        { trigger: '/ephe', description: 'Ephe coding agent' },
      ],
    }),
}))

// Every mount in this file goes through these two. ChatInput writes state after mount
// (the draft read and the autosize pass), and with a bare render that update lands after
// RTL's own act scope has closed: React then prints "An update to ChatInput inside a test
// was not wrapped in act(...)" for it — 32 of them here and 87 in ChatInput.p3.test.tsx
// (measured 2026-11-23 with `CI=true pnpm exec vitest run --maxWorkers=1 <file>`). The
// tick inside the act scope is what the update needs to arrive while it is still open.
let lastView: RenderResult | null = null

async function mountComposer(ui: ReactElement): Promise<RenderResult> {
  let view!: RenderResult
  await act(async () => {
    view = render(ui)
    lastView = view
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  return view
}

async function repaint(ui: ReactElement): Promise<void> {
  const view = lastView
  if (!view) throw new Error('repaint before mountComposer')
  await act(async () => {
    view.rerender(ui)
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

const ta = () => screen.getByRole('textbox') as HTMLTextAreaElement

describe('ChatInput slash commands (phase F)', () => {
  it('an exact command plus Enter calls onSlashCommand and never onSend', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/help' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/help')
    expect(onSend).not.toHaveBeenCalled()
    // the input is empty afterwards
    expect(ta().value).toBe('')
  })

  it('a prefix plus Enter takes the suggestion with its leading slash (regression fix)', async () => {
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={vi.fn()} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/comp' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    // the suggestion is taken over, the slash survives — otherwise the next
    // Enter would send the message instead of the command.
    expect(ta().value).toBe('/compact')
    expect(onSlash).not.toHaveBeenCalled()
  })

  it('an ordinary message goes to onSend and never to onSlashCommand', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: 'Hallo' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('Hallo', undefined)
    expect(onSlash).not.toHaveBeenCalled()
  })

  it('without onSlashCommand a slash input goes to onSend (backwards compatible)', async () => {
    const onSend = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} />)
    fireEvent.change(ta(), { target: { value: '/help' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('/help', undefined)
  })

  it('the screenshot entry sits in the plus menu only with getDisplayMedia (P6/ref-23)', async () => {
    // jsdom: no getDisplayMedia → the menu entry is absent
    const first = await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(first.getByTestId('composer-attach-plus'))
    expect(first.queryByTestId('composer-attach-screenshot')).toBeNull()
    first.unmount()

    // simulate desktop chrome → the entry appears in the opened menu
    const md = navigator.mediaDevices as MediaDevices
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { ...md, getDisplayMedia: vi.fn() },
    })
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    expect(screen.getByTestId('composer-attach-screenshot')).toBeTruthy()
  })

  it('R34: the slash menu is height-capped and scrolls internally (judge fix)', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    const menu = await screen.findByTestId('slash-menu')
    const scroller = menu.querySelector('[data-testid="slash-menu-scroll"]')
    expect(scroller).toBeTruthy()
    // Regression lock: without a height cap the list grows past the viewport at
    // 60+ entries and cuts the app commands off at the top.
    expect(scroller!.className).toContain('overflow-y-auto')
    expect(scroller!.className).toContain('max-h-')
  })

  it('R34: skill entries appear grouped under headers', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/fac' } })
    // Mocked listSkills delivers /factory → it must show up as a menu row,
    // under a dedicated skills group header (testids keep this i18n-stable).
    expect(await screen.findByText('/factory')).toBeTruthy()
    const menu = await screen.findByTestId('slash-menu')
    expect(menu.querySelector('[data-testid="slash-group-skills"]')).toBeTruthy()
    expect(menu.querySelector('[data-testid="slash-group-commands"]')).toBeNull()
    fireEvent.change(ta(), { target: { value: '/comp' } })
    expect(screen.getByText('/compact')).toBeTruthy()
    expect(
      screen.getByTestId('slash-menu').querySelector('[data-testid="slash-group-commands"]'),
    ).toBeTruthy()
  })

  it('R34: clicking a skill row puts "/factory" into the input', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/fac' } })
    fireEvent.click(await screen.findByText('/factory'))
    expect(ta().value).toBe('/factory')
  })

  it('R33: ArrowDown walks the highlight, Enter picks the highlighted row', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    const menu = await screen.findByTestId('slash-menu')
    const selected = () => menu.querySelectorAll('[role="option"][aria-selected="true"]')
    expect(selected()).toHaveLength(1)
    const firstId = (selected()[0] as HTMLElement).id
    fireEvent.keyDown(ta(), { key: 'ArrowDown' })
    const secondId = (selected()[0] as HTMLElement).id
    expect(secondId).not.toBe(firstId)
    fireEvent.keyDown(ta(), { key: 'Enter' })
    // The highlighted command lands in the input, leading slash preserved.
    expect(ta().value.startsWith('/')).toBe(true)
    expect(ta().value.length).toBeGreaterThan(1)
  })

  it('R33: Escape dismisses the menu and keeps the draft + focus target', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    await screen.findByTestId('slash-menu')
    fireEvent.keyDown(ta(), { key: 'Escape' })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    // Dismissal must not destroy what the user typed.
    expect(ta().value).toBe('/')
  })

  it('B14: Tab closes the slash menu and lets focus leave the composer', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    await screen.findByTestId('slash-menu')
    // Tab is the page's: it must not be read as a pick (the old branch inserted
    // the first suggestion and kept the caret in the field).
    fireEvent.keyDown(ta(), { key: 'Tab' })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    expect(ta().value).toBe('/')
  })

  it('P3: dropping a file on the input zone adds an attachment chip', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    const file = new File(['hallo'], 'test.txt', { type: 'text/plain' })
    const dt = {
      types: ['Files'],
      files: [file],
      data: { getData: () => '', setData: () => {} },
    } as unknown as DataTransfer
    // Drop zone = the outer container (the parent of the glass-control input)
    const zone = screen.getByRole('textbox').closest('.glass-control')?.parentElement
    expect(zone).toBeTruthy()
    fireEvent.dragOver(zone!, { dataTransfer: dt })
    fireEvent.drop(zone!, { dataTransfer: dt })
    expect(await screen.findByText('test.txt')).toBeTruthy()
  })
})

describe('ChatInput draftSeed (welcome cards)', () => {
  it('seeds the textarea from the parent-owned seed without sending', async () => {
    const onSend = vi.fn()
    await mountComposer(
      <ChatInput onSend={onSend} draftSeed={{ text: 'Build a landing page', nonce: 1 }} />,
    )
    expect(ta().value).toBe('Build a landing page')
    expect(onSend).not.toHaveBeenCalled()
    // A new nonce with the same text re-seeds after the user cleared it.
    fireEvent.change(ta(), { target: { value: '' } })
    await repaint(
      <ChatInput onSend={onSend} draftSeed={{ text: 'Build a landing page', nonce: 2 }} />,
    )
    expect(ta().value).toBe('Build a landing page')
  })

  it('null seed keeps the draft untouched', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} draftSeed={null} />)
    fireEvent.change(ta(), { target: { value: 'manual' } })
    expect(ta().value).toBe('manual')
  })
})

describe('ChatInput queue auto-flush (DD-01)', () => {
  it('flushes the queued message automatically when the stream settles', async () => {
    const onSend = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} streaming={false} />)
    // Turn runs → user presses Enter mid-stream → message lands in the queue.
    await repaint(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'queued one' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText(/queue/i)).toBeTruthy()
    // Stream settles → the queue must flush on its own (owner-visible bug DD-01).
    await repaint(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledWith('queued one', undefined)
    expect(screen.queryByText(/queue/i)).toBeNull()
  })

  it('one item per stream end: FIFO chain across two settle transitions', async () => {
    const onSend = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} streaming={false} />)
    await repaint(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'first' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    fireEvent.change(ta(), { target: { value: 'second' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    await repaint(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend.mock.calls[0]).toEqual(['first', undefined])
    await repaint(<ChatInput onSend={onSend} streaming={true} />)
    await repaint(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledTimes(2)
    expect(onSend.mock.calls[1]).toEqual(['second', undefined])
  })

  it('queued slash item goes through onSlashCommand on auto-flush', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={false} />)
    await repaint(<ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={true} />)
    fireEvent.change(ta(), { target: { value: '/compact' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).not.toHaveBeenCalled()
    await repaint(<ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={false} />)
    expect(onSlash).toHaveBeenCalledWith('/compact')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('a live draft is never stolen: flush waits for an empty composer', async () => {
    const onSend = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} streaming={false} />)
    await repaint(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'queued' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    fireEvent.change(ta(), { target: { value: 'user is typing' } })
    await repaint(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('user is typing')
    expect(screen.getByText(/queue/i)).toBeTruthy()
  })
})

// ── I6 P1-3: the Enter after a slash pick must not be swallowed ─────────────
// Regression pins: the chat stream deep test (2026-09-08) found that "/ephe <task>"
// with an argument — the Enter landed in the slash autocomplete and replaced the
// input with the bare command line (argument lost, nothing sent).
describe('ChatInput Enter versus the slash menu (I6 P1-3)', () => {
  it('/command <argument> plus Enter sends the full text (menu closed after a space)', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/ephe baue ein python-projekt' } })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    fireEvent.keyDown(ta(), { key: 'Enter' })
    // the parent routes the skill command — the FULL text has to arrive.
    expect(onSlash).toHaveBeenCalledWith('/ephe baue ein python-projekt')
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('')
  })

  it('a prefix pick with an argument: "/pd" to "/pdf", type on, Enter sends "/pdf bericht"', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/pd' } })
    // skill triggers load asynchronously — wait for the command row.
    await screen.findByText('/pdf')
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(ta().value).toBe('/pdf')
    fireEvent.change(ta(), { target: { value: '/pdf mein bericht' } })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/pdf mein bericht')
    expect(ta().value).toBe('')
  })

  it('Escape releases the menu: Enter then sends the raw text over completing', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/co' } })
    await screen.findByTestId('slash-menu')
    fireEvent.keyDown(ta(), { key: 'Escape' })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/co')
    expect(ta().value).toBe('')
  })

  it('W10-P1-1: Enter does not send during a running IME composition', async () => {
    const onSend = vi.fn()
    await mountComposer(<ChatInput onSend={onSend} onSlashCommand={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: 'にほん' } })
    // jsdom does not set isComposing through the init dict — shadow the
    // prototype getter on the instance, as a real browser delivers it mid-composition.
    const mk = (composing: boolean) => {
      const ev = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
      Object.defineProperty(ev, 'isComposing', { value: composing })
      return ev
    }
    act(() => {
      ta().dispatchEvent(mk(true))
    })
    expect(onSend).not.toHaveBeenCalled()
    act(() => {
      ta().dispatchEvent(mk(false))
    })
    expect(onSend).toHaveBeenCalledWith('にほん', undefined)
  })
})

// ── P1-4: viewport-wide drag-and-drop (not just the composer zone) ──────────
describe('ChatInput viewport drag-and-drop (P1-4)', () => {
  const fileDt = (files: File[] = []) =>
    ({
      types: ['Files'],
      files,
      data: { getData: () => '', setData: () => {} },
    }) as unknown as DataTransfer

  it('a file drag in the viewport shows the drop overlay', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    act(() => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt() })
    })
    expect(screen.getByTestId('viewport-drop-overlay')).toBeTruthy()
  })

  it('a drop on document.body, away from the composer, still attaches the file', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    const file = new File(['x'], 'body.txt', { type: 'text/plain' })
    await act(async () => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt([file]) })
      fireEvent.drop(document.body, { dataTransfer: fileDt([file]) })
    })
    expect(await screen.findByText('body.txt')).toBeTruthy()
    // the overlay disappears after the drop.
    expect(screen.queryByTestId('viewport-drop-overlay')).toBeNull()
  })

  it('a non-file drag such as text shows no overlay', async () => {
    await mountComposer(<ChatInput onSend={vi.fn()} />)
    const textDt = {
      types: ['text/plain'],
      files: [],
      data: { getData: () => '', setData: () => {} },
    } as unknown as DataTransfer
    act(() => {
      fireEvent.dragEnter(window, { dataTransfer: textDt })
    })
    expect(screen.queryByTestId('viewport-drop-overlay')).toBeNull()
  })
})

// ── P0-3: Esc aborts a running turn (Cockpit "ESC-cancel") ───────────────────
describe('ChatInput Esc → stop generation (P0-3)', () => {
  const escOnWindow = () =>
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })

  it('calls onStop while streaming', async () => {
    const onStop = vi.fn()
    await mountComposer(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    escOnWindow()
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('at idle (streaming=false) Esc stays unbound from onStop', async () => {
    const onStop = vi.fn()
    await mountComposer(<ChatInput onSend={vi.fn()} streaming={false} onStop={onStop} />)
    escOnWindow()
    expect(onStop).not.toHaveBeenCalled()
  })

  it('an open slash menu wins: Esc only dismisses and never calls onStop', async () => {
    const onStop = vi.fn()
    await mountComposer(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    await screen.findByTestId('slash-menu')
    escOnWindow()
    expect(onStop).not.toHaveBeenCalled()
  })
})
