/**
 * The confirm sheet is one of two surfaces the shell paints only when it is
 * asked to (the command palette is the other). Its chunk therefore is not in the
 * first load; the host that `lib/confirmAction` promises must still be there, or
 * `askConfirm` falls back to the operating system's sheet and the verb on the
 * button is lost. This holds that contract at the app boundary.
 */
import { describe, it, expect, vi } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts ? `${k}:${Object.values(opts).join('|')}` : k,
  }),
}))

vi.mock('@/lib/api', () => ({
  getSetupStatus: () => Promise.resolve({ configured: true, skipped: false }),
}))

const readyGate = { ready: true, configured: true, skipped: false }
vi.mock('@/lib', () => ({
  consumeSetupIntent: () => false,
  shouldLeaveSetup: () => false,
  gateSnapshot: () => readyGate,
  loadSetupGate: async () => {},
  subscribeGate: () => () => {},
}))

vi.mock('@/hooks', () => ({
  useCommandPalette: () => ({
    open: false,
    setOpen: () => {},
    query: '',
    setQuery: () => {},
    inputRef: { current: null },
    grouped: {},
    t: (k: string) => k,
    recordUsage: () => {},
  }),
}))

vi.mock('./pages/ChatPage', () => ({ default: () => <div data-testid="chat-page" /> }))

import App from './App'
import { askConfirm } from '@/lib/confirmAction'

describe('the confirm surface is hosted before its chunk is needed', () => {
  it('answers through the product sheet, not the native one', async () => {
    window.location.hash = '#/a/hash/the/app/does/not/know'
    render(<App />)
    await screen.findByTestId('route-unknown')

    const nativeConfirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    let answer!: Promise<boolean>
    await act(async () => {
      answer = askConfirm({ title: 'Delete checkpoint cp-a?', action: 'Delete checkpoint' })
    })

    expect(await screen.findByTestId('confirm-dialog')).toBeInTheDocument()
    expect(nativeConfirm).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('confirm-action'))
    await expect(answer).resolves.toBe(true)
    nativeConfirm.mockRestore()
  })
})
