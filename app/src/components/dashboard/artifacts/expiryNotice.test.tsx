// R4/A4: the expiry asks a question. No delete path without an answer, and the
// answer may hit exactly the cards the user selected.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import ArtifactExpiryNotice from './expiryNotice'

beforeEach(() => {
  document.body.innerHTML = ''
  answer.mockReset()
  expiry.mockReset()
})
afterEach(cleanup)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string) => k,
    i18n: { language: 'de' },
  }),
}))

const answer = vi.fn()
const expiry = vi.fn()

vi.mock('@/lib/api', () => ({
  listArtifactExpiry: () => expiry(),
  answerArtifactExpiry: (ids: string[], action: 'keep' | 'delete') => answer(ids, action),
}))

const due = (n: number) => ({
  due: Array.from({ length: n }, (_, i) => ({
    id: `art-${i}`,
    root_id: `art-${i}`,
    version: 1,
    session_id: 's1',
    name: `bericht-${i}.pdf`,
    path: `/tmp/bericht-${i}.pdf`,
    kind: 'pdf',
    size: 1024,
    topic: '',
    created_at: '2026-09-01T00:00:00+00:00',
    favorite: false,
    tags: [],
  })),
  count: n,
  bytes: n * 1024,
  days: 30,
})

describe('ArtifactExpiryNotice', () => {
  it('verschwindet still, wenn nichts fällig ist', async () => {
    expiry.mockResolvedValue(due(0))
    const { container } = render(<ArtifactExpiryNotice active />)
    await waitFor(() => expect(expiry).toHaveBeenCalled())
    expect(container.innerHTML).toBe('')
    expect(answer).not.toHaveBeenCalled()
  })

  it('verschwindet auch bei Fehler — eine Frage, die sie nicht stellen kann, erfindet sie nicht', async () => {
    expiry.mockRejectedValue(new Error('offline'))
    const { container } = render(<ArtifactExpiryNotice active />)
    await waitFor(() => expect(expiry).toHaveBeenCalled())
    expect(container.innerHTML).toBe('')
  })

  it('fragt und behält auf Antwort', async () => {
    expiry.mockResolvedValue(due(2))
    answer.mockResolvedValue({ kept: ['art-0', 'art-1'], deleted: [], skipped: [] })
    render(<ArtifactExpiryNotice active />)
    fireEvent.click(await screen.findByTestId('expiry-keep'))
    await waitFor(() => expect(answer).toHaveBeenCalledWith(['art-0', 'art-1'], 'keep'))
  })

  it('löscht erst nach der zweiten Bestätigung', async () => {
    expiry.mockResolvedValue(due(1))
    render(<ArtifactExpiryNotice active />)
    fireEvent.click(await screen.findByTestId('expiry-delete'))
    expect(answer).not.toHaveBeenCalled()
    answer.mockResolvedValue({ kept: [], deleted: ['art-0'], skipped: [] })
    fireEvent.click(screen.getByTestId('expiry-delete-yes'))
    await waitFor(() => expect(answer).toHaveBeenCalledWith(['art-0'], 'delete'))
  })

  it('trifft nur, was ausgewählt ist — eine Karte von mehreren', async () => {
    expiry.mockResolvedValue(due(3))
    answer.mockResolvedValue({ kept: [], deleted: ['art-1'], skipped: [] })
    render(<ArtifactExpiryNotice active />)
    await screen.findByTestId('expiry-keep')
    fireEvent.click(screen.getByTestId('expiry-choose'))
    const boxes = await screen.findAllByRole('checkbox')
    expect(boxes).toHaveLength(3)
    fireEvent.click(boxes[0]!)
    fireEvent.click(boxes[2]!)
    fireEvent.click(screen.getByTestId('expiry-keep'))
    await waitFor(() => expect(answer).toHaveBeenCalledWith(['art-1'], 'keep'))
  })

  it('meldet die Liste nach der Antwort neu', async () => {
    expiry.mockResolvedValue(due(1))
    answer.mockResolvedValue({ kept: ['art-0'], deleted: [], skipped: [] })
    const onAnswered = vi.fn()
    render(<ArtifactExpiryNotice active onAnswered={onAnswered} />)
    fireEvent.click(await screen.findByTestId('expiry-keep'))
    await waitFor(() => expect(onAnswered).toHaveBeenCalled())
  })

  it('ist stumm, wenn die Fläche ausgeblendet ist', async () => {
    expiry.mockResolvedValue(due(2))
    render(<ArtifactExpiryNotice active={false} />)
    expect(expiry).not.toHaveBeenCalled()
  })
})

// A4: a lost answer is a failure surface too — the sentence stays, and the retry
// under it sends the very answer the server dropped.
describe('a lost answer names the next step', () => {
  it('offers the retry that sends the same answer again', async () => {
    expiry.mockResolvedValue(due(2))
    answer
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ kept: ['art-0', 'art-1'], deleted: [], skipped: [] })
    render(<ArtifactExpiryNotice active />)
    fireEvent.click(await screen.findByTestId('expiry-keep'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('artifacts.expiry.failed')
    const retry = screen.getByTestId('expiry-retry')
    expect(retry.textContent).toBe('agentPanel.retry')
    fireEvent.click(retry)
    await waitFor(() => expect(answer).toHaveBeenCalledTimes(2))
    expect(answer).toHaveBeenLastCalledWith(['art-0', 'art-1'], 'keep')
  })
})
