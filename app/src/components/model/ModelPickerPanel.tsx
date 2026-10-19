/**
 * S2 — the body of the one model picker, apart from the frame that hosts it.
 *
 * The three hosts frame the list differently: setup and the engine settings open an
 * anchored panel under a field (a full-screen sheet on a phone), the composer opens
 * its chip menu above the composer. What is inside is the same everywhere — search,
 * four filters, four sorts, favorites and recents over the groups, metadata rows that
 * print an em-dash where the engine said nothing, and the combobox keyboard path.
 *
 * A host that keeps its own taxonomy passes `groupOf`/`groupOrder` so its headings
 * stay what they were; a host that lacks the long-standing ids passes `ids`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Search, X } from 'lucide-react'
import type { ModelRow } from './modelPickerTypes'
import {
  FILTERS,
  SORTS,
  searchRows,
  sectionRows,
  sortRows,
  type PickerFilter,
  type PickerSort,
} from './modelPickerQuery'
import { ModelPickerRow } from './ModelPickerRow'
import { readFavorites, readRecents, rememberRecent, toggleFavorite } from './modelPickerStore'

const FILTER_KEYS: Record<PickerFilter, string> = {
  free: 'modelPicker.free',
  tools: 'modelPicker.tools',
  vision: 'modelPicker.vision',
  longContext: 'modelPicker.longContext',
}

const SORT_KEYS: Record<PickerSort, string> = {
  name: 'modelPicker.sortName',
  freeFirst: 'modelPicker.sortFree',
  context: 'modelPicker.sortContext',
  price: 'modelPicker.sortPrice',
}

export interface ModelPickerIds {
  row?: (row: ModelRow) => string
  option?: (row: ModelRow) => string
  /** Keyed on the section itself, because a host renames groups by their heading. */
  section?: (section: { id: string; group?: string; labelKey: string }) => string
}

export interface ModelPickerPanelProps {
  rows: ModelRow[]
  /** The chosen tag; '' means nothing chosen yet. */
  value: string
  /** A host whose rows can repeat a tag across endpoints marks one row by its key. */
  selectedKey?: string
  onChoose: (row: ModelRow) => void
  /** The frame's close path; `true` means the trigger gets the focus back. */
  onClose: (returnFocus: boolean) => void
  /** Prefix every generated id and test id hangs off. */
  testId: string
  label: string
  /** The list's own name, when the host words it differently from the search field. */
  listLabel?: string
  placeholder?: string
  loading?: boolean
  error?: string | null
  /** Full-screen sheet: the panel carries the visible close control. */
  sheet?: boolean
  /** The composer's chip menu focuses its search field on open. */
  autoFocus?: boolean
  /** Hosts that kept their own ids pass them here; the defaults are the picker's. */
  ids?: ModelPickerIds
  /** Show the number of selectable rows beside the search field. */
  count?: boolean
  /** A host whose headings are a taxonomy passes its own grouping and order. */
  groupOf?: (row: ModelRow) => string
  groupOrder?: string[]
}

export function ModelPickerPanel({
  rows,
  value,
  selectedKey,
  onChoose,
  onClose,
  testId,
  label,
  listLabel,
  placeholder,
  loading = false,
  error = null,
  sheet = false,
  autoFocus = true,
  ids,
  count = false,
  groupOf,
  groupOrder,
}: ModelPickerPanelProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<PickerFilter[]>([])
  const [sort, setSort] = useState<PickerSort>('name')
  const [favorites, setFavorites] = useState<string[]>(() => readFavorites())
  const [recents, setRecents] = useState<string[]>(() => readRecents())
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

  const searched = useMemo(() => searchRows(rows, query, filters), [rows, query, filters])
  const sections = useMemo(
    () => sectionRows(searched, favorites, recents, groupOf, groupOrder),
    [searched, favorites, recents, groupOf, groupOrder],
  )
  /** Keyboard order is the order on screen: each section sorted, sections ordered. */
  const visible = useMemo(() => {
    const ordered: ModelRow[] = []
    for (const section of sections) {
      for (const row of sortRows(section.rows, sort)) {
        if (!ordered.some((entry) => entry.key === row.key)) ordered.push(row)
      }
    }
    return ordered
  }, [sections, sort])
  const selectable = useMemo(() => visible.filter((row) => row.selectable), [visible])
  const isSelected = useCallback(
    (row: ModelRow) => (selectedKey ? row.key === selectedKey : row.id === value),
    [selectedKey, value],
  )
  const selected = rows.find(isSelected) ?? null
  const listId = `${testId}-list`
  const rowTestId = ids?.row ?? ((row: ModelRow) => `${testId}-row-${row.id}`)
  const optionId = ids?.option ?? ((row: ModelRow) => `${testId}-option-${row.id}`)
  const sectionTestId =
    ids?.section ?? ((section: { id: string }) => `${testId}-section-${section.id}`)

  useEffect(() => {
    if (!autoFocus) return
    // rAF: in the test renderer the portal node only exists after the commit.
    const frame = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [autoFocus])

  useEffect(() => {
    setCursor((current) => {
      if (selectable.length === 0) return 0
      const hit = selectable.findIndex(isSelected)
      return hit >= 0 ? hit : Math.min(current, selectable.length - 1)
    })
  }, [isSelected, selectable])

  useEffect(() => {
    if (!listRef.current || selectable.length === 0) return
    const node = listRef.current.querySelector(`[data-index="${cursor}"]`)
    // jsdom has no layout, so the call is optional exactly as it is in the register.
    node?.scrollIntoView?.({ block: 'nearest' })
  }, [cursor, selectable])

  const choose = (row: ModelRow) => {
    if (!row.selectable) return
    setRecents(rememberRecent(row.id, recents))
    onChoose(row)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (selectable.length === 0) return
      event.preventDefault()
      setCursor((current) =>
        Math.min(
          Math.max(current + (event.key === 'ArrowDown' ? 1 : -1), 0),
          selectable.length - 1,
        ),
      )
    } else if (event.key === 'Home' || event.key === 'End') {
      if (selectable.length === 0) return
      event.preventDefault()
      setCursor(event.key === 'Home' ? 0 : selectable.length - 1)
    } else if (event.key === 'Enter') {
      if (selectable.length === 0) return
      event.preventDefault()
      const row = selectable[cursor]
      if (row) choose(row)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      onClose(true)
    }
  }

  const toggleFilter = (filter: PickerFilter) => {
    setFilters((current) =>
      current.includes(filter) ? current.filter((entry) => entry !== filter) : [...current, filter],
    )
    setCursor(0)
  }

  return (
    <>
      <div className="flex items-center gap-2 border-b border-hairline px-2 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setCursor(0)
          }}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t('modelPicker.search')}
          aria-label={label}
          role="combobox"
          aria-expanded="true"
          aria-haspopup="listbox"
          aria-controls={listId}
          aria-activedescendant={
            selectable.length > 0 && selectable[cursor]
              ? optionId(selectable[cursor] as ModelRow)
              : undefined
          }
          data-testid={`${testId}-search`}
          className="min-w-0 flex-1 bg-transparent text-ui-sm text-foreground outline-none placeholder:text-ink-faint"
        />
        {count && (
          <span
            className="shrink-0 text-ui-2xs font-mono text-ink-faint"
            data-testid={`${testId}-count`}
          >
            {selectable.length}
          </span>
        )}
        {sheet && (
          <button
            type="button"
            onClick={() => onClose(true)}
            data-testid={`${testId}-close`}
            aria-label={t('modelPicker.close')}
            className="shrink-0 rounded-lg p-2 text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-b border-hairline px-2 py-2">
        {FILTERS.map((filter) => (
          <button
            key={filter}
            type="button"
            aria-pressed={filters.includes(filter)}
            onClick={() => toggleFilter(filter)}
            data-testid={`${testId}-filter-${filter}`}
            className={`rounded-full border px-2 py-1 text-ui-2xs transition-colors focus-ring ${
              filters.includes(filter)
                ? 'border-brand/40 bg-brand/15 text-brand-deep'
                : 'border-control text-ink-soft hover:text-foreground'
            }`}
          >
            {t(FILTER_KEYS[filter])}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 text-ui-2xs text-ink-faint">
          <span>{t('modelPicker.sort')}</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as PickerSort)}
            data-testid={`${testId}-sort`}
            aria-label={t('modelPicker.sort')}
            className="rounded-md border border-control bg-input px-1.5 py-1 text-ui-2xs text-foreground focus-ring"
          >
            {SORTS.map((option) => (
              <option key={option} value={option}>
                {t(SORT_KEYS[option])}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        ref={listRef}
        id={listId}
        role="listbox"
        aria-label={listLabel ?? label}
        data-testid={`${testId}-list`}
        className="max-h-[min(52vh,22rem)] min-h-0 flex-1 overflow-y-auto overscroll-contain p-1"
      >
        {loading && (
          <p
            className="flex items-center gap-2 px-2 py-3 text-ui-xs text-ink-faint"
            data-testid={`${testId}-loading`}
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            {t('modelPicker.loading')}
          </p>
        )}
        {!loading && error && (
          <p
            className="px-2 py-3 text-ui-xs text-status-danger"
            role="alert"
            data-testid={`${testId}-error`}
          >
            {error}
          </p>
        )}
        {!loading && !error && visible.length === 0 && (
          <div className="px-2 py-3 text-ui-xs text-ink-faint" data-testid={`${testId}-empty`}>
            <p>{t('modelPicker.noResults')}</p>
            <button
              type="button"
              onClick={() => {
                setQuery('')
                setFilters([])
              }}
              data-testid={`${testId}-clear`}
              className="mt-2 rounded-lg border border-control px-2 py-1 text-ui-2xs text-ink-soft transition-colors hover:text-foreground focus-ring"
            >
              {t('modelPicker.clearFilters')}
            </button>
          </div>
        )}
        {!loading &&
          !error &&
          sections.map((section) => {
            const rowsInSection = sortRows(section.rows, sort)
            if (rowsInSection.length === 0) return null
            return (
              <div key={section.id} role="group" data-testid={sectionTestId(section)}>
                <p className="px-2 pb-1 pt-2 font-mono text-ui-2xs uppercase tracking-wider text-ink-faint">
                  {section.group ? section.labelKey : t(section.labelKey)}
                </p>
                {rowsInSection.map((row) => {
                  const index = selectable.indexOf(row)
                  return (
                    <div key={row.key} data-index={index >= 0 ? index : undefined}>
                      <ModelPickerRow
                        row={row}
                        optionId={optionId(row)}
                        testId={rowTestId(row)}
                        active={index >= 0 && index === cursor}
                        selected={isSelected(row) && selected !== null}
                        favorite={favorites.includes(row.id)}
                        onSelect={() => choose(row)}
                        onToggleFavorite={() =>
                          setFavorites((current) => toggleFavorite(row.id, current))
                        }
                      />
                    </div>
                  )
                })}
              </div>
            )
          })}
      </div>
    </>
  )
}
