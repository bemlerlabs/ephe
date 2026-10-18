/**
 * The live guide: the keyframe bee as a cut-out 2.5-D sprite, flown by a spring.
 *
 * The actor is not redrawn: `bee-3d-actor.webp` is the hero frame's bee with a soft
 * alpha, and its two wings are separate layers that turn around the shoulders in real
 * HTML 3D. The component owns a 60 fps spring, a click-to-fly lock, a continuous gold
 * trail and the idle hover; the parent aims it at the card, a control, the engine core
 * or the header.
 */
import './InteractiveBeeGuide.css'
import { playSparkChime, playWingWhoosh } from '@/lib/spiritAudio'
import { BeeEyelids } from '@/components/bee/BeeEyelids'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'

export interface BeeGuideHandle {
  flyTo(x: number, y: number): void
  flyToControl(element: Element | null): void
  flyToElement(element: Element | null): void
  flyToPanelPerch(panel: Element | null): void
  finale(): void
  burst(x: number, y: number): void
  position(): { x: number; y: number }
}

interface GuideProps {
  still?: boolean
  size?: string
  onFinaleLanded?: () => void
}

interface Spark {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  max: number
  size: number
}

const CLICK_LOCK_MS = 1350

export const InteractiveBeeGuide = forwardRef<BeeGuideHandle, GuideProps>(
  function InteractiveBeeGuide(
    { still = false, size = 'clamp(13rem, 24vw, 20rem)', onFinaleLanded },
    ref,
  ) {
    const rootRef = useRef<HTMLDivElement>(null)
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const pos = useRef({ x: 0, y: 0 })
    const vel = useRef({ x: 0, y: 0 })
    const target = useRef({ x: 0, y: 0 })
    const home = useRef<{ x: number; y: number } | null>(null)
    const lockUntil = useRef(0)
    const pendingBurst = useRef(false)
    const finale = useRef(false)
    const landed = useRef(false)
    const raf = useRef(0)
    const last = useRef(0)
    const sparks = useRef<Spark[]>([])
    const [flying, setFlying] = useState(false)

    const place = useCallback((x: number, y: number) => {
      pos.current = { x, y }
      target.current = { x, y }
      if (rootRef.current) {
        rootRef.current.style.setProperty('--bee-x', `${x}px`)
        rootRef.current.style.setProperty('--bee-y', `${y}px`)
      }
    }, [])

    const burstAt = useCallback((x: number, y: number, count = 24) => {
      playSparkChime()
      for (let i = 0; i < count; i += 1) {
        const a = Math.random() * Math.PI * 2
        const v = 1.2 + Math.random() * 4.2
        sparks.current.push({
          x,
          y,
          vx: Math.cos(a) * v,
          vy: Math.sin(a) * v,
          life: 700 + Math.random() * 600,
          max: 1300,
          size: 0.8 + Math.random() * 2.4,
        })
      }
    }, [])

    const aim = useCallback((x: number, y: number) => {
      playWingWhoosh(Math.max(-0.8, Math.min(0.8, (x / window.innerWidth - 0.5) * 1.6)))
      target.current = { x, y }
      lockUntil.current = performance.now() + CLICK_LOCK_MS
      pendingBurst.current = true
      finale.current = false
      landed.current = false
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        flyTo(x, y) {
          aim(x, y)
        },
        flyToControl(element) {
          if (!element) return
          const rect = element.getBoundingClientRect()
          const beside = rect.left > 220 ? rect.left - 150 : rect.right + 150
          aim(
            Math.max(110, Math.min(window.innerWidth - 110, beside)),
            rect.top + rect.height * 0.32,
          )
        },
        flyToElement(element) {
          if (!element) return
          const rect = element.getBoundingClientRect()
          aim(Math.max(110, rect.left - 150), rect.top + rect.height * 0.32)
        },
        flyToPanelPerch(panel) {
          if (!panel) return
          const rect = panel.getBoundingClientRect()
          home.current = {
            x: Math.max(110, rect.left - Math.min(170, window.innerWidth * 0.14)),
            y: rect.top + rect.height * 0.28,
          }
          // A click flight keeps its target until its lock runs out.
          if (performance.now() >= lockUntil.current && !finale.current) {
            target.current = { ...home.current }
            pendingBurst.current = false
          }
        },
        finale() {
          target.current = { x: 44, y: 28 }
          lockUntil.current = Number.POSITIVE_INFINITY
          finale.current = true
          pendingBurst.current = true
          landed.current = false
        },
        burst(x, y) {
          burstAt(x, y)
        },
        position() {
          return { ...pos.current }
        },
      }),
      [aim, burstAt],
    )

    useEffect(() => {
      if (still) return
      const root = rootRef.current
      if (!root) return
      place(window.innerWidth * 0.62, window.innerHeight * 0.34)

      const step = (now: number) => {
        const dt = Math.min(34, now - (last.current || now))
        last.current = now
        const nowLocked = now < lockUntil.current
        if (!nowLocked && !finale.current && home.current) {
          target.current = { ...home.current }
        }
        const dx = target.current.x - pos.current.x
        const dy = target.current.y - pos.current.y
        vel.current.x = (vel.current.x + dx * 0.055) * 0.84
        vel.current.y = (vel.current.y + dy * 0.055) * 0.84
        pos.current.x += vel.current.x * (dt / 16.67)
        pos.current.y += vel.current.y * (dt / 16.67)
        const dist = Math.hypot(dx, dy)
        const speed = Math.hypot(vel.current.x, vel.current.y)
        if (dist < 28 && pendingBurst.current) {
          pendingBurst.current = false
          burstAt(pos.current.x, pos.current.y + 12)
        }
        if (finale.current && dist < 28 && !landed.current) {
          landed.current = true
          burstAt(44, 28, 30)
          onFinaleLanded?.()
        }

        // Idle hover: the body breathes even when the target is reached.
        const hoverX = Math.sin(now * 0.0026) * 14 + Math.cos(now * 0.0013) * 6
        const hoverY = Math.cos(now * 0.0038) * 12
        const hoverBank = Math.sin(now * 0.0026) * 6

        // Continuous comet trail while flying; a sparse shimmer while hovering.
        if (speed > 0.9) {
          for (let i = 0; i < 2 + (Math.random() < 0.4 ? 1 : 0); i += 1) {
            sparks.current.push({
              x: pos.current.x + (Math.random() - 0.5) * 12,
              y: pos.current.y + 16 + (Math.random() - 0.5) * 8,
              vx: -vel.current.x * 0.25 + (Math.random() - 0.5) * 0.7,
              vy: -vel.current.y * 0.25 + (Math.random() - 0.5) * 0.7,
              life: 550 + Math.random() * 400,
              max: 950,
              size: 1 + Math.random() * 2.2,
            })
          }
        } else if (Math.random() < 0.2) {
          sparks.current.push({
            x: pos.current.x + (Math.random() - 0.5) * 26,
            y: pos.current.y + 18,
            vx: (Math.random() - 0.5) * 0.5,
            vy: -0.3 - Math.random() * 0.5,
            life: 600 + Math.random() * 500,
            max: 1100,
            size: 0.8 + Math.random() * 1.6,
          })
        }

        const bank = Math.max(-28, Math.min(28, vel.current.x * 1.4)) + hoverBank
        const yaw = Math.max(-34, Math.min(34, vel.current.x * 2))
        const pitch = Math.max(-22, Math.min(22, -vel.current.y * 1.2))
        const z = 0.9 + Math.min(0.34, speed * 0.012)
        root.style.setProperty('--bee-x', `${pos.current.x + hoverX}px`)
        root.style.setProperty('--bee-y', `${pos.current.y + hoverY}px`)
        root.style.setProperty('--bee-z', z.toFixed(3))
        root.style.setProperty('--bee-bank', `${bank.toFixed(2)}deg`)
        root.style.setProperty('--bee-yaw', `${yaw.toFixed(2)}deg`)
        root.style.setProperty('--bee-pitch', `${pitch.toFixed(2)}deg`)
        root.style.setProperty('--bee-speed', Math.min(1, speed / 12).toFixed(3))
        setFlying(speed > 0.9)
        raf.current = requestAnimationFrame(step)
      }
      raf.current = requestAnimationFrame(step)

      const onMove = (event: PointerEvent) => {
        const dx = event.clientX - pos.current.x
        const dy = event.clientY - pos.current.y
        const len = Math.max(1, Math.hypot(dx, dy))
        root.style.setProperty('--look-x', (dx / len).toFixed(3))
        root.style.setProperty('--look-y', (dy / len).toFixed(3))
      }
      window.addEventListener('pointermove', onMove)
      return () => {
        cancelAnimationFrame(raf.current)
        window.removeEventListener('pointermove', onMove)
      }
    }, [burstAt, onFinaleLanded, place, still])

    useEffect(() => {
      if (still) return
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      let frame = 0
      let lastFrame = performance.now()
      const resize = () => {
        const dpr = Math.min(2, window.devicePixelRatio || 1)
        canvas.width = Math.round(canvas.clientWidth * dpr)
        canvas.height = Math.round(canvas.clientHeight * dpr)
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      }
      resize()
      window.addEventListener('resize', resize)
      const draw = (now: number) => {
        const dt = now - lastFrame
        lastFrame = now
        ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)
        ctx.globalCompositeOperation = 'lighter'
        for (let i = sparks.current.length - 1; i >= 0; i -= 1) {
          const p = sparks.current[i]
          if (!p) continue
          p.life -= dt
          if (p.life <= 0) {
            sparks.current.splice(i, 1)
            continue
          }
          p.x += p.vx * (dt / 16.67)
          p.y += p.vy * (dt / 16.67)
          p.vy += 0.008 * (dt / 16.67)
          const a = Math.max(0, p.life / p.max)
          ctx.fillStyle = `rgba(255, ${150 + Math.round(80 * a)}, 60, ${a})`
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalCompositeOperation = 'source-over'
        frame = requestAnimationFrame(draw)
      }
      frame = requestAnimationFrame(draw)
      return () => {
        cancelAnimationFrame(frame)
        window.removeEventListener('resize', resize)
      }
    }, [still])

    if (still) return null

    return (
      <>
        <canvas ref={canvasRef} className="bee-guide-sparks" aria-hidden="true" />
        <div
          ref={rootRef}
          data-testid="interactive-bee-guide"
          className={`bee-guide${flying ? ' is-flying' : ''}`}
          style={{ '--bee-size': size } as React.CSSProperties}
          aria-hidden="true"
        >
          <span className="bee-guide-light" />
          <div className="bee-actor">
            <div className="bee-actor-motion">
              <img
                className="bee-actor-body"
                src="/onboarding/bee-3d-actor.webp"
                alt=""
                draggable={false}
              />
              <img
                className="bee-actor-wing bee-wing-l"
                src="/onboarding/bee-3d-wing-l.webp"
                alt=""
                draggable={false}
              />
              <img
                className="bee-actor-wing bee-wing-r"
                src="/onboarding/bee-3d-wing-r.webp"
                alt=""
                draggable={false}
              />
              <img
                className="bee-actor-flame"
                src="/onboarding/bee-3d-flame.webp"
                alt=""
                draggable={false}
              />
              <BeeEyelids still={still} />
            </div>
          </div>
        </div>
      </>
    )
  },
)
