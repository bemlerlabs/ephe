import { useCallback } from 'react'

// Tauri 2.x IPC — graceful fallback in the browser / dev mode
function invoke(cmd: string): Promise<unknown> {
  if (window.__TAURI__?.core?.invoke) {
    return window.__TAURI__.core.invoke(cmd)
  }
  console.log(`[Tauri IPC] ${cmd}`)
  return Promise.resolve()
}

export interface TauriWindow {
  isTauri: boolean
  minimize: () => void
  maximize: () => void
  close: () => void
  show: () => void
  hide: () => void
}

export function useTauriWindow(): TauriWindow {
  const isTauri = !!window.__TAURI__?.core?.invoke

  const minimize = useCallback(() => {
    void invoke('minimize_window')
  }, [])
  const maximize = useCallback(() => {
    void invoke('maximize_window')
  }, [])
  const close = useCallback(() => {
    void invoke('close_window')
  }, [])
  const show = useCallback(() => {
    void invoke('show_window')
  }, [])
  const hide = useCallback(() => {
    void invoke('hide_window')
  }, [])

  return { isTauri, minimize, maximize, close, show, hide }
}
