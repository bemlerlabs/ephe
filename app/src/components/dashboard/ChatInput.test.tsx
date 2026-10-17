import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
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

const ta = () => screen.getByRole('textbox') as HTMLTextAreaElement

describe('ChatInput Slash-Commands (Phase F)', () => {
  it('exaktes Kommando + Enter → onSlashCommand (kein onSend)', () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/help' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/help')
    expect(onSend).not.toHaveBeenCalled()
    // the input is empty afterwards
    expect(ta().value).toBe('')
  })

  it('Prefix + Enter → Vorschlag mit führendem "/" übernehmen (Regressions-Fix)', () => {
    const onSlash = vi.fn()
    render(<ChatInput onSend={vi.fn()} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/comp' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    // the suggestion is taken over, the slash survives — otherwise the next
    // Enter would send the message instead of the command.
    expect(ta().value).toBe('/compact')
    expect(onSlash).not.toHaveBeenCalled()
  })

  it('normale Nachricht → onSend, nicht onSlashCommand', () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: 'Hallo' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('Hallo', undefined)
    expect(onSlash).not.toHaveBeenCalled()
  })

  it('ohne onSlashCommand: "/"-Input geht an onSend (backwards-kompatibel)', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    fireEvent.change(ta(), { target: { value: '/help' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('/help', undefined)
  })

  it('Screenshot-Eintrag im Plus-Menü nur wenn getDisplayMedia verfügbar (P6/ref-23)', () => {
    // jsdom: no getDisplayMedia → the menu entry is absent
    const first = render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(first.getByTestId('composer-attach-plus'))
    expect(first.queryByTestId('composer-attach-screenshot')).toBeNull()
    first.unmount()

    // simulate desktop chrome → the entry appears in the opened menu
    const md = navigator.mediaDevices as MediaDevices
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { ...md, getDisplayMedia: vi.fn() },
    })
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    expect(screen.getByTestId('composer-attach-screenshot')).toBeTruthy()
  })

  it('R34: Slash-Menü ist nach oben begrenzt und scrollt intern (Judge-Fix)', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    const menu = await screen.findByTestId('slash-menu')
    const scroller = menu.querySelector('[data-testid="slash-menu-scroll"]')
    expect(scroller).toBeTruthy()
    // Regression lock: without a height cap the list grows past the viewport at
    // 60+ entries and cuts the app commands off at the top.
    expect(scroller!.className).toContain('overflow-y-auto')
    expect(scroller!.className).toContain('max-h-')
  })

  it('R34: Skill-Einträge erscheinen gruppiert mit Köpfen', async () => {
    render(<ChatInput onSend={vi.fn()} />)
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

  it('R34: Klick auf Skill-Zeile setzt "/factory" ins Eingabefeld', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/fac' } })
    fireEvent.click(await screen.findByText('/factory'))
    expect(ta().value).toBe('/factory')
  })

  it('R33: ArrowDown walks the highlight, Enter picks the highlighted row', async () => {
    render(<ChatInput onSend={vi.fn()} />)
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
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    await screen.findByTestId('slash-menu')
    fireEvent.keyDown(ta(), { key: 'Escape' })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    // Dismissal must not destroy what the user typed.
    expect(ta().value).toBe('/')
  })

  it('P3: Datei-Drop auf Input-Zone → Attachment-Chip', async () => {
    render(<ChatInput onSend={vi.fn()} />)
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
  it('seeds the textarea from the parent-owned seed without sending', () => {
    const onSend = vi.fn()
    const { rerender } = render(
      <ChatInput onSend={onSend} draftSeed={{ text: 'Build a landing page', nonce: 1 }} />,
    )
    expect(ta().value).toBe('Build a landing page')
    expect(onSend).not.toHaveBeenCalled()
    // A new nonce with the same text re-seeds after the user cleared it.
    fireEvent.change(ta(), { target: { value: '' } })
    rerender(<ChatInput onSend={onSend} draftSeed={{ text: 'Build a landing page', nonce: 2 }} />)
    expect(ta().value).toBe('Build a landing page')
  })

  it('null seed keeps the draft untouched', () => {
    render(<ChatInput onSend={vi.fn()} draftSeed={null} />)
    fireEvent.change(ta(), { target: { value: 'manual' } })
    expect(ta().value).toBe('manual')
  })
})

describe('ChatInput queue auto-flush (DD-01)', () => {
  it('flushes the queued message automatically when the stream settles', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    // Turn runs → user presses Enter mid-stream → message lands in the queue.
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'queued one' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText(/queue/i)).toBeTruthy()
    // Stream settles → the queue must flush on its own (owner-visible bug DD-01).
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledWith('queued one', undefined)
    expect(screen.queryByText(/queue/i)).toBeNull()
  })

  it('one item per stream end: FIFO chain across two settle transitions', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'first' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    fireEvent.change(ta(), { target: { value: 'second' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend.mock.calls[0]).toEqual(['first', undefined])
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledTimes(2)
    expect(onSend.mock.calls[1]).toEqual(['second', undefined])
  })

  it('queued slash item goes through onSlashCommand on auto-flush', () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    const { rerender } = render(
      <ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={false} />,
    )
    rerender(<ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={true} />)
    fireEvent.change(ta(), { target: { value: '/compact' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).not.toHaveBeenCalled()
    rerender(<ChatInput onSend={onSend} onSlashCommand={onSlash} streaming={false} />)
    expect(onSlash).toHaveBeenCalledWith('/compact')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('a live draft is never stolen: flush waits for an empty composer', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'queued' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    fireEvent.change(ta(), { target: { value: 'user is typing' } })
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('user is typing')
    expect(screen.getByText(/queue/i)).toBeTruthy()
  })
})

// ── I6 P1-3: the Enter after a slash pick must not be swallowed ─────────────
// Regression pins: the chat stream deep test (2026-09-08) found that "/ephe <task>"
// with an argument — the Enter landed in the slash autocomplete and replaced the
// input with the bare command line (argument lost, nothing sent).
describe('ChatInput Enter-vs-Slash-Menue (I6 P1-3)', () => {
  it('/kommando <argument> + Enter → sendet den vollen Text (Menue zu nach Leerzeichen)', () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/ephe baue ein python-projekt' } })
    expect(screen.queryByTestId('slash-menu')).toBeNull()
    fireEvent.keyDown(ta(), { key: 'Enter' })
    // the parent routes the skill command — the FULL text has to arrive.
    expect(onSlash).toHaveBeenCalledWith('/ephe baue ein python-projekt')
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('')
  })

  it('Prefix-Pick mit Argument: "/pd"→"/pdf", dann Argument tippen + Enter → sendet "/pdf bericht"', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
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

  it('Escape entlaesst das Menue: Enter sendet danach den Rohtext statt zu completen', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    fireEvent.change(ta(), { target: { value: '/co' } })
    await screen.findByTestId('slash-menu')
    fireEvent.keyDown(ta(), { key: 'Escape' })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/co')
    expect(ta().value).toBe('')
  })

  it('W10-P1-1: waehrend laufender IME-Komposition sendet Enter NICHT', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={vi.fn()} />)
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

  it('Datei-Drag im Viewport zeigt das Drop-Overlay', () => {
    render(<ChatInput onSend={vi.fn()} />)
    act(() => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt() })
    })
    expect(screen.getByTestId('viewport-drop-overlay')).toBeTruthy()
  })

  it('Drop auf document.body (nicht Composer) hängt die Datei an', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    const file = new File(['x'], 'body.txt', { type: 'text/plain' })
    await act(async () => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt([file]) })
      fireEvent.drop(document.body, { dataTransfer: fileDt([file]) })
    })
    expect(await screen.findByText('body.txt')).toBeTruthy()
    // the overlay disappears after the drop.
    expect(screen.queryByTestId('viewport-drop-overlay')).toBeNull()
  })

  it('Nicht-Datei-Drag (z.B. Text) zeigt kein Overlay', () => {
    render(<ChatInput onSend={vi.fn()} />)
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

  it('ruft onStop während des Streamings auf', () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    escOnWindow()
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('im Leerlauf (streaming=false) ist Esc NICHT an onStop gebunden', () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming={false} onStop={onStop} />)
    escOnWindow()
    expect(onStop).not.toHaveBeenCalled()
  })

  it('offenes Slash-Menü hat Vorrang: Esc dismisst nur, kein onStop', async () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    await screen.findByTestId('slash-menu')
    escOnWindow()
    expect(onStop).not.toHaveBeenCalled()
  })
})
