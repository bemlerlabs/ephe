/**
 * Wave 4 — the session store row: it previews with the endpoint's own dry run,
 * deletes nothing before that preview, and names the number it shows.
 *
 * The product ships two right counts that read as a defect: `GET /api/sessions`
 * `total` (every file, all groups) and the task list the sidebar shows. This suite
 * pins the row's half of the fix — the number is labelled as a file count and the
 * smaller task count is printed beside it — plus the safety property the owner
 * asked for: nothing is deleted before a dry run has reported what it would free,
 * and freeing is a second, confirmed click.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const getSessionStore = vi.fn()
const pruneSessions = vi.fn()
const clearSessions = vi.fn()

vi.mock('@/lib/api', () => ({
  getSessionStore: () => getSessionStore(),
  pruneSessions: (body: unknown) => pruneSessions(body),
  clearSessions: () => clearSessions(),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o ? `${k} ${JSON.stringify(o)}` : k),
    i18n: { language: 'en' },
  }),
}))

import { SessionStoreSection } from './sections-sessions'
import { useChatStore } from '@/store/chatStore'

/** The store as the route answers it: 8,631 files, of which lists reach 2,381. */
const STORE = {
  session_dir: '/Users/example/.ephe/sessions',
  total: 8631,
  bytes: 47 * 1024 * 1024,
  by_namespace: { 'rest-': { files: 2562, bytes: 1 }, 'pwa-': { files: 3688, bytes: 1 } },
  registered_sessions: 2381,
  listed_files: 2381,
  unreachable_by_list: 6250,
  reachable_by_restore: 50,
  oldest: null,
  newest: null,
  sessions: [],
}

beforeEach(() => {
  getSessionStore.mockReset()
  pruneSessions.mockReset()
  clearSessions.mockReset()
  getSessionStore.mockResolvedValue(STORE)
})

describe('SessionStoreSection (Wave 4)', () => {
  it('names the file count and the smaller task count, so the two cannot disagree', async () => {
    render(<SessionStoreSection />)

    await waitFor(() => expect(getSessionStore).toHaveBeenCalled())
    const row = await screen.findByTestId('session-store-row')
    // The row's own name is the indexed key (findable in the settings search).
    expect(row.textContent).toContain('settings.sessionStoreRow')
    // Both numbers, named: total files beside the task count.
    expect(row.textContent).toContain('"total":"8,631"')
    expect(row.textContent).toContain('"tasks":"2,381"')
  })

  it('says it cannot read the store instead of showing a zero', async () => {
    getSessionStore.mockRejectedValue(new Error('down'))
    render(<SessionStoreSection />)

    await waitFor(() =>
      expect(screen.getByTestId('session-store-row').textContent).toContain(
        'settings.sessionStoreUnreadable',
      ),
    )
  })

  it('previews with the endpoint dry run and offers no delete before it', async () => {
    pruneSessions.mockResolvedValue({
      deleted: ['rest-0', 'rest-1'],
      kept: 3,
      bytes_freed: 2048,
      remaining: { 'rest-': 2, 'pwa-': 1, '': 3 },
      namespaces: ['rest-', 'pwa-'],
      dry_run: true,
    })
    render(<SessionStoreSection />)
    await screen.findByTestId('session-store-row')

    // Before the preview there is no way to delete anything.
    expect(screen.queryByTestId('prune-ask')).toBeNull()
    expect(screen.queryByTestId('prune-apply')).toBeNull()

    fireEvent.click(screen.getByTestId('prune-preview'))

    await waitFor(() => expect(pruneSessions).toHaveBeenCalledTimes(1))
    expect(pruneSessions).toHaveBeenCalledWith({
      keep_rest: 500,
      keep_pwa: 200,
      dry_run: true,
    })
    // The preview states the endpoint's number, not an estimate computed here.
    const preview = await screen.findByTestId('prune-preview-text')
    expect(preview.textContent).toContain('"files":"2"')
    expect(preview.textContent).toContain('2 KB')
    // Still a dry run: the apply path is a further, separate click.
    expect(screen.getByTestId('prune-ask')).toBeTruthy()
    expect(screen.queryByTestId('prune-apply')).toBeNull()
  })

  it('sends the counts the user typed, and only the confirmed run deletes', async () => {
    pruneSessions.mockResolvedValueOnce({
      deleted: ['rest-0'],
      kept: 1,
      bytes_freed: 4096,
      remaining: { 'rest-': 1, 'pwa-': 0, '': 3 },
      namespaces: ['rest-', 'pwa-'],
      dry_run: true,
    })
    pruneSessions.mockResolvedValueOnce({
      deleted: ['rest-0'],
      kept: 1,
      bytes_freed: 4096,
      remaining: { 'rest-': 1, 'pwa-': 0, '': 3 },
      namespaces: ['rest-', 'pwa-'],
      dry_run: false,
    })
    render(<SessionStoreSection />)
    await screen.findByTestId('session-store-row')

    fireEvent.change(screen.getByTestId('prune-keep-rest'), { target: { value: '1' } })
    fireEvent.click(screen.getByTestId('prune-preview'))
    await waitFor(() => expect(pruneSessions).toHaveBeenCalledTimes(1))
    expect(pruneSessions).toHaveBeenCalledWith(
      expect.objectContaining({ keep_rest: 1, dry_run: true }),
    )

    fireEvent.click(await screen.findByTestId('prune-ask'))
    fireEvent.click(screen.getByTestId('prune-apply'))

    await waitFor(() => expect(pruneSessions).toHaveBeenCalledTimes(2))
    expect(pruneSessions).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ keep_rest: 1, dry_run: false }),
    )
    // The outcome is a sentence: what went, what it freed, what stays.
    const outcome = await screen.findByTestId('session-store-outcome')
    expect(outcome.textContent).toContain('settings.sessionStoreDone')
    expect(outcome.textContent).toContain('"files":"1"')
    expect(outcome.textContent).toContain('"remaining":"4"')
  })

  it('clears every chat only after a second, confirmed click', async () => {
    const clearAll = vi.fn()
    useChatStore.setState({ clearAllSessions: clearAll })
    clearSessions.mockResolvedValue({
      deleted: ['a', 'b'],
      kept: 0,
      bytes_freed: 10,
      remaining: { 'rest-': 0, 'pwa-': 0, '': 0 },
      namespaces: ['rest-', 'pwa-'],
      dry_run: false,
    })
    render(<SessionStoreSection />)
    await screen.findByTestId('session-store-row')

    fireEvent.click(screen.getByTestId('clear-all-chats'))
    expect(clearSessions).not.toHaveBeenCalled()
    expect(clearAll).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('clear-all-chats-confirm'))
    await waitFor(() => expect(clearSessions).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(clearAll).toHaveBeenCalledTimes(1))
    expect((await screen.findByTestId('clear-all-chats-note')).textContent).toContain(
      'settings.clearAllChatsDone',
    )
  })
})
