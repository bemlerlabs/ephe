/**
 * The scene a browser meets on its first load: the fire spirit's own arc.
 *
 * A sibling of the app in `main.tsx`: the surface the setup gate resolved is
 * mounted behind the overlay and stands there when the scene ends. Nothing here
 * waits on the backend, so a slow engine answer costs the scene nothing.
 *
 * The arc is eight named beats on one 600 ms unit: light gathers, the wall spreads
 * across the ground and surges, it falls as the being lands in its fierce read, the
 * being holds, turns to its calm read, leans in and leaves to the right. The sheet
 * carries the motion; this file carries the clock, and `data-beat` names the frame a
 * capture or a test is looking at.
 *
 * Held by tests: title and sentence inside the opening condense (480 / 720 ms), the
 * button at 1.2 s, the beats on their own clock, then `--ephe-decay-duration`
 * (380 ms) eats the overlay from the right. `prefers-reduced-motion` and
 * `appearance.animations_enabled` land on the still: every block visible, the being
 * in its calm read, no timer but the closing one.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { FireSpirit } from '@/components/shell/FireSpirit'
import type { SpiritRegister, SpiritState } from '@/components/shell/FireSpirit'
import { useDeepBool } from '@/lib/deepSettings'
import { hasSeenFirstRunIntro, markFirstRunIntroSeen } from '@/lib/firstRun'
import { readSetupGateHint } from '@/lib/setupGate'

/* The key of the install flag. Re-exported here so a test can name it through the scene,
   while the boot gate and the scene both read the one definition in `lib/firstRun`. */
export { INTRO_SEEN_KEY } from '@/lib/firstRun'

/* The scene clock in ms, mirrored from the tokens in app/src/styles/globals.css.
   The token-drift test reads the sheet and compares. */
export const CONDENSE_MS = 240 // --ephe-mark-condense-duration
export const WORK_PERIOD_MS = 2400 // --ephe-mark-work-period
export const DECAY_MS = 380 // --ephe-decay-duration
export const BEAT_MS = 600 // --ephe-scene-beat
export const TITLE_AT_MS = CONDENSE_MS * 2 // 480
export const LINE_AT_MS = CONDENSE_MS * 3 // 720
export const CTA_AT_MS = CONDENSE_MS * 5 // 1.2 s — the wait for interaction
export const SCENE_MS = BEAT_MS * 10 // 6.0 s — two and a half work periods, then the decay closes it
/** The reduced-motion hold: one breath of the still, then the overlay closes. */
export const STILL_MS = WORK_PERIOD_MS

/** The arc: what happens, and at which multiple of the beat it happens. */
export const BEATS = [
  { at: 0, beat: 'light' }, // an ember point gathers
  { at: BEAT_MS * 1, beat: 'wall' }, // the glow lies across the ground
  { at: BEAT_MS * 3, beat: 'surge' }, // the wall lifts and leans; the brightest frame
  { at: BEAT_MS * 4, beat: 'land' }, // the wall falls, the being lands in its fierce read
  { at: BEAT_MS * 5, beat: 'hold' }, // held: the light pinched to the eyes
  { at: BEAT_MS * 7, beat: 'turn' }, // the crossfade: the threat read becomes the trust read
  { at: BEAT_MS * 8, beat: 'lean' }, // it leans in, the glow evens out
  { at: BEAT_MS * 9, beat: 'lead' }, // it steps off to the right, the decay follows it
] as const

export type SceneBeat = (typeof BEATS)[number]['beat']

/** The being arrives as the threat and leaves as the companion; the turn is the swap. */
const REGISTER_AT: Record<SceneBeat, SpiritRegister> = {
  light: 'fierce',
  wall: 'fierce',
  surge: 'fierce',
  land: 'fierce',
  hold: 'fierce',
  turn: 'calm',
  lean: 'calm',
  lead: 'calm',
}

const STATE_AT: Record<SceneBeat, SpiritState> = {
  light: 'rest',
  wall: 'rest',
  surge: 'rest',
  land: 'land',
  hold: 'hold',
  turn: 'hold',
  lean: 'lean',
  lead: 'lead',
}

const TITLE_ID = 'first-run-intro-title'
const LINE_ID = 'first-run-intro-line'

export default function FirstRunIntro({ onDone }: { onDone?: () => void } = {}) {
  const systemReduced = useReducedMotion()
  // The product's own switch (I3-4): html.no-motion comes from the appearance setting,
  // and a viewer who turned animations off there wants the still as well.
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const still = Boolean(systemReduced) || !animationsEnabled
  const { t } = useTranslation()

  const [open, setOpen] = useState(() => !hasSeenFirstRunIntro())
  const [leaving, setLeaving] = useState(false)
  // The remembered gate answer is read once, before the app's own round trip lands, so
  // the closing sentence cannot swap under the viewer mid-scene. No stored answer means
  // a browser that has not decided yet, and for it the engine choice comes next.
  const [engineChosen] = useState(() => readSetupGateHint()?.configured === true)
  const [beat, setBeat] = useState<SceneBeat>('light')
  const overlayRef = useRef<HTMLDivElement>(null)
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

  // The scene clock. A still gets the short hold; the animated scene gets the full one.
  useEffect(() => {
    if (!open || leaving) return
    const id = window.setTimeout(exit, still ? STILL_MS : SCENE_MS)
    return () => window.clearTimeout(id)
  }, [open, leaving, still, exit])

  // The arc's own clock. It names the beat for captures and tests; the motion itself
  // lives in the sheet, so a beat that is late by a frame moves nothing on its own.
  useEffect(() => {
    if (!open || leaving || still) return
    const timers = BEATS.filter((entry) => entry.at > 0).map((entry) =>
      window.setTimeout(() => setBeat(entry.beat), entry.at),
    )
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [open, leaving, still])

  // Handover: the overlay stays mounted for the decay so its own exit motion is visible,
  // then it leaves the tree and the surface behind it is the app.
  useEffect(() => {
    if (!leaving) return
    const id = window.setTimeout(() => setOpen(false), DECAY_MS)
    return () => window.clearTimeout(id)
  }, [leaving])

  useEffect(() => {
    if (!open || leaving) return
    const onKey = (event: KeyboardEvent) => {
      // Tab stays inside the scene: the app behind the overlay must not take focus
      // where the viewer can not see it.
      if (event.key === 'Tab') {
        event.preventDefault()
        const controls = [skipRef.current, ctaRef.current].filter(Boolean) as HTMLElement[]
        if (controls.length === 0) return
        const at = controls.indexOf(document.activeElement as HTMLElement)
        const step = event.shiftKey ? -1 : 1
        controls[(at + step + controls.length) % controls.length]?.focus()
        return
      }
      exit()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', exit)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', exit)
    }
  }, [open, leaving, exit])

  // Focus lands on the dialog first; the skip control is reachable from there.
  // screen reader, the first Tab lands on the way out, and no control wears a focus ring
  // in the frame the viewer sees (Chromium paints one on a programmatic button focus,
  // measured in the capture pass).
  useEffect(() => {
    if (!open || leaving) return
    overlayRef.current?.focus()
  }, [open, leaving])

  if (!open) return null

  // Staging is one inline animation-delay per block on the sheet's own entrance rule
  // (`.ephe-condense`, fill-mode both). Every block sits in the DOM from frame one, so a
  // screen reader reads the whole scene at once and no focusable control is ever invisible
  // to the keyboard.
  const delay = (at: number) => ({ animationDelay: `${still ? 0 : at}ms` })

  return (
    <div
      ref={overlayRef}
      data-testid="first-run-intro"
      data-phase={leaving ? 'leaving' : 'running'}
      data-beat={still ? 'still' : beat}
      data-reduced={still ? 'true' : undefined}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      aria-labelledby={TITLE_ID}
      aria-describedby={LINE_ID}
      className={`ephe-scene fixed inset-0 z-modal flex flex-col items-center justify-center gap-6 bg-background px-6 text-center${
        leaving ? ' ephe-decay' : ''
      }`}
    >
      {/* The ground light of the arc: the wall that spreads and surges, the seam that
          stays as coals once it falls, and the embers it throws. Threat is scale and
          ground glow, never a face. */}
      <div className="ephe-scene-ground" aria-hidden="true" />
      <div className="ephe-scene-embers" aria-hidden="true" />
      <div className="ephe-scene-core" aria-hidden="true" />
      <div className="ephe-scene-flash" aria-hidden="true" />

      <button
        ref={skipRef}
        type="button"
        data-testid="intro-skip"
        onClick={exit}
        className="focus-ring absolute end-4 top-4 rounded border border-hairline px-3 py-1.5 text-ui-xs text-ink-soft transition-colors hover:text-foreground"
      >
        {t('welcome.introSkip')}
      </button>

      {/* The being that carries the arc: it lands in its fierce read, turns to the calm
          one at the turn beat, leans in and leaves to the right. Two wrappers, because the
          sheet gives each phase its own animation and one element holds one of each. */}
      <span className="ephe-scene-actor">
        <span className="ephe-scene-actor-leave">
          <FireSpirit
            register={still ? 'calm' : REGISTER_AT[beat]}
            state={still ? 'rest' : STATE_AT[beat]}
            size="clamp(8rem, 26vw, 12rem)"
            testId="intro-spirit"
          />
        </span>
      </span>

      <h1
        id={TITLE_ID}
        style={delay(TITLE_AT_MS)}
        className="ephe-condense text-ui-xl font-medium text-foreground"
      >
        {t('welcome.introTitle')}
      </h1>

      <p
        id={LINE_ID}
        style={delay(LINE_AT_MS)}
        className="ephe-condense max-w-sm text-ui-base text-ink-soft"
      >
        {engineChosen ? t('welcome.introLineReady') : t('welcome.introLine')}
      </p>

      <button
        ref={ctaRef}
        type="button"
        data-testid="intro-cta"
        onClick={exit}
        style={delay(CTA_AT_MS)}
        className="ephe-condense focus-ring rounded border border-hairline px-4 py-2 text-ui-sm font-medium text-foreground transition-colors hover:border-brand/50 hover:text-brand"
      >
        {t('welcome.introCta')}
      </button>

      <p style={delay(CTA_AT_MS)} className="ephe-condense text-ui-xs text-ink-faint">
        {t('welcome.introSkipHint')}
      </p>
    </div>
  )
}
