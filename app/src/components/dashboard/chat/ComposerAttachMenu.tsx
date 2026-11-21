/**
 * Ephe — plus menu of the composer (P3 wave 2026-10-05, out of ChatInput).
 *
 * Finding P3-2: the menu sat with `absolute bottom-12` inside the composer panel and was
 * painted over by the panel — «Datei anhängen» and «Bild anhängen» were not // language-gate: ignore — both are German labels the UI renders (de.json:85-86)
 * reachable (the hit-test of the rows returned `composer-actions-row`). On top of that
 * a `div.fixed.inset-0.z-overlay` covered the whole window: the sidebar and
 * even the text field were click-dead, and Escape left the menu open.
 *
 * Now: a body portal above the trigger, clamped to the viewport, an outside-click
 * listener instead of a scrim, the keyboard ring from row 1, Escape closes.
 */
import { useTranslation } from 'react-i18next'
import { type RefObject } from 'react'
import { Image, Monitor, Paperclip, Telescope } from 'lucide-react'
import { canCaptureScreen } from '@/lib/attachments'
import {
  ComposerMenu,
  MenuOptionRow,
  useMenuFocus,
  useRovingSelection,
  type MenuPos,
} from './ComposerMenu'

export interface ComposerAttachMenuProps {
  pos: MenuPos | null
  anchorRef: RefObject<HTMLElement | null>
  onClose: () => void
  onAttachFile: () => void
  onAttachImage: () => void
  onCaptureScreen: () => void
  onWideResearch: () => void
}

export default function ComposerAttachMenu({
  pos,
  anchorRef,
  onClose,
  onAttachFile,
  onAttachImage,
  onCaptureScreen,
  onWideResearch,
}: ComposerAttachMenuProps) {
  const { t } = useTranslation()
  const { ref, release } = useMenuFocus(anchorRef)

  type Item = { testId: string; label: string; icon: typeof Paperclip; run: () => void }
  const items: Item[] = [
    {
      testId: 'composer-attach-file',
      label: t('chat.attachFile'),
      icon: Paperclip,
      run: onAttachFile,
    },
    {
      testId: 'composer-attach-image',
      label: t('chat.attachImage'),
      icon: Image,
      run: onAttachImage,
    },
  ]
  if (canCaptureScreen()) {
    items.push({
      testId: 'composer-attach-screenshot',
      label: t('chat.captureScreen', { defaultValue: 'Capture screenshot' }),
      icon: Monitor,
      run: onCaptureScreen,
    })
  }
  items.push({
    testId: 'composer-wide-research',
    label: t('chat.wideResearchLabel'),
    icon: Telescope,
    run: onWideResearch,
  })

  const { index, move } = useRovingSelection(items.length, items.length)

  const pick = (item: Item | undefined, fromKeyboard = false) => {
    if (!item) return
    if (fromKeyboard) release()
    item.run()
  }

  return (
    <ComposerMenu
      testId="composer-attach-menu"
      pos={pos}
      anchorRef={anchorRef}
      onClose={onClose}
      role={null}
      widthClass="min-w-52"
    >
      <div
        ref={ref}
        tabIndex={-1}
        data-testid="composer-attach-list"
        role="menu"
        aria-label={t('chat.attachMenuAria', { defaultValue: 'Add attachment' })}
        aria-activedescendant={items[index] ? `attach-opt-${index}` : undefined}
        className="py-1.5 outline-none"
        onKeyDown={(ev) => {
          if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault()
            move(ev.key === 'ArrowDown' ? 1 : -1)
          } else if (ev.key === 'Enter' || ev.key === 'Tab') {
            ev.preventDefault()
            pick(items[index], true)
          } else if (ev.key === 'Escape') {
            ev.preventDefault()
            ev.stopPropagation()
            release()
            onClose()
          }
        }}
      >
        {items.map((item, i) => {
          const Icon = item.icon
          return (
            <MenuOptionRow
              key={item.testId}
              id={`attach-opt-${i}`}
              testId={item.testId}
              role="menuitem"
              active={i === index}
              onSelect={() => pick(item)}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{item.label}</span>
              </span>
            </MenuOptionRow>
          )
        })}
      </div>
    </ComposerMenu>
  )
}
