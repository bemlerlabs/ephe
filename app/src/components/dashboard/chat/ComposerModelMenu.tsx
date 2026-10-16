/**
 * Ephe — the composer's model menu (P3 wave 2026-10-05, split out of ChatInput).
 *
 * Finding P3-4: the container had no maximum height and no overflow-y — with
 * 56 scanned models the menu grew past the window edge (measured: height
 * 1470 px, top −782 px, 30 rows unreachable, scrolling impossible), and there
 * was neither search nor keyboard marking.
 *
 * Finding P3-5: between chat models stood an unfilled catalog placeholder
 * (`https://${SNOWFLAKE_ACCOUNT}…`) and speech models (whisper-1, base).
 * Hence: sections by type, template rows disabled with a reason,
 * loopback/tailnet endpoints not as a raw URL.
 *
 * Everything in the list comes out of the real provider/scan data — the search
 * only filters, it invents no entries.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
} from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'
import { ComposerMenu, MenuOptionRow, MenuSectionLabel, useRovingSelection } from './ComposerMenu'
import {
  entryKey,
  entryMatchesQuery,
  groupModelEntries,
  isActiveEntry,
  isUnconfiguredEntry,
  type ModelChipEntry,
} from './composerModelEntries'
import type { MenuPos } from './composerPopups'

export interface ComposerModelMenuProps {
  pos: MenuPos | null
  anchorRef: RefObject<HTMLElement | null>
  entries: ModelChipEntry[]
  activeP: string
  model: string
  needsSetup: boolean
  onClose: () => void
  onPick: (id: string, model?: string, endpoint?: string) => void
  onSetup: () => void
}

export default function ComposerModelMenu({
  pos,
  anchorRef,
  entries,
  activeP,
  model,
  needsSetup,
  onClose,
  onPick,
  onSetup,
}: ComposerModelMenuProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const activeRowRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // rAF: in the test renderer the portal node only exists after the commit.
    const id = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [])

  const groups = useMemo(() => {
    const hits = query.trim() ? entries.filter((e) => entryMatchesQuery(e, query)) : entries
    return groupModelEntries(hits)
  }, [entries, query])

  // Navigation == reading direction: unconfigured templates last, before them
  // the other types, chat models on top. Disabled rows stay in place —
  // the ring skips them.
  const flat = useMemo(() => [...groups.chat, ...groups.other, ...groups.unconfigured], [groups])
  const selectable = useMemo(() => flat.filter((e) => !isUnconfiguredEntry(e)), [flat])
  const { index, setIndex, move } = useRovingSelection(selectable.length, `${query}|${flat.length}`)
  const current = selectable[Math.min(index, Math.max(0, selectable.length - 1))]

  // Make the current position visible (P3-4): when opening and at every
  // highlight step. jsdom does not know scrollIntoView → guarded.
  useEffect(() => {
    const el = activeRowRef.current
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest' })
  }, [index, query, flat.length])

  const pick = (e: ModelChipEntry | undefined, fromKeyboard = false) => {
    if (!e || isUnconfiguredEntry(e)) return
    if (fromKeyboard) anchorRef.current?.focus()
    onPick(e.kind ?? entryKey(e), e.model, e.endpoint)
  }

  const onKeyDown = (ev: ReactKeyboardEvent) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (selectable.length === 0) return
      ev.preventDefault()
      move(ev.key === 'ArrowDown' ? 1 : -1)
    } else if (ev.key === 'Home' || ev.key === 'End') {
      if (selectable.length === 0) return
      ev.preventDefault()
      setIndex(ev.key === 'Home' ? 0 : selectable.length - 1)
    } else if (ev.key === 'Enter' || ev.key === 'Tab') {
      ev.preventDefault()
      pick(current, true)
    } else if (ev.key === 'Escape') {
      ev.preventDefault()
      ev.stopPropagation()
      anchorRef.current?.focus()
      onClose()
    }
  }

  /** Endpoint display: raw loopback/tailnet URLs do not belong in the list. */
  const endpointText = (e: ModelChipEntry): string => {
    if (isUnconfiguredEntry(e))
      return t('chat.modelUnconfiguredHint', { defaultValue: 'not configured' })
    if (e.endpointKind === 'loopback')
      return t('chat.modelEndpointLocal', { defaultValue: 'local' })
    if (e.endpointKind === 'private')
      return t('chat.modelEndpointPrivate', { defaultValue: 'private network' })
    return e.endpoint ?? ''
  }

  const renderRow = (e: ModelChipEntry) => {
    const key = entryKey(e)
    const selected = isActiveEntry(e, activeP, model)
    const disabled = isUnconfiguredEntry(e)
    const ringPos = selectable.indexOf(e)
    const active = !disabled && current === e
    const hint = endpointText(e)
    return (
      <div key={`${key}|${e.endpoint ?? ''}`} ref={selected ? activeRowRef : undefined}>
        <MenuOptionRow
          id={`model-opt-${ringPos >= 0 ? ringPos : key}`}
          testId={`model-chip-option-${key}`}
          role="option"
          active={active}
          selected={selected}
          disabled={disabled}
          title={e.endpoint ? `${e.label} — ${e.endpoint}` : e.label}
          ariaLabel={`${e.label}${hint ? ` — ${hint}` : ''}`}
          hint={hint ? <span className="truncate max-w-40">{hint}</span> : undefined}
          onSelect={() => pick(e)}
        >
          {e.label}
        </MenuOptionRow>
      </div>
    )
  }

  /** One section of the list: its heading and its rows. An empty group
   *  renders nothing — "Andere Typen" disappears instead of leaving // language-gate: ignore — the German section heading quoted here (de.json:238 modelGroupOther)
   *  a heading above no row at all. */
  const renderGroup = (id: string, label: string, entries: ModelChipEntry[]) => {
    if (entries.length === 0) return null
    return (
      <div role="group" data-testid={id}>
        <MenuSectionLabel>{label}</MenuSectionLabel>
        {entries.map(renderRow)}
      </div>
    )
  }

  return (
    <ComposerMenu
      testId="model-chip-menu"
      pos={pos}
      anchorRef={anchorRef}
      onClose={onClose}
      role={null}
      widthClass="w-[min(30rem,calc(100vw-2rem))]"
      scroll="child"
    >
      <div onKeyDown={onKeyDown}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-hairline">
          <Search className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(ev) => setQuery(ev.target.value)}
            data-testid="model-chip-search"
            role="combobox"
            aria-expanded="true"
            aria-haspopup="listbox"
            aria-controls="model-chip-listbox"
            aria-activedescendant={
              current ? `model-opt-${Math.min(index, selectable.length - 1)}` : undefined
            }
            aria-label={t('chat.modelSearchAria', { defaultValue: 'Search models' })}
            placeholder={t('chat.modelSearchPlaceholder', {
              defaultValue: 'Type a model or endpoint…',
            })}
            className="w-full min-w-0 bg-transparent text-ui-xs text-foreground placeholder:text-ink-faint outline-none"
          />
          <span
            className="shrink-0 text-ui-2xs text-ink-faint font-mono"
            data-testid="model-chip-count"
          >
            {selectable.length}
          </span>
        </div>
        <div
          id="model-chip-listbox"
          role="listbox"
          aria-label={t('chat.modelMenuAria', { defaultValue: 'Choose a model' })}
          data-testid="model-chip-list"
          className="max-h-[min(52vh,22rem)] min-h-0 overflow-y-auto overscroll-contain py-1.5"
        >
          {needsSetup && (
            <div role="group" data-testid="model-group-setup">
              <MenuSectionLabel>
                {t('chat.modelGroupSetup', { defaultValue: 'Set up the engine' })}
              </MenuSectionLabel>
              <MenuOptionRow
                id="model-opt-setup"
                testId="model-chip-option-setup"
                role="option"
                active={false}
                onSelect={onSetup}
              >
                {t('chat.setupEngineChip')}
              </MenuOptionRow>
            </div>
          )}
          {renderGroup(
            'model-group-chat',
            t('chat.modelGroupChat', { defaultValue: 'Chat models' }),
            groups.chat,
          )}
          {renderGroup(
            'model-group-other',
            t('chat.modelGroupOther', { defaultValue: 'Other types (speech, image)' }),
            groups.other,
          )}
          {renderGroup(
            'model-group-unconfigured',
            t('chat.modelGroupUnconfigured', {
              defaultValue: 'No endpoint — not configurable',
            }),
            groups.unconfigured,
          )}
          {flat.length === 0 && !needsSetup && (
            <p data-testid="model-chip-empty" className="px-3 py-2 text-ui-xs text-ink-faint">
              {t('chat.modelNoHits', {
                defaultValue: 'No model matches what you typed.',
              })}
            </p>
          )}
        </div>
      </div>
    </ComposerMenu>
  )
}
