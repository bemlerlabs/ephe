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
 *
 * One machine, every surface. The header's sheet and Settings → Version &
 * Updates each ran an instance, and an instance kept its own state: the surface
 * that mounted second inherited the live gate the first had closed, answered
 * nothing, and offered no update while the header was naming one. The state and
 * its runs live here now, every mount subscribes to them, and `updateActionOf`
 * with `updateNoticeOf` are the two readings a surface draws from the answer.
 */
import { useEffect, useState, useSyncExternalStore } from 'react'
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

/** The closures that end the retry loop rather than inviting another click. */
const BLOCKED_CODES = ['not_a_checkout', 'not_on_main', 'dirty_tree']

function initialState(): UpdateState {
  return { phase: 'idle', progress: null }
}

let state: UpdateState = initialState()
const subscribers = new Set<() => void>()
/** The gate and the runs sit on the module. The chat panel mounts and unmounts
 *  as the user moves through the app, and a remount must not reopen a gate the
 *  last mount closed, nor ask a question the app has already asked. */
let liveGateAt = 0
let busy = false
/** A run that is overtaken must not land: a click during a live question, or an
 *  installation during one, takes the answer over. */
let token = 0
let mountedSurfaces = 0
let stopDrivers: (() => void) | null = null

function write(next: UpdateState): void {
  state = next
  for (const notify of [...subscribers]) notify()
}

function setPhase(phase: UpdatePhase, patch: Partial<UpdateState> = {}): void {
  write({ ...state, phase, ...patch })
}

function subscribe(notify: () => void): () => void {
  subscribers.add(notify)
  return () => subscribers.delete(notify)
}

/** The user asked: always a live answer, never gated. */
async function check(): Promise<void> {
  if (busy) return
  busy = true
  // A window switch one second after a click would answer the same question.
  liveGateAt = Date.now() + LIVE_GAP_MS
  const run = ++token
  setPhase('checking', { progress: null })
  try {
    const next = await runCheck(true)
    if (run === token) write(next)
  } finally {
    busy = false
  }
}

/**
 * A question the surface asks by itself — at start, when the window is in
 * front again, and on the half-hour tick. All three want a live answer; the
 * gate above keeps the feed from seeing a hand that switches windows all
 * day, and a phase that is already settled carries no question at all.
 */
async function runLive(): Promise<void> {
  if (SETTLED.includes(state.phase)) return
  const now = Date.now()
  if (now < liveGateAt) return
  liveGateAt = now + LIVE_GAP_MS
  const run = ++token
  const next = await runCheck(true)
  if (next.phase === 'failed') liveGateAt = Date.now() + FAILED_BACKOFF_MS
  if (run !== token || SETTLED.includes(state.phase)) return
  write(next)
}

/**
 * Download and installation through the signed updater, as two calls: that is
 * what lets the surface name whichever of the two is running, where
 * downloadAndInstall folds them into one and the installing phase would be a
 * guess. The installation itself reports no percentage at all.
 */
async function install(): Promise<boolean> {
  if (!isDesktopShell()) return false
  token += 1 // a live answer still in flight must not land here
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
    if (!state.notes) write({ ...state, notes: manifestNotes })
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
}

/**
 * Restart the app so the installed bundle takes over.
 *
 * The guard is read when the click arrives, so a turn that started after the
 * dialog opened still holds the restart back. The dialog draws the reason
 * from `restartBlocked`.
 */
async function relaunch(): Promise<boolean> {
  if (restartGuardNow().blocked) return false
  try {
    return await relaunchApp()
  } catch {
    /* The shell may already be on its way out; a stayed surface is better
       than a surface that reports a restart it did not get. */
    return false
  }
}

/**
 * Take the newest commits the check found. The backend owns the guards; the
 * surface owns the words, so a refusal arrives as a sentence with its reason
 * rather than as a silent no-op.
 */
async function apply(): Promise<boolean> {
  token += 1
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
}

/** The machine's three self-asked moments, started with the first surface and
 *  stopped with the last one so no unmounted page keeps a timer. */
function startDrivers(): () => void {
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
}

export function useUpdateCheck() {
  const current = useSyncExternalStore(
    subscribe,
    () => state,
    () => state,
  )
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState<string | null>(null)

  useEffect(() => {
    mountedSurfaces += 1
    stopDrivers ??= startDrivers()
    // Every mount asks its surface's own first question; the gate keeps that
    // from becoming a second request while the machine already has an answer.
    void runLive()
    return () => {
      mountedSurfaces -= 1
      if (mountedSurfaces === 0) {
        stopDrivers?.()
        stopDrivers = null
      }
    }
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
  }, [])

  const restartBlocked: RestartBlock | null = useRestartGuard().reason
  const show = current.phase === 'available' && !!current.latest && dismissed !== current.latest

  return {
    state: current,
    show,
    open,
    setOpen,
    check,
    install,
    apply,
    relaunch,
    restartBlocked,
    dismiss: () => current.latest && setDismissed(current.latest),
  }
}

/** What one click can do about the answer, and the words the click carries. */
export interface UpdateAction {
  /** Which run of the machine the click starts. */
  run: 'apply' | 'install'
  /** The label: the sheet and the settings page say the same words because they
   *  read the same answer. */
  labelKey: string
  /** Whether the click changes anything where it is made — a release the browser
   *  surface cannot install is a page it points at. */
  takesEffect: boolean
}

export function updateActionOf(answer: UpdateState): UpdateAction | null {
  if (answer.phase !== 'available') return null
  if (answer.channel === 'main') {
    return answer.applyBlocked
      ? null
      : { run: 'apply', labelKey: 'update.applyNow', takesEffect: true }
  }
  const desktop = isDesktopShell()
  return {
    run: 'install',
    labelKey: desktop ? 'update.installAndRestart' : 'update.viewReleases',
    takesEffect: desktop,
  }
}

/** The sentence for an answer with nothing to click: why the update cannot run
 *  here and what the reader does next. Null when the answer needs no explaining. */
export function updateNoticeOf(answer: UpdateState, desktop = isDesktopShell()): string | null {
  if (answer.phase === 'failed') return updateFailureKey(answer)
  if (answer.phase === 'unsupported') return 'update.disabledHint'
  if (answer.phase !== 'available') return null
  if (answer.channel === 'main')
    return answer.applyBlocked ? `update.blocked.${updateBlockedKey(answer.applyBlocked)}` : null
  return desktop ? null : 'update.browserNote'
}

/** Which of the closed-commit-path sentences a refusal or a block answers with. */
export function updateBlockedKey(code?: string): string {
  return BLOCKED_CODES.includes(code ?? '') ? (code as string) : 'other'
}

/** The failure sentence: an installer that refused names its own reason, and a
 *  release source that did not answer names that one. */
export function updateFailureKey(answer: UpdateState): string {
  if (answer.failedAt !== 'install') return 'update.checkFailed'
  const code = answer.reasonCode ?? ''
  return BLOCKED_CODES.includes(code) ? `update.blocked.${code}` : 'update.installFailed'
}

/** Compatibility read for older callers (header pill). */
export function updateInfoOf(answer: UpdateState): UpdateCheckInfo | null {
  if (answer.phase === 'idle' || answer.phase === 'checking') return null
  return {
    enabled: true,
    available:
      answer.phase === 'available' || answer.phase === 'downloading' || answer.phase === 'ready',
    current: answer.current,
    latest: answer.latest,
    url: answer.url,
    notes: answer.notes,
    error: answer.phase === 'failed' ? answer.reason : undefined,
    channel: answer.channel,
    commitsBehind: answer.commitsBehind,
    commit: answer.commit,
  }
}
