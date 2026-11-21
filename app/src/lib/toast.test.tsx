/**
 * G4 — toast/feedback system
 *
 * GIVEN  toastBus (event bus without context) + Toaster component
 * WHEN   toast.info/success/error is called
 * THEN   subscribed listeners receive the toast item
 * AND    Toaster renders the title in an aria-live region
 * AND    toasts dismiss themselves automatically (auto timeout)
 * AND    the subscribe return value (unsubscribe) removes the listener
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: (() => ({ t: (key: string) => key })) as never,
}))

import { toastBus, type ToastItem } from './toast'
import { Toaster } from '../components/ui/Toaster'

describe('toastBus (G4)', () => {
  it('broadcasts to subscribed listeners', () => {
    const spy = vi.fn()
    toastBus.subscribe(spy)
    toastBus.info('Hallo', 'Beschreibung')
    expect(spy).toHaveBeenCalledTimes(1)
    const item: ToastItem = spy.mock.calls[0]![0]
    expect(item.kind).toBe('info')
    expect(item.title).toBe('Hallo')
    expect(item.description).toBe('Beschreibung')
    expect(item.id).toBeTruthy()
  })

  it('unsubscribing removes the listener', () => {
    const spy = vi.fn()
    const unsub = toastBus.subscribe(spy)
    unsub()
    toastBus.success('Nicht gesehen')
    expect(spy).not.toHaveBeenCalled()
  })

  it('the success and error shortcuts set the right kind', () => {
    const spy = vi.fn()
    toastBus.subscribe(spy)
    toastBus.success('OK')
    toastBus.error('Fehler')
    expect(spy.mock.calls[0]![0].kind).toBe('success')
    expect(spy.mock.calls[1]![0].kind).toBe('error')
  })

  it('the optional action button comes along (G7 sw update flow)', () => {
    const onClick = vi.fn()
    const spy = vi.fn()
    toastBus.subscribe(spy)
    toastBus.info('Neue Version', 'Hint', { label: 'Neu laden', onClick })
    const item: ToastItem = spy.mock.calls[0]![0]
    expect(item.action).toEqual({ label: 'Neu laden', onClick })
  })
})

describe('Toaster (G4)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('renders a received toast in the standing aria-live region', () => {
    render(<Toaster />)
    // The region exists before the first message; an inserted region may never be announced.
    expect(screen.getByTestId('toaster-live').textContent).toBe('')
    act(() => {
      toastBus.error('Backend getrennt')
    })
    expect(screen.getByRole('alert').textContent).toContain('Backend getrennt')
  })

  it('a dismissed toast disappears after the auto timeout', () => {
    render(<Toaster />)
    act(() => {
      toastBus.info('Vergängliche Meldung')
    })
    expect(screen.getByRole('status').textContent).toContain('Vergängliche Meldung')
    act(() => {
      vi.advanceTimersByTime(6000)
    })
    expect(screen.queryByText('Vergängliche Meldung')).toBeNull()
  })

  it('the close button removes the toast right away', () => {
    render(<Toaster />)
    act(() => {
      toastBus.info('Manuell schließen')
    })
    const close = screen.getByRole('button', { name: /schlie[ßs]en|close/i })
    act(() => {
      close.click()
    })
    expect(screen.queryByText('Manuell schließen')).toBeNull()
  })

  it('a waiting notice stands until the reader closes it', () => {
    render(<Toaster />)
    const onDismiss = vi.fn()
    act(() => {
      toastBus.info('Neue Version wartet', 'Lade neu', undefined, 'sw-update', {
        sticky: true,
        onDismiss,
      })
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getAllByText('Neue Version wartet').length).toBeGreaterThan(0)
    act(() => {
      screen.getByRole('button', { name: /schlie[ßs]en|close/i }).click()
    })
    expect(screen.queryByText('Neue Version wartet')).toBeNull()
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('the action button runs the action and removes the toast (G7)', () => {
    render(<Toaster />)
    const onClick = vi.fn()
    act(() => {
      toastBus.info('Neue Version verfügbar', undefined, { label: 'Neu laden', onClick })
    })
    const action = screen.getByRole('button', { name: 'Neu laden' })
    act(() => {
      action.click()
    })
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Neue Version verfügbar')).toBeNull()
  })
})
