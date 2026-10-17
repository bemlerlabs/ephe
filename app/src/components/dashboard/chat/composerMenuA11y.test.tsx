/**
 * Composer menu + feedback contract (WS3-21).
 *
 * The model menu already named its highlighted row (`aria-activedescendant`) and
 * carried exactly one role container. The mode and plus menus only moved DOM
 * focus: a `role="menu"` wrapped a second `role="menu"`, and the keyboard
 * highlight existed for the eye (aria-current) but not for AT. This file holds
 * the three menus to the same shape, plus the two feedback gaps at the composer's
 * foot (queued messages were silent) and on the mic (recording state unnamed).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useRef, type ReactNode, type RefObject } from 'react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue ?? key),
  }),
}))

import ComposerModeMenu from './ComposerModeMenu'
import ComposerAttachMenu from './ComposerAttachMenu'
import ComposerFooterHints from './ComposerFooterHints'
import ComposerMicButton from './ComposerMicButton'

const POS = { left: 120, bottom: 60 }

function withAnchor(ui: (ref: RefObject<HTMLButtonElement | null>) => ReactNode) {
  function Host() {
    const anchorRef = useRef<HTMLButtonElement>(null)
    return (
      <>
        <button ref={anchorRef} data-testid="trigger">
          trigger
        </button>
        {ui(anchorRef)}
      </>
    )
  }
  return render(<Host />)
}

describe('mode menu — one menu, named highlight, checked single choice', () => {
  it('renders one role=menu and carries the label on it, not on a second menu', () => {
    withAnchor((anchorRef) => (
      <ComposerModeMenu
        pos={POS}
        anchorRef={anchorRef}
        mode="ask"
        onClose={vi.fn()}
        onPick={vi.fn()}
      />
    ))
    expect(document.querySelectorAll('[role="menu"]')).toHaveLength(1)
    const menu = screen.getByTestId('composer-mode-list')
    expect(menu.getAttribute('role')).toBe('menu')
    expect(menu.getAttribute('aria-label')).toBe('chat.modeSelectorAria')
    // No role on the portal wrapper — the duplicate menu is gone.
    expect(screen.getByTestId('composer-mode-menu').getAttribute('role')).toBeNull()
  })

  it('names the highlighted row and follows it on ArrowDown', () => {
    withAnchor((anchorRef) => (
      <ComposerModeMenu
        pos={POS}
        anchorRef={anchorRef}
        mode="ask"
        onClose={vi.fn()}
        onPick={vi.fn()}
      />
    ))
    const menu = screen.getByTestId('composer-mode-list')
    expect(menu.getAttribute('aria-activedescendant')).toBe('mode-opt-ask')
    // The referenced row is in the document, otherwise the name points at nothing.
    expect(document.getElementById('mode-opt-ask')).not.toBeNull()

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(menu.getAttribute('aria-activedescendant')).toBe('mode-opt-plan')
    expect(document.getElementById('mode-opt-plan')).not.toBeNull()
  })

  it('exposes the active mode as a checked menuitemradio', () => {
    withAnchor((anchorRef) => (
      <ComposerModeMenu
        pos={POS}
        anchorRef={anchorRef}
        mode="plan"
        onClose={vi.fn()}
        onPick={vi.fn()}
      />
    ))
    const rows = screen.getAllByRole('menuitemradio')
    expect(rows).toHaveLength(4)
    expect(screen.getByTestId('composer-mode-plan').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByTestId('composer-mode-ask').getAttribute('aria-checked')).toBe('false')
    // A menuitemradio never claims aria-selected — that is the listbox role's.
    expect(screen.getByTestId('composer-mode-plan').getAttribute('aria-selected')).toBeNull()
  })
})

describe('plus menu — one menu, named highlight', () => {
  it('renders one role=menu with a label and a highlight that moves', () => {
    withAnchor((anchorRef) => (
      <ComposerAttachMenu
        pos={POS}
        anchorRef={anchorRef}
        onClose={vi.fn()}
        onAttachFile={vi.fn()}
        onAttachImage={vi.fn()}
        onCaptureScreen={vi.fn()}
        onWideResearch={vi.fn()}
      />
    ))
    expect(document.querySelectorAll('[role="menu"]')).toHaveLength(1)
    const menu = screen.getByTestId('composer-attach-list')
    expect(menu.getAttribute('aria-label')).toBe('Add attachment')
    expect(menu.getAttribute('aria-activedescendant')).toBe('attach-opt-0')
    expect(document.getElementById('attach-opt-0')).not.toBeNull()

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(menu.getAttribute('aria-activedescendant')).toBe('attach-opt-1')
  })
})

describe('composer feedback — the foot and the mic speak', () => {
  it('a queued message is a live status, not a silent glyph row', () => {
    const { unmount } = render(<ComposerFooterHints recall={{ pos: 0, total: 0 }} queueCount={2} />)
    expect(screen.getByTestId('composer-queue-hint').getAttribute('role')).toBe('status')
    unmount()
    render(<ComposerFooterHints recall={{ pos: 0, total: 0 }} queueCount={0} />)
    expect(screen.queryByTestId('composer-queue-hint')).toBeNull()
  })

  it('the recall counter stays a status region while browsing', () => {
    render(<ComposerFooterHints recall={{ pos: 1, total: 3 }} queueCount={0} />)
    expect(screen.getByTestId('composer-recall-counter').getAttribute('role')).toBe('status')
  })

  it('the mic reports its recording state', () => {
    const levels = { current: new Float32Array(4) }
    const { rerender } = render(
      <ComposerMicButton
        recording={false}
        transcribing={false}
        micFrame={0}
        micLevelsRef={levels}
        onPointerDown={vi.fn()}
        onPointerUp={vi.fn()}
      />,
    )
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('false')

    rerender(
      <ComposerMicButton
        recording
        transcribing={false}
        micFrame={1}
        micLevelsRef={levels}
        onPointerDown={vi.fn()}
        onPointerUp={vi.fn()}
      />,
    )
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('mic-waveform')).toBeTruthy()
  })
})
