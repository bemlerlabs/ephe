import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RefObject } from 'react'
import ComposerAttachMenu from './ComposerAttachMenu'
import type { MenuPos } from './composerPopups'

/**
 * P6 (ref-23): ONE plus for all attachments — file/image/screenshot live in the
 * menu, the main row stays narrow. Extracted from ChatInput.tsx; the open state
 * stays with the caller so the shared escape chain keeps working.
 */
export default function ComposerAttachButton({
  open,
  onToggle,
  onClose,
  anchorRef,
  menuPos,
  onAttachFile,
  onAttachImage,
  onCaptureScreen,
  onWideResearch,
}: {
  open: boolean
  onToggle: () => void
  onClose: () => void
  anchorRef: RefObject<HTMLButtonElement | null>
  menuPos: MenuPos | null
  onAttachFile: () => void
  onAttachImage: () => void
  onCaptureScreen: () => void
  onWideResearch: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="relative inline-flex items-center shrink-0">
      <button
        type="button"
        ref={anchorRef}
        onClick={onToggle}
        aria-label={t('chat.attachMenuAria', { defaultValue: 'Add attachment' })}
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid="composer-attach-plus"
        className="p-2.5 rounded-lg shrink-0 hover:bg-brand/10 text-ink-soft hover:text-brand transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 max-lg:min-w-11 max-lg:min-h-11"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
      </button>
      {/* P3-2: menu as a body portal above the trigger (before: `absolute`
          inside the composer window — the first two items sat behind it),
          without a full-surface scrim — that made the sidebar AND the
          text field unclickable. */}
      {open && (
        <ComposerAttachMenu
          pos={menuPos}
          anchorRef={anchorRef}
          onClose={onClose}
          onAttachFile={() => {
            onClose()
            onAttachFile()
          }}
          onAttachImage={() => {
            onClose()
            onAttachImage()
          }}
          onCaptureScreen={() => {
            onClose()
            onCaptureScreen()
          }}
          onWideResearch={() => {
            onClose()
            onWideResearch()
          }}
        />
      )}
    </div>
  )
}
