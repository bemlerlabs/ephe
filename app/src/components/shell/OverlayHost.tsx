/**
 * W1-4 — the overlay host: a plugin surface in a browser tab.
 *
 * The desktop half (#43) puts the same document in a window with its own label.
 * Here it is a frame in a stack the shell draws, and the two halves keep the same
 * two rules: one surface per plugin, and a title row the user can grab. The stack
 * itself is `overlayModel`'s; this file only turns one surface into one box, and
 * the box into the geometry operations the model already answers.
 *
 * Three things about this file are decisions worth stating where they are made:
 *
 *   - The frame is sandboxed at the embedder as well as in the response. #42 gave
 *     the document `sandbox allow-scripts allow-popups` with no `allow-same-origin`,
 *     which is what takes its authority away; the attribute is the same effect at a
 *     second enforcement point. What it costs a plugin is measured in
 *     `w1-4-report.md`, because a claim about an engine is not a measurement.
 *   - A surface is not a modal. The workbench behind it stays reachable — no inert,
 *     no Tab trap — because a floating plugin window that took the composer away
 *     would be the defect the review trail names. Escape here minimizes, the
 *     reversible half of closing.
 *   - The chrome is quiet: one 44 px rail, its buttons revealed by the pointer or
 *     the keyboard and always there on a touch device. Nothing outside the surface's
 *     own box is added to the page.
 */
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDownRight, Minus, Square, X } from 'lucide-react'
import { useChatStore } from '@/store'
import { stableFocusTarget } from '@/hooks/useFocusReturn'
import { ApiError, request } from '@/lib/api/http'
import { releaseSurfaceCredential } from '@/lib/pluginDisplay'
import { saveHostSurface, type HostSurface } from '@/lib/surfaceHost'
import { attachPluginClient } from '@/lib/pluginClientHost'
import { OVERLAY_RAIL_HEIGHT, type OverlaySurface, type Rect, type Viewport } from './overlayModel'
import './OverlayHost.css'

/** The embedder's copy of `server/plugin_surface_policy.py`'s isolation directive. */
const SURFACE_SANDBOX = 'allow-scripts allow-popups'

function hostFromSurface(surface: OverlaySurface, open: boolean): HostSurface {
  return {
    slot: 'overlay',
    x: Math.round(surface.bounds.x),
    y: Math.round(surface.bounds.y),
    width: Math.round(surface.bounds.width),
    height: Math.round(surface.bounds.height),
    open,
    minimized: surface.minimized,
    placed: true,
  }
}

function rememberOpen(pluginId: string): void {
  const surface = useChatStore
    .getState()
    .overlay.surfaces.find((item) => item.pluginId === pluginId)
  if (!surface) return
  void saveHostSurface(pluginId, hostFromSurface(surface, true)).catch(() => {})
}

function reloadedUrl(url: string, epoch: number): string {
  if (epoch < 1) return url
  return `${url}${url.includes('?') ? '&' : '?'}ephe_reload=${epoch}`
}

function diffNames(payload: unknown): string[] {
  if (!payload || typeof payload !== 'object') return []
  const diff = (payload as { diff?: unknown }).diff
  if (!Array.isArray(diff)) return []
  return diff
    .map((item) => (item && typeof item === 'object' ? (item as { name?: unknown }).name : ''))
    .filter((name): name is string => typeof name === 'string' && name.length > 0)
}

/** One key press on the grip: a fifth of the smallest usable width. */
const KEY_STEP = 16

const viewportNow = (): Viewport => ({ width: window.innerWidth, height: window.innerHeight })

export default function OverlayHost() {
  const surfaces = useChatStore((s) => s.overlay.surfaces)
  const resizeOverlay = useChatStore((s) => s.resizeOverlay)

  /// A surface parked at the right edge of a wide window is off screen in a narrow
  /// one, and the model is the only place that knows how to bring it back. Passing
  /// the size it already has asks for the clamp, nothing else.
  useEffect(() => {
    if (!surfaces.length) return
    let last = viewportNow()
    const onResize = () => {
      const next = viewportNow()
      if (next.width === last.width && next.height === last.height) return
      last = next
      for (const surface of surfaces) resizeOverlay(surface.key, surface.bounds, next)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [surfaces, resizeOverlay])

  if (!surfaces.length) return null
  const ordered = [...surfaces].sort((a, b) => a.z - b.z)
  return (
    <div className="overlay-host" data-testid="overlay-host" data-inert-exempt="">
      {ordered.map((surface, rank) => (
        <OverlayWindow key={surface.key} surface={surface} rank={rank} />
      ))}
    </div>
  )
}

type Gesture = { kind: 'move' | 'resize'; pointer: number; x: number; y: number; from: Rect }

function OverlayWindow({ surface, rank }: { surface: OverlaySurface; rank: number }) {
  const { t } = useTranslation()
  const closeOverlay = useChatStore((s) => s.closeOverlay)
  const focusOverlay = useChatStore((s) => s.focusOverlay)
  const minimizeOverlay = useChatStore((s) => s.minimizeOverlay)
  const restoreOverlay = useChatStore((s) => s.restoreOverlay)
  const moveOverlay = useChatStore((s) => s.moveOverlay)
  const resizeOverlay = useChatStore((s) => s.resizeOverlay)

  const box = useRef<HTMLDivElement>(null)
  const toggle = useRef<HTMLButtonElement>(null)
  const frame = useRef<HTMLIFrameElement>(null)
  const gesture = useRef<Gesture | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [changed, setChanged] = useState<string[] | null>(null)
  const name = surface.title || surface.pluginId

  useEffect(() => {
    const node = frame.current
    if (!node) return
    return attachPluginClient(node, surface.pluginId, (event, data) => {
      if (event !== 'plugin.mount') return
      const phase = data && typeof data === 'object' ? (data as { phase?: unknown }).phase : ''
      if (phase !== 'mounted') return
      setEpoch((current) => current + 1)
    })
  }, [surface.pluginId])

  async function reloadBundle() {
    setChanged(null)
    try {
      await request(`/api/plugins/${encodeURIComponent(surface.pluginId)}/hot-mount`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
    } catch (error) {
      if (error instanceof ApiError && error.reasonCode === 'mount_change_unacknowledged') {
        setChanged(diffNames(error.payload))
      }
    }
  }

  const begin = (kind: Gesture['kind']) => (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return
    // The rail is a handle, not a button: a drag must not select the title beside it.
    event.preventDefault()
    gesture.current = {
      kind,
      pointer: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      from: surface.bounds,
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const during = (event: ReactPointerEvent<HTMLElement>) => {
    const held = gesture.current
    if (!held || held.pointer !== event.pointerId) return
    const dx = event.clientX - held.x
    const dy = event.clientY - held.y
    const viewport = viewportNow()
    if (held.kind === 'move') {
      moveOverlay(surface.key, { x: held.from.x + dx, y: held.from.y + dy }, viewport)
      return
    }
    resizeOverlay(
      surface.key,
      { width: held.from.width + dx, height: held.from.height + dy },
      viewport,
    )
  }

  const end = (event: ReactPointerEvent<HTMLElement>) => {
    const held = gesture.current
    if (!held || held.pointer !== event.pointerId) return
    gesture.current = null
    // The capture is per element, so a gesture that ends on the rail is released
    // there and one that ends on the grip there; a stray pointerup finds nothing.
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    rememberOpen(surface.pluginId)
  }

  /** The surface is not modal, so closing it must not yank the caret out of a
   *  composer that was busy mid-sentence. Only a surface that held the focus owes
   *  the page a landing place, and `stableFocusTarget` never answers `<body>`. */
  const close = () => {
    const heldFocus = Boolean(box.current?.contains(document.activeElement))
    releaseSurfaceCredential(surface.pluginId)
    void saveHostSurface(surface.pluginId, hostFromSurface(surface, false)).catch(() => {})
    closeOverlay(surface.key)
    if (heldFocus) stableFocusTarget()?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Escape') return
    minimizeOverlay(surface.key)
    toggle.current?.focus()
  }

  const onGripKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step: Record<string, [number, number]> = {
      ArrowRight: [KEY_STEP, 0],
      ArrowLeft: [-KEY_STEP, 0],
      ArrowDown: [0, KEY_STEP],
      ArrowUp: [0, -KEY_STEP],
    }
    const delta = step[event.key]
    if (!delta) return
    event.preventDefault()
    resizeOverlay(
      surface.key,
      { width: surface.bounds.width + delta[0], height: surface.bounds.height + delta[1] },
      viewportNow(),
    )
    rememberOpen(surface.pluginId)
  }

  const style = {
    left: surface.bounds.x,
    top: surface.bounds.y,
    width: surface.bounds.width,
    height: surface.minimized ? OVERLAY_RAIL_HEIGHT : surface.bounds.height,
    ['--stack-rank']: String(rank),
  } as CSSProperties

  return (
    <div
      ref={box}
      data-overlay-window
      data-plugin={surface.pluginId}
      data-surface-type={surface.surfaceType}
      data-transparent={String(surface.transparent)}
      data-minimized={String(surface.minimized)}
      role="region"
      aria-label={name}
      className="float-surface overlay-window"
      style={style}
      onKeyDown={onKeyDown}
      onPointerDownCapture={() => focusOverlay(surface.key)}
    >
      <div
        data-testid="overlay-rail"
        className="overlay-rail"
        onPointerDown={begin('move')}
        onPointerMove={during}
        onPointerUp={end}
        onPointerCancel={end}
      >
        <span className="overlay-title text-foreground/70">{name}</span>
        <button
          type="button"
          data-testid={`overlay-reload-${surface.pluginId}`}
          className="overlay-control"
          aria-label={t('overlay.reload')}
          onClick={() => void reloadBundle()}
        >
          {t('overlay.reload')}
        </button>
        <button
          type="button"
          ref={toggle}
          className="overlay-control"
          aria-label={surface.minimized ? t('nav.maximize') : t('nav.minimize')}
          onClick={() => {
            if (surface.minimized) restoreOverlay(surface.key, viewportNow())
            else minimizeOverlay(surface.key)
            rememberOpen(surface.pluginId)
          }}
        >
          {surface.minimized ? (
            <Square className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Minus className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          className="overlay-control"
          aria-label={t('a11y.close')}
          onClick={close}
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
      {changed && (
        <p data-testid={`overlay-reload-diff-${surface.pluginId}`} className="overlay-title">
          {t('overlay.reloadDiff')}
          {changed.length > 0 ? `: ${changed.join(', ')}` : ''}
        </p>
      )}
      <iframe
        ref={frame}
        data-testid={`overlay-frame-${surface.pluginId}`}
        className="overlay-frame"
        title={name}
        src={reloadedUrl(surface.url, epoch)}
        sandbox={SURFACE_SANDBOX}
        allow=""
        referrerPolicy="no-referrer"
        hidden={surface.minimized}
      />
      <button
        type="button"
        className="overlay-control overlay-grip"
        aria-label={t('a11y.resizeSurface')}
        onKeyDown={onGripKeyDown}
        onPointerDown={begin('resize')}
        onPointerMove={during}
        onPointerUp={end}
        onPointerCancel={end}
      >
        <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}
