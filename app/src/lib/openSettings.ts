/** Ask for the settings hub from anywhere in the app.
 *
 *  The hub is mounted with the chat shell, so a request that arrives on another page
 *  — Discover, the workbench, the memory pages — has to survive the route change. The
 *  palette used to dispatch the event into a page that had no listener, and the row
 *  did nothing there.
 */

const isChatRoute = (hash: string): boolean =>
  hash === '' || hash === '#' || hash === '#/' || hash.startsWith('#/chat')

let pending = false

export function requestSettingsOpen(): void {
  if (!isChatRoute(window.location.hash)) {
    pending = true
    window.location.hash = '#/chat'
    return
  }
  window.dispatchEvent(new CustomEvent('ephe:open-settings'))
}

/** The chat shell asks once when it mounts; the answer is true at most once. */
export function takePendingSettingsOpen(): boolean {
  const was = pending
  pending = false
  return was
}
