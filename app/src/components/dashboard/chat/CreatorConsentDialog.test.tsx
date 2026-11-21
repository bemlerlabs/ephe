/**
 * Creator Mode asks for its permissions before it runs with them.
 *
 * The guard (`core/tools/creator_guard.py`, `80e3852f`) enforces `code`,
 * `files` and `network` one call at a time, and the owner ruled the granularity
 * that governs entry: one of the three is enough for a session to have Creator
 * mode at all. This sheet is where that ruling is stated to a person, so the
 * three claims it has to keep are pinned here — the rows are the guard's own
 * closed set, the enter control refuses the empty set the way the ruling does,
 * and a confirm writes the whole set for the session it was opened with.
 *
 * The read is a separate claim: a session that holds nothing and a session the
 * app could not ask are two different answers, and showing the first when the
 * second happened would make an unchecked row look like a decision the user
 * never made.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const api = vi.hoisted(() => ({
  CREATOR_PRIVILEGES: ['code', 'files', 'network'] as const,
  getCreatorConsent: vi.fn(),
  putCreatorConsent: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

import CreatorConsentDialog from './CreatorConsentDialog'

const answer = (held: string[]) => ({
  session_id: 'sess-1',
  privileges: ['code', 'files', 'network'],
  held,
  mode: 'creator',
})

/** The checkedness of a row. Not `[checked]`: that attribute is the HTML
 *  *initial* value, and React maintains a controlled checkbox through the
 *  `checked` property — an attribute probe reads false for a row the read just
 *  ticked, which is a property of the probe, not of the sheet. */
const checkedOf = (testId: string): boolean =>
  (screen.getByTestId(testId) as HTMLInputElement).checked

function open(props: Partial<React.ComponentProps<typeof CreatorConsentDialog>> = {}) {
  const onConfirm = vi.fn()
  const onClosed = vi.fn()
  render(
    <CreatorConsentDialog
      open
      sessionId="sess-1"
      onConfirm={onConfirm}
      onClosed={onClosed}
      {...props}
    />,
  )
  return { onConfirm, onClosed }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getCreatorConsent.mockResolvedValue(answer([]))
  api.putCreatorConsent.mockResolvedValue(answer(['code']))
})

describe('the creator consent sheet', () => {
  it('asks for the three permissions the guard knows, by name', async () => {
    open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())
    expect(screen.getByTestId('creator-consent-files')).toBeTruthy()
    expect(screen.getByTestId('creator-consent-network')).toBeTruthy()
    for (const name of ['code', 'files', 'network']) {
      expect(screen.getByTestId(`creator-consent-${name}`).textContent).toContain(
        `chat.creatorConsent.${name}.label`,
      )
      expect(screen.getByTestId(`creator-consent-${name}`).textContent).toContain(
        `chat.creatorConsent.${name}.detail`,
      )
    }
  })

  it('starts with nothing checked and reads what the session already holds', async () => {
    api.getCreatorConsent.mockResolvedValue(answer(['files']))

    open()
    await waitFor(() => expect(checkedOf('creator-consent-files-input')).toBe(true))

    expect(api.getCreatorConsent).toHaveBeenCalledWith('sess-1')
    expect(checkedOf('creator-consent-code-input')).toBe(false)
    expect(checkedOf('creator-consent-network-input')).toBe(false)
  })

  it('refuses to enter on no permission at all, and accepts one', async () => {
    const { onConfirm } = open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-enter')).toBeTruthy())

    expect(screen.getByTestId('creator-consent-enter').hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    expect(screen.getByTestId('creator-consent-enter').hasAttribute('disabled')).toBe(false)

    fireEvent.click(screen.getByTestId('creator-consent-enter'))
    await waitFor(() => expect(onConfirm).toHaveBeenCalled())
    expect(api.putCreatorConsent).toHaveBeenCalledWith('sess-1', ['code'])
  })

  it('writes the whole set the user chose, in the guard order', async () => {
    const { onConfirm } = open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-network')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-network-input'))
    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    fireEvent.click(screen.getByTestId('creator-consent-enter'))

    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith(['code', 'network']))
    expect(api.putCreatorConsent).toHaveBeenCalledTimes(1)
  })

  it('says the ruling out loud: one of the three is enough, and each is enforced', async () => {
    open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-note')).toBeTruthy())
    expect(screen.getByTestId('creator-consent-note').textContent).toContain(
      'chat.creatorConsent.note',
    )
  })

  it('names a failed read as a failed read instead of an empty grant', async () => {
    api.getCreatorConsent.mockRejectedValue(new Error('offline'))

    open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-read-failed')).toBeTruthy())

    // The write stays the user's decision: an unread session is not a refusal.
    expect(screen.getByTestId('creator-consent-code')).toBeTruthy()
    expect(screen.getByTestId('creator-consent-enter').hasAttribute('disabled')).toBe(true)
  })

  it('says the write failed and grants nothing when the backend refuses it', async () => {
    // A sheet that closes on a rejected write tells the user they entered Creator
    // Mode while the guard holds nothing for the session — the refusals would
    // arrive with no explanation, and the mode would read as broken.
    api.putCreatorConsent.mockRejectedValue(new Error('backend down'))

    const { onConfirm } = open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-enter')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    fireEvent.click(screen.getByTestId('creator-consent-enter'))

    await waitFor(() => expect(screen.getByTestId('creator-consent-write-failed')).toBeTruthy())
    expect(onConfirm).not.toHaveBeenCalled()
    // The choice survives the failure: the user re-sends it, they do not rebuild it.
    expect(checkedOf('creator-consent-code-input')).toBe(true)
  })

  it('writes nothing when the user closes the sheet', async () => {
    const { onConfirm, onClosed } = open()
    await waitFor(() => expect(screen.getByTestId('creator-consent-cancel')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    fireEvent.click(screen.getByTestId('creator-consent-cancel'))

    expect(api.putCreatorConsent).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
    expect(onClosed).toHaveBeenCalled()
  })
})
