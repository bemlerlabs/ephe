/**
 * The approval picker as a keyboard menu. The rows and the outside-click listener
 * were already there; what this file pins is that the list owns focus once the menu
 * opens, so the existing ArrowDown/Enter handlers can ever run.
 *
 * The composer mounts this control closed and opens it later, so the test does the
 * same: a mount-time focus effect runs against a null ref and never runs again.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createRef } from 'react'
import ComposerAccessControl from './ComposerAccessControl'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}))

describe('ComposerAccessControl — the menu list takes focus on open', () => {
  const raf = vi.fn()

  beforeEach(() => {
    raf.mockReset()
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      raf(cb)
      cb(0)
      return 7
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })
  afterEach(() => vi.unstubAllGlobals())

  function mount(onPick = vi.fn(async () => {})) {
    const anchorRef = createRef<HTMLButtonElement>()
    const control = (open: boolean) => (
      <ComposerAccessControl
        profile="strict"
        open={open}
        anchorRef={anchorRef}
        menuPos={{ left: 120, bottom: 60 }}
        onToggle={vi.fn()}
        onClose={vi.fn()}
        onPick={onPick}
      />
    )
    const view = render(control(false))
    return { onPick, open: () => view.rerender(control(true)) }
  }

  it('focuses the listbox container, not the trigger', async () => {
    const { open } = mount()
    open()
    const list = screen.getByTestId('composer-access-list')
    await waitFor(() => expect(document.activeElement).toBe(list))
  })

  it('ArrowDown + Enter picks the next profile', async () => {
    const { onPick, open } = mount()
    open()
    const list = screen.getByTestId('composer-access-list')
    await waitFor(() => expect(document.activeElement).toBe(list))
    fireEvent.keyDown(list, { key: 'ArrowDown' })
    fireEvent.keyDown(list, { key: 'Enter' })
    await waitFor(() => expect(onPick).toHaveBeenCalledWith('session'))
  })
})
