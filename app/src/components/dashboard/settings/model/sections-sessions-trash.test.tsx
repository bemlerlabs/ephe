/**
 * Chat trash — the settings row: it lists what waits, restores one session by
 * its unchanged id, and empties only after the endpoint's own dry run has
 * named its number.
 *
 * The safety property is the one the store row above follows too: the emptying
 * shows what it would free before anything goes, freeing is a second confirmed
 * click, and a refusal answers in words the reader can act on — the 409
 * `session_exists` stays on the row that asked, the 409 `trash_empty` reads as
 * the empty state it is, never as a failure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const listSessionTrash = vi.fn()
const restoreTrashedSession = vi.fn()
const emptySessionTrash = vi.fn()
const initFromDb = vi.fn()

const apiError = vi.hoisted(() => {
  class ApiError extends Error {
    status: number
    reasonCode: string
    constructor(message: string, status = 0, reasonCode = '') {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.reasonCode = reasonCode
    }
  }
  return ApiError
})

vi.mock('@/lib/api', () => ({
  ApiError: apiError,
  listSessionTrash: () => listSessionTrash(),
  restoreTrashedSession: (id: string) => restoreTrashedSession(id),
  emptySessionTrash: (dryRun: boolean) => emptySessionTrash(dryRun),
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: { getState: () => ({ initFromDb }) },
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o ? `${k} ${JSON.stringify(o)}` : k),
    i18n: { language: 'en' },
  }),
}))

import { SessionTrashSection } from './sections-sessions-trash'

/** Newest run first, as `GET /api/sessions/trash` answers: the row without a
 *  registry title carries null and must show its id. */
const TRASH = {
  entries: [
    {
      session_id: 'pwa-abc123',
      namespace: 'pwa-',
      title: 'Pitchdeck',
      bytes: 2048,
      trashed_at: '2026-11-14T10:00:00+00:00',
      run: '20261114T100000Z',
    },
    {
      session_id: 'pwa-def456',
      namespace: 'pwa-',
      title: null,
      bytes: 512,
      trashed_at: '2026-11-14T09:00:00+00:00',
      run: '20261114T090000Z',
    },
  ],
  total: 2,
}

beforeEach(() => {
  listSessionTrash.mockReset()
  restoreTrashedSession.mockReset()
  emptySessionTrash.mockReset()
  initFromDb.mockReset()
  listSessionTrash.mockResolvedValue(TRASH)
  restoreTrashedSession.mockResolvedValue({ restored: 'pwa-abc123', run: '20261114T100000Z' })
})

describe('SessionTrashSection', () => {
  it('lists the waiting sessions verbatim: title when present, id otherwise', async () => {
    render(<SessionTrashSection />)
    await waitFor(() => expect(listSessionTrash).toHaveBeenCalled())

    const list = await screen.findByTestId('session-trash-list')
    expect(list.textContent).toContain('Pitchdeck')
    // No title on its registry row — the id is the only surviving fact, shown as stored.
    expect(list.textContent).toContain('pwa-def456')
    // Bytes read as size, not as a raw count.
    expect(list.textContent).toContain('2 KB')
    expect(list.textContent).toContain('512 B')
    // The count the endpoint counts, named in the row.
    expect(screen.getByTestId('session-trash-row').textContent).toContain('sessionTrash.hint')
    expect(screen.getByTestId('session-trash-row').textContent).toContain('"count":"2"')
  })

  it('says the trash could not be read instead of pretending it is empty', async () => {
    listSessionTrash.mockRejectedValue(new Error('down'))
    render(<SessionTrashSection />)

    await waitFor(() =>
      expect(screen.getByTestId('session-trash-row').textContent).toContain(
        'sessionTrash.unreadable',
      ),
    )
    expect(screen.queryByTestId('session-trash-list')).toBeNull()
  })

  it('reads a 200 without its entries as unreadable, the same state as a refusal', async () => {
    // The browser sweep answers unknown /api routes with `{}`; a row that
    // painted that as an empty trash would hide the fact it never read one.
    listSessionTrash.mockResolvedValue({} as Awaited<ReturnType<typeof listSessionTrash>>)
    render(<SessionTrashSection />)

    await waitFor(() =>
      expect(screen.getByTestId('session-trash-row').textContent).toContain(
        'sessionTrash.unreadable',
      ),
    )
    expect(screen.queryByTestId('session-trash-list')).toBeNull()
  })

  it('restores one row by its unchanged id and refreshes the list and the session list', async () => {
    render(<SessionTrashSection />)
    const button = await screen.findByTestId('session-trash-restore-pwa-abc123')

    fireEvent.click(button)

    await waitFor(() => expect(restoreTrashedSession).toHaveBeenCalledWith('pwa-abc123'))
    // The prefix the list showed is the prefix the restore posts back — a
    // prettified id would restore nothing.
    await waitFor(() => expect(listSessionTrash).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(initFromDb).toHaveBeenCalledTimes(1))
  })

  it('leaves a 409 refusal on the row that asked, not in a toast someone misses', async () => {
    restoreTrashedSession.mockRejectedValue(
      new apiError('A live session already carries the id', 409, 'session_exists'),
    )
    render(<SessionTrashSection />)
    fireEvent.click(await screen.findByTestId('session-trash-restore-pwa-abc123'))

    const reason = await screen.findByTestId('session-trash-restore-error-pwa-abc123')
    expect(reason.textContent).toContain('A live session already carries the id')
    // The list stays as it was: the row is still waiting, still restorable.
    expect(await screen.findByTestId('session-trash-restore-pwa-abc123')).toBeTruthy()
  })

  it('empties only after the dry run named its number and a second click confirmed', async () => {
    emptySessionTrash.mockResolvedValue({
      deleted: ['pwa-abc123', 'pwa-def456'],
      runs: ['20261114T100000Z', '20261114T090000Z'],
      bytes_freed: 2560,
      dry_run: true,
    })
    render(<SessionTrashSection />)

    // Before the preview there is no way to delete anything.
    expect(screen.queryByTestId('trash-empty-apply')).toBeNull()

    fireEvent.click(await screen.findByTestId('trash-empty'))
    await waitFor(() => expect(emptySessionTrash).toHaveBeenCalledWith(true))
    expect(emptySessionTrash).not.toHaveBeenCalledWith(false)

    // The preview states the endpoint's own numbers.
    const preview = await screen.findByTestId('trash-preview')
    expect(preview.textContent).toContain('"sessions":"2"')
    expect(preview.textContent).toContain('2.6 KB')

    // Still a dry run: the final call needs a further, separate confirmation.
    expect(screen.queryByTestId('trash-empty-apply')).toBeNull()
    fireEvent.click(screen.getByTestId('trash-empty-ask'))
    fireEvent.click(await screen.findByTestId('trash-empty-apply'))

    await waitFor(() => expect(emptySessionTrash).toHaveBeenCalledWith(false))
    const note = await screen.findByTestId('trash-empty-note')
    expect(note.textContent).toContain('sessionTrash.emptied')
    expect(note.textContent).toContain('"sessions":"2"')
    expect(note.textContent).toContain('"size":"2.6 KB"')
  })

  it('names a dry run that answered without its numbers as a failure', async () => {
    // The sweep hands `{}` to unknown routes; a preview that would free
    // nothing it can name must fail out loud, never paint a confirm step.
    emptySessionTrash.mockResolvedValue({} as Awaited<ReturnType<typeof emptySessionTrash>>)
    render(<SessionTrashSection />)

    fireEvent.click(await screen.findByTestId('trash-empty'))
    await waitFor(() => expect(emptySessionTrash).toHaveBeenCalledWith(true))

    const note = await screen.findByTestId('trash-empty-note')
    expect(note.textContent).toContain('sessionTrash.emptyFailed')
    expect(screen.queryByTestId('trash-empty-apply')).toBeNull()
  })

  it('a trash that is already empty reads as the empty state, not as a failure', async () => {
    listSessionTrash.mockResolvedValue({ entries: [], total: 0 })
    emptySessionTrash.mockRejectedValue(
      new apiError('The session trash is already empty', 409, 'trash_empty'),
    )
    render(<SessionTrashSection />)

    fireEvent.click(await screen.findByTestId('trash-empty'))
    await waitFor(() => expect(emptySessionTrash).toHaveBeenCalledWith(true))

    const refusal = await screen.findByTestId('trash-empty-refusal')
    expect(refusal.textContent).toContain('The session trash is already empty')
    // No failure wording, and nothing was deleted: the apply path never opened.
    expect(screen.queryByTestId('trash-empty-note')).toBeNull()
    expect(screen.queryByTestId('trash-empty-apply')).toBeNull()
    expect(emptySessionTrash).not.toHaveBeenCalledWith(false)
  })
})
