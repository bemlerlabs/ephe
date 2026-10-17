/** R5: the empty state of the shelf.
 *
 * Finding from the review run: the "Adopted" tab read
 * "Nothing in the workbench yet. Everything a tool produces lands here" — while
 * the shelf next to it showed 35 cards. The sentence was not meant wrongly, it
 * was simply written for the other surface. The list knows its own reason, so it
 * states it too.
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

const regal = () =>
  render(<ArtifactShelf items={[]} selectedId={null} onSelect={() => {}} onChanged={() => {}} />)

describe('leeres Regal', () => {
  it('erklärt die Werkbank, wenn die Fläche das Regal ist', () => {
    regal()
    expect(screen.getByTestId('artifacts-shelf-empty').textContent).toBe('artifacts.page.empty')
  })

  it('überlässt der Fläche den Satz, wenn sie ihn weiß', () => {
    render(
      <ArtifactShelf
        items={[]}
        selectedId={null}
        onSelect={() => {}}
        onChanged={() => {}}
        leerText="Du hast noch nichts übernommen."
      />,
    )
    expect(screen.getByTestId('artifacts-shelf-empty').textContent).toBe(
      'Du hast noch nichts übernommen.',
    )
  })
})

/**
 * R5 leftovers, finding 1: the collision arises *inside* one group, so the group
 * has to recognise it. Two cards of the same name in different groups (PDF beside
 * PNG) are already told apart by the kind — those get no tag.
 */
const karte = (id: string, name: string, kind: string, turn_id: string): ArtifactEntry => ({
  id,
  root_id: id,
  version: 1,
  session_id: `sess-${id}`,
  name,
  path: `/home/x/.ephe/artifacts/sess-${id}/${name}`,
  kind,
  size: 1024,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
  turn_id,
})

describe('Kollision in der Gruppe (R5-Reste/Befund 1)', () => {
  const regal_mit = (items: ArtifactEntry[]) =>
    render(
      <ArtifactShelf items={items} selectedId={null} onSelect={() => {}} onChanged={() => {}} />,
    )

  it('gibt nur den gleichnamigen Karten einer Gruppe das Kürzel', () => {
    regal_mit([
      karte('a1', 'file-summary.pdf', 'pdf', 'aaaaaaaaaaaa'),
      karte('a2', 'file-summary.pdf', 'pdf', 'bbbbbbbbbbbb'),
      karte('a3', 'analyse-2026.pdf', 'pdf', 'cccccccccccc'),
    ])
    expect(screen.getByTestId('artifact-origin-a1').textContent).toBe('#aaaaaaaa')
    expect(screen.getByTestId('artifact-origin-a2').textContent).toBe('#bbbbbbbb')
    expect(screen.queryByTestId('artifact-origin-a3')).toBeNull()
  })

  it('sieht über den Gruppenrand hinweg keine Kollision', () => {
    regal_mit([
      karte('p1', 'bericht.pdf', 'pdf', 'dddddddddddd'),
      karte('s1', 'bericht.pdf', 'deck', 'eeeeeeeeeeee'),
    ])
    expect(screen.queryByTestId('artifact-origin-p1')).toBeNull()
    expect(screen.queryByTestId('artifact-origin-s1')).toBeNull()
  })

  it('zählt auch die Karten, die hinter „weitere" stehen', () => {
    const viele = Array.from({ length: 11 }, (_, i) =>
      karte(`x${i}`, 'file-summary.pdf', 'pdf', `turn${i}000000000`),
    )
    regal_mit(viele)
    expect(screen.getByRole('heading', { name: /PDF 11/ })).toBeTruthy()
    expect(screen.getByTestId('shelf-more-pdf')).toBeTruthy()
    // the truncated rows hang under the same name — every one of them carries the
    // tag, the eighth included.
    expect(screen.getByTestId('artifact-origin-x7')).toBeTruthy()
  })
})

/**
 * R6, finding 1: two cards from the SAME task, same name, born in the same
 * minute. The origin tag is built from that task, so both cards carry the same
 * tag — the mark that separates five foreign twins cannot separate these.
 *
 * The disambiguation reads the birth to the second, because `created_at` is the
 * only field that every card carries: in the live bank 32 of 36 rows have no
 * `call_id` at all, so a call ordinal would be dead code exactly where the
 * clusters are. Nothing is invented: the seconds are the same instant the index
 * stores, and the row says so in its title.
 */
// Built with the cases below un-skipped: the shelf flags the pair whose origin mark ties, and
// the row renders `artifact-stamp-*` — the stored `created_at` read to the second, the instant
// named verbatim in its title. Non-tied cards keep the minute stamp.
describe('same task, same name, same minute (R6)', () => {
  const zeilen = (...items: ArtifactEntry[]) =>
    render(
      <ArtifactShelf items={items} selectedId={null} onSelect={() => {}} onChanged={() => {}} />,
    )
  const twin = (id: string, seconds: string) => ({
    ...karte(id, 'file-summary.pdf', 'pdf', 'aaaaaaaaaaaa'),
    created_at: `2026-10-06T09:00:${seconds}+00:00`,
  })
  const stamp = (id: string) => screen.getByTestId(`artifact-stamp-${id}`).textContent ?? ''

  it('shows the same origin tag on both, which is why the tag alone fails', () => {
    zeilen(twin('t1', '11'), twin('t2', '43'))
    expect(screen.getByTestId('artifact-origin-t1').textContent).toBe('#aaaaaaaa')
    expect(screen.getByTestId('artifact-origin-t2').textContent).toBe('#aaaaaaaa')
  })

  it('separates them by reading the birth to the second', () => {
    zeilen(twin('t1', '11'), twin('t2', '43'))
    expect(stamp('t1')).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(stamp('t2')).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(stamp('t1')).not.toBe(stamp('t2'))
  })

  it('keeps the date part of the stamp untouched while doing so', () => {
    zeilen(twin('t1', '11'), twin('t2', '43'))
    // same day, same minute: only the seconds may differ, the slot stays put
    expect(stamp('t1').slice(0, 6)).toBe(stamp('t2').slice(0, 6))
  })

  it('names the instant it derived the mark from', () => {
    zeilen(twin('t1', '11'))
    expect(screen.getByTestId('artifact-stamp-t1').getAttribute('title')).toBe(
      '2026-10-06T09:00:11+00:00',
    )
  })

  it('invents nothing when even the second ties', () => {
    zeilen(twin('t1', '11'), twin('t2', '11'))
    // two cards written in the same second of the same call: the row stops at
    // what the data says instead of appending a token nobody can ask about
    expect(stamp('t1')).toBe(stamp('t2'))
    expect(screen.getByTestId('artifact-origin-t1').textContent).toBe('#aaaaaaaa')
    expect(screen.getByTestId('artifact-origin-t2').textContent).toBe('#aaaaaaaa')
  })

  it('leaves the minute stamp alone when the task tags differ', () => {
    zeilen(
      {
        ...karte('u1', 'file-summary.pdf', 'pdf', 'bbbbbbbbbbbb'),
        created_at: '2026-10-06T09:00:11+00:00',
      },
      {
        ...karte('u2', 'file-summary.pdf', 'pdf', 'cccccccccccc'),
        created_at: '2026-10-06T09:00:43+00:00',
      },
    )
    expect(stamp('u1')).not.toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(stamp('u2')).not.toMatch(/\d{2}:\d{2}:\d{2}/)
  })
})
