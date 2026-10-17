/**
 * Ephe — Wave 3: native notification when a task finishes (Finding 4).
 *
 * The user dispatches a task and switches to another window — Ephe reports done as
 * soon as the stream ends, IF the tab is currently hidden. No timeout tinkering, no
 * queue: purely reactive at finishTurn.
 *
 * Guard chain in notifyTaskDone: API available → permission 'granted' →
 * tab hidden (document.hidden). Without the hidden check every answer
 * in the foreground would pop up — that is exactly what annoys people about notifications.
 */
export function notificationsSupported(): boolean {
  if (typeof window === 'undefined') return false
  // Tauri desktop: the native plugin takes over (no browser permission).
  if (isTauriRuntime()) return true
  return 'Notification' in window
}

function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && !!(window as unknown as Record<string, unknown>).__TAURI__
}

/** Tauri: permission through the plugin (the `notification:default` capability decides). */
async function tauriPermissionGranted(): Promise<boolean> {
  try {
    const mod = await import('@tauri-apps/plugin-notification')
    let granted = await mod.isPermissionGranted()
    if (!granted) {
      granted = (await mod.requestPermission()) === 'granted'
    }
    return granted
  } catch {
    return false
  }
}

/** Call at task START: lazy permission request (default → the user decides once). */
export function requestTaskNotifyPermission(): void {
  if (!notificationsSupported()) return
  if (isTauriRuntime()) {
    // On the desktop client ask once — drop it silently when declined.
    void tauriPermissionGranted()
    return
  }
  try {
    if (Notification.permission === 'default') void Notification.requestPermission()
  } catch {
    /* Insecure context (http over LAN without localhost): Notification throws — no matter. */
  }
}

/** Call at task END: only shows with a hidden tab + granted permission. */
export async function notifyTaskDone(title: string, body: string): Promise<void> {
  if (!notificationsSupported()) return
  try {
    if (isTauriRuntime()) {
      if (tauriPermissionCache === false) return
      if (tauriPermissionCache !== true) {
        tauriPermissionCache = await tauriPermissionGranted()
        if (!tauriPermissionCache) return
      }
      const { sendNotification } = await import('@tauri-apps/plugin-notification')
      sendNotification({ title, body })
      return
    }
    if (Notification.permission !== 'granted') return
    if (!document.hidden) return
    const n = new Notification(title, {
      body: body.slice(0, 160),
      tag: 'ephe-task-done',
      // Same icon as the PWA manifest — no double maintenance here.
      icon: '/icon-192.png',
    })
    // Click → bring the tab back to the foreground (Windows/Linux otherwise pop up blank).
    n.addEventListener('click', () => {
      window.focus()
      n.close()
    })
  } catch {
    /* The Notification constructor can be missing in embedded webviews. */
  }
}

/** Tauri permission cache: one request per session instead of one per task. */
let tauriPermissionCache: boolean | null = null
