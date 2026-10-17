/**
 * R6 — two cards from ONE task, same name, born in the same minute.
 *
 * S5 gave a repeating card its origin mark: `#` plus the first eight characters
 * of `turn_id`, falling back to `session_id`. That separates cards from
 * different tasks — and it is silent exactly where it was supposed to help,
 * because two cards written by the same task carry the same mark. Then the row
 * holds nothing but a minute stamp, and both cards show the same minute.
 *
 * This file pins the case against the contract as it stands today: only
 * `ArtifactShelf`'s existing props, only test ids the shelf already renders
 * (`artifact-row-*`, `artifact-origin-*`). It fails on the missing
 * disambiguation, not on a type.
 *
 * The mark to add is the stored birth read to the second — `created_at` is a
 * column on every row of `artifacts` and all 36 rows in the live bank carry it
 * to the second (`2026-09-23T20:18:08+00:00`, `:20:18:22`, `:20:18:37` — three
 * cards inside one minute, all distinct). The call ordinal was measured and
 * dropped: `call_id` is filled in 6 of 36 rows, and the `args_hash` behind it
 * repeats — the three newest `file-summary.pdf` cards share
 * `264b8e73938c7224` — so it would separate nothing while going missing for
 * most of the shelf. Nothing here is random: the seconds are the same instant
 * the index already stores, and the detail pane's "Geboren" line is that
 * instant to the minute.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { vi } from 'vitest'
import ArtifactShelf from './shelf'
import type { ArtifactEntry } from '@/lib/api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

afterEach(cleanup)

/** One card of a same-name cluster: one task, one minute, `seconds` apart. */
function twin(id: string, seconds: number, turnId = 'aaaaaaaaaaaa'): ArtifactEntry {
  const pad = String(seconds).padStart(2, '0')
  return {
    id,
    root_id: id,
    version: 1,
    session_id: 'ob-g3-r1-1790194677',
    name: 'file-summary.pdf',
    path: `/home/x/.ephe/artifacts/ob-g3-r1-1790194677/${id}-file-summary.pdf`,
    kind: 'pdf',
    size: 2742 + seconds,
    topic: '',
    created_at: `2026-09-23T20:18:${pad}+00:00`,
    favorite: false,
    tags: [],
    turn_id: turnId,
    call_id: `${turnId.slice(0, 8)}-0`,
  }
}

function shelf(items: ArtifactEntry[]) {
  return render(
    <ArtifactShelf items={items} selectedId={null} onSelect={() => {}} onChanged={() => {}} />,
  )
}

/** Everything the row says out loud — the visible line, not one of its parts. */
function line(id: string): string {
  return screen.getByTestId(`artifact-row-${id}`).textContent ?? ''
}

function mark(id: string): string {
  return screen.getByTestId(`artifact-origin-${id}`).textContent ?? ''
}

// The behaviour the cases in shelf.test.tsx pin, seen from the origin side: a tied pair gets
// its stored birth read to the second, and only a tied pair.
describe('two cards of one task inside one minute (R6)', () => {
  it('carries the same origin mark on both, which is why the mark cannot separate them', () => {
    shelf([twin('t1', 8), twin('t2', 37)])
    expect(mark('t1')).toBe('#aaaaaaaa')
    expect(mark('t2')).toBe('#aaaaaaaa')
    expect(mark('t1')).toBe(mark('t2'))
  })

  it('separates the two rows, because the shelf shows them as two cards', () => {
    shelf([twin('t1', 8), twin('t2', 37)])
    // Today both lines read "file-summary.pdfvor 15 Tagen23.09., 22:18#aaaaaaaa".
    expect(line('t1')).not.toBe(line('t2'))
  })

  it('does it by reading the stored birth to the second', () => {
    shelf([twin('t1', 8), twin('t2', 37)])
    expect(line('t1')).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(line('t2')).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('keeps the finer reading where it belongs: only on the tied pair', () => {
    // Different tasks, same name, same minute — the origin mark already
    // separates these, so the stamp must stay at the minute.
    shelf([twin('u1', 8, 'bbbbbbbbbbbb'), twin('u2', 37, 'cccccccccccc')])
    expect(mark('u1')).toBe('#bbbbbbbb')
    expect(mark('u2')).toBe('#cccccccc')
    expect(line('u1')).not.toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(line('u2')).not.toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('invents nothing when even the stored second ties', () => {
    // Two cards written in the same second of the same call: the row stops at
    // what the index says instead of appending a token nobody can ask about.
    shelf([twin('v1', 12), twin('v2', 12)])
    expect(mark('v1')).toBe(mark('v2'))
    expect(line('v1')).toBe(line('v2'))
  })
})
