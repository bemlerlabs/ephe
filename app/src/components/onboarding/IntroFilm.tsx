/**
 * The first-open film as one continuous 60 fps choreography: a spark falls into the
 * clearing, runs a spline through the forest, spins into a fire tornado and becomes the
 * bee that hovers in the awakening.
 *
 * The same component runs live in the intro and behind `?film=capture`, where
 * `__epheIntroSeek(ms)` renders an exact frame so `scripts/render_onboarding_film.py`
 * can capture the video at 60 fps. Every particle is a pure function of time, so a
 * seeked frame and a live frame are the same image.
 */
import './IntroFilm.css'
import { useEffect, useRef } from 'react'

export const FILM_MS = 12_800
const IMPACT_MS = 700
const CHASE_AT = 2200
const GATHER_AT = 5200
const VORTEX_AT = 6600
const AWAKEN_AT = 9400
const MORPH_AT = 7400
const WINGS_AT = 8000
const SHOCK_AT = 8000

/** The five camera setups. Returns 1-5 for a timestamp in ms. */
export function shotAt(t: number): 1 | 2 | 3 | 4 | 5 {
  if (t < CHASE_AT) return 1
  if (t < GATHER_AT) return 2
  if (t < VORTEX_AT) return 3
  if (t < AWAKEN_AT) return 4
  return 5
}

interface Seed {
  a: number
  b: number
  c: number
  d: number
}

interface PathPoint {
  t: number
  x: number
  y: number
}

const CHASE: PathPoint[] = [
  { t: 2200, x: 0.5, y: 0.62 },
  { t: 2600, x: 0.34, y: 0.68 },
  { t: 3000, x: 0.22, y: 0.7 },
  { t: 3300, x: 0.4, y: 0.6 },
  { t: 3600, x: 0.66, y: 0.55 },
  { t: 3900, x: 0.78, y: 0.54 },
  { t: 4200, x: 0.62, y: 0.62 },
  { t: 4550, x: 0.38, y: 0.68 },
  { t: 4800, x: 0.3, y: 0.66 },
  { t: 4950, x: 0.46, y: 0.58 },
  { t: 5200, x: 0.5, y: 0.5 },
]

const clamp = (value: number, low = 0, high = 1) => Math.min(high, Math.max(low, value))

const smooth = (from: number, to: number, value: number) => {
  const x = clamp((value - from) / (to - from))
  return x * x * (3 - 2 * x)
}

const easeOutCubic = (x: number) => 1 - (1 - clamp(x)) ** 3
const easeOutBack = (x: number) => {
  const c = 1.70158
  const p = clamp(x) - 1
  return 1 + (c + 1) * p ** 3 + c * p ** 2
}

function seeded(count: number, seed: number): Seed[] {
  let state = seed >>> 0
  const next = () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return Array.from({ length: count }, () => ({ a: next(), b: next(), c: next(), d: next() }))
}

const AMBIENT = seeded(70, 0x51f15e)
const IMPACT = seeded(50, 0xb00)
const RIBBON = seeded(180, 0x7a11)
const TORNADO = seeded(320, 0xf17e)
const SHOCK = seeded(80, 0x5a0c)
const MOTES = seeded(70, 0x9e11)
const MOSS = seeded(26, 0x30f5)
const FIREFLIES = seeded(120, 0x1eaf)

function catmull(p0: PathPoint, p1: PathPoint, p2: PathPoint, p3: PathPoint, u: number) {
  const u2 = u * u
  const u3 = u2 * u
  return {
    x:
      0.5 *
      (2 * p1.x +
        (-p0.x + p2.x) * u +
        (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * u2 +
        (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * u3),
    y:
      0.5 *
      (2 * p1.y +
        (-p0.y + p2.y) * u +
        (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * u2 +
        (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * u3),
  }
}

function chaseAt(t: number) {
  const first = CHASE[0]!
  if (t <= first.t) return { x: first.x, y: first.y }
  for (let i = 1; i < CHASE.length; i += 1) {
    const p1 = CHASE[i - 1]!
    const p2 = CHASE[i]!
    if (t <= p2.t) {
      const p0 = CHASE[Math.max(0, i - 2)]!
      const p3 = CHASE[Math.min(CHASE.length - 1, i + 1)]!
      const u = (t - p1.t) / (p2.t - p1.t)
      const point = catmull(p0, p1, p2, p3, u)
      return { x: clamp(point.x, 0.12, 0.88), y: clamp(point.y, 0.3, 0.78) }
    }
  }
  const last = CHASE[CHASE.length - 1]!
  return { x: last.x, y: last.y }
}

/** The spark's path in viewport fractions; null once the bee owns the frame. */
function sparkAt(t: number): { x: number; y: number } | null {
  if (t < IMPACT_MS) {
    const u = easeOutCubic(t / IMPACT_MS)
    const a = { x: 0.68, y: -0.05 }
    const b = { x: 0.82, y: 0.22 }
    const c = { x: 0.5, y: 0.62 }
    const v = 1 - u
    return {
      x: v * v * a.x + 2 * v * u * b.x + u * u * c.x,
      y: v * v * a.y + 2 * v * u * b.y + u * u * c.y,
    }
  }
  if (t < CHASE_AT) {
    const age = (t - IMPACT_MS) * 0.003
    return { x: 0.5 + Math.sin(age) * 0.012, y: 0.62 + Math.cos(age * 0.8) * 0.014 }
  }
  if (t < GATHER_AT) return chaseAt(t)
  if (t < VORTEX_AT) {
    // The spark brakes in front of the lens: a small breath, not a path.
    const age = (t - GATHER_AT) * 0.003
    return { x: 0.5 + Math.sin(age) * 0.008, y: 0.5 + Math.cos(age * 0.9) * 0.01 }
  }
  if (t < AWAKEN_AT) {
    const p = clamp((t - VORTEX_AT) / (AWAKEN_AT - VORTEX_AT))
    const radius = 0.19 * (1 - p * 0.93)
    const angle = (t - VORTEX_AT) * 0.018
    return {
      x: 0.5 + Math.cos(angle) * radius * 0.72,
      y: 0.52 - p * 0.2 + Math.sin(angle) * radius * 0.55,
    }
  }
  return null
}

function drawHex(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, alpha: number) {
  ctx.beginPath()
  for (let i = 0; i < 6; i += 1) {
    const a = (i / 6) * Math.PI * 2 + Math.PI / 6
    const px = x + Math.cos(a) * size
    const py = y + Math.sin(a) * size
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
  ctx.strokeStyle = `rgba(255, 200, 90, ${alpha})`
  ctx.lineWidth = 1.1
  ctx.stroke()
}

export default function IntroFilm({ capture = false }: { capture?: boolean }) {
  const stageRef = useRef<HTMLDivElement>(null)
  const cameraRef = useRef<HTMLDivElement>(null)
  const fogARef = useRef<HTMLDivElement>(null)
  const fogBRef = useRef<HTMLDivElement>(null)
  const lightRef = useRef<HTMLDivElement>(null)
  const sparkRef = useRef<HTMLDivElement>(null)
  const eyesRef = useRef<HTMLSpanElement>(null)
  const impactRef = useRef<HTMLDivElement>(null)
  const beeRef = useRef<HTMLDivElement>(null)
  const bokehRef = useRef<HTMLDivElement>(null)
  const wingLRef = useRef<HTMLImageElement>(null)
  const lidLRef = useRef<HTMLElement>(null)
  const lidRRef = useRef<HTMLElement>(null)
  const wingRRef = useRef<HTMLImageElement>(null)
  const flameRef = useRef<HTMLImageElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const pointer = useRef({ x: 0, y: 0 })

  useEffect(() => {
    if (capture) return
    const onMove = (event: PointerEvent) => {
      pointer.current = {
        x: (event.clientX / window.innerWidth - 0.5) * 2,
        y: (event.clientY / window.innerHeight - 0.5) * 2,
      }
    }
    window.addEventListener('pointermove', onMove)
    return () => window.removeEventListener('pointermove', onMove)
  }, [capture])

  useEffect(() => {
    const stage = stageRef.current
    const canvas = canvasRef.current
    if (!stage || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let width = 0
    let height = 0
    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      width = stage.clientWidth
      height = stage.clientHeight
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const set = (node: HTMLElement | null, key: string, value: string) => {
      node?.style.setProperty(key, value)
    }

    const render = (t: number) => {
      if (!width || !height) resize()
      const progress = clamp(t / FILM_MS)
      const spark = sparkAt(t)
      const centerX = width * 0.5
      const centerY = height * 0.52

      // Five camera setups cut on the film's own clock. Each shot owns its scale,
      // its origin and its pan; the forest rides the camera, the bee never does.
      const shot = shotAt(t)
      stage.dataset.shot = String(shot)
      const beat = (center: number) => Math.exp(-(((t - center) / 85) ** 2))
      let scale = 1.06
      const originX = '50%'
      let originY = '55%'
      let panX = 0
      let panY = 0
      let blur = 0
      let dim = 1
      if (shot === 1) {
        scale = 1.045 + progress * 0.02
        panX = Math.sin(t * 0.00021) * 9 - progress * 6
        panY = -progress * 8
      } else if (shot === 2) {
        const tracking = chaseAt(t).x - 0.5
        scale = 1.24
        originY = '72%'
        panX = -tracking * width * 0.42
        panY = -height * 0.035
      } else if (shot === 3) {
        const pulse = beat(5600) + beat(6120)
        scale = 1.34 + pulse * 0.035
        originY = '52%'
        panY = -height * 0.012
      } else if (shot === 4) {
        scale = 1.28 - smooth(VORTEX_AT, AWAKEN_AT, t) * 0.2
        originY = '50%'
        panX = Math.sin(t * 0.0006) * 6
      } else {
        scale = 1.06 + Math.sin((t - AWAKEN_AT) * 0.0004) * 0.008
        originY = '52%'
        panY = -height * 0.01
        blur = smooth(AWAKEN_AT, AWAKEN_AT + 420, t) * 3.5
        dim = 1 - smooth(AWAKEN_AT, AWAKEN_AT + 420, t) * 0.25
      }
      set(cameraRef.current, 'transform-origin', `${originX} ${originY}`)
      set(cameraRef.current, 'transform', `translate3d(${panX}px, ${panY}px, 0) scale(${scale})`)
      set(cameraRef.current, 'filter', `blur(${blur.toFixed(2)}px) brightness(${dim.toFixed(3)})`)
      set(bokehRef.current, 'opacity', `${shot === 5 ? smooth(AWAKEN_AT, AWAKEN_AT + 500, t) : 0}`)
      set(
        fogARef.current,
        'transform',
        `translate3d(${Math.sin(t * 0.00013) * 46}px, ${Math.sin(t * 0.00021) * 8}px, 0)`,
      )
      set(
        fogBRef.current,
        'transform',
        `translate3d(${Math.cos(t * 0.00009) * 62}px, ${Math.cos(t * 0.00017) * 12}px, 0)`,
      )

      // The ground light follows the spark exactly.
      if (spark) {
        const sx = spark.x * width
        const sy = spark.y * height
        set(lightRef.current, 'left', `${sx}px`)
        set(lightRef.current, 'top', `${height * 0.8}px`)
        set(lightRef.current, 'opacity', `${0.35 + (1 - clamp(spark.y, 0.2, 0.9)) * 0.6}`)
        set(sparkRef.current, 'left', `${sx}px`)
        set(sparkRef.current, 'top', `${sy}px`)
        const life = t < MORPH_AT ? 1 : 1 - smooth(MORPH_AT, MORPH_AT + 500, t)
        set(sparkRef.current, 'opacity', `${life}`)
        const pulse = beat(5600) + beat(6120)
        const scale =
          t < IMPACT_MS ? 0.7 + 0.5 * (t / IMPACT_MS) : 1 + Math.sin(t * 0.02) * 0.08 + pulse * 0.55
        set(sparkRef.current, 'transform', `translate(-50%, -50%) scale(${scale})`)
        const eyeAlpha =
          smooth(CHASE_AT, CHASE_AT + 250, t) * (1 - smooth(MORPH_AT - 300, MORPH_AT, t))
        set(eyesRef.current, 'opacity', `${0.92 * eyeAlpha}`)
      }

      // Act 1's impact: an expanding ring on the moss.
      const impactAge = t - IMPACT_MS
      if (impactAge >= 0 && impactAge < 820) {
        const u = impactAge / 820
        set(impactRef.current, 'opacity', `${(1 - u) * 0.9}`)
        set(
          impactRef.current,
          'transform',
          `translate(-50%, -50%) scale(${0.25 + easeOutCubic(u) * 1.9})`,
        )
      } else {
        set(impactRef.current, 'opacity', '0')
      }

      // The bee: born out of the fire, then alive.
      const born = t - MORPH_AT
      if (born < 0) {
        set(beeRef.current, 'opacity', '0')
      } else {
        const appear = smooth(0, 260, born)
        const grow = easeOutBack(clamp(born / 640))
        const settle = smooth(WINGS_AT, AWAKEN_AT, t)
        const hovered = Math.max(0, t - AWAKEN_AT)
        const breathe = Math.sin(hovered * 0.0018) * 8
        const lean = capture ? Math.sin(t * 0.0011) * 2.2 : pointer.current.x * 3.4
        const tilt = capture ? Math.cos(t * 0.0013) * 1.4 : pointer.current.y * 2.2
        const hover = t > AWAKEN_AT ? 1 + Math.sin(hovered * 0.0016) * 0.014 : 1
        const scale = (born < 640 ? 0.25 + (1.08 - 0.25) * grow : 1.08 - 0.08 * settle) * hover
        set(beeRef.current, 'opacity', `${appear}`)
        set(
          beeRef.current,
          'transform',
          `translate(-50%, -50%) translate3d(${lean}px, ${breathe}px, 0) rotateX(${tilt}deg) rotateZ(${lean * 0.6}deg) scale(${scale})`,
        )
        const brightness = 4.2 - 3.2 * settle
        const sepia = 1 - settle
        const saturate = 4 - 3 * settle
        const glow = 44 - 32 * settle
        const blur = (1 - settle) * 1.6
        set(
          beeRef.current,
          'filter',
          `brightness(${brightness.toFixed(3)}) sepia(${sepia.toFixed(3)}) saturate(${saturate.toFixed(3)}) blur(${blur.toFixed(2)}px) drop-shadow(0 0 ${glow.toFixed(1)}px rgba(255, 191, 71, ${(0.85 - 0.45 * settle).toFixed(3)}))`,
        )
        const open = smooth(WINGS_AT, WINGS_AT + 420, t)
        const flap = 0.5 + 0.5 * Math.sin(t * 0.045)
        const foldY = 74
        const foldZ = 26
        const flapY = 8 + 28 * flap
        const flapZ = 2 + 3 * flap
        const yL = (1 - open) * foldY + open * flapY
        const yR = -((1 - open) * foldY + open * flapY)
        const zL = -(1 - open) * foldZ + open * flapZ
        const zR = (1 - open) * foldZ - open * flapZ
        const wingAlpha = smooth(WINGS_AT - 120, WINGS_AT + 90, t)
        set(wingLRef.current, 'opacity', `${wingAlpha}`)
        set(wingRRef.current, 'opacity', `${wingAlpha}`)
        set(
          wingLRef.current,
          'transform',
          `rotateY(${yL.toFixed(2)}deg) rotateZ(${zL.toFixed(2)}deg)`,
        )
        set(
          wingRRef.current,
          'transform',
          `rotateY(${yR.toFixed(2)}deg) rotateZ(${zR.toFixed(2)}deg)`,
        )
        const blink =
          (t > 10050 && t < 10200) || (t > 11400 && t < 11550) || (t > 12300 && t < 12450)
        const wink = t > 10700 && t < 10940
        set(lidLRef.current, 'transform', `translate(-50%, 0) scaleY(${blink || wink ? 1 : 0})`)
        set(lidRRef.current, 'transform', `translate(-50%, 0) scaleY(${blink ? 1 : 0})`)
        if (capture) {
          set(flameRef.current, 'animationPlayState', 'paused')
          set(flameRef.current, 'animationDelay', `${-t}ms`)
        }
      }

      // Canvas: the ribbon, the tornado, the shockwave and the embers.
      ctx.clearRect(0, 0, width, height)
      ctx.globalCompositeOperation = 'lighter'

      const waterline = height * 0.74

      // Ambient red-gold dust that never stops drifting.
      for (const seed of AMBIENT) {
        const speed = 0.006 + seed.a * 0.014
        const y = height * (1.02 - ((seed.b * height + t * speed) % (height * 1.06)) / height)
        const x = seed.c * width + Math.sin(t * 0.0007 + seed.d * 9) * 12
        const alpha = 0.18 + seed.d * 0.3
        ctx.fillStyle = `rgba(255, ${170 + Math.round(seed.a * 60)}, 90, ${alpha})`
        ctx.beginPath()
        ctx.arc(x, y, 0.7 + seed.b * 1.5, 0, Math.PI * 2)
        ctx.fill()
      }

      // The moss answers the spark's proximity.
      if (spark) {
        for (const seed of MOSS) {
          const mx = (0.08 + seed.a * 0.84) * width
          const my = (0.64 + seed.b * 0.2) * height
          const dx = (spark.x - 0.08 - seed.a * 0.84) * 1.4
          const dy = (spark.y - 0.64 - seed.b * 0.2) * 1.7
          const near = Math.exp(-(dx * dx + dy * dy) * 42)
          if (near < 0.06) continue
          ctx.fillStyle = `rgba(190, 255, 210, ${near * 0.55})`
          ctx.beginPath()
          ctx.arc(mx, my, 1.4 + near * 2.6, 0, Math.PI * 2)
          ctx.fill()
          ctx.fillStyle = `rgba(255, 220, 130, ${near * 0.42})`
          ctx.beginPath()
          ctx.arc(mx, my, 3.4 + near * 5, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      // Shot 3: the clearing's fireflies spiral into the spark's core.
      if (t >= GATHER_AT && t < VORTEX_AT + 300) {
        const gather = clamp((t - GATHER_AT) / (VORTEX_AT - GATHER_AT))
        const fade = 1 - smooth(VORTEX_AT - 200, VORTEX_AT + 300, t)
        for (const seed of FIREFLIES) {
          const angle = seed.a * Math.PI * 2 + gather * (4 + seed.b * 3)
          const radius = Math.min(width, height) * (0.06 + seed.c * 0.24) * (1 - gather * 0.96)
          const x = centerX + Math.cos(angle) * radius * 1.25
          const y = centerY + Math.sin(angle) * radius * 0.85
          const alpha = (0.22 + seed.d * 0.5) * fade
          ctx.fillStyle = `rgba(${170 + Math.round(seed.b * 60)}, 255, ${150 + Math.round(seed.c * 70)}, ${alpha * 0.7})`
          ctx.beginPath()
          ctx.arc(x, y, 1 + seed.d * 1.8, 0, Math.PI * 2)
          ctx.fill()
          ctx.fillStyle = `rgba(255, 232, 150, ${alpha * 0.55})`
          ctx.beginPath()
          ctx.arc(x, y, 2.2 + seed.a * 2.4, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      // The living spark: a soft flame body over the DOM core.
      if (spark) {
        const sx = spark.x * width
        const sy = spark.y * height
        if (t > IMPACT_MS && t < MORPH_AT) {
          for (let i = 0; i < 7; i += 1) {
            const wobble = Math.sin(t * 0.02 + i * 1.9) * (3 + i)
            const rise = i * 2.1
            ctx.fillStyle = `rgba(255, ${180 + i * 8}, 70, ${0.22 - i * 0.018})`
            ctx.beginPath()
            ctx.arc(sx + wobble, sy - rise, 6 + i * 1.6, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      }

      // The ribbon: 180 additive flame particles along the last 1.6 s of the path.
      if (t > CHASE_AT + 80 && t < AWAKEN_AT + 240) {
        const fadeOut = 1 - smooth(AWAKEN_AT - 400, AWAKEN_AT + 240, t)
        for (let i = 0; i < RIBBON.length; i += 1) {
          const seed = RIBBON[i]!
          const past = sparkAt(t - i * 9)
          if (!past) continue
          const life = 1 - i / RIBBON.length
          const jitterX = (seed.a - 0.5) * (6 + i * 0.14)
          const jitterY = (seed.b - 0.5) * (5 + i * 0.1)
          const x = past.x * width + jitterX
          const y = past.y * height + jitterY
          const alpha = life * 0.46 * fadeOut
          ctx.fillStyle = `rgba(255, ${150 + Math.round(seed.c * 70)}, ${50 + Math.round(seed.d * 40)}, ${alpha})`
          ctx.beginPath()
          ctx.arc(x, y, 1 + life * 3.1, 0, Math.PI * 2)
          ctx.fill()
          if (y < waterline) {
            const mirror = waterline + (waterline - y) * 0.92
            ctx.fillStyle = `rgba(255, 180, 80, ${alpha * 0.2})`
            ctx.beginPath()
            ctx.arc(x + Math.sin(t * 0.002 + i) * 3, mirror, 1.6 + life * 4.2, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      }

      // The fire tornado: a shrinking helix of three hundred embers.
      if (t >= VORTEX_AT && t < AWAKEN_AT + 500) {
        const p = clamp((t - VORTEX_AT) / (AWAKEN_AT - VORTEX_AT))
        const fade = 1 - smooth(AWAKEN_AT - 200, AWAKEN_AT + 500, t)
        ctx.save()
        ctx.translate(centerX, height * 0.5)
        ctx.scale(0.32, 1)
        const core = ctx.createRadialGradient(0, 0, 0, 0, 0, height * 0.46)
        core.addColorStop(0, `rgba(255, 196, 100, ${0.3 * fade})`)
        core.addColorStop(0.45, `rgba(255, 130, 35, ${0.16 * fade})`)
        core.addColorStop(1, 'rgba(255, 90, 10, 0)')
        ctx.fillStyle = core
        ctx.fillRect(-width, -height, width * 2, height * 2)
        ctx.restore()
        for (let i = 0; i < TORNADO.length; i += 1) {
          const seed = TORNADO[i]!
          const life = (i / TORNADO.length + p * 1.55 + seed.a * 0.05) % 1
          const angle = (t - VORTEX_AT) * 0.016 + life * 7.2 + seed.b * 0.7
          const funnel = 0.055 + (1 - life) * 0.34
          const radius =
            Math.min(width, height) * funnel * (0.62 + seed.c * 0.38) * (0.55 + (1 - p) * 0.45)
          const x = centerX + Math.cos(angle) * radius
          const y = height * 0.7 - life * height * 0.4 - p * height * 0.05
          const alpha = (0.16 + seed.d * 0.42) * fade * (0.35 + (1 - life) * 0.65)
          ctx.fillStyle = `rgba(255, ${150 + Math.round(seed.a * 80)}, ${40 + Math.round(seed.c * 40)}, ${alpha})`
          ctx.beginPath()
          ctx.arc(x, y, 0.9 + seed.d * 3.4, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      // The wings' opening throws 80 honeycomb sparks through the vortex.
      const shockAge = t - SHOCK_AT
      if (shockAge >= 0 && shockAge < 1000) {
        const u = shockAge / 1000
        for (let i = 0; i < SHOCK.length; i += 1) {
          const seed = SHOCK[i]!
          const angle = (i / SHOCK.length) * Math.PI * 2 + seed.a * 0.2
          const distance =
            Math.min(width, height) * (0.04 + easeOutCubic(u) * 0.36) * (0.75 + seed.b * 0.5)
          const x = centerX + Math.cos(angle) * distance
          const y = centerY + Math.sin(angle) * distance * 0.72
          drawHex(ctx, x, y, 2.2 + seed.c * 3.4, (1 - u) * (0.5 + seed.d * 0.4))
        }
      }

      // Impact embers: fifty glows off the floor at 0.7 s.
      if (t > IMPACT_MS && t < IMPACT_MS + 2400) {
        for (let i = 0; i < IMPACT.length; i += 1) {
          const seed = IMPACT[i]!
          const age = t - IMPACT_MS - seed.a * 220
          if (age <= 0) continue
          const seconds = age / 1000
          const x = width * (0.5 + (seed.b - 0.5) * 0.34 * seconds)
          const y = height * (0.62 - (0.2 + seed.c * 0.5) * seconds + 0.22 * seconds * seconds)
          const alpha = Math.max(0, 1 - age / 2200) * 0.8
          ctx.fillStyle = `rgba(255, ${170 + Math.round(seed.d * 70)}, 70, ${alpha})`
          ctx.beginPath()
          ctx.arc(x, y, 1 + seed.d * 2.2, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      // The awakened bee's own rising motes.
      if (t > AWAKEN_AT) {
        const fadeIn = smooth(AWAKEN_AT, AWAKEN_AT + 600, t)
        for (const seed of MOTES) {
          const cycle = (t * 0.00006 + seed.a) % 1
          const x = width * (0.32 + seed.b * 0.36) + Math.sin(t * 0.0012 + seed.c * 8) * 18
          const y = height * (0.88 - cycle * 0.55)
          const alpha = fadeIn * (0.25 + seed.d * 0.45) * (1 - cycle * 0.5)
          ctx.fillStyle = `rgba(255, ${185 + Math.round(seed.c * 50)}, 90, ${alpha})`
          ctx.beginPath()
          ctx.arc(x, y, 0.8 + seed.d * 2, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      ctx.globalCompositeOperation = 'source-over'
    }

    if (capture) {
      render(0)
      const host = window as unknown as { __epheIntroSeek?: (ms: number) => void }
      host.__epheIntroSeek = (ms: number) => render(clamp(ms, 0, FILM_MS))
      return () => {
        delete host.__epheIntroSeek
        window.removeEventListener('resize', resize)
      }
    }

    let frame = 0
    const start = performance.now()
    const loop = (now: number) => {
      render((now - start) % FILM_MS)
      frame = requestAnimationFrame(loop)
    }
    frame = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
    }
  }, [capture])

  return (
    <div
      ref={stageRef}
      data-testid={capture ? 'intro-film-capture' : 'intro-film'}
      className="intro-media intro-live-stage"
      aria-hidden="true"
    >
      <div ref={cameraRef} className="intro-live-camera">
        <img
          className="intro-live-forest"
          src="/onboarding/scene-1-ignition.jpg"
          alt=""
          draggable={false}
        />
        <div className="intro-live-rays" />
        <div ref={fogARef} className="intro-live-fog intro-live-fog-a" />
        <div ref={fogBRef} className="intro-live-fog intro-live-fog-b" />
        <div ref={lightRef} className="intro-live-ground-light" />
      </div>
      <div ref={impactRef} className="intro-live-impact" />
      <div ref={sparkRef} className="intro-live-spark">
        <span className="intro-live-spark-halo" />
        <span className="intro-live-spark-core" />
        <span ref={eyesRef} className="intro-live-spark-eyes">
          <i />
          <i />
        </span>
      </div>
      <div ref={bokehRef} className="intro-live-bokeh" />
      <div ref={beeRef} className="intro-live-bee">
        <img
          className="intro-live-bee-body"
          src="/onboarding/bee-3d-actor.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={wingLRef}
          className="intro-live-wing intro-live-wing-l"
          src="/onboarding/bee-3d-wing-l.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={wingRRef}
          className="intro-live-wing intro-live-wing-r"
          src="/onboarding/bee-3d-wing-r.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={flameRef}
          className="intro-live-flame"
          src="/onboarding/bee-3d-flame.webp"
          alt=""
          draggable={false}
        />
        <span className="intro-live-lids" aria-hidden="true">
          <i ref={lidLRef} />
          <i ref={lidRRef} />
        </span>
      </div>
      <canvas ref={canvasRef} className="intro-sparks intro-live-particles" aria-hidden="true" />
      <div className="intro-vignette intro-live-vignette" aria-hidden="true" />
    </div>
  )
}
