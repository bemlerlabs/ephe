/**
 * Finding #68 — the confirming button carries the verb.
 *
 * The defect was the operating system naming the button: a question about deleting a
 * checkpoint answered "OK". These tests hold the two things that make the sheet an answer:
 * the verb on the button, and a refusal for every path that presses nothing.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

import { ConfirmHost } from './ConfirmDialog'
import { askConfirm } from '@/lib/confirmAction'

afterEach(() => {
  cleanup()
})

describe('the confirmation sheet', () => {
  it('names the action on the button that performs it', async () => {
    render(<ConfirmHost />)
    let accepted: boolean | null = null
    askConfirm({ title: 'Delete checkpoint cp-a?', action: 'Delete checkpoint' }).then((value) => {
      accepted = value
    })

    const sheet = await screen.findByTestId('confirm-dialog')
    expect(sheet.textContent).toContain('Delete checkpoint cp-a?')
    expect(screen.getByTestId('confirm-action').textContent).toBe('Delete checkpoint')
    expect(screen.getByTestId('confirm-cancel').textContent).toBe('common.cancel')

    fireEvent.click(screen.getByTestId('confirm-action'))
    await waitFor(() => expect(accepted).toBe(true))
    expect(screen.queryByTestId('confirm-dialog')).toBeNull()
  })

  it('treats a dismissed sheet as a refusal', async () => {
    render(<ConfirmHost />)
    let accepted: boolean | null = null
    askConfirm({ title: 'Discard the changes?', action: 'Discard changes' }).then((value) => {
      accepted = value
    })
    await screen.findByTestId('confirm-dialog')

    fireEvent.keyDown(screen.getByTestId('confirm-dialog'), { key: 'Escape', code: 'Escape' })
    await waitFor(() => expect(accepted).toBe(false))
  })

  it('asks the reader through the native sheet when no shell hosts it', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    // A component test renders one surface: without the host the question still has to
    // reach somebody, so the fallback is the old dialog with our sentence inside it.
    await expect(askConfirm({ title: 'Roll back to cp-b?', action: 'Roll back' })).resolves.toBe(
      true,
    )
    expect(confirmSpy).toHaveBeenCalledWith('Roll back to cp-b?')
    confirmSpy.mockRestore()
  })
})
