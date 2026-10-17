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
  // P3-7: the short title on the chip comes from the already-translated hint text
  // («Fragen — Ephe antwortet nur…» → «Fragen»); if it cannot be resolved the // language-gate: ignore — both are the German composer-mode hint and short label (app/src/locales/de.json:210 ask)
  // fallback name applies, so a raw key never shows up in the interface.
  const activeMode = COMPOSER_MODES.find((m) => m.key === mode) ?? COMPOSER_MODES[0]!
  const modeLabel = modeShortLabel(activeMode, String(t(activeMode.hintKey)))
  return (
    <div className="relative inline-flex items-center shrink-0">
      <button
        type="button"
        ref={anchorRef}
        data-testid="composer-mode-selector"
        aria-label={t('chat.modeSelectorAria')}
        aria-haspopup="menu"
        aria-expanded={open}
        title={String(t(activeMode.hintKey))}
        onClick={onToggle}
        className="inline-flex items-center gap-1 rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors shrink-0 min-h-6 max-lg:min-h-11"
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
