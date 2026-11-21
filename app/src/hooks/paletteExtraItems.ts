/**
 * P1 [F5] palette item builders (artifacts + settings sub-pages).
 * Its own module so useCommandPalette stays under the architecture line
 * (maxFileLines 400) — the builders are purely functional.
 *
 * W10 (FINDINGS 2026-10-12, medium): the settings rows used to be a literal list
 * here — 17 keys against the 23 the panel really has, one of them a phantom
 * ('deep', which no TabKey, no NAV row and no section knew about). Both families are
 * now read off the panel's own sources: the tab rows from the navigation's one list
 * (NAV_KEYS in settings/types.ts, from which settings/model.tsx builds NAV), the
 * control rows from ROW_INDEX (settings/model/rowIndex.ts) — a navigation that grows
 * cannot leave the palette behind again.
 */
import type { CommandItem } from './paletteTypes'
import type { TabKey } from '@/components/dashboard/settings/types'
import { NAV_KEYS } from '@/components/dashboard/settings/types'
import { ROW_INDEX } from '@/components/dashboard/settings/model/rowIndex'

/** The navigation's tab rows (settings/types.ts NAV_KEYS) — the palette's settings entries ARE the nav. */
export const SETTINGS_NAV_KEYS: readonly TabKey[] = NAV_KEYS

/** "Open artifact": file names → palette entries with a preview action. */
export function buildArtifactCommands(args: {
  filenames: string[]
  fileUrl: (path: string) => string
  sectionLabel: string
  open: (url: string) => void
}): CommandItem[] {
  return args.filenames.map((filename) => ({
    id: `artifact-${filename}`,
    label: filename,
    section: args.sectionLabel,
    action: () => args.open(args.fileUrl(filename)),
  }))
}

/** "Jump to a setting": every settings NAV tab as its own entry. */
export function buildSettingsCommands(args: {
  label: (key: string) => string
  sectionLabel: string
  openTab: (tab: TabKey) => void
}): CommandItem[] {
  return SETTINGS_NAV_KEYS.map((key) => ({
    id: `settings-${key}`,
    label: args.label(key),
    section: args.sectionLabel,
    action: () => args.openTab(key),
  }))
}

/**
 * "Find a control": the panel's row index — the rows that carry their own endpoint
 * (capabilities, MCP, voices, network, …) and that a tab jump cannot name. Each entry
 * opens the row's tab and hands the row's own label along as the panel's search, so
 * the panel lists the control the user asked for instead of only the page it sits on.
 */
export function buildControlCommands(args: {
  label: (key: string) => string
  sectionLabel: string
  openControl: (tab: TabKey, query: string) => void
}): CommandItem[] {
  return ROW_INDEX.map((row) => {
    const label = args.label(row.key)
    return {
      id: `settings-row-${row.tab}-${row.key}`,
      label,
      section: args.sectionLabel,
      action: () => args.openControl(row.tab, label),
    }
  })
}
