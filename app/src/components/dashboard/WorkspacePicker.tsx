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
import { useCallback, useEffect, useState } from 'react'
import { listFs, updateSettings } from '@/lib/api'

export const WORKSPACE_CHANGED_EVENT = 'ephe:workspace-changed'

export interface WorkspaceState {
  /** Basename of the active workspace (null when unresolvable). */
  name: string | null
  /** True when the user chose a project (engine.json workspace_dir non-empty);
   *  false = neutral "Workspace" state with the documented CWD root fallback. */
  set: boolean
}

export function useWorkspaceState(): WorkspaceState {
  const [state, setState] = useState<WorkspaceState>({ name: null, set: false })
  const refresh = useCallback(() => {
    listFs()
      .then((fs) => {
        const dir = fs.workspace
        const set = (fs as { workspace_set?: boolean }).workspace_set === true
        setState({
          name: dir ? (dir.split('/').filter(Boolean).pop() ?? dir) : null,
          set,
        })
      })
      .catch(() => setState({ name: null, set: false }))
  }, [])
  useEffect(() => {
    refresh()
    window.addEventListener(WORKSPACE_CHANGED_EVENT, refresh)
    return () => window.removeEventListener(WORKSPACE_CHANGED_EVENT, refresh)
  }, [refresh])
  return state
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
