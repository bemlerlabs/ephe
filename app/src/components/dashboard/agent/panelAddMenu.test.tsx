/**
 * Unit contract of the +-menu (PanelAddMenu) — the controlled keyboard surface.
 *
 * The integration a11y test (AgentPanel.addmenu.a11y.test.tsx) already pins:
 * the trigger wiring (aria-haspopup/expanded/controls), the complete inventory
 * (4 menu keys + 6 extra pages), 'Know'/'audit'/'zzzz' filtering, the plain
 * Arrow/Home/End walk, Enter-in-search handing focus to the first result, the
 * Tab trap (last → search, search Shift+Tab → last), Escape at the pane level
 * and the group structure. This file pins what that one cannot see:
 *   · the wrap-around edges of the roving focus and the jump from the search
 *     field into the list end,
 *   · the exact preventDefault/stopPropagation protocol (consumed keys vs.
 *     keys that bubble through to the chrome behind the menu),
 *   · the Enter semantics — never a pick, only a focus handoff,
 *   · every row kind's callback wiring with exact arguments (open/pick/close),
 *   · the menuKey → tab mapping (review → git, browser → preview),
 *   · the recent section's gate on the EXACT empty query,
 *   · the controlled search field's contract (value from prop, onQuery raw).
 *
 * Surprises verified in the source and pinned here as-is (see notes):
 *   · there is NO aria-current — the active row is document.activeElement
 *     (roving focus), the current TAB is marked by the '— now' label only,
 *   · Enter is never a pick: in the search field it focuses the first row, on
 *     a row it is left to the native button (not even preventDefault),
 *   · the recent section renders only while `query === ''` exactly — a lone
 *     space hides it although the trimmed query still matches everything,
 *   · the open-tabs section ignores the search completely — its rows and close
 *     controls stay in the menu under every query, only the offer filters,
 *   · matching is substring-based on label + menuKey + tab key, so 'review'
 *     also hits the browser entry (tab 'preview' contains 'review').
 */
import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { PanelAddMenu } from './panelAddMenu'
import type { Tab, TabState } from './primitives'

// Product labels — the search filters on them, not on keys.
const LABELS: Record<Tab, string> = {
  preview: 'Browser',
  terminal: 'Terminal',
  git: 'Changes',
  files: 'Files',
  audit: 'Audit',
  trajectory: 'Replay',
  subagents: 'Helpers',
  memory: 'Knowledge',
  side: 'Side chat',
  browser: 'Browser (legacy)', // legacy union member — no menu entry maps to it
}

const DE: Record<string, string> = {
  'agentPanel.addTab': 'Add tab',
  'agentPanel.searchTabs': 'Search tabs…',
  'agentPanel.openTabsSection': 'Open tabs',
  'agentPanel.closedTabsSection': 'Recently closed tabs',
  'agentPanel.availableTabsSection': 'Available',
  'agentPanel.noTabMatches': 'No matching tabs',
  'agentPanel.now': 'now',
  'agentPanel.closeTab': 'Close tab',
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'de' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      // Like the real i18next: {{placeholders}} are filled from the options.
      const raw = DE[key] ?? (o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        o && o[name] !== undefined ? String(o[name]) : `{{${name}}}`,
      )
    },
  }),
}))

type Overrides = Partial<{
  tabs: Tab[]
  active: Tab | null
  recent: TabState['recent']
  query: string
  withTrigger: boolean
}>

/** Dispatch a real cancelable keydown and report whether the handler ate it. */
function press(el: HTMLElement, key: string, init: KeyboardEventInit = {}): boolean {
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  el.dispatchEvent(ev)
  return ev.defaultPrevented
}

function type(search: HTMLElement, value: string) {
  fireEvent.change(search, { target: { value } })
}

function renderMenu(over: Overrides = {}) {
  const spies = {
    onPickTab: vi.fn(),
    onCloseTab: vi.fn(),
    onOpenTab: vi.fn(),
    onDismiss: vi.fn(),
    onQuery: vi.fn(),
    onAncestorKeyDown: vi.fn(),
  }
  function Host() {
    const [query, setQuery] = useState(over.query ?? '')
    return (
      // Surrounding chrome: a key the menu consumes must not reach this, an
      // unhandled one must bubble through.
      <div data-testid="host" onKeyDown={spies.onAncestorKeyDown}>
        {(over.withTrigger ?? true) && (
          <button type="button" data-testid="panel-add-tab">
            +
          </button>
        )}
        <PanelAddMenu
          tabs={over.tabs ?? ['preview']}
          active={over.active ?? 'preview'}
          recent={over.recent ?? []}
          labels={LABELS}
          query={query}
          onQuery={(next) => {
            spies.onQuery(next)
            setQuery(next)
          }}
          onPickTab={spies.onPickTab}
          onCloseTab={spies.onCloseTab}
          onOpenTab={spies.onOpenTab}
          onDismiss={spies.onDismiss}
        />
      </div>
    )
  }
  render(<Host />)
  const menu = screen.getByTestId('panel-add-menu')
  const search = screen.getByTestId('panel-tab-search') as HTMLInputElement
  // queryAll (not getAll) — several tests assert the honest empty state.
  const items = () => within(menu).queryAllByRole('menuitem') as HTMLElement[]
  // The SEARCHABLE offer rows — the open-tabs section (rows + close controls)
  // is not filtered by the query and stays for every search.
  const offerRows = () =>
    items().filter((el) => {
      const id = el.getAttribute('data-testid') ?? ''
      return id.startsWith('panel-new-tab-item-') || id.startsWith('panel-page-item-')
    })
  return { menu, search, items, offerRows, ...spies }
}

describe('PanelAddMenu — roving focus (keyboard protocol)', () => {
  it('focus starts in the search field; ArrowDown enters the list at the top, ArrowUp at its end', () => {
    const m = renderMenu()
    expect(document.activeElement).toBe(m.search)
    press(m.search, 'ArrowDown')
    expect(document.activeElement).toBe(m.items()[0])
    m.search.focus()
    press(m.search, 'ArrowUp')
    const list = m.items()
    expect(document.activeElement).toBe(list[list.length - 1])
  })

  it('ArrowDown past the last row wraps to the first, ArrowUp before the first wraps to the last', () => {
    const m = renderMenu()
    const first = m.items()[0]!
    let list = m.items()
    const last = list[list.length - 1]!
    last.focus()
    press(last, 'ArrowDown')
    expect(document.activeElement).toBe(first)
    list = m.items()
    list[0]!.focus()
    press(m.items()[0]!, 'ArrowUp')
    list = m.items()
    expect(document.activeElement).toBe(list[list.length - 1])
  })

  it('Home and End jump to the first and last row from anywhere in the list', () => {
    const m = renderMenu()
    m.items()[3]!.focus()
    press(document.activeElement as HTMLElement, 'End')
    let list = m.items()
    expect(document.activeElement).toBe(list[list.length - 1])
    press(document.activeElement as HTMLElement, 'Home')
    list = m.items()
    expect(document.activeElement).toBe(list[0])
  })

  it('the roving keys are consumed — preventDefault, and no bubbling into the chrome behind the menu', () => {
    const m = renderMenu()
    expect(press(m.search, 'ArrowDown')).toBe(true)
    expect(press(m.search, 'ArrowUp')).toBe(true)
    expect(press(m.search, 'Home')).toBe(true)
    expect(press(m.search, 'End')).toBe(true)
    expect(m.onAncestorKeyDown).not.toHaveBeenCalled()
  })

  it('keys the menu does not handle bubble through untouched — it only owns its own keys', () => {
    const m = renderMenu()
    expect(press(m.search, 'j')).toBe(false)
    expect(m.onAncestorKeyDown).toHaveBeenCalledTimes(1)
  })

  it('Enter in the search field hands focus to the first result but picks and opens nothing', () => {
    const m = renderMenu()
    expect(press(m.search, 'Enter')).toBe(true)
    expect(document.activeElement).toBe(m.items()[0])
    expect(m.onPickTab).not.toHaveBeenCalled()
    expect(m.onOpenTab).not.toHaveBeenCalled()
    expect(m.onCloseTab).not.toHaveBeenCalled()
  })

  it('Enter on a row stays with the native button — the handler neither prevents it nor activates the row', () => {
    const m = renderMenu()
    const row = m.items()[0]!
    row.focus()
    expect(press(row, 'Enter')).toBe(false)
    expect(document.activeElement).toBe(row)
    expect(m.onPickTab).not.toHaveBeenCalled()
    expect(m.onOpenTab).not.toHaveBeenCalled()
  })

  it('without a single result the roving keys stay harmless — consumed, but focus does not leave the search field', () => {
    const m = renderMenu({ tabs: [], recent: [], query: 'qqqq' })
    expect(m.items()).toHaveLength(0)
    expect(press(m.search, 'ArrowDown')).toBe(true)
    expect(press(m.search, 'ArrowUp')).toBe(true)
    expect(press(m.search, 'Home')).toBe(true)
    expect(press(m.search, 'End')).toBe(true)
    expect(document.activeElement).toBe(m.search)
    // Nothing to focus: Enter is not even consumed then.
    expect(press(m.search, 'Enter')).toBe(false)
    expect(document.activeElement).toBe(m.search)
  })

  it('Tab cycles inside the menu — search → rows → search, Shift+Tab walks backwards', () => {
    const m = renderMenu()
    expect(press(m.search, 'Tab')).toBe(true)
    expect(document.activeElement).toBe(m.items()[0])
    press(document.activeElement as HTMLElement, 'Tab')
    expect(document.activeElement).toBe(m.items()[1])
    let list = m.items()
    list[list.length - 1]!.focus()
    press(document.activeElement as HTMLElement, 'Tab')
    expect(document.activeElement).toBe(m.search)
    press(m.search, 'Tab', { shiftKey: true })
    list = m.items()
    expect(document.activeElement).toBe(list[list.length - 1])
    list[0]!.focus()
    press(list[0]!, 'Tab', { shiftKey: true })
    expect(document.activeElement).toBe(m.search)
  })

  it('Escape dismisses exactly once per press, picks nothing, and hands focus back to the trigger', () => {
    const m = renderMenu()
    expect(press(m.search, 'Escape')).toBe(true)
    expect(m.onDismiss).toHaveBeenCalledTimes(1)
    expect(m.onPickTab).not.toHaveBeenCalled()
    expect(m.onOpenTab).not.toHaveBeenCalled()
    expect(m.onCloseTab).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(screen.getByTestId('panel-add-tab'))
    // once per press — no double fire, no swallow of the surrounding chrome
    press(m.search, 'Escape')
    expect(m.onDismiss).toHaveBeenCalledTimes(2)
    expect(m.onAncestorKeyDown).not.toHaveBeenCalled()
  })

  it('Escape without a trigger in the DOM neither crashes nor moves focus somewhere random', () => {
    const m = renderMenu({ withTrigger: false })
    expect(press(m.search, 'Escape')).toBe(true)
    expect(m.onDismiss).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(m.search)
  })

  it('the search field is the menu-owned controlled input — value from the query prop, named for screen readers', () => {
    const m = renderMenu({ query: 'git' })
    expect(m.search.value).toBe('git')
    expect(m.search.getAttribute('aria-label')).toBe('Search tabs…')
    expect(m.menu.getAttribute('aria-label')).toBe('Add tab')
  })
})

describe('PanelAddMenu — search filtering', () => {
  it('the search matches label, tab key and menu key — case-insensitively and trimmed', () => {
    const m = renderMenu()
    type(m.search, '  KNOW  ') // label 'Knowledge'
    expect(m.search.value).toBe('  KNOW  ')
    expect(screen.getByTestId('panel-page-item-memory')).toBeTruthy()
    expect(screen.queryByTestId('panel-new-tab-item-terminal')).toBeNull()
    type(m.search, 'audit') // tab key of an extra page
    expect(screen.getByTestId('panel-page-item-audit')).toBeTruthy()
    expect(screen.queryByTestId('panel-page-item-memory')).toBeNull()
    type(m.search, 'git') // tab key of a MAIN entry — its menu-key row answers
    const list = m.offerRows()
    expect(list).toHaveLength(1)
    expect(list[0]!.getAttribute('data-testid')).toBe('panel-new-tab-item-review')
    type(m.search, 'review') // the menu key itself — and a substring of tab 'preview'
    const rows = m.offerRows().map((el) => el.getAttribute('data-testid'))
    expect(rows).toEqual(['panel-new-tab-item-review', 'panel-new-tab-item-browser'])
    expect(m.onQuery).toHaveBeenLastCalledWith('review')
  })

  it('clearing the query restores the full offer', () => {
    const m = renderMenu()
    type(m.search, 'qqqq')
    expect(m.offerRows()).toHaveLength(0)
    type(m.search, '')
    for (const key of ['side', 'review', 'terminal', 'browser']) {
      expect(screen.getByTestId(`panel-new-tab-item-${key}`)).toBeTruthy()
    }
    for (const tab of ['files', 'audit', 'trajectory', 'subagents', 'memory']) {
      expect(screen.getByTestId(`panel-page-item-${tab}`)).toBeTruthy()
    }
    expect(screen.queryByText('No matching tabs')).toBeNull()
    expect(m.search.value).toBe('')
  })

  it('garbage input empties the offer — the open tabs stay, the empty text appears', () => {
    const m = renderMenu({ recent: [{ tab: 'memory', closedAt: Date.now() - 300_000 }] })
    type(m.search, 'qqqq')
    expect(m.offerRows()).toHaveLength(0)
    // Pinned as-is: the open-tabs section ignores the query — its row and close
    // control stay reachable while the offer is empty.
    expect(screen.getByTestId('panel-open-tab-row-preview')).toBeTruthy()
    expect(screen.getByTestId('panel-open-tab-close-preview')).toBeTruthy()
    expect(m.items()).toHaveLength(2)
    expect(screen.getByText('No matching tabs')).toBeTruthy()
    expect(screen.queryByTestId('panel-recent-memory')).toBeNull()
    expect(m.onQuery).toHaveBeenCalledWith('qqqq')
  })
})

describe('PanelAddMenu — recently closed section', () => {
  it('the recent section exists only while the query is exactly empty — a single space already hides it', () => {
    const m = renderMenu({ recent: [{ tab: 'memory', closedAt: Date.now() - 300_000 }] })
    const row = screen.getByTestId('panel-recent-memory')
    expect(row.textContent).toContain('Knowledge')
    expect(row.textContent).toContain('5m')
    type(m.search, ' ')
    expect(screen.queryByTestId('panel-recent-memory')).toBeNull()
    // A lone space trims to the empty query — every item still matches.
    expect(screen.getByTestId('panel-page-item-memory')).toBeTruthy()
    expect(m.items().length).toBeGreaterThan(0)
    type(m.search, '')
    expect(screen.getByTestId('panel-recent-memory')).toBeTruthy()
  })

  it('without closed tabs the section stays away even at the empty query', () => {
    renderMenu()
    expect(screen.queryByTestId('panel-recent-memory')).toBeNull()
    expect(screen.queryByText('Recently closed tabs')).toBeNull()
  })

  it('clicking a recent row restores it through onOpenTab — never through onPickTab', () => {
    const m = renderMenu({ recent: [{ tab: 'memory', closedAt: Date.now() - 300_000 }] })
    fireEvent.click(screen.getByTestId('panel-recent-memory'))
    expect(m.onOpenTab).toHaveBeenCalledTimes(1)
    expect(m.onOpenTab).toHaveBeenCalledWith('memory')
    expect(m.onPickTab).not.toHaveBeenCalled()
    expect(m.onCloseTab).not.toHaveBeenCalled()
  })
})

describe('PanelAddMenu — click contract of the row kinds', () => {
  it('an extra page row opens exactly its own tab via onOpenTab', () => {
    const m = renderMenu()
    fireEvent.click(screen.getByTestId('panel-page-item-audit'))
    expect(m.onOpenTab).toHaveBeenCalledTimes(1)
    expect(m.onOpenTab).toHaveBeenCalledWith('audit')
    expect(m.onPickTab).not.toHaveBeenCalled()
    expect(m.onCloseTab).not.toHaveBeenCalled()
  })

  it('the menu-key rows map their menu key to the pane tab — review → git, browser → preview', () => {
    const m = renderMenu()
    fireEvent.click(screen.getByTestId('panel-new-tab-item-review'))
    expect(m.onOpenTab).toHaveBeenLastCalledWith('git')
    fireEvent.click(screen.getByTestId('panel-new-tab-item-browser'))
    expect(m.onOpenTab).toHaveBeenLastCalledWith('preview')
    // The menu key itself must never travel as a tab.
    expect(m.onOpenTab.mock.calls.map((c) => c[0])).toEqual(['git', 'preview'])
    expect(m.onPickTab).not.toHaveBeenCalled()
  })

  it('open-tab rows mark only the current tab and picking reports the row tab', () => {
    const m = renderMenu({ tabs: ['preview', 'memory'], active: 'preview' })
    const current = screen.getByTestId('panel-open-tab-row-preview')
    const other = screen.getByTestId('panel-open-tab-row-memory')
    expect(current.getAttribute('aria-label')).toBe('Browser — now')
    expect(current.className).toContain('bg-brand/20')
    expect(other.getAttribute('aria-label')).toBe('Knowledge')
    expect(other.className).not.toContain('bg-brand/20')
    fireEvent.click(other)
    expect(m.onPickTab).toHaveBeenCalledTimes(1)
    expect(m.onPickTab).toHaveBeenCalledWith('memory')
    // Pinned as-is: even the current tab reports a pick — no guard in the row.
    fireEvent.click(current)
    expect(m.onPickTab).toHaveBeenCalledTimes(2)
    expect(m.onPickTab).toHaveBeenLastCalledWith('preview')
    expect(m.onOpenTab).not.toHaveBeenCalled()
  })

  it('the close control closes its own tab and the click does not fall through to the row', () => {
    const m = renderMenu({ tabs: ['preview', 'memory'], active: 'preview' })
    fireEvent.click(screen.getByTestId('panel-open-tab-close-preview'))
    expect(m.onCloseTab).toHaveBeenCalledTimes(1)
    expect(m.onCloseTab).toHaveBeenCalledWith('preview')
    expect(m.onPickTab).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('panel-open-tab-close-memory'))
    expect(m.onCloseTab).toHaveBeenCalledTimes(2)
    expect(m.onCloseTab).toHaveBeenLastCalledWith('memory')
    expect(m.onPickTab).not.toHaveBeenCalled()
  })

  it('the scrim behind the menu dismisses on click', () => {
    const m = renderMenu()
    fireEvent.click(m.menu.previousElementSibling as HTMLElement)
    expect(m.onDismiss).toHaveBeenCalledTimes(1)
    expect(m.onPickTab).not.toHaveBeenCalled()
  })
})
