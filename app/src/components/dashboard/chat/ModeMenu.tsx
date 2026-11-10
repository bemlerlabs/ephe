/**
 * Ephe — the response-mode menu (owner wish 2026-11-10: the mode is chosen in
 * the header, like the reference client, and the composer keeps the access side).
 *
 * The rows are the four modes with the icon, the short title and the sentence
 * that says what the mode does (`chat.modeHint.*`); the tag on the right is the
 * access the mode grants (`chat.modeSection.*`). The footnote names the second
 * store and which of the two is the ceiling, so a reader who opens this menu
 * learns the rule where the rule applies.
 *
 * It is a portal because the header clips (`overflow-hidden` on the column) and
 * measures downward against the trigger; the composer's menus open upward and
 * keep their own shell (`ComposerMenu`).
 */
import { useEffect, useLayoutEffect, useMemo, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { clampCenter } from './composerPopups'
import {
  MenuOptionRow,
  useDismissOnOutside,
  useMenuFocus,
  useRovingSelection,
} from './ComposerMenu'
import { SESSION_MODES, modeMeaning, modeShortLabel } from './modeCatalog'

export interface ModeMenuProps {
  /** The header trigger — a click on it does not count as outside. */
  anchorRef: RefObject<HTMLElement | null>
  mode: string
  onClose: () => void
  onPick: (key: string) => void
}

/** The menu is 20rem wide; the clamp needs the number, the class writes it. */
const MENU_WIDTH = 288

export default function ModeMenu({ anchorRef, mode, onClose, onPick }: ModeMenuProps) {
  const { t } = useTranslation()
  const [top, setTop] = useState(0)
  const [left, setLeft] = useState(0)

  const rows = useMemo(
    () =>
      SESSION_MODES.map((entry) => {
        const hint = String(t(entry.hintKey))
        return {
          mode: entry,
          label: modeShortLabel(entry, hint),
          meaning: modeMeaning(entry, hint),
          hint,
          access: String(t(entry.sectionKey, { defaultValue: entry.sectionDefault })),
        }
      }),
    [t],
  )
  const { index, move, setIndex } = useRovingSelection(rows.length, mode)
  // The ring starts on the mode the session runs, so the highlight and the check
  // mark the same row when the menu opens.
  useEffect(() => {
    const at = SESSION_MODES.findIndex((entry) => entry.key === mode)
    if (at >= 0) setIndex(at)
  }, [mode, setIndex])
  const { ref, release } = useMenuFocus(anchorRef)
  const activeKey = rows[Math.min(index, Math.max(0, rows.length - 1))]?.mode.key

  useLayoutEffect(() => {
    const anchor = anchorRef.current
    if (!anchor) return
    const rect = anchor.getBoundingClientRect()
    setTop(Math.round(rect.bottom + 6))
    setLeft(Math.round(clampCenter(rect.left + rect.width / 2, MENU_WIDTH, window.innerWidth)))
  }, [anchorRef])

  useDismissOnOutside(true, onClose, () => [ref.current, anchorRef.current])

  const choose = (key: string) => {
    release()
    onPick(key)
  }

  return createPortal(
    <div
      data-testid="mode-menu"
      style={{ top, left }}
      className="fixed z-modal w-72 -translate-x-1/2 rounded-xl border border-hairline bg-surface shadow-elevation-2 max-h-[min(70vh,30rem)] overflow-y-auto overscroll-contain py-1.5"
    >
      <div
        ref={ref}
        tabIndex={-1}
        data-testid="mode-list"
        role="menu"
        aria-label={t('chat.modeSelectorAria')}
        aria-activedescendant={activeKey ? `mode-opt-${activeKey}` : undefined}
        className="outline-none"
        onKeyDown={(ev) => {
          if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault()
            move(ev.key === 'ArrowDown' ? 1 : -1)
          } else if (ev.key === 'Home' || ev.key === 'End') {
            ev.preventDefault()
            setIndex(ev.key === 'Home' ? 0 : rows.length - 1)
          } else if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault()
            const hit = rows[index]
            if (hit) choose(hit.mode.key)
          } else if (ev.key === 'Tab') {
            release()
            onClose()
          } else if (ev.key === 'Escape') {
            ev.preventDefault()
            ev.stopPropagation()
            release()
            onClose()
          }
        }}
      >
        {rows.map(({ mode: entry, label, meaning, hint, access }) => {
          const ring = rows.findIndex((x) => x.mode.key === entry.key)
          const Icon = entry.icon
          return (
            <MenuOptionRow
              key={entry.key}
              id={`mode-opt-${entry.key}`}
              testId={`mode-option-${entry.key}`}
              role="menuitemradio"
              active={ring === index}
              selected={mode === entry.key}
              title={hint}
              ariaLabel={hint}
              onSelect={() => choose(entry.key)}
            >
              <span className="flex min-w-0 flex-1 flex-col items-start gap-0.5">
                <span className="flex w-full items-center gap-2">
                  <Icon
                    className="h-4 w-4 shrink-0 text-ink-soft"
                    aria-hidden="true"
                    data-testid={`mode-icon-${entry.key}`}
                  />
                  <span className="truncate text-ui-sm font-medium text-foreground/90">
                    {label}
                  </span>
                  <span className="ml-auto shrink-0 pr-1.5 text-ui-2xs text-ink-faint">
                    {access}
                  </span>
                </span>
                {meaning && (
                  <span
                    data-testid={`mode-option-${entry.key}-meaning`}
                    className="whitespace-normal text-left text-ui-2xs leading-snug text-ink-faint/90"
                  >
                    {meaning}
                  </span>
                )}
              </span>
            </MenuOptionRow>
          )
        })}
      </div>
      <p
        data-testid="mode-menu-note"
        className="whitespace-normal border-t border-hairline px-3 py-2 text-ui-2xs leading-relaxed text-ink-faint"
      >
        {t('chat.modeMenuNote')}
      </p>
    </div>,
    document.body,
  )
}
