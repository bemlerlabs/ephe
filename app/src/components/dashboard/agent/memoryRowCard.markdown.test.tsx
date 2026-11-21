/**
 * Reading a stored note inside its card: markdown becomes markup, and the card
 * stays a card.
 *
 * GIVEN  a memory note whose text is markdown (a heading, a bold line, a bullet
 *        list, a two-row GFM table, an inline code span) and a second note whose
 *        text is one long unbroken path
 * WHEN   either row renders through `MemoryRowCard`
 * THEN   the first shows real elements, with none of the `**` or `|` source
 *        syntax left in what the reader reads and both actions still reachable,
 *        and the second sits inside the wrap contract that holds it to the width
 *        the card already has
 *
 * jsdom has no layout engine, so the width half pins the class contract, the same
 * shape `bubble/messageMarkdown.mobile.test.tsx` uses for the chat.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRowCard, type MemoryRow, type MemoryRowCardProps } from './memoryRowCard'

// The card localises its own action labels; the keys are the whole vocabulary here.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const NOTE = [
  '## What I checked',
  '',
  '**Before building anything:**',
  '',
  '- the numbers file',
  '- two coverage pid files',
  '',
  '| Where | Result |',
  '| --- | --- |',
  '| /meta/ephe-numbers | found |',
  '| /meta/ephe-sheets | missing |',
  '',
  'Rerun with `ephe memory list` once the sheet lands.',
].join('\n')

// One token with no break opportunity in it: the shape that used to widen the card.
const LONG_PATH = `/meta/${'fieldrecords'.repeat(6)}/${'numbersarchive'.repeat(6)}.csv`

function card(text: string) {
  const row: MemoryRow = { id: 'note-1', text, metadata: {} }
  const props: MemoryRowCardProps = {
    row,
    index: 0,
    trash: false,
    isEditing: false,
    editLocked: false,
    draft: '',
    saving: false,
    onDraft: () => {},
    onStartEdit: () => {},
    onCancelEdit: () => {},
    onCommit: () => {},
    onRemove: () => {},
    onRestore: () => {},
  }
  return render(<MemoryRowCard {...props} />)
}

describe('MemoryRowCard — the note the store holds', () => {
  it('renders a bold line, a list, a two-row table and a code span as elements', () => {
    const { container } = card(NOTE)
    expect(container.querySelector('h2')?.textContent).toBe('What I checked')
    expect(container.querySelector('strong')?.textContent).toBe('Before building anything:')
    expect(within(screen.getByRole('list')).getAllByRole('listitem')).toHaveLength(2)

    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['Where', 'Result'])
    expect(
      within(table)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['/meta/ephe-numbers', 'found', '/meta/ephe-sheets', 'missing'])
    // the reused overrides travel with the renderer: the table caps itself at the
    // card, and wraps keep it from ever needing the scroll that cap allows.
    expect(String(table.parentElement?.className)).toContain('max-w-full')

    expect(container.querySelector('code')?.textContent).toBe('ephe memory list')
    expect(container.textContent).not.toContain('**')
    expect(container.textContent).not.toContain('|')

    expect(screen.getByTestId('memory-edit-0')).toBeTruthy()
    expect(screen.getByTestId('memory-delete-0')).toBeTruthy()
  })

  it('keeps one long unbroken path inside the card width', () => {
    const { container } = card(`Checked \`${LONG_PATH}\` before writing anything.`)
    const body = screen.getByTestId('memory-note-body')
    expect(body.textContent).toContain(LONG_PATH)
    // inherited by everything below it, every table cell included, and the fenced
    // run wraps rather than asking the row to scroll sideways.
    expect(String(body.className)).toContain('prose-invert')
    expect(String(body.className)).toContain('[overflow-wrap:anywhere]')
    expect(String(body.className)).toContain('[&_pre]:whitespace-pre-wrap')
    expect(String(body.className)).toContain('min-w-0')

    expect(String(container.querySelector('code')?.className)).toContain('[overflow-wrap:anywhere]')
    expect(screen.getByTestId('memory-delete-0')).toBeTruthy()
  })
})
