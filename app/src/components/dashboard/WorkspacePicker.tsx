/**
 * Ephe — Workspace hooks (R26, W4)
 *
 * Workspace state + switching logic for the dashboard surfaces. The old
 * default-exported chip/label components were unreachable dead code and were
 * removed (feature inventory F-3); WorkspaceBar renders the bar + dialog.
 *
 * Every switch broadcasts `ephe:workspace-changed` so other surfaces
 * (bar chip, git info) re-sync without a page reload.
 */
import { useCallback, useState, useSyncExternalStore } from 'react'
import { listFs, updateSettings } from '@/lib/api'

export const WORKSPACE_CHANGED_EVENT = 'ephe:workspace-changed'

export interface WorkspaceState {
  /** Basename of the active workspace (null when unresolvable). */
  name: string | null
  /** True when the user chose a project (engine.json workspace_dir non-empty);
   *  false = neutral "Workspace" state with the documented CWD root fallback. */
  set: boolean
}

const EMPTY: WorkspaceState = { name: null, set: false }

/**
 * One fact about the device, read once.
 *
 * The bar chip, the composer and the header all want `set`, and a hook that
 * fetched per instance doubled the boot request count — the q-quality budget
 * caught it at 27 against a ceiling of 25. Consumers now share one snapshot,
 * one in-flight request, and one window listener while anyone is watching.
 */
let snapshot: WorkspaceState = EMPTY
const listeners = new Set<() => void>()
let inflight: Promise<void> | null = null
let watching = false

function publish(next: WorkspaceState) {
  if (next.name === snapshot.name && next.set === snapshot.set) return
  snapshot = next
  for (const notify of listeners) notify()
}

function refreshWorkspace(): Promise<void> {
  if (inflight) return inflight
  inflight = listFs()
    .then((fs) => {
      const dir = fs.workspace
      const set = (fs as { workspace_set?: boolean }).workspace_set === true
      publish({
        name: dir ? (dir.split('/').filter(Boolean).pop() ?? dir) : null,
        set,
      })
    })
    .catch(() => publish(EMPTY))
    .finally(() => {
      inflight = null
    })
  return inflight
}

function onWorkspaceChanged() {
  void refreshWorkspace()
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  if (!watching) {
    watching = true
    window.addEventListener(WORKSPACE_CHANGED_EVENT, onWorkspaceChanged)
    void refreshWorkspace()
  }
  return () => {
    listeners.delete(notify)
    if (listeners.size === 0) {
      watching = false
      window.removeEventListener(WORKSPACE_CHANGED_EVENT, onWorkspaceChanged)
    }
  }
}

export function useWorkspaceState(): WorkspaceState {
  return useSyncExternalStore(subscribe, () => snapshot)
}

export function useWorkspaceName(): string | null {
  return useWorkspaceState().name
}

export function useWorkspaceSwitcher() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const pick = useCallback(async (path: string) => {
    setPickerOpen(false)
    try {
      await updateSettings({ workspace_dir: path })
      window.dispatchEvent(new CustomEvent(WORKSPACE_CHANGED_EVENT, { detail: { path } }))
    } catch {
      // Silent: the label simply keeps showing the previous workspace.
      // FolderPickerDialog already surfaces its own errors while browsing.
    }
  }, [])
  return {
    pickerOpen,
    openPicker: () => setPickerOpen(true),
    closePicker: () => setPickerOpen(false),
    pick,
  }
}
