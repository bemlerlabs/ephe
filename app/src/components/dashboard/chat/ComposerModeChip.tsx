import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RefObject } from 'react'
import ComposerModeMenu, { COMPOSER_MODES, modeShortLabel } from './ComposerModeMenu'
import type { MenuPos } from './composerPopups'

/**
 * M3/G-A (reference pattern): interactive mode selector as a pop-up menu
 * (like the model chip) — compact, one chip + a dropdown picker.
 * Extracted from ChatInput.tsx; the open state stays with the caller so the
 * shared escape chain keeps working.
 */
export default function ComposerModeChip({
  open,
  mode,
  approval,
  anchorRef,
  menuPos,
  onToggle,
  onClose,
  onPick,
}: {
  open: boolean
  mode: string
  /** F2: the approval profile the chip states next to the mode. */
  approval: string
  anchorRef: RefObject<HTMLButtonElement | null>
  menuPos: MenuPos | null
  onToggle: () => void
  onClose: () => void
  onPick: (key: string) => void
}) {
  const { t } = useTranslation()
  // P3-7: the short title is cut from the already-translated mode hint, so a raw
  // key never reaches the interface. F2: the chip names itself as the profile and
  // carries the mode as its value.
  const activeMode = COMPOSER_MODES.find((m) => m.key === mode) ?? COMPOSER_MODES[0]!
  const modeLabel = modeShortLabel(activeMode, String(t(activeMode.hintKey)))
  return (
    <div className="relative inline-flex items-center shrink-0">
      <button
        type="button"
        ref={anchorRef}
        data-testid="composer-mode-selector"
        aria-label={`${String(t('chat.modeSelectorAria'))} · ${String(t(`chat.perm.${approval}`))}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title={String(t(activeMode.hintKey))}
        onClick={onToggle}
        className="inline-flex items-center gap-1 rounded-md border border-control bg-surface px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors shrink-0 min-h-6 max-lg:min-h-11"
      >
        <span className="truncate">
          {t('chat.profilePrefix')} {modeLabel}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {/* P3-7: sections + short title from the translated hint text,
          keyboard ring from row 1, Escape closes. */}
      {open && menuPos && (
        <ComposerModeMenu
          pos={menuPos}
          anchorRef={anchorRef}
          mode={mode}
          onClose={onClose}
          onPick={onPick}
        />
      )}
    </div>
  )
}
