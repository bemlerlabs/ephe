/**
 * The first open: the 12.8-second Black Forest film — a spark falls into the clearing,
 * runs a spline over the stream, spins into a fire tornado and becomes the bee that
 * hovers in the awakening; the title and the way in appear with her.
 *
 * The scene is a live 60 fps choreography (`IntroFilm`), not a cut of stills: the same
 * component is captured by `scripts/render_onboarding_film.py` into
 * `first-run-film.mp4/webm`. A click on the stage throws sparks and never ends the
 * scene. The film ends on its clock, the skip control, the CTA, or Escape/Enter/Space;
 * reduced motion and the animations switch land on the awakened still.
 */
import './FirstRunIntro.css'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { useDeepBool } from '@/lib/deepSettings'
import { hasSeenFirstRunIntro, markFirstRunIntroSeen } from '@/lib/firstRun'
import { readSetupGateHint } from '@/lib/setupGate'
import IntroFilm from './IntroFilm'
import { PaperMoth } from '@/components/brand/PaperMoth'

export { INTRO_SEEN_KEY } from '@/lib/firstRun'

export const CONDENSE_MS = 240
export const WORK_PERIOD_MS = 2400
export const DECAY_MS = 380
export const BEAT_MS = 600
/** The copy arrives with the awakening, 9.4 s into the film. */
export const TITLE_AT_MS = 9400
export const LINE_AT_MS = 9700
export const CTA_AT_MS = 10000
export const SCENE_MS = 12_800
export const STILL_MS = WORK_PERIOD_MS

/** The four acts and where each begins; the film itself runs on the same clock. */
export const ACTS = [
  { at: 0, act: 'ignition' },
  { at: 2200, act: 'chase' },
  { at: 6600, act: 'vortex' },
  { at: 9400, act: 'awakening' },
] as const

export type SceneAct = (typeof ACTS)[number]['act']

const TITLE_ID = 'first-run-intro-title'
const LINE_ID = 'first-run-intro-line'

interface Spark {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  max: number
  size: number
}

export default function FirstRunIntro({ onDone }: { onDone?: () => void } = {}) {
  const systemReduced = useReducedMotion()
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const still = Boolean(systemReduced) || !animationsEnabled
  const { t } = useTranslation()

  const [open, setOpen] = useState(() => !hasSeenFirstRunIntro())
  const [leaving, setLeaving] = useState(false)
  const [engineChosen] = useState(() => readSetupGateHint()?.configured === true)
  const [act, setAct] = useState<SceneAct>(still ? 'awakening' : 'ignition')
  const overlayRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const skipRef = useRef<HTMLButtonElement>(null)
  const ctaRef = useRef<HTMLButtonElement>(null)
  const settled = useRef(false)

  const exit = useCallback(() => {
    if (settled.current) return
    settled.current = true
    markFirstRunIntroSeen(String(Date.now()))
    onDone?.()
    if (still) setOpen(false)
    else setLeaving(true)
  }, [onDone, still])

  useEffect(() => {
    if (!open || leaving) return
    const id = window.setTimeout(exit, still ? STILL_MS : SCENE_MS)
    return () => window.clearTimeout(id)
  }, [open, leaving, still, exit])

  useEffect(() => {
    if (!open || leaving || still) return
    const timers = ACTS.filter((entry) => entry.at > 0).map((entry) =>
      window.setTimeout(() => setAct(entry.act), entry.at),
    )
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [open, leaving, still])

  // A click on the stage: a small shower of gold sparks at the pointer. It never
  // ends the film — the only exits are named in the header and the copy.
  const sparks = useRef<Spark[]>([])
  const showerAt = useCallback((x: number, y: number) => {
    for (let i = 0; i < 18; i += 1) {
      const a = Math.random() * Math.PI * 2
      const v = 0.8 + Math.random() * 3.2
      sparks.current.push({
        x,
        y,
        vx: Math.cos(a) * v,
        vy: Math.sin(a) * v - 0.6,
        life: 700 + Math.random() * 500,
        max: 1200,
        size: 0.8 + Math.random() * 2,
      })
    }
    const canvas = canvasRef.current
    if (!canvas || !canvas.getContext) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    if (canvas.width !== Math.round(canvas.clientWidth * dpr)) {
      canvas.width = Math.round(canvas.clientWidth * dpr)
      canvas.height = Math.round(canvas.clientHeight * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    let last = performance.now()
    const draw = (now: number) => {
      const dt = now - last
      last = now
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
        p.vy += 0.012 * (dt / 16.67)
        const alpha = Math.max(0, p.life / p.max)
        ctx.fillStyle = `rgba(255, ${150 + Math.round(90 * alpha)}, 60, ${alpha})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalCompositeOperation = 'source-over'
      if (sparks.current.length > 0) requestAnimationFrame(draw)
    }
    requestAnimationFrame(draw)
  }, [])

  const onClickStage = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const rect = event.currentTarget.getBoundingClientRect()
      showerAt(event.clientX - rect.left, event.clientY - rect.top)
    },
    [showerAt],
  )

  useEffect(() => {
    if (!open || leaving) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Tab') {
        event.preventDefault()
        const controls = [skipRef.current, ctaRef.current].filter(Boolean) as HTMLElement[]
        if (controls.length === 0) return
        const at = controls.indexOf(document.activeElement as HTMLElement)
        const step = event.shiftKey ? -1 : 1
        controls[(at + step + controls.length) % controls.length]?.focus()
        return
      }
      if (['Escape', 'Enter', ' '].includes(event.key)) {
        event.preventDefault()
        exit()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, leaving, exit])

  useEffect(() => {
    if (!open || leaving) return
    overlayRef.current?.focus()
  }, [open, leaving])

  useEffect(() => {
    if (!leaving) return
    const id = window.setTimeout(() => setOpen(false), DECAY_MS)
    return () => window.clearTimeout(id)
  }, [leaving])

  if (!open) return null

  const shown = still ? 'awakening' : act
  const textIn = still || shown === 'awakening'
  const delay = (at: number) => ({ animationDelay: `${still ? 0 : at}ms` })

  return (
    <div
      ref={overlayRef}
      data-testid="first-run-intro"
      data-phase={leaving ? 'leaving' : 'running'}
      data-act={shown}
      data-beat={still ? 'still' : shown}
      data-reduced={still ? 'true' : undefined}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      aria-labelledby={TITLE_ID}
      aria-describedby={LINE_ID}
      onPointerDown={onClickStage}
      className={`intro-stage${leaving ? ' intro-decay' : ''}${still ? ' is-still' : ''}`}
    >
      {still ? (
        <div className="intro-still" aria-hidden="true">
          <PaperMoth state="ready" size="clamp(9rem, 20vw, 15rem)" testId="intro-still-moth" />
        </div>
      ) : (
        <IntroFilm />
      )}
      <div className="intro-vignette" aria-hidden="true" />

      <button
        ref={skipRef}
        type="button"
        data-testid="intro-skip"
        onClick={exit}
        className="intro-skip focus-ring"
      >
        {t('welcome.introSkip')}
      </button>

      <canvas ref={canvasRef} className="intro-sparks" aria-hidden="true" />

      <div className={`intro-copy${textIn ? ' is-in' : ''}`}>
        <h1 id={TITLE_ID} style={delay(TITLE_AT_MS)} className="intro-title font-display">
          {t('welcome.introTitle')}
        </h1>
        <p id={LINE_ID} style={delay(LINE_AT_MS)} className="intro-line">
          {engineChosen ? t('welcome.introLineReady') : t('welcome.introLine')}
        </p>
        <button
          ref={ctaRef}
          type="button"
          data-testid="intro-cta"
          onClick={exit}
          style={delay(CTA_AT_MS)}
          className="intro-cta focus-ring"
        >
          {t('welcome.introCta')}
        </button>
        <p style={delay(CTA_AT_MS)} className="intro-hint">
          {t('welcome.introSkipHint')}
        </p>
      </div>
    </div>
  )
}
