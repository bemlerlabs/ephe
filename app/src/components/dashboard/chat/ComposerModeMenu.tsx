/**
 * Ephe — the composer's mode menu (P3 wave 2026-10-05, extracted from ChatInput).
 *
 * Finding P3-7: «Ask | Edit auto | Plan | Full access» stood in English inside
 * the German interface, with no sections and no keyboard marking.
 *
 * Short titles: NO new text is invented — the existing hint text, already
 * translated into both languages (`chat.modeHint.*`), begins with the short
 * title («Fragen — Ephe antwortet nur…» → «Fragen»). Without a resolved // language-gate: ignore — the German hint text and its short label (de.json:210 ask)
 * translation (tests, missing key) the hard-coded fallback name takes over.
 *
 * Sections: ask runs no tools, plan permits only read-only inspection,
 * edit-auto and full-access may write — exactly the semantics of
 * `server/routes/chat.py::_mode_context`.
 */
import { useMemo, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ComposerMenu,
  MenuOptionRow,
  MenuSectionLabel,
  useMenuFocus,
  useRovingSelection,
  type MenuPos,
} from './ComposerMenu'

export interface ComposerMode {
  key: string
  /** Hard-coded fallback name when the translation does not resolve (tests, missing key). */
  fallback: string
  hintKey: string
  sectionKey: string
  sectionDefault: string
}

/** Order == reading direction == keyboard ring. */
export const COMPOSER_MODES: ComposerMode[] = [
  {
    key: 'ask',
    fallback: 'Ask',
    hintKey: 'chat.modeHint.ask',
    sectionKey: 'chat.modeSection.none',
    sectionDefault: 'Without tools',
  },
  {
    key: 'plan',
    fallback: 'Plan',
    hintKey: 'chat.modeHint.plan',
    sectionKey: 'chat.modeSection.read',
    sectionDefault: 'Read only',
  },
  {
    key: 'edit-auto',
    fallback: 'Edit auto',
    hintKey: 'chat.modeHint.edit-auto',
    sectionKey: 'chat.modeSection.write',
    sectionDefault: 'With write access',
  },
  {
    key: 'full-access',
    fallback: 'Full access',
    hintKey: 'chat.modeHint.full-access',
    sectionKey: 'chat.modeSection.write',
    sectionDefault: 'With write access',
  },
]

/**
 * The short title of a mode, read from the real hint text: everything before the
 * em dash. If the translation does not resolve (t returns the key) or the separator
 * is missing, the hard-coded fallback name stays.
 */
export function modeShortLabel(mode: ComposerMode, hint: string): string {
  if (!hint || hint === mode.hintKey) return mode.fallback
  const head = hint.split('—')[0]?.trim() ?? ''
  return head && head.length <= 24 ? head : mode.fallback
}

/**
 * The half of the hint that says what the mode does: everything after the em
 * dash. Empty when the translation did not resolve, so a row shows the label
 * alone rather than a sentence that is not there.
 */
export function modeMeaning(mode: ComposerMode, hint: string): string {
  if (!hint || hint === mode.hintKey) return ''
  return hint.split('—').slice(1).join('—').trim()
}

export interface ComposerModeMenuProps {
  pos: MenuPos | null
  anchorRef: RefObject<HTMLElement | null>
  mode: string
  onClose: () => void
  onPick: (key: string) => void
}

export default function ComposerModeMenu({
  pos,
  anchorRef,
  mode,
  onClose,
  onPick,
}: ComposerModeMenuProps) {
  const { t } = useTranslation()
  const labelled = useMemo(
    () =>
      COMPOSER_MODES.map((m) => {
        const hint = String(t(m.hintKey))
        return { mode: m, label: modeShortLabel(m, hint), meaning: modeMeaning(m, hint) }
      }),
    [t],
  )
  const { index, move } = useRovingSelection(labelled.length, mode)
  const { ref, release } = useMenuFocus(anchorRef)
  // The keyboard ring's current row — the menu names it via aria-activedescendant,
  // so AT follows the highlight the same way the model menu does.
  const activeModeKey = labelled[Math.min(index, Math.max(0, labelled.length - 1))]?.mode.key

  const sections: { key: string; def: string; items: typeof labelled }[] = []
  for (const item of labelled) {
    const last = sections[sections.length - 1]
    if (last && last.key === item.mode.sectionKey) last.items.push(item)
    else sections.push({ key: item.mode.sectionKey, def: item.mode.sectionDefault, items: [item] })
  }

  return (
    <ComposerMenu
      testId="composer-mode-menu"
      pos={pos}
      anchorRef={anchorRef}
      onClose={onClose}
      role={null}
      widthClass="w-72"
    >
      <div
        ref={ref}
        tabIndex={-1}
        data-testid="composer-mode-list"
        role="menu"
        aria-label={t('chat.modeSelectorAria')}
        aria-activedescendant={activeModeKey ? `mode-opt-${activeModeKey}` : undefined}
        className="py-1.5 outline-none"
        onKeyDown={(ev) => {
          if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault()
            move(ev.key === 'ArrowDown' ? 1 : -1)
          } else if (ev.key === 'Enter' || ev.key === 'Tab') {
            ev.preventDefault()
            const hit = labelled[index]
            if (hit) {
              release()
              onPick(hit.mode.key)
            }
          } else if (ev.key === 'Escape') {
            ev.preventDefault()
            ev.stopPropagation()
            release()
            onClose()
          }
        }}
      >
        {sections.map((section) => (
          <div key={section.key} role="group">
            <MenuSectionLabel testId={`composer-mode-section-${section.key.split('.').pop()}`}>
              {t(section.key, { defaultValue: section.def })}
            </MenuSectionLabel>
            {section.items.map(({ mode: m, label, meaning }) => {
              const ring = labelled.findIndex((x) => x.mode.key === m.key)
              const active = ring === index
              const hint = String(t(m.hintKey))
              return (
                <MenuOptionRow
                  key={m.key}
                  id={`mode-opt-${m.key}`}
                  testId={`composer-mode-${m.key}`}
                  role="menuitemradio"
                  active={active}
                  selected={mode === m.key}
                  title={hint}
                  ariaLabel={hint}
                  onSelect={() => onPick(m.key)}
                >
                  <span className="flex min-w-0 flex-col items-start">
                    <span className="truncate max-w-full">{label}</span>
                    {meaning && (
                      <span
                        data-testid={`composer-mode-${m.key}-meaning`}
                        className="whitespace-normal text-ui-2xs leading-snug text-ink-faint/90"
                      >
                        {meaning}
                      </span>
                    )}
                  </span>
                </MenuOptionRow>
              )
            })}
          </div>
        ))}
      </div>
      <p
        data-testid="composer-mode-note"
        className="whitespace-normal border-t border-hairline px-3 py-2 text-ui-2xs leading-relaxed text-ink-faint"
      >
        {t('chat.modeMenuNote')}
      </p>
    </ComposerMenu>
  )
}
