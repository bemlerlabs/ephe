// WS-E 47 — the tab bar's keyboard walk, at the unit boundary. The arrow
// move/wrap/roving contract already lives in AgentPanel.tabs.test.tsx; this file
// holds what that one does not: Home/End on the tablist, the "not on a pill"
// guard (chat/model.ts has a global arrow listener), and focus recovery when a
// pill close removes the focused close button.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PanelTabBar } from './panelTabBar'
import { useTabRegistry } from './useTabRegistry'
import { TAB_KEYS, Tab } from './primitives'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const labels = Object.fromEntries(TAB_KEYS.map((k) => [k, `L:${k}`])) as Record<Tab, string>

function renderBar(over: Partial<React.ComponentProps<typeof PanelTabBar>> = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onCloseTab: vi.fn(),
    onToggleMenu: vi.fn(),
    onCollapse: vi.fn(),
    onCycleWidth: vi.fn(),
    onToggleDock: vi.fn(),
  }
  render(
    <PanelTabBar
      tabs={['preview', 'terminal', 'git']}
      active="terminal"
      labels={labels}
      dock="right"
      menuOpen={false}
      {...handlers}
      {...over}
    />,
  )
  return handlers
}

const tab = (key: Tab) => screen.getByRole('tab', { name: `L:${key}` })

describe('PanelTabBar — the ends of the tablist (Home/End)', () => {
  it('End jumps to the last pill, Home back to the first', () => {
    const h = renderBar()
    tab('terminal').focus()

    fireEvent.keyDown(tab('terminal'), { key: 'End' })
    expect(h.onSelect).toHaveBeenCalledWith('git')
    expect(document.activeElement).toBe(tab('git'))

    fireEvent.keyDown(tab('git'), { key: 'Home' })
    expect(h.onSelect).toHaveBeenLastCalledWith('preview')
    expect(document.activeElement).toBe(tab('preview'))
  })

  it('Home/End are cancelled and stay inside the bar', () => {
    renderBar()
    const seen = vi.fn()
    window.addEventListener('keydown', seen)
    try {
      tab('terminal').focus()
      // fireEvent returns false when the handler called preventDefault.
      expect(fireEvent.keyDown(tab('terminal'), { key: 'End' })).toBe(false)
      expect(seen).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('keydown', seen)
    }
  })

  it('a key on the list but not on a pill does nothing', () => {
    const h = renderBar()
    const list = screen.getByRole('tablist')
    fireEvent.keyDown(list, { key: 'ArrowRight' })
    fireEvent.keyDown(list, { key: 'End' })
    expect(h.onSelect).not.toHaveBeenCalled()
  })

  it('with no active pill the first one carries the tab stop', () => {
    renderBar({ active: null })
    expect(tab('preview').tabIndex).toBe(0)
    expect(tab('terminal').tabIndex).toBe(-1)
    expect(tab('git').tabIndex).toBe(-1)
  })
})

describe('PanelTabBar — focus after a pill close', () => {
  // A registry-backed parent, so the close runs the real inventory move.
  function RegistryBar() {
    const { tabState, closeTab, selectTab, menuOpen, setMenuOpen } = useTabRegistry()
    return (
      <PanelTabBar
        tabs={tabState.open}
        active={tabState.active}
        labels={labels}
        dock="right"
        menuOpen={menuOpen}
        onSelect={selectTab}
        onCloseTab={closeTab}
        onToggleMenu={() => setMenuOpen((v) => !v)}
        onCollapse={() => {}}
        onCycleWidth={() => {}}
        onToggleDock={() => {}}
      />
    )
  }

  const boot = (tabs: string[], active: string) => {
    localStorage.clear()
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabs))
    localStorage.setItem('ephe.panel.activeTab', JSON.stringify(active))
    render(<RegistryBar />)
  }

  it('a background close keeps focus in the bar on the active pill', () => {
    boot(['preview', 'terminal', 'git'], 'git')
    const close = screen.getByTestId('panel-tab-close-terminal')
    close.focus()
    fireEvent.click(close)
    expect(screen.queryByTestId('panel-tab-pill-terminal')).toBeNull()
    expect(document.activeElement).toBe(tab('git'))
  })

  it('closing the active pill hands focus to the pill that becomes active', () => {
    boot(['preview', 'terminal', 'git'], 'git')
    const close = screen.getByTestId('panel-tab-close-git')
    close.focus()
    fireEvent.click(close)
    // closeTab activates the last remaining pill; the bar focuses it.
    expect(tab('terminal').getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(tab('terminal'))
  })

  it('closing the last pill leaves no pill behind and does not throw', () => {
    boot(['preview'], 'preview')
    const close = screen.getByTestId('panel-tab-close-preview')
    close.focus()
    fireEvent.click(close)
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
    expect(screen.queryByTestId('panel-tab-pill-preview')).toBeNull()
  })
})
