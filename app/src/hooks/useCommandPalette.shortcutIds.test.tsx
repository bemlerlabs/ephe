/**
 * P1-16: the palette and the shortcut table agree on ids.
 *
 * Before this the palette carried its own namespace (`new-session` where the table
 * says `new`) and its own key strings (a `⌘K` glyph on an entry that did not open
 * the palette). Now a command names the table row with `shortcutId`; this file
 * pins both directions:
 *   - every id a command names is a real row (no invented id survives a typo),
 *   - the rows no command names are listed below on purpose, so a forgotten tail
 *     shows up as a diff instead of hiding,
 *   - no glyph literal can grow back into the palette source.
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const api = vi.hoisted(() => ({
  searchSessionContent: vi.fn(),
  fileUrl: vi.fn((p: string) => `/api/file?path=${encodeURIComponent(p)}`),
}))
vi.mock('@/lib/api', () => api)

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useCommandPalette } from './useCommandPalette'
import type { CommandItem } from './paletteTypes'
import { SHORTCUTS, SHORTCUTS_BY_ID } from '@/lib/shortcuts'

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>
}

const commandsOf = (grouped: Record<string, CommandItem[]>): CommandItem[] =>
  Object.values(grouped).flat()

/** The palette command → table row agreement, as the product means it. */
const KEYED = [
  ['new-session', 'new'],
  ['sidebar-toggle', 'sidebar'],
  ['panel-dock-toggle', 'panelDock'],
  ['panel-terminal', 'panelTabs'],
  ['panel-git', 'panelTabs'],
  ['panel-files', 'panelTabs'],
  ['panel-subagents', 'panelTabs'],
  ['panel-browser', 'panelTabs'],
] as const

/** Rows no palette command needs: each is reachable by its key alone, and the
 *  palette is for finding what a key cannot name. Written down here so the list
 *  stays a decision. */
const ROWS_WITHOUT_COMMAND = [
  'close',
  'companion',
  'focusComposer',
  'palette',
  'panelFocus',
  'panelToggle',
  'send',
  'thisOverlay',
  'toggleFiles',
]

describe('the palette names table rows, not its own keys', () => {
  it('gives every keyed command the id of the row that drives it', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const commands = commandsOf(result.current.grouped)

    for (const [commandId, rowId] of KEYED) {
      const cmd = commands.find((c) => c.id === commandId)
      expect(cmd, `command ${commandId} must exist`).toBeTruthy()
      expect(cmd!.shortcutId, `${commandId} must name its table row`).toBe(rowId)
    }
  })

  it('lets no command name an id the table does not carry', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    for (const cmd of commandsOf(result.current.grouped)) {
      if (!cmd.shortcutId) continue
      expect(SHORTCUTS_BY_ID[cmd.shortcutId], `${cmd.id} → ${cmd.shortcutId}`).toBeTruthy()
    }
  })

  it('leaves exactly the documented rows without a palette command', () => {
    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    const used = new Set(
      commandsOf(result.current.grouped)
        .map((c) => c.shortcutId)
        .filter((id): id is NonNullable<typeof id> => Boolean(id)),
    )

    const unused = SHORTCUTS.filter((s) => !used.has(s.id))
      .map((s) => s.id)
      .sort()
    expect(unused).toEqual(ROWS_WITHOUT_COMMAND)

    // And the other direction: the palette carries no key the table does not know.
    for (const id of used) expect(SHORTCUTS_BY_ID[id]).toBeTruthy()
  })

  it('keeps the glyph out of the palette source — the table renders it', () => {
    // process.cwd() is the vite root (app/), which is where vitest resolves tests.
    const source = readFileSync(resolve(process.cwd(), 'src/hooks/useCommandPalette.ts'), 'utf8')
    // Comments may name a key (they document the convention); code may not carry
    // one. Statement lines only, so a comment mentioning "⌥ ⌘ B" stays legal.
    const code = source
      .split('\n')
      .filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line))
      .join('\n')
    // A hand-written key string next to an id is how the two namespaces drifted.
    expect(code).not.toMatch(/shortcut:\s*'/)
    expect(code).not.toMatch(/['"`][^'"`\n]*[⌘⇧⌥]/)
  })
})
