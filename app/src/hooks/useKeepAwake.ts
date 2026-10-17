import { useCallback, useEffect, useRef, useState } from 'react'
import { useChatStore } from '@/store/chatStore'

/**
 * Keep-awake (P2-B automations): holds the machine awake while a chat is running
 * AND the user switched the toggle on — nothing else.
 *
 * Two honest paths (no silent fallback):
 *  - Desktop (Tauri): invoke('set_keep_awake', { enabled }) — Rust starts/stops
 *    `caffeinate -dimsu` (macOS; other platforms answer false
 *    → supported honestly flips to false).
 *  - Web: the Screen Wake Lock API (navigator.wakeLock.request('screen')).
 *    The browser releases the lock itself when the tab hides → re-request on
 *    visibilitychange → visible, as long as the need still stands.
 *
 * No mechanism available → supported=false; the UI disables the toggle with an
 * honest hint (never a dead toggle). API failure → error=true, active=false (the
 * UI shows the hint).
 *
 * Streaming detection (same pattern as StatusBar R25): the last assistant message
 * of the active session has streaming=true. The hook follows it event-driven via a
 * store subscription, and a slow interval is the safety net (lost events, system
 * sleep); unmount always releases.
 */

type KeepAwakeVia = 'tauri' | 'wakeLock' | null

export interface KeepAwakeHandle {
  /** At least one mechanism exists — only then may the toggle be active. */
  supported: boolean
  /** The lock is currently held (only meaningful while a chat is streaming). */
  active: boolean
  /** The last acquire attempt failed (API fail) → hint in the UI. */
  error: boolean
  /** Which mechanism — so the UI hints stay honest. */
  via: KeepAwakeVia
}

interface TauriBridge {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

function tauriInvoke(cmd: string, args: Record<string, unknown>): Promise<unknown> | null {
  const bridge = (window as { __TAURI__?: TauriBridge }).__TAURI__
  if (!bridge?.core?.invoke) return null
  return bridge.core.invoke(cmd, args)
}

function detectVia(): KeepAwakeVia {
  if (typeof window === 'undefined') return null
  if ((window as { __TAURI__?: TauriBridge }).__TAURI__?.core?.invoke) return 'tauri'
  if (typeof navigator !== 'undefined' && 'wakeLock' in navigator) return 'wakeLock'
  return null
}

/** Is the last assistant message streaming? (scan from the end — cheap) */
function isChatStreaming(): boolean {
  const msgs = useChatStore.getState().currentSession?.messages
  if (!msgs) return false
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m?.role === 'assistant') return !!m.streaming
  }
  return false
}

export function useKeepAwake(enabled: boolean): KeepAwakeHandle {
  const [via, setVia] = useState<KeepAwakeVia>(detectVia)
  const [supported, setSupported] = useState(() => detectVia() !== null)
  const [active, setActive] = useState(false)
  const [error, setError] = useState(false)

  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const desiredRef = useRef(false)
  const activeRef = useRef(false)
  const sentinelRef = useRef<WakeLockSentinel | null>(null)
  // Drop stale async acquires (the toggle flipped while the request was running)
  const syncTokenRef = useRef(0)
  // No double acquire on interleaved syncs (store event + interval)
  const inFlightRef = useRef(false)

  const markActive = useCallback((isActive: boolean) => {
    activeRef.current = isActive
    setActive(isActive)
  }, [])

  const release = useCallback(async () => {
    activeRef.current = false
    setActive(false)
    setError(false)
    const v = detectVia()
    if (v === 'tauri') {
      try {
        await tauriInvoke('set_keep_awake', { enabled: false })
      } catch {
        /* a failed release is worthless to report — the lock status stays false */
      }
      return
    }
    const s = sentinelRef.current
    sentinelRef.current = null
    if (s) {
      try {
        await s.release()
      } catch {
        /* already released by the browser */
      }
    }
  }, [])

  const acquire = useCallback(async () => {
    const v = detectVia()
    if (!v) {
      setSupported(false)
      return
    }
    if (v === 'tauri') {
      try {
        const res = await tauriInvoke('set_keep_awake', { enabled: true })
        if (!desiredRef.current) return // superseded (toggle/turn switched off since)
        if (res === true) {
          setVia('tauri')
          setSupported(true)
          setError(false)
          markActive(true)
        } else {
          // a platform without any mechanism → disable honestly (no dead toggle)
          setVia(null)
          setSupported(false)
          markActive(false)
        }
      } catch {
        setVia('tauri')
        setSupported(true)
        setError(true)
        markActive(false)
      }
      return
    }
    // wakeLock
    try {
      const s = await navigator.wakeLock.request('screen')
      if (!desiredRef.current) {
        try {
          await s.release()
        } catch {
          /* noop */
        }
        return
      }
      sentinelRef.current = s
      setVia('wakeLock')
      setSupported(true)
      setError(false)
      markActive(true)
    } catch {
      setError(true)
      markActive(false)
    }
  }, [markActive])

  const sync = useCallback(async () => {
    const desired = enabledRef.current && isChatStreaming()
    desiredRef.current = desired
    syncTokenRef.current += 1
    const token = syncTokenRef.current
    // The wake lock may have been released quietly by the browser (tab hidden) —
    // treat it honestly as "not held" and request it again.
    const sentinel = sentinelRef.current
    const lockHeld = activeRef.current && !(sentinel && sentinel.released)
    if (desired && !lockHeld && !inFlightRef.current) {
      inFlightRef.current = true
      try {
        await acquire()
      } finally {
        inFlightRef.current = false
      }
      if (token !== syncTokenRef.current) return // superseded — the current sync handles it
      // an acquire kept running after a release flip → catch the state up
      if (!desiredRef.current && activeRef.current) await release()
    } else if (!desired && (activeRef.current || sentinel)) {
      // a running acquire checks desiredRef itself after the await
      if (!inFlightRef.current) await release()
    }
  }, [acquire, release])

  // Toggle change + mount: sync right away
  useEffect(() => {
    void sync()
  }, [enabled, sync])

  // Streaming changes arrive as store updates → event-driven sync
  useEffect(() => {
    return useChatStore.subscribe(() => {
      void sync()
    })
  }, [sync])

  // Safety net: lost events / system sleep / late errors
  useEffect(() => {
    const id = setInterval(() => {
      void sync()
    }, 5000)
    return () => clearInterval(id)
  }, [sync])

  // Wake lock: the browser releases it automatically on tab hide → re-acquire on return
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return
      if (!desiredRef.current) return
      const s = sentinelRef.current
      if (!s || s.released) void sync()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [sync])

  // unmount → always release the lock (discard acquires still open)
  useEffect(() => {
    return () => {
      syncTokenRef.current += 1
      desiredRef.current = false
      if (activeRef.current || sentinelRef.current) void release()
    }
  }, [release])

  return { supported, active, error, via }
}
