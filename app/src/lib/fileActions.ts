/**
 * N4 — the Finder verbs on a file the workbench produced.
 *
 * The WebView can show an artifact but cannot hand it to Finder, so the shell
 * does it: `reveal_file_in_finder` selects the file, `open_file_in_default_app`
 * launches it with whatever the user set. Both are fenced in Rust
 * (`app/src-tauri/src/desktop.rs`): only a canonicalized regular file inside the
 * artifact store, the configured project or the usual save folders is accepted.
 *
 * A refusal comes back as `false`; the row shows one sentence and the rest of
 * the card keeps working.
 */
import { isDesktopShell, tauriInvoke } from './tauriBridge'

export function canUseNativeFileActions(): boolean {
  return isDesktopShell()
}

async function invokePath(command: string, path: string): Promise<boolean> {
  const invoke = tauriInvoke()
  if (!invoke) return false
  try {
    await invoke(command, { path })
    return true
  } catch {
    return false
  }
}

export function revealInFinder(path: string): Promise<boolean> {
  return invokePath('reveal_file_in_finder', path)
}

export function openInDefaultApp(path: string): Promise<boolean> {
  return invokePath('open_file_in_default_app', path)
}

/** N5: the native preview panel, behind the same path fence. */
export function quickLook(path: string): Promise<boolean> {
  return invokePath('quick_look_file', path)
}
