/**
 * Ephe — shortcut cheatsheet (round 14, P3-F1)
 *
 * "?" (no focused input) opens the overlay, ESC/⌘K closes it.
 * Purpose: shortcuts stay undiscoverable otherwise — a shortcut nobody
 * finds is wasted development (AI-client parity: pro tools document
 * their keys visibly).
 */
import { useEffect } from 'react'
import { m, AnimatePresence } from 'framer-motion'
import { Keyboard } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SHORTCUTS, isMacPlatform, renderKeys } from '@/lib/shortcuts'

interface ShortcutRow {
  keys: string
  label: string
}

export const SHORTCUTS_EVENT = 'ephe:toggle-shortcuts'

export default function ShortcutOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const isMac = isMacPlatform()
  // P2-4 (DRY): the rows come from the central SHORTCUTS table —
  // the same truth ChatLayout uses to wire its handlers.
  // P2-A: `fallback` acts as the i18n defaultValue so that, until the
  // locale copy is filled in, no raw key appears in the overlay.
  const rows: ShortcutRow[] = SHORTCUTS.map((s) => ({
    keys: renderKeys(s.keys, isMac),
    label: t(s.labelKey, { defaultValue: s.fallback ?? s.labelKey }),
  }))

  return (
    <AnimatePresence>
      {open && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-modal bg-canvas/70 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={onClose}
          data-testid="shortcuts-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t('shortcuts.title')}
        >
          <m.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="float-surface w-full max-w-sm p-5"
            data-float="3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4">
              <Keyboard className="h-4 w-4 text-brand" />
              <h2 className="text-ui-sm font-semibold text-foreground/90">
                {t('shortcuts.title')}
              </h2>
            </div>
            <ul className="space-y-2">
              {rows.map((row) => (
                <li key={row.label} className="flex items-center justify-between gap-4">
                  <span className="text-ui-xs text-ink-faint">{row.label}</span>
                  <kbd className="rounded-md border border-hairline bg-canvas px-2 py-0.5 font-mono text-ui-sm text-foreground/80 whitespace-nowrap">
                    {row.keys}
                  </kbd>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-ui-xs text-ink-faint">{t('shortcuts.hint')}</p>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
