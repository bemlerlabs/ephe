/**
 * The docked region: one panel in shell-owned chrome, the same sandboxed frame.
 *
 * The region is the second placement `components.ui.type` names, and the tests hold
 * both halves of its promise: the frame keeps the mount's sandbox (no same-origin
 * authority), and the controls that fold or close it reach the one close path the
 * store row uses. The width and the phone behaviour are CSS; what is pinned here is
 * the accessibility tree and the store contract.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import axe from 'axe-core'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const hide = vi.fn<(pluginId: string, t: unknown) => Promise<boolean>>(async () => true)
vi.mock('@/lib/pluginDisplay', () => ({
  hidePluginSurface: (pluginId: string, t: unknown) => hide(pluginId, t),
}))

vi.mock('@/lib/pluginClientHost', () => ({
  attachPluginClient: () => () => {},
}))

import { useChatStore } from '@/store'
import DockHost from './DockHost'

const panel = (over: Record<string, unknown> = {}) => ({
  pluginId: 'docklet',
  title: 'Docklet',
  url: '/api/plugins/ui/docklet/n0nce/',
  surfaceType: 'dock-panel',
  collapsed: false,
  ...over,
})

beforeEach(() => {
  hide.mockClear()
  useChatStore.setState({ dock: null })
})

describe('the docked region', () => {
  it('paints nothing while no plugin asks for the dock', () => {
    render(<DockHost />)
    expect(screen.queryByTestId('dock-host')).toBeNull()
  })

  it('draws one named region with the panel title', () => {
    useChatStore.setState({ dock: panel() })
    render(<DockHost />)
    const region = screen.getByTestId('dock-host')
    expect(region.getAttribute('role')).toBe('complementary')
    expect(region.getAttribute('aria-label')).toBe('surface.dockRegionAria')
    expect(screen.getByTestId('dock-title').textContent).toBe('Docklet')
  })

  it('keeps the mount sandbox: scripts on, same-origin authority off', () => {
    useChatStore.setState({ dock: panel() })
    render(<DockHost />)
    const frame = screen.getByTestId('dock-frame') as HTMLIFrameElement
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-popups')
    expect(frame.getAttribute('sandbox')).not.toContain('allow-same-origin')
    expect(frame.getAttribute('title')).toBe('Docklet')
    expect(frame.getAttribute('src')).toBe('/api/plugins/ui/docklet/n0nce/')
  })

  it('closes through the same path the store row uses', () => {
    useChatStore.setState({ dock: panel() })
    render(<DockHost />)
    fireEvent.click(screen.getByTestId('dock-close'))
    expect(hide).toHaveBeenCalledWith('docklet', expect.any(Function))
  })

  it('folds the phone sheet away and offers one toggle to unfold it', () => {
    useChatStore.setState({ dock: panel() })
    render(<DockHost />)
    fireEvent.click(screen.getByTestId('dock-collapse'))
    expect(useChatStore.getState().dock?.collapsed).toBe(true)
    expect(screen.getByTestId('dock-host').getAttribute('data-collapsed')).toBe('true')
    const toggle = screen.getByTestId('dock-toggle')
    expect(toggle.getAttribute('aria-controls')).toBe('plugin-dock-docklet')
    fireEvent.click(toggle)
    expect(useChatStore.getState().dock?.collapsed).toBe(false)
    expect(screen.queryByTestId('dock-toggle')).toBeNull()
  })

  it('reports no WCAG A/AA violation in the region it draws', async () => {
    useChatStore.setState({ dock: panel() })
    const { container } = render(<DockHost />)
    // The sandboxed document belongs to the plugin and has its own policy; axe is asked
    // about the shell chrome this file draws, not about descending into the frame.
    const results = await axe.run(container, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
      iframes: false,
    })
    expect(results.violations).toEqual([])
  })

  it('keeps the frame mounted while the sheet is folded, so the page state survives', () => {
    useChatStore.setState({ dock: panel({ collapsed: true }) })
    render(<DockHost />)
    expect(screen.getByTestId('dock-frame')).toBeTruthy()
    expect(screen.getByTestId('dock-host').getAttribute('data-collapsed')).toBe('true')
  })
})

describe('the dock after a second plugin', () => {
  it('draws only the newest panel', async () => {
    useChatStore.setState({ dock: panel() })
    render(<DockHost />)
    act(() =>
      useChatStore.getState().openDock({
        pluginId: 'other',
        title: 'Other',
        url: '/api/plugins/ui/other/n0nce/',
        surfaceType: 'dock-panel',
      }),
    )
    await waitFor(() =>
      expect(screen.getByTestId('dock-frame').getAttribute('src')).toBe(
        '/api/plugins/ui/other/n0nce/',
      ),
    )
    expect(screen.getByTestId('dock-title').textContent).toBe('Other')
  })
})
