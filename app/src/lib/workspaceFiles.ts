/**
 * Ephe — the files a person has open in the workspace column (register #111).
 *
 * The tree and the file it opens are one job: the column answers "what is in this
 * folder" and "what does this file say". Before this store, a click on a file handed
 * the path to the browser pane, because that was the only surface in the panel that
 * could hold a URL — so opening a README put an address bar on the screen, and opening
 * a PNG put a download there.
 *
 * The list lives here rather than in the tab so that everything which can reach a file
 * — the tree, a tool card that wrote one, an artifact that names its source — opens it
 * in the same place, and a restart brings the same files back.
 *
 * The preview slot is the part worth keeping from an editor: a single click shows a
 * file without claiming a tab of its own, and the next single click reuses that slot.
 * A person who means to keep a file open double-clicks it, and the entry is pinned
 * from then on. Without it, reading five files in a row leaves five tabs to clean up.
 */
import { useSyncExternalStore } from 'react'
import type { FileView } from './fileOpen'

const STORE_KEY = 'ephe.workspace.files'
const ACTIVE_KEY = 'ephe.workspace.files.active'
const VIEW_KEY = 'ephe.workspace.files.view'

/** The slot is a bound, not a style: a column this narrow reads as a mistake at 40. */
export const MAX_OPEN_FILES = 12

export type OpenFile = {
  path: string
  name: string
  size?: number
  pinned: boolean
}

export type WorkspaceFileView = 'file' | 'tree'

export type WorkspaceFileState = {
  files: OpenFile[]
  active: string | null
  view: WorkspaceFileView
  /** The chosen reading for a file that has more than one — Markdown as a page or as
   *  the text that made it. Keyed by path so two open READMEs decide for themselves. */
  modes: Record<string, FileView>
}

export type OpenFileInput = {
  path: string
  name?: string
  size?: number
  /** False keeps the preview slot: the file shows, and the next single click replaces it. */
  pin?: boolean
  /** Where the click lands: the tree's own row asks for the file the moment it opens. */
  view?: WorkspaceFileView
}

function nameOf(path: string): string {
  return path.split('/').filter(Boolean).pop() ?? path
}

function readStored(): OpenFile[] {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .filter((item) => typeof item.path === 'string' && (item.path as string).startsWith('/'))
      .slice(0, MAX_OPEN_FILES)
      .map((item) => ({
        path: item.path as string,
        name: typeof item.name === 'string' && item.name ? item.name : nameOf(item.path as string),
        size: typeof item.size === 'number' ? item.size : undefined,
        pinned: item.pinned === true,
      }))
  } catch {
    return []
  }
}

function readStoredActive(paths: OpenFile[]): string | null {
  const raw = localStorage.getItem(ACTIVE_KEY)
  if (raw && paths.some((f) => f.path === raw)) return raw
  return paths[paths.length - 1]?.path ?? null
}

function seed(): WorkspaceFileState {
  const files = readStored()
  const active = readStoredActive(files)
  return {
    files,
    active,
    view: localStorage.getItem(VIEW_KEY) === 'tree' || !active ? 'tree' : 'file',
    modes: {},
  }
}

let state = seed()
const listeners = new Set<() => void>()

function persist(next: WorkspaceFileState): void {
  state = next
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(next.files))
    if (next.active) localStorage.setItem(ACTIVE_KEY, next.active)
    else localStorage.removeItem(ACTIVE_KEY)
    localStorage.setItem(VIEW_KEY, next.view)
  } catch {
    // A store that cannot write keeps working for the session; the files a person
    // opened are still on screen, only the restart cannot bring them back.
  }
  for (const listener of [...listeners]) listener()
}

export function workspaceFiles(): WorkspaceFileState {
  return state
}

/** Open a file in the column. The preview slot is reused while it is still unclaimed. */
export function openWorkspaceFile(input: OpenFileInput): void {
  const path = input.path
  if (!path) return
  const existing = state.files.find((f) => f.path === path)
  const entry: OpenFile = {
    path,
    name: input.name ?? existing?.name ?? nameOf(path),
    size: input.size ?? existing?.size,
    pinned: input.pin === true || (existing?.pinned ?? false),
  }
  let files: OpenFile[]
  if (existing) {
    files = state.files.map((f) => (f.path === path ? entry : f))
  } else {
    const slot = state.files.findIndex((f) => !f.pinned)
    if (slot >= 0 && !entry.pinned) {
      files = state.files.map((f, i) => (i === slot ? entry : f))
    } else {
      files = [...state.files, entry]
      if (files.length > MAX_OPEN_FILES) {
        // The oldest file nobody chose to keep goes first, and the one being opened is
        // never the one dropped. When every entry is pinned the strip grows: a person
        // asked for each of these, and closing one of them is not the column's call.
        const droppable = files.findIndex((f, i) => i < files.length - 1 && !f.pinned)
        if (droppable >= 0) files = files.filter((_, i) => i !== droppable)
      }
    }
  }
  persist({ ...state, files, active: path, view: input.view ?? 'file' })
}

/** Keep a file, or hand its slot back. The gesture lives on the tab and on the reader's
 *  own line, because a double click on the tree row cannot reach it: the first click of
 *  that pair already replaced the tree with the file, so the row is gone before the
 *  second one lands (measured in a real browser, 2026-11-02). */
export function setWorkspaceFilePinned(path: string, pinned: boolean): void {
  if (!state.files.some((f) => f.path === path)) return
  persist({
    ...state,
    files: state.files.map((f) => (f.path === path ? { ...f, pinned } : f)),
  })
}

export function selectWorkspaceFile(path: string): void {
  if (!state.files.some((f) => f.path === path)) return
  persist({ ...state, active: path, view: 'file' })
}

/** Close a file. The neighbour that takes its place is the one beside it, so the
 *  reading does not jump to the far end of the strip. */
export function closeWorkspaceFile(path: string): void {
  const index = state.files.findIndex((f) => f.path === path)
  if (index < 0) return
  const files = state.files.filter((f) => f.path !== path)
  const next = files[Math.min(index, files.length - 1)]
  const active = state.active === path ? (next?.path ?? null) : state.active
  persist({
    ...state,
    files,
    active,
    view: active ? 'file' : 'tree',
    modes: Object.fromEntries(Object.entries(state.modes).filter(([key]) => key !== path)),
  })
}

export function closeAllWorkspaceFiles(): void {
  if (!state.files.length) return
  persist({ ...state, files: [], active: null, view: 'tree', modes: {} })
}

export function showWorkspaceView(view: WorkspaceFileView): void {
  if (view === state.view) return
  persist({ ...state, view })
}

/** The reading a file is in. Only Markdown has a second one, so this is the whole rule. */
export function setWorkspaceFileView(path: string, mode: FileView): void {
  if (state.modes[path] === mode) return
  persist({ ...state, modes: { ...state.modes, [path]: mode } })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useWorkspaceFiles(): WorkspaceFileState {
  return useSyncExternalStore(subscribe, workspaceFiles)
}
