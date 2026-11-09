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
  anchorRef,
  menuPos,
  onToggle,
  onClose,
  onPick,
}: {
  open: boolean
  mode: string
  anchorRef: RefObject<HTMLButtonElement | null>
  menuPos: MenuPos | null
  onToggle: () => void
  onClose: () => void
  onPick: (key: string) => void
}) {
  const { t } = useTranslation()
  // P3-7: the short title is cut from the already-translated mode hint, so for a
  // menu mode a raw key never reaches the interface. W-3 (2026-11-02): the chip
  // names the mode in both halves. The security profile is a different setting
  // with its own chip (ChatInput.tsx, `chat.permissionAria`), and this one used
  // to read the profile word under a label that showed the mode.
  // Task 3 (2026-11-04): a stored value that owns no tile — a kept `edit-auto` or
  // another client's mode — renders its section wording from the existing locale
  // leaves (`chat.modeSection.*`). Every untiled value the rename left behind is
  // an edit-family session, so "With write access" is true of it; a raw stored
  // key names nothing a user can read, and a tile title would name a mode the
  // session does not run.
  const activeMode = COMPOSER_MODES.find((m) => m.key === mode)
  const untiledSection = String(t('chat.modeSection.write'))
  const hint = activeMode ? String(t(activeMode.hintKey)) : untiledSection
  const modeLabel = activeMode ? modeShortLabel(activeMode, hint) : untiledSection
  return (
    <div className="relative inline-flex items-center shrink-0">
      <button
        type="button"
        ref={anchorRef}
        data-testid="composer-mode-selector"
        aria-label={`${String(t('chat.modeSelectorAria'))}: ${modeLabel}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title={hint}
        onClick={onToggle}
        className="inline-flex items-center gap-1 rounded-md border border-control bg-surface px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors shrink-0 min-h-6 max-lg:min-h-11"
      >
        <span className="truncate">{modeLabel}</span>
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
