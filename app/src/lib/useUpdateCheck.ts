/**
 * Ephe — update check and installation (update-experience wave).
 *
 * The state is a machine, not a boolean claim: the surface may only say "no
 * update" when the check really answered. If it fails (backend gone, GitHub
 * unreachable, no release source) it says "check not possible" with the reason
 * — not "up to date".
 *
 * Desktop: the signed Tauri updater downloads and installs, with progress.
 * Browser: there is nothing to install — the surface points at the releases.
 * Nothing installs by itself; every step is a click.
 *
 * The surface asks the first question of a session by itself, at start, at the
 * moment the window is in front again and on a half-hour tick. Every one of
 * those answers arrives live (see `runLive`).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  relaunchApp,
  restartGuardNow,
  useRestartGuard,
  type RestartBlock,
} from '@/lib/restartGuard'
import { readAsset, readManifestNotes, readPlatform } from '@/lib/updateDetails'
import {
  applyUpdate,
  isDesktopShell,
  runCheck,
  type UpdateCheckInfo,
  type UpdatePhase,
  type UpdateState,
} from '@/lib/updateCheckRun'

/** The cadence of a session that stays open: the feed is asked every half
 *  hour. A live question costs one request against a public API with an hourly
 *  budget, and a release does not appear more often than that. */
const POLL_MS = 30 * 60 * 1000

/** The floor between two live questions the surface asks by itself. A live
 *  question leaves the backend TTL cache (6 h) behind, so each one of them
 *  reaches the feed — and switching windows is movement a hand makes all day.
 *  Five minutes caps that at twelve requests an hour, and a release published a
 *  moment ago is still noticed long before the half-hour tick would. */
const LIVE_GAP_MS = 5 * 60 * 1000

/** A source that just failed is left alone for fifteen minutes: the backend
 *  holds a failed answer for FAILURE_TTL_S (300 s), so a shorter floor would
 *  ask the same broken source again for the same nothing. A click is never
 *  gated, which is what makes a quiet quarter hour safe. */
const FAILED_BACKOFF_MS = 15 * 60 * 1000

/** Phases where a further question has nothing to add: the answer is known
 *  (available) or the installation owns the surface. */
const SETTLED: readonly UpdatePhase[] = [
  'available',
  'downloading',
  'installing',
  'ready',
  'applying',
  'applied',
]

/** The gate lives on the module. The chat panel mounts and unmounts as the
 *  user moves through the app, and a remount must not reopen a gate the last
 *  mount closed. */
let liveGateAt = 0

function initialState(): UpdateState {
  return { phase: 'idle', progress: null }
}

export function useUpdateCheck() {
  const [state, setState] = useState<UpdateState>(initialState)
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  /** One click questions the feed once, however fast the hand is. */
  const busyRef = useRef(false)
  /** The phase a live run reads before it writes, and the write that keeps it
   *  current. `phaseRef` cannot wait for a re-render: a live run asks its
   *  question and both belong to the run that is already in flight. */
  const phaseRef = useRef<UpdatePhase>('idle')
  /** A run that is overtaken must not land. A click during a live question,
   *  or an installation during one, takes the state over. */
  const tokenRef = useRef(0)

  const setPhase = useCallback((phase: UpdatePhase, patch: Partial<UpdateState> = {}) => {
    phaseRef.current = phase
    setState((s) => ({ ...s, phase, ...patch }))
  }, [])

  /** The user asked: always a live answer, never gated. */
  const check = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true
    // A window switch one second after a click would answer the same question.
    liveGateAt = Date.now() + LIVE_GAP_MS
    const token = ++tokenRef.current
    setPhase('checking', { progress: null })
    try {
      const next = await runCheck(true)
      if (token === tokenRef.current) {
        phaseRef.current = next.phase
        setState(next)
      }
    } finally {
      busyRef.current = false
    }
  }, [setPhase])

  /**
   * A question the surface asks by itself — at start, when the window is in
   * front again, and on the half-hour tick. All three want a live answer; the
   * gate above keeps the feed from seeing a hand that switches windows all
   * day, and a phase that is already settled carries no question at all.
   */
  const runLive = useCallback(async () => {
    if (SETTLED.includes(phaseRef.current)) return
    const now = Date.now()
    if (now < liveGateAt) return
    liveGateAt = now + LIVE_GAP_MS
    const token = ++tokenRef.current
    const next = await runCheck(true)
    if (next.phase === 'failed') liveGateAt = Date.now() + FAILED_BACKOFF_MS
    if (token !== tokenRef.current || SETTLED.includes(phaseRef.current)) return
    phaseRef.current = next.phase
    setState(next)
  }, [])

  // The native menu (next to the Apple mark) and the tray fire the same event as
  // the header button: open the dialog, run the check. The channel is
  // window.__TAURI__.event — @tauri-apps/api is not a dependency here.
  useEffect(() => {
    const ev = (
      window as {
        __TAURI__?: {
          event?: {
            listen: (name: string, cb: (e: unknown) => void) => Promise<() => void>
          }
        }
      }
    ).__TAURI__?.event
    if (!ev?.listen) return
    let unlisten: (() => void) | undefined
    let dead = false
    void ev
      .listen('update:check', () => {
        setOpen(true)
        void check()
      })
      .then((fn) => {
        if (dead) fn()
        else unlisten = fn
      })
    return () => {
      dead = true
      unlisten?.()
    }
  }, [check])

  useEffect(() => {
    void runLive()
    const askIfVisible = () => {
      if (document.visibilityState === 'visible') void runLive()
    }
    document.addEventListener('visibilitychange', askIfVisible)
    // A hidden tab throttles its timers anyway; the interval skips the tick it
    // cannot see, and the return to the front is the moment that matters.
    const handle = setInterval(askIfVisible, POLL_MS)
    return () => {
      document.removeEventListener('visibilitychange', askIfVisible)
      clearInterval(handle)
    }
  }, [runLive])

  /**
   * Download and installation through the signed updater, as two calls: that is
   * what lets the surface name whichever of the two is running, where
   * downloadAndInstall folds them into one and the installing phase would be a
   * guess. The installation itself reports no percentage at all.
   */
  const install = useCallback(async () => {
    if (!isDesktopShell()) return false
    tokenRef.current += 1 // a live answer still in flight must not land here
    setPhase('downloading', { progress: 0 })
    try {
      const updater = await import('@tauri-apps/plugin-updater')
      const update = await updater.check()
      if (!update?.available) {
        setPhase('current', { progress: null })
        return false
      }
      // The manifest names the package and often carries notes of its own; the
      // feed is asked first, so the release's own words win either way.
      const asset = readAsset(update.rawJson)
      const platform = readPlatform()
      const manifestNotes = readManifestNotes(update.body)
      if (manifestNotes) setState((s) => (s.notes ? s : { ...s, notes: manifestNotes }))
      let done = 0
      let total = 0
      await update.download((event) => {
        if (event.event === 'Started') {
          total = event.data.contentLength ?? 0
          // Without a total the bar has no scale: progress stays null and the
          // surface shows the indeterminate state it really is in.
          setPhase('downloading', {
            progress: total > 0 ? 0 : null,
            sizeBytes: total > 0 ? total : undefined,
            asset,
            platform,
          })
          return
        }
        if (event.event !== 'Progress') return
        done += event.data.chunkLength
        setPhase('downloading', { progress: total > 0 ? Math.min(1, done / total) : null })
      })
      setPhase('installing', { progress: 1 })
      await update.install()
      setPhase('ready', { progress: 1 })
      return true
    } catch (e) {
      setPhase('failed', {
        progress: null,
        reason: e instanceof Error ? e.message : String(e),
        failedAt: 'install',
      })
      return false
    }
  }, [setPhase])

  /**
   * Restart the app so the installed bundle takes over.
   *
   * The guard is read when the click arrives, so a turn that started after the
   * dialog opened still holds the restart back. The dialog draws the reason
   * from `restartBlocked`.
   */
  const relaunch = useCallback(async () => {
    if (restartGuardNow().blocked) return false
    try {
      return await relaunchApp()
    } catch {
      /* The shell may already be on its way out; a stayed surface is better
         than a surface that reports a restart it did not get. */
      return false
    }
  }, [])

  /**
   * Take the newest commits the check found. The backend owns the guards; the
   * surface owns the words, so a refusal arrives as a sentence with its reason
   * rather than as a silent no-op.
   */
  const apply = useCallback(async () => {
    tokenRef.current += 1
    setPhase('applying', { progress: null })
    const result = await applyUpdate()
    if (!result.ok) {
      // The code travels beside the prose: the surface owns the sentence the
      // user reads, the backend's detail stays as the technical line.
      setPhase('failed', {
        progress: null,
        reason: result.detail || result.reason || '',
        reasonCode: result.reason,
        failedAt: 'install',
      })
      return false
    }
    setPhase('applied', {
      progress: null,
      steps: result.steps,
      restart: result.restart,
      current: result.after ?? undefined,
    })
    return true
  }, [setPhase])

  const restartBlocked: RestartBlock | null = useRestartGuard().reason

  const show = state.phase === 'available' && !!state.latest && dismissed !== state.latest

  return {
    state,
    show,
    open,
    setOpen,
    check,
    install,
    apply,
    relaunch,
    restartBlocked,
    dismiss: () => state.latest && setDismissed(state.latest),
  }
}

/** Compatibility read for older callers (header pill). */
export function updateInfoOf(state: UpdateState): UpdateCheckInfo | null {
  if (state.phase === 'idle' || state.phase === 'checking') return null
  return {
    enabled: true,
    available:
      state.phase === 'available' || state.phase === 'downloading' || state.phase === 'ready',
    current: state.current,
    latest: state.latest,
    url: state.url,
    notes: state.notes,
    error: state.phase === 'failed' ? state.reason : undefined,
    channel: state.channel,
    commitsBehind: state.commitsBehind,
    commit: state.commit,
  }
}
