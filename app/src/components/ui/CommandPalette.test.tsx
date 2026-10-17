import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { useState } from 'react'
import CommandPalette from '@/components/ui/CommandPalette'
import type { CommandItem } from '@/hooks/useCommandPalette'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const mk = (id: string, label: string): CommandItem =>
  ({ id, label, action: () => undefined }) as unknown as CommandItem

const GROUPED: Record<string, CommandItem[]> = {
  PAGES: [mk('p1', 'Open chat'), mk('p2', 'Open settings')],
  AGENT: [mk('a1', 'Toggle terminal')],
}

function openPalette(over: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  const onSelect = vi.fn()
  const setQuery = vi.fn()
  render(
    <CommandPalette
      open
      query=""
      setQuery={setQuery}
      inputRef={{ current: null }}
      grouped={GROUPED}
      t={((k: string) => k) as never}
      onClose={() => undefined}
      onSelect={onSelect}
      {...over}
    />,
  )
  return { onSelect }
}

const options = () => screen.queryAllByRole('option')
const selectedIndex = () => options().findIndex((o) => o.getAttribute('aria-selected') === 'true')

describe('CommandPalette — DD-14 aktive Zeile', () => {
  it('oeffnet mitaktiv markierter ERSTER Zeile (kein unbemarkter Startzustand)', () => {
    openPalette()
    expect(selectedIndex()).toBe(0)
  })

  it('erster ArrowDown markiert Zeile 2 — Zeile 1 wird nicht uebersprungen', () => {
    openPalette()
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    expect(selectedIndex()).toBe(1)
  })

  it('Enter ohne Pfeiltastendruck waehlt die erste Zeile', () => {
    const { onSelect } = openPalette()
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect((onSelect.mock.calls[0]?.[0] as CommandItem | undefined)?.id).toBe('p1')
  })

  it('ArrowDown ueber das Ende claempft — letzte Zeile bleibt markiert, keine Geisterauswahl', () => {
    openPalette()
    for (let i = 0; i < 6; i++) fireEvent.keyDown(window, { key: 'ArrowDown' })
    expect(selectedIndex()).toBe(2)
  })

  it('leere Trefferliste: kein Crash, keine selected-Zeile', () => {
    openPalette({ grouped: {} })
    expect(options()).toHaveLength(0)
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    fireEvent.keyDown(window, { key: 'Enter' }) // no onSelect, no throw
  })
})

describe('CommandPalette — Enter-Vertrag (Fund 2026-10-01)', () => {
  it('Enter nach Treffer schließt die Palette garantiert mit (onClose)', () => {
    const onClose = vi.fn()
    const { onSelect } = openPalette({ onClose })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Enter bei leerer Trefferliste schließt NICHT (nichts gewählt)', () => {
    const onClose = vi.fn()
    openPalette({ grouped: {}, onClose })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('Items werden per Ref gelesen — ein Rerender mit gefilterter Liste wird sofort getroffen', () => {
    const onSelect = vi.fn()
    const FILTERED = { PAGES: [mk('settings', 'Open settings')] }
    const { rerender } = render(
      <CommandPalette
        open
        query=""
        setQuery={vi.fn()}
        inputRef={{ current: null }}
        grouped={GROUPED}
        t={((k: string) => k) as never}
        onClose={() => undefined}
        onSelect={onSelect}
      />,
    )
    // Query update: the palette re-renders with the filtered hit list (same
    // open-true — the Enter keydown can land between render and effect).
    rerender(
      <CommandPalette
        open
        query="settings"
        setQuery={vi.fn()}
        inputRef={{ current: null }}
        grouped={FILTERED}
        t={((k: string) => k) as never}
        onClose={() => undefined}
        onSelect={onSelect}
      />,
    )
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect((onSelect.mock.calls[0]?.[0] as CommandItem | undefined)?.id).toBe('settings')
  })
})

describe('CommandPalette — Escape-Kette', () => {
  it('Escape schließt die Maske selbst (nicht das Pane dahinter)', () => {
    const onClose = vi.fn()
    openPalette({ onClose })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

// Wave 10 (persona 06, measured): the mask declares role=dialog aria-modal and
// did not honour it — Tab left it after 5 stops and the shell behind it stayed
// reachable. These pin the contract (the live proof is
// e2e/walkthrough/persona-06-tastatur.spec.ts, cases (b), (d1) and (extra)).

/** The mask with state behind it, so a close really unmounts it. */
function Host({ onSelect = vi.fn() }: { onSelect?: (cmd: CommandItem) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <input id="ephe-chat-input" aria-label="composer" />
      <button data-testid="shell" onClick={() => undefined}>
        shell
      </button>
      <button data-testid="invoker" onClick={() => setOpen(true)}>
        open
      </button>
      <CommandPalette
        open={open}
        query=""
        setQuery={vi.fn()}
        inputRef={{ current: null }}
        grouped={GROUPED}
        t={((k: string) => k) as never}
        onClose={() => setOpen(false)}
        onSelect={onSelect}
      />
    </>
  )
}

describe('CommandPalette — aria-modal contract (Wave 10)', () => {
  it('focus moves in on open and Tab cannot leave: the last stop wraps to the combobox', () => {
    openPalette()
    const combobox = screen.getByRole('combobox')
    expect(document.activeElement).toBe(combobox)

    const optionButtons = options().map((li) => within(li).getByRole('button'))
    expect(optionButtons.length).toBe(3)
    const last = optionButtons[optionButtons.length - 1]!
    last.focus()
    // fireEvent reports false when the handler called preventDefault.
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(false)
    expect(document.activeElement).toBe(combobox)
  })

  it('the mask carries the trap and a focus target of its own (tabIndex -1)', () => {
    openPalette()
    const mask = screen.getByRole('dialog')
    expect(mask.getAttribute('tabindex')).toBe('-1')
  })

  it('makes the shell behind it inert while open', () => {
    render(<Host />)
    fireEvent.click(screen.getByTestId('invoker'))
    const shell = screen.getByTestId('shell')
    expect(shell.hasAttribute('inert')).toBe(true)
    expect(shell.getAttribute('aria-hidden')).toBe('true')
  })

  it('Escape closes, lifts the inert and hands focus back to the invoker — never to <body>', () => {
    render(<Host />)
    const composer = screen.getByLabelText('composer')
    composer.focus()
    fireEvent.click(screen.getByTestId('invoker'))
    expect(document.activeElement).toBe(screen.getByRole('combobox'))

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByTestId('shell').hasAttribute('inert')).toBe(false)
    expect(document.activeElement).toBe(composer)
    expect(document.activeElement).not.toBe(document.body)
  })
})

// P1 item 10: the header rendered bare section labels for 5 groups / 42 commands —
// the row count per group was invisible. Each grouped header carries the count.
describe('CommandPalette — per-group counts (P1-10)', () => {
  it('renders each group header with its row count as a badge', () => {
    openPalette()
    expect(screen.getByTestId('cmd-group-count-PAGES').textContent).toBe('2')
    expect(screen.getByTestId('cmd-group-count-AGENT').textContent).toBe('1')
  })
})
