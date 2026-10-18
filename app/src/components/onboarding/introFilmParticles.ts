/**
 * The first-open film's particle layer: ambient dust, the moss answer, the gathered
 * fireflies, the ribbon, the tornado, the honeycomb shock and the awakened motes.
 *
 * One call paints every layer for a timestamp; the caller owns only the canvas size.
 */
import {
  AWAKEN_AT,
  CHASE_AT,
  GATHER_AT,
  IMPACT_MS,
  MORPH_AT,
  SHOCK_AT,
  VORTEX_AT,
  clamp,
  easeOutCubic,
  seeded,
  smooth,
  sparkAt,
} from './introFilmTimeline'

const AMBIENT = seeded(70, 0x51f15e)
const IMPACT = seeded(50, 0xb00)
const RIBBON = seeded(180, 0x7a11)
const TORNADO = seeded(320, 0xf17e)
const SHOCK = seeded(80, 0x5a0c)
const MOTES = seeded(70, 0x9e11)
const MOSS = seeded(26, 0x30f5)
const FIREFLIES = seeded(120, 0x1eaf)

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

export function paintIntroParticles(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  t: number,
) {
  const spark = sparkAt(t)
  const centerX = width * 0.5
  const centerY = height * 0.52

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
