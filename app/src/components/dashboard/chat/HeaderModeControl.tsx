/**
 * Ephe — the response mode, chosen in the header (owner wish 2026-11-10:
 * "den Modus soll der User oben im Kopf von Ephe auswählen, wie es DeepSeek
 * Harness macht").
 *
 * One control, not two: the composer used to carry a mode chip beside the
 * approval badge, which read as two unrelated states side by side. The mode is
 * a per-session attribute and gates what a turn may run, so it sits with the
 * identity of the session it belongs to; the approval profile is the ceiling and
 * stays on the composer, where every tool call is approved.
 *
 * The trigger names the mode and opens downward; the menu is `ModeMenu`.
 * Creator is the one tile that asks first (`CreatorConsentDialog`), and only the
 * answer switches the session — an entry that set the mode first would hand the
 * user a mode whose calls the guard then refuses.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { DEFAULT_COMPOSER_MODE, useChatStore } from '@/store/chatStore'
import CreatorConsentDialog from './CreatorConsentDialog'
import ModeMenu from './ModeMenu'
import { SESSION_MODES, modeMeaning, modeShortLabel } from './modeCatalog'

export default function HeaderModeControl() {
  const { t } = useTranslation()
  const activeSessionId = useChatStore((s) => s.activeSessionId)
  const storeMode = useChatStore((s) => s.sessions.find((x) => x.id === s.activeSessionId)?.mode)
  // W19: the mode is a session attribute (IndexedDB + server mirror), so this
  // view follows the store and a pick writes back through it.
  const [mode, setMode] = useState<string>(() =>
    typeof storeMode === 'string' && storeMode ? storeMode : DEFAULT_COMPOSER_MODE,
  )
  useEffect(() => {
    if (typeof storeMode === 'string' && storeMode) setMode(storeMode)
  }, [activeSessionId, storeMode])

  const [open, setOpen] = useState(false)
  const [consentOpen, setConsentOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  const commitMode = useCallback(
    (key: string) => {
      setMode(key)
      if (activeSessionId) {
        const store = useChatStore.getState() as unknown as {
          setSessionMode?: (id: string, mode: string) => void
        }
        store.setSessionMode?.(activeSessionId, key)
      }
    },
    [activeSessionId],
  )

  const pickMode = useCallback(
    (key: string) => {
      setOpen(false)
      if (key === 'creator' && activeSessionId) {
        setConsentOpen(true)
        return
      }
      commitMode(key)
    },
    [activeSessionId, commitMode],
  )

  const closeMenu = useCallback(() => {
    setOpen(false)
  }, [])

  // A stored value that owns no tile (a kept `edit-auto`, another client's mode)
  // names a section instead of a mode: the header must not print a raw key.
  const activeMode = SESSION_MODES.find((m) => m.key === mode)
  const untiledSection = String(t('chat.modeSection.write'))
  const hint = activeMode ? String(t(activeMode.hintKey)) : untiledSection
  const label = activeMode ? modeShortLabel(activeMode, hint) : untiledSection
  const meaning = activeMode ? modeMeaning(activeMode, hint) : ''
  const Icon = activeMode?.icon

  return (
    <div className="relative flex items-center shrink-0">
      <button
        type="button"
        ref={triggerRef}
        data-testid="header-mode-control"
        data-mode={mode}
        aria-label={`${String(t('chat.modeSelectorAria'))}: ${label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title={meaning ? `${label} — ${meaning}` : hint}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(ev) => {
          if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault()
            setOpen(true)
          }
        }}
        className="inline-flex items-center gap-1 rounded-md border border-control bg-surface px-1.5 py-0.5 text-ui-xs text-ink-soft transition-colors shrink-0 min-h-6 max-lg:min-h-9 hover:text-foreground hover:border-brand/30 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        {Icon && <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
        <span className="hidden xl:inline truncate max-w-24">{label}</span>
        {/* Below lg the label is gone, so the chevron would only cost the header's
            last pixels; the button still reads as a menu by its box and its name. */}
        <ChevronDown
          className={`hidden lg:block h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <ModeMenu anchorRef={triggerRef} mode={mode} onClose={closeMenu} onPick={pickMode} />
      )}
      {consentOpen && activeSessionId && (
        <CreatorConsentDialog
          open
          sessionId={activeSessionId}
          onConfirm={() => {
            setConsentOpen(false)
            commitMode('creator')
          }}
          onClosed={() => setConsentOpen(false)}
        />
      )}
    </div>
  )
}
