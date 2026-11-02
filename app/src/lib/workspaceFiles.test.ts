/**
 * #111 — the files the workspace column holds.
 *
 * The store has one rule that a plain list would get wrong: a single click is a look, a
 * double click is a keep. Without it, reading five files in a row leaves five tabs to
 * clean up, which is the reason people close a panel they only meant to glance into. The
 * other rule is the bound: a column this narrow cannot hold forty tabs, and the entry it
 * drops is always one the person never chose to keep.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Mod = typeof import('./workspaceFiles')
let mod: Mod

beforeEach(async () => {
  localStorage.clear()
  vi.resetModules()
  mod = await import('./workspaceFiles')
})

const paths = (m: Mod) => m.workspaceFiles().files.map((f) => f.path)

describe('the preview slot', () => {
  it('shows a single click without claiming a tab of its own', () => {
    mod.openWorkspaceFile({ path: '/werk/a.md', name: 'a.md' })
    expect(paths(mod)).toEqual(['/werk/a.md'])
    expect(mod.workspaceFiles().files[0]?.pinned).toBe(false)
    expect(mod.workspaceFiles().view).toBe('file')

    mod.openWorkspaceFile({ path: '/werk/b.md', name: 'b.md' })
    // The slot is reused: the column shows b.md and still holds one entry.
    expect(paths(mod)).toEqual(['/werk/b.md'])
    expect(mod.workspaceFiles().active).toBe('/werk/b.md')
  })

  it('keeps what a double click pins, and opens the next file beside it', () => {
    mod.openWorkspaceFile({ path: '/werk/a.md', pin: true })
    mod.openWorkspaceFile({ path: '/werk/b.md' })
    expect(paths(mod)).toEqual(['/werk/a.md', '/werk/b.md'])
    mod.openWorkspaceFile({ path: '/werk/c.md' })
    // b.md was the slot, so c.md takes it; the pinned a.md stays where it was.
    expect(paths(mod)).toEqual(['/werk/a.md', '/werk/c.md'])
  })

  it('pins a file the moment its own tab is opened again', () => {
    mod.openWorkspaceFile({ path: '/werk/a.md' })
    mod.openWorkspaceFile({ path: '/werk/a.md', pin: true })
    expect(mod.workspaceFiles().files[0]?.pinned).toBe(true)
    expect(paths(mod)).toEqual(['/werk/a.md'])
  })

  it('keeps and releases a tab from the strip, where the gesture can land', () => {
    mod.openWorkspaceFile({ path: '/werk/a.md' })
    mod.openWorkspaceFile({ path: '/werk/b.md' })
    // Only b.md is left: a.md was the unclaimed slot. Pinning b.md frees the slot again.
    expect(paths(mod)).toEqual(['/werk/b.md'])
    mod.setWorkspaceFilePinned('/werk/b.md', true)
    expect(mod.workspaceFiles().files[0]?.pinned).toBe(true)
    mod.openWorkspaceFile({ path: '/werk/c.md' })
    expect(paths(mod)).toEqual(['/werk/b.md', '/werk/c.md'])
    mod.setWorkspaceFilePinned('/werk/b.md', false)
    expect(mod.workspaceFiles().files.find((f) => f.path === '/werk/b.md')?.pinned).toBe(false)
    // A release hands the slot back, so the next look can take it.
    mod.openWorkspaceFile({ path: '/werk/d.md' })
    expect(paths(mod)).toEqual(['/werk/d.md', '/werk/c.md'])
  })

  it('says nothing about a file the strip does not hold', () => {
    mod.openWorkspaceFile({ path: '/werk/a.md' })
    mod.setWorkspaceFilePinned('/werk/absent.md', true)
    expect(mod.workspaceFiles().files[0]?.pinned).toBe(false)
  })

  it('makes room for a kept file by dropping the oldest one nobody kept', () => {
    mod.openWorkspaceFile({ path: '/werk/slot.md' })
    for (let i = 0; i < mod.MAX_OPEN_FILES - 1; i += 1) {
      mod.openWorkspaceFile({ path: `/werk/f${i}.md`, pin: true })
    }
    // The slot is the newest entry, so a pinned file pushed past the bound releases it
    // and the strip holds exactly what the person chose to keep.
    mod.openWorkspaceFile({ path: '/werk/neu.md', pin: true })
    const after = paths(mod)
    expect(after.length).toBe(mod.MAX_OPEN_FILES)
    expect(after).toContain('/werk/neu.md')
    expect(after).not.toContain('/werk/slot.md')
    expect(after[0]).toBe('/werk/f0.md')
  })

  it('grows past the bound when every entry was chosen to keep', () => {
    for (let i = 0; i < mod.MAX_OPEN_FILES + 2; i += 1) {
      mod.openWorkspaceFile({ path: `/werk/f${i}.md`, pin: true })
    }
    // Closing a file the person asked to keep is never the column's decision to make.
    expect(mod.workspaceFiles().files.length).toBe(mod.MAX_OPEN_FILES + 2)
  })
})

describe('selecting and closing', () => {
  it('brings the neighbour into view when the active tab closes', () => {
    mod.openWorkspaceFile({ path: '/a.md', pin: true })
    mod.openWorkspaceFile({ path: '/b.md', pin: true })
    mod.openWorkspaceFile({ path: '/c.md', pin: true })
    mod.selectWorkspaceFile('/b.md')
    mod.closeWorkspaceFile('/b.md')
    expect(mod.workspaceFiles().active).toBe('/c.md')
    expect(paths(mod)).toEqual(['/a.md', '/c.md'])
  })

  it('returns the column to the folder when the last file goes', () => {
    mod.openWorkspaceFile({ path: '/a.md' })
    mod.closeWorkspaceFile('/a.md')
    expect(mod.workspaceFiles().files).toEqual([])
    expect(mod.workspaceFiles().active).toBeNull()
    expect(mod.workspaceFiles().view).toBe('tree')
  })

  it('closes everything the column holds in one gesture', () => {
    mod.openWorkspaceFile({ path: '/a.md', pin: true })
    mod.openWorkspaceFile({ path: '/b.md', pin: true })
    mod.closeAllWorkspaceFiles()
    expect(mod.workspaceFiles().files).toEqual([])
    expect(mod.workspaceFiles().modes).toEqual({})
  })

  it('ignores a selection that names a file it does not hold', () => {
    mod.openWorkspaceFile({ path: '/a.md' })
    mod.selectWorkspaceFile('/andere.md')
    expect(mod.workspaceFiles().active).toBe('/a.md')
    mod.closeWorkspaceFile('/andere.md')
    expect(paths(mod)).toEqual(['/a.md'])
  })

  it('refuses a path that is empty, so no tab can open on nothing', () => {
    mod.openWorkspaceFile({ path: '' })
    expect(mod.workspaceFiles().files).toEqual([])
  })
})

describe('the reading a file is in', () => {
  it('remembers the choice per path, so two open READMEs decide for themselves', () => {
    mod.openWorkspaceFile({ path: '/a.md', pin: true })
    mod.openWorkspaceFile({ path: '/b.md', pin: true })
    mod.setWorkspaceFileView('/a.md', 'source')
    expect(mod.workspaceFiles().modes).toEqual({ '/a.md': 'source' })
    expect(mod.workspaceFiles().modes['/b.md']).toBeUndefined()
  })

  it('shows the folder when the person asks for it and the file when they pick one', () => {
    mod.openWorkspaceFile({ path: '/a.md' })
    mod.showWorkspaceView('tree')
    expect(mod.workspaceFiles().view).toBe('tree')
    // The tab stays chosen: the file is still open, only the column is looking away.
    expect(mod.workspaceFiles().active).toBe('/a.md')
    mod.selectWorkspaceFile('/a.md')
    expect(mod.workspaceFiles().view).toBe('file')
  })
})

describe('a restart', () => {
  it('brings the same files back, and the same one in front', async () => {
    mod.openWorkspaceFile({ path: '/a.md', name: 'a.md', size: 12, pin: true })
    mod.openWorkspaceFile({ path: '/b.md', name: 'b.md' })
    vi.resetModules()
    const again: Mod = await import('./workspaceFiles')
    expect(paths(again)).toEqual(['/a.md', '/b.md'])
    expect(again.workspaceFiles().active).toBe('/b.md')
    expect(again.workspaceFiles().files[0]?.size).toBe(12)
    expect(again.workspaceFiles().view).toBe('file')
  })

  it('keeps the column on the folder when nothing was open', async () => {
    mod.openWorkspaceFile({ path: '/a.md' })
    mod.showWorkspaceView('tree')
    vi.resetModules()
    const again: Mod = await import('./workspaceFiles')
    expect(again.workspaceFiles().view).toBe('tree')
    expect(again.workspaceFiles().active).toBe('/a.md')
  })

  it('survives a store that holds something else than files', () => {
    localStorage.setItem('ephe.workspace.files', '{"not":"a list"}')
    localStorage.setItem('ephe.workspace.files.active', 'null')
    expect(mod.workspaceFiles().files).toEqual([])
    localStorage.setItem('ephe.workspace.files', '[{"path":"relativ.md"}]')
    expect(mod.workspaceFiles().files).toEqual([])
  })
})
