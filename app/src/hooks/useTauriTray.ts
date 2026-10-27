import { useEffect, useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import { openExternally } from '@/lib/nativeBrowser'

// Tauri 2.x event system — graceful fallback in the browser/dev mode
interface TauriBridge {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
  event?: {
    listen: (event: string, cb: (e: unknown) => void) => Promise<() => void>
  }
}

const bridge = (window as { __TAURI__?: TauriBridge }).__TAURI__

interface TauriEventPayload {
  payload?: unknown
}

function listen(event: string, cb: (e: TauriEventPayload) => void): Promise<() => void> | null {
  if (bridge?.event?.listen) {
    return bridge.event.listen(event, cb as (e: unknown) => void) as Promise<() => void>
  }
  return null
}

export interface TauriTray {
  isTauri: boolean
  windowVisible: boolean
}

export function useTauriTray(): TauriTray {
  const [windowVisible, setWindowVisible] = useState(true)
  const isTauri = !!bridge?.event?.listen

  useEffect(() => {
    if (!isTauri) return

    const unlistenFns: Array<() => void> = []

    const showSub = listen('show', () => setWindowVisible(true))
    const hideSub = listen('hide', () => setWindowVisible(false))
    const quitSub = listen('quit', () => {
      if (bridge?.core?.invoke) {
        void bridge.core.invoke('quit_app')
      }
    })
    // System Tray 'New Session' -> createSession() from the store
    const sessionSub = listen('create-session', () => {
      useChatStore.getState().createSession()
    })
    // N2: the macOS menu bar's Settings… (⌘,) and the tray share this hook. The
    // shell has already raised the window; `ephe:open-settings` is the event the
    // chat layout listens for, so the menu opens the same panel the palette does.
    // That panel belongs to the chat surface, and the menu bar is global, so a
    // page without it takes the settings route instead of firing into a void.
    const settingsSub = listen('open-settings', () => {
      const hash = window.location.hash
      if (hash === '' || hash === '#/' || hash.startsWith('#/chat')) {
        window.dispatchEvent(new CustomEvent('ephe:open-settings'))
      } else {
        window.location.hash = '#/settings'
      }
    })
    // Help -> Documentation. window.open is a no-op inside the shell, so the
    // address leaves through the native opener, as the palette's entry does.
    const docsSub = listen('open-docs', () => {
      void openExternally('https://ephe.app/docs')
    })

    if (showSub)
      unlistenFns.push(() => {
        void showSub.then((f) => f())
      })
    if (hideSub)
      unlistenFns.push(() => {
        void hideSub.then((f) => f())
      })
    if (quitSub)
      unlistenFns.push(() => {
        void quitSub.then((f) => f())
      })
    if (sessionSub)
      unlistenFns.push(() => {
        void sessionSub.then((f) => f())
      })
    if (settingsSub)
      unlistenFns.push(() => {
        void settingsSub.then((f) => f())
      })
    if (docsSub)
      unlistenFns.push(() => {
        void docsSub.then((f) => f())
      })

    return () => {
      for (const f of unlistenFns) f()
    }
  }, [isTauri])

  return { isTauri, windowVisible }
}
