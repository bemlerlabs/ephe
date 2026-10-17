import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Command as CommandIcon, ArrowRight } from 'lucide-react'
import type { CommandItem } from '@/hooks/useCommandPalette'
import { useFocusReturn } from '@/hooks/useFocusReturn'
import { shortcutGlyph } from '@/lib/shortcuts'

interface CommandPaletteProps {
  open: boolean
  query: string
  setQuery: (q: string) => void
  inputRef: React.RefObject<HTMLInputElement | null>
  grouped: Record<string, CommandItem[]>
  t: ReturnType<typeof useTranslation>['t']
  onClose: () => void
  onSelect: (cmd: CommandItem) => void
}

export default function CommandPalette({
  open,
  query,
  setQuery,
  inputRef,
  grouped,
  t,
  onClose,
  onSelect,
}: CommandPaletteProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  // M3 (2026-Palette): focus returns to the opener — captured before opening.
  // Wave 10 (persona 06, measured): the palette claims `aria-modal` and did not
  // honour it — Tab left the mask after 5 stops and a close could drop focus onto
  // <body>. useFocusReturn carries the whole contract now: focus in on open, Tab
  // trapped, shell behind inert, handback to the invoker (or a stable target).
  const panelRef = useRef<HTMLDivElement>(null)
  const { onKeyDown: trapFocus, releaseFocus } = useFocusReturn({
    active: open,
    containerRef: panelRef,
  })
  // DD-14: the list must ALREADY be complete in the first render — filled as a ref
  // + useEffect it was empty on the first render, indexOf never landed, and the
  // first row stayed unmarked while the first ArrowDown skipped over it.
  const allItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = []
    for (const section of Object.values(grouped)) {
      items.push(...section)
    }
    return items
  }, [grouped])
  // New filter results (query typed) -> the marker goes back to the first row.
  useEffect(() => {
    setActiveIndex(0)
  }, [grouped])
  // Clamp instead of a ghost index: after filtering (fewer hits) the mark stays on
  // the last row that actually exists.
  const safeIndex =
    allItems.length > 0 ? Math.min(Math.max(activeIndex, 0), allItems.length - 1) : 0

  // Keyboard navigation. Important: the items come through a ref (always the
  // current render state) — otherwise an Enter typed immediately after the
  // query hits a stale list and the match never runs (found 2026-10-01: typed
  // "settings", the first Enter did nothing).
  const itemsRef = useRef(allItems)
  itemsRef.current = allItems
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Escape belongs to the mask: without this branch the key fell through the
        // window and panel.tsx threw the agent pane shut behind the open palette —
        // the mask stayed standing.
        e.preventDefault()
        // Hand focus back in THIS task: the mask unmounts with the next commit,
        // and a handback from an effect would race that unmount (and, when the
        // commit opens another modal in the same task, land on <body>).
        releaseFocus()
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        const items = itemsRef.current
        setActiveIndex(Math.min(safeIndex + 1, items.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex(Math.max(safeIndex - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const items = itemsRef.current
        const active = items[safeIndex]
        if (active) {
          releaseFocus()
          onSelect(active)
          onClose()
          return
        }
        // If input has value, trigger first match
        const first = items[0]
        if (first) {
          releaseFocus()
          onSelect(first)
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, safeIndex, onSelect, onClose, releaseFocus])

  if (!open) return null

  return (
    <div
      ref={panelRef}
      // The mask is the aria-modal surface: it takes the Tab trap (and carries
      // tabIndex={-1} so a surface without focusables can still hold focus).
      tabIndex={-1}
      onKeyDown={trapFocus}
      // px-3: without a mobile edge inset the w-full panel touches both screen
      // edges on a phone (the desktop max-w-xl still centres it). dvh, not vh:
      // on mobile the URL bar makes vh taller than what the user can actually see.
      className="fixed inset-0 z-modal flex items-start justify-center px-3 pt-[20dvh]"
      role="dialog"
      aria-modal="true"
      aria-label={t('commandPalette.title')}
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-canvas/60 backdrop-blur-sm"
        onClick={() => {
          releaseFocus()
          onClose()
        }}
      />

      {/* Panel */}
      <div
        className="relative z-sticky w-full max-w-xl float-surface overflow-hidden"
        data-float="3"
      >
        {/* Search Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-hairline">
          <Search className="h-4 w-4 text-ink-faint flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('commandPalette.placeholder')}
            className="flex-1 bg-transparent text-ui-sm text-foreground placeholder:text-ink-faint outline-none"
            role="combobox"
            aria-expanded
            aria-haspopup="listbox"
            aria-controls="cmd-palette-listbox"
            aria-activedescendant={allItems.length ? `cmd-opt-${safeIndex}` : undefined}
            aria-label={t('commandPalette.placeholder')}
          />
          <kbd className="hidden sm:inline-flex items-center gap-0.5 text-ui-xs text-ink-faint bg-surface rounded px-1.5 py-0.5 font-mono">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div
          className="max-h-[60dvh] overflow-y-auto p-2"
          role="listbox"
          id="cmd-palette-listbox"
          aria-label={t('commandPalette.title')}
        >
          {Object.keys(grouped).length === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-ui-sm text-ink-faint">{t('commandPalette.noResults')}</p>
            </div>
          ) : (
            Object.entries(grouped).map(([section, commands]) => (
              <div key={section}>
                <p className="px-2 py-1.5 flex items-center justify-between text-ui-xs font-medium text-ink-faint uppercase tracking-wider">
                  <span>{section}</span>
                  <span
                    data-testid={`cmd-group-count-${section}`}
                    className="font-mono normal-case text-ink-faint/70"
                  >
                    {commands.length}
                  </span>
                </p>
                <ul role="list">
                  {commands.map((cmd) => {
                    const idx = allItems.indexOf(cmd)
                    const isActive = idx === safeIndex
                    return (
                      <li key={cmd.id} id={`cmd-opt-${idx}`} role="option" aria-selected={isActive}>
                        <button
                          onClick={() => {
                            releaseFocus()
                            onSelect(cmd)
                          }}
                          onMouseEnter={() => setActiveIndex(allItems.indexOf(cmd))}
                          className={`w-full flex items-center gap-3 px-3 py-2 text-left text-ui-sm transition-colors rounded-lg ${
                            isActive
                              ? 'bg-brand/20 text-foreground ring-1 ring-brand/30'
                              : 'text-foreground/70 hover:bg-surface-interactive hover:text-foreground'
                          }`}
                        >
                          <CommandIcon className="h-3.5 w-3.5 text-ink-faint flex-shrink-0" />
                          <span className="flex-1 min-w-0">
                            <span className="block truncate">{cmd.label}</span>
                            {cmd.hint && (
                              <span className="block truncate text-ui-sm text-ink-faint">
                                {cmd.hint}
                              </span>
                            )}
                          </span>
                          {/* P1-16: the glyph comes from the shared shortcut table,
                              keyed by the row's own id. */}
                          {cmd.shortcutId && (
                            <span className="text-ui-xs text-ink-faint font-mono">
                              {shortcutGlyph(cmd.shortcutId)}
                            </span>
                          )}
                          <ArrowRight className="h-3 w-3 text-status-info/20" />
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-3 py-2 border-t border-hairline flex items-center gap-3 text-ui-xs text-status-info/20">
          <span className="flex items-center gap-1">
            <kbd className="bg-surface rounded px-1">↑↓</kbd> {t('commandPalette.navigate')}
          </span>
          <span className="flex items-center gap-1">
            <kbd className="bg-surface rounded px-1">↵</kbd> {t('commandPalette.select')}
          </span>
          <span className="flex items-center gap-1">
            <kbd className="bg-surface rounded px-1">ESC</kbd> {t('commandPalette.close')}
          </span>
          <span
            className="ml-auto truncate hidden sm:inline"
            title={t('commandPalette.contentHint')}
          >
            {t('commandPalette.contentHint')}
          </span>
        </div>
      </div>
    </div>
  )
}
