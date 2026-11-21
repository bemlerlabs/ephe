/**
 * The companion in the product surfaces — the same cut-out actor the first open
 * ends on, or the ember spark of act two, or the quiet mark.
 *
 * The actor is three images plus the forehead flame, so a click-flight can turn
 * the whole figure on its 3D axis and a burst can leave it in gold without a
 * repaint. `turnTo` and `burst` are imperative because the welcome cards aim the
 * figure at themselves, not at a component state.
 */
import './Companion.css'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { playSparkBurst, playWingWhoosh } from '@/lib/spiritAudio'
import { EpheMark } from '@/components/shell/EpheMark'
import { BeeEyelids } from '@/components/bee/BeeEyelids'

export type CompanionSpecies = 'paper_moth' | 'fire_bee' | 'ember_spark' | 'minimal'

/** Each cut-out actor is a body, two hinged wings and one accent part. */
interface ActorArt {
  body: string
  wingLeft: string
  wingRight: string
  accent: string
}

const MOTH_ART: ActorArt = {
  body: '/onboarding/paper-moth-actor.webp',
  wingLeft: '/onboarding/paper-moth-wing-l.webp',
  wingRight: '/onboarding/paper-moth-wing-r.webp',
  accent: '/onboarding/paper-moth-thread.webp',
}

const BEE_ART: ActorArt = {
  body: '/onboarding/bee-3d-actor.webp',
  wingLeft: '/onboarding/bee-3d-wing-l.webp',
  wingRight: '/onboarding/bee-3d-wing-r.webp',
  accent: '/onboarding/bee-3d-flame.webp',
}

export interface CompanionHandle {
  turnTo(degrees: number): void
  burst(): void
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

interface CompanionActorProps {
  species: CompanionSpecies
  scale?: number
  still?: boolean
  flying?: boolean
  size?: 'hero' | 'workspace' | 'header' | 'studio'
  testId?: string
  className?: string
  onActivate?: () => void
}

export const CompanionActor = forwardRef<CompanionHandle, CompanionActorProps>(
  function CompanionActor(
    {
      species,
      scale = 100,
      still = false,
      flying = false,
      size = 'workspace',
      testId,
      className = '',
      onActivate,
    },
    ref,
  ) {
    const rootRef = useRef<HTMLDivElement>(null)
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const sparks = useRef<Spark[]>([])
    const raf = useRef(0)
    const turnTimer = useRef(0)
    const [wink, setWink] = useState(0)

    const burst = useCallback(() => {
      playSparkBurst(4)
      const canvas = canvasRef.current
      if (!canvas) return
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      for (let i = 0; i < 26; i += 1) {
        const angle = Math.random() * Math.PI * 2
        const speed = 1.1 + Math.random() * 3.8
        sparks.current.push({
          x: width / 2,
          y: height * 0.56,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 0.7,
          life: 700 + Math.random() * 600,
          max: 1300,
          size: 0.9 + Math.random() * 2.4,
        })
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      cancelAnimationFrame(raf.current)
      let last = performance.now()
      const draw = (now: number) => {
        const dt = now - last
        last = now
        const dpr = Math.min(2, window.devicePixelRatio || 1)
        if (canvas.width !== Math.round(width * dpr)) {
          canvas.width = Math.round(width * dpr)
          canvas.height = Math.round(height * dpr)
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        }
        ctx.clearRect(0, 0, width, height)
        ctx.globalCompositeOperation = 'lighter'
        for (let i = sparks.current.length - 1; i >= 0; i -= 1) {
          const spark = sparks.current[i]
          if (!spark) continue
          spark.life -= dt
          if (spark.life <= 0) {
            sparks.current.splice(i, 1)
            continue
          }
          spark.x += spark.vx * (dt / 16.67)
          spark.y += spark.vy * (dt / 16.67)
          spark.vy += 0.012 * (dt / 16.67)
          const alpha = Math.max(0, spark.life / spark.max)
          ctx.fillStyle = `rgba(255, ${150 + Math.round(90 * alpha)}, 60, ${alpha})`
          ctx.beginPath()
          ctx.arc(spark.x, spark.y, spark.size, 0, Math.PI * 2)
          ctx.fill()
        }
        ctx.globalCompositeOperation = 'source-over'
        if (sparks.current.length > 0) raf.current = requestAnimationFrame(draw)
      }
      raf.current = requestAnimationFrame(draw)
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        turnTo(degrees: number) {
          rootRef.current?.style.setProperty('--companion-turn', `${degrees.toFixed(1)}deg`)
          playWingWhoosh(Math.max(-0.7, Math.min(0.7, degrees / 45)))
          window.clearTimeout(turnTimer.current)
          turnTimer.current = window.setTimeout(() => {
            rootRef.current?.style.setProperty('--companion-turn', '0deg')
          }, 900)
        },
        burst,
      }),
      [burst],
    )

    useEffect(() => {
      const root = rootRef.current
      if (!root || still) return
      const onMove = (event: PointerEvent) => {
        const rect = root.getBoundingClientRect()
        const dx = (event.clientX - (rect.left + rect.width / 2)) / Math.max(120, rect.width)
        const dy = (event.clientY - (rect.top + rect.height / 2)) / Math.max(120, rect.height)
        root.style.setProperty('--companion-look-x', `${Math.max(-1, Math.min(1, dx)).toFixed(2)}`)
        root.style.setProperty('--companion-look-y', `${Math.max(-1, Math.min(1, dy)).toFixed(2)}`)
      }
      window.addEventListener('pointermove', onMove)
      return () => window.removeEventListener('pointermove', onMove)
    }, [still])

    useEffect(() => () => cancelAnimationFrame(raf.current), [])

    const art = species === 'fire_bee' ? BEE_ART : MOTH_ART
    const showsActor = species === 'paper_moth' || species === 'fire_bee'

    return (
      <div
        ref={rootRef}
        data-testid={testId}
        data-species={species}
        className={`companion-actor is-${size}${still ? ' is-still' : ''}${flying ? ' is-flying' : ''} ${className}`}
        style={
          { '--companion-scale': Math.max(0.7, Math.min(1.4, scale / 100)) } as React.CSSProperties
        }
        aria-hidden="true"
      >
        {showsActor && (
          <div
            className="companion-turn"
            onClick={
              onActivate
                ? () => {
                    setWink((value) => value + 1)
                    onActivate()
                  }
                : undefined
            }
          >
            <span className="companion-glow" />
            <div className="companion-motion">
              <img className="companion-body" src={art.body} alt="" draggable={false} />
              <img
                className="companion-wing companion-wing-l"
                src={art.wingLeft}
                alt=""
                draggable={false}
              />
              <img
                className="companion-wing companion-wing-r"
                src={art.wingRight}
                alt=""
                draggable={false}
              />
              <img className="companion-flame" src={art.accent} alt="" draggable={false} />
              <BeeEyelids still={still} winkSignal={wink} />
            </div>
          </div>
        )}
        {species === 'ember_spark' && (
          <div
            className="companion-turn companion-spark"
            onClick={onActivate ? () => onActivate() : undefined}
          >
            <span className="companion-spark-halo" />
            <span className="companion-spark-core" />
            <span className="companion-spark-eyes">
              <i />
              <i />
            </span>
          </div>
        )}
        {species === 'minimal' && (
          <span className="companion-minimal">
            <EpheMark state="settle" size="2.4rem" testId="companion-mark" />
          </span>
        )}
        <canvas ref={canvasRef} className="companion-sparks" />
      </div>
    )
  },
)
