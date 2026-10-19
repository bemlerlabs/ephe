import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RefObject } from 'react'
import ComposerModelMenu from './ComposerModelMenu'
import type { ModelChipEntry } from './composerModelEntries'
import type { MenuPos } from './composerPopups'

/**
 * M3 (reference pattern): the model chip + its provider-picker menu — the only
 * engine entry point in the composer. State (open/menu pos/provider list) comes
 * from chat/useComposerModelSelection. Extracted from ChatInput.tsx.
 */
export default function ComposerModelChip({
  open,
  onToggle,
  onClose,
  anchorRef,
  menuPos,
  needsSetup,
  model,
  providers,
  activeP,
  onPick,
  onSetup,
}: {
  open: boolean
  onToggle: () => void
  onClose: () => void
  anchorRef: RefObject<HTMLButtonElement | null>
  menuPos: MenuPos | null
  needsSetup: boolean
  model: string
  providers: ModelChipEntry[]
  activeP: string
  onPick: (id: string, model?: string, endpoint?: string) => void
  onSetup: () => void
}) {
  const { t } = useTranslation()
  return (
    <>
      <button
        type="button"
        ref={anchorRef}
        onClick={onToggle}
        aria-label={needsSetup ? t('chat.setupEngineChipAria') : t('chat.modelChipAria')}
        aria-haspopup="listbox"
        aria-expanded={open}
        data-testid="model-chip"
        data-needs-setup={needsSetup ? 'true' : 'false'}
        className={`inline-flex items-center gap-1.5 min-w-6 min-h-6 rounded-md border px-1.5 py-0.5 text-ui-xs transition-colors max-lg:min-h-11 max-lg:min-w-11 ${
          needsSetup
            ? 'border-amber-400/40 bg-status-warning/10 text-status-warning hover:text-status-warning hover:border-amber-400/60'
            : 'border-control bg-surface text-ink-faint hover:text-foreground hover:border-brand/30'
        }`}
      >
        <span className="truncate max-w-36 min-w-0 max-lg:max-w-28">
          {needsSetup ? t('chat.setupEngineChip') : model || '…'}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {/* P3-4/P3-5: the model menu is its own module — max height at the
          viewport, internal scroll list, search from the first character,
          marked + visible current position, keyboard ring, sections by type
          and non-selectable template ENDPOINTS (`https://${…}`) as a disabled row. */}
      {open && menuPos && (
        <ComposerModelMenu
          pos={menuPos}
          anchorRef={anchorRef}
          entries={providers}
          activeP={activeP}
          model={model}
          needsSetup={needsSetup}
          onClose={onClose}
          onPick={onPick}
          onSetup={onSetup}
        />
      )}
    </>
  )
}
