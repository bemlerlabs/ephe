/**
 * The dock holds one panel, and a displaced one comes back to the caller.
 *
 * These are the model's cases: no DOM, no store — the rule that a second dock
 * replaces the first, the reveal that does not re-mount, and the URL/ sheet
 * operations the display module and the component read.
 */
import { describe, expect, it } from 'vitest'
import {
  closeDocked,
  collapseDocked,
  dockKey,
  openDocked,
  retargetDocked,
  type DockPanel,
} from './dockModel'

const spec = (pluginId: string, over: Record<string, unknown> = {}) => ({
  pluginId,
  title: pluginId,
  url: `/api/plugins/ui/${pluginId}/n0nce/`,
  surfaceType: 'dock-panel',
  ...over,
})

describe('opening the dock', () => {
  it('mounts the first panel unfolded', () => {
    const opened = openDocked(null, spec('first'))
    expect(opened.created).toBe(true)
    expect(opened.replaced).toBeNull()
    expect(opened.panel).toMatchObject({ pluginId: 'first', collapsed: false })
  })

  it('displaces a different plugin and hands it back to be closed loudly', () => {
    const standing: DockPanel = { ...spec('first'), collapsed: false }
    const opened = openDocked(standing, spec('second'))
    expect(opened.created).toBe(true)
    expect(opened.replaced?.pluginId).toBe('first')
    expect(opened.panel.pluginId).toBe('second')
  })

  it('reveals the standing panel instead of re-mounting it', () => {
    const standing: DockPanel = { ...spec('first'), collapsed: true }
    const opened = openDocked(standing, spec('first', { url: '/api/plugins/ui/first/fresh/' }))
    expect(opened.created).toBe(false)
    expect(opened.replaced).toBeNull()
    // The mounted document keeps the credential it was given, and the sheet unfolds.
    expect(opened.panel.url).toBe('/api/plugins/ui/first/n0nce/')
    expect(opened.panel.collapsed).toBe(false)
  })
})

describe('the standing panel', () => {
  const standing: DockPanel = { ...spec('first'), collapsed: false }

  it('closes for its own plugin and refuses an ask for another', () => {
    expect(closeDocked(standing, 'first')).toBeNull()
    expect(closeDocked(standing, 'second')).toBe(standing)
    expect(closeDocked(standing)).toBeNull()
    expect(closeDocked(null)).toBeNull()
  })

  it('retargets only its own URL, and only when the URL changed', () => {
    expect(retargetDocked(standing, 'first', '/api/plugins/ui/first/new/')?.url).toBe(
      '/api/plugins/ui/first/new/',
    )
    expect(retargetDocked(standing, 'first', standing.url)).toBe(standing)
    expect(retargetDocked(standing, 'second', '/other/')).toBe(standing)
    expect(retargetDocked(null, 'first', '/other/')).toBeNull()
  })

  it('folds and unfolds only for its own plugin', () => {
    expect(collapseDocked(standing, 'first', true)?.collapsed).toBe(true)
    expect(collapseDocked(standing, 'first', false)).toBe(standing)
    expect(collapseDocked(standing, 'second', true)).toBe(standing)
  })

  it('names its handle once, so a close and a reopen match', () => {
    expect(dockKey('first')).toBe('dock:first')
  })
})
