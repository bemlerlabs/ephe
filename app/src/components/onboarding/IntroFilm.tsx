/**
 * The first-open film as one continuous 60 fps choreography: a spark falls into the
 * clearing, runs a spline through the forest, spins into a fire tornado and unfolds into
 * the paper moth that hovers in the awakening. The four figure layers are the moth's
 * (left wing, right wing, body, crimson thread), cut from one master.
 *
 * The same component runs live in the intro and behind `?film=capture`, where
 * `__epheIntroSeek(ms)` renders an exact frame so `scripts/render_onboarding_film.py`
 * can capture the video at 60 fps. Every particle is a pure function of time, so a
 * seeked frame and a live frame are the same image.
 */
import './IntroFilm.css'
import { useEffect, useRef } from 'react'
import { paintIntroParticles } from './introFilmParticles'
import {
  AWAKEN_AT,
  CHASE_AT,
  FILM_MS,
  IMPACT_MS,
  MORPH_AT,
  VORTEX_AT,
  WINGS_AT,
  chaseAt,
  clamp,
  easeOutBack,
  easeOutCubic,
  shotAt,
  smooth,
  sparkAt,
} from './introFilmTimeline'

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

      paintIntroParticles(ctx, width, height, t)
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
          src="/onboarding/paper-moth-actor.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={wingLRef}
          className="intro-live-wing intro-live-wing-l"
          src="/onboarding/paper-moth-wing-l.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={wingRRef}
          className="intro-live-wing intro-live-wing-r"
          src="/onboarding/paper-moth-wing-r.webp"
          alt=""
          draggable={false}
        />
        <img
          ref={flameRef}
          className="intro-live-flame"
          src="/onboarding/paper-moth-thread.webp"
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
