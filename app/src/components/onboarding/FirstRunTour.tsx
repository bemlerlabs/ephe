'use client'

/**
 * The first open after the six-second scene: four questions, then the desk.
 *
 * The greeting and the desk frame the questions; the bee is the guide. The
 * answers land in the device marker (`/api/tour`), not in the browser: the PWA
 * and the desktop app must agree on whether the tour has been walked. The engine
 * question hands off to the shipped setup card instead of re-implementing it; the
 * tour resumes at the activation stop when that page reloads.
 */
import './FirstRunTour.css'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { Code2, FileText, Layers, Loader2, Search, ShieldCheck } from 'lucide-react'
import { useDeepBool } from '@/lib/deepSettings'
import { InteractiveBeeGuide, type BeeGuideHandle } from './InteractiveBeeGuide'
import {
  gateSnapshot,
  loadSetupGate,
  markSetupIntent,
  skipSetupGate,
  subscribeGate,
} from '@/lib/setupGate'
import {
  disableSkill,
  enableSkill,
  getPlugins,
  getSettings,
  listSkills,
  saveSections,
  setPluginEnabled,
} from '@/lib/api'
import { apiUrl } from '@/lib/api/http'
import {
  loadTourMarker,
  shouldOpenTour,
  tourForceFromUrl,
  writeTourMarker,
  TOUR_DESK_STEP,
  TOUR_QUESTION_COUNT,
  TOUR_VERSION,
  type TourActivate,
  type TourAnswers,
  type TourCarry,
  type TourMarker,
  type TourUsage,
} from '@/lib/firstRunTour'

const USAGE_OPTIONS: { value: TourUsage; key: string; icon: typeof Code2 }[] = [
  { value: 'code', key: 'tour.usage.code', icon: Code2 },
  { value: 'research', key: 'tour.usage.research', icon: Search },
  { value: 'documents', key: 'tour.usage.documents', icon: FileText },
  { value: 'mix', key: 'tour.usage.mix', icon: Layers },
]

interface EngineView {
  model?: string
  endpoint?: string
}

interface ImportSummary {
  skills: number
  servers: number
  persona: boolean
}

function emptyMarker(): TourMarker {
  return {
    version: TOUR_VERSION,
    step: 0,
    walked: false,
    skipped: false,
    answers: {},
    exists: false,
  }
}

function isDesktop(): boolean {
  return Boolean(
    (window as { __TAURI__?: { core?: { invoke?: unknown } } }).__TAURI__?.core?.invoke,
  )
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
  testId,
  disabled = false,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  hint: string
  testId: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      data-testid={testId}
      onClick={() => onChange(!checked)}
      className="tour-switch-row focus-ring"
    >
      <span className="min-w-0">
        <span className="block text-scale-ui text-foreground">{label}</span>
        <span className="mt-0.5 block text-scale-ui text-ink-faint">{hint}</span>
      </span>
      <span className={`tour-switch${checked ? ' is-on' : ''}`} aria-hidden="true">
        <span className="tour-switch-thumb" />
      </span>
    </button>
  )
}

export default function FirstRunTour() {
  const { t } = useTranslation()
  const gate = useSyncExternalStore(subscribeGate, gateSnapshot)
  const systemReduced = useReducedMotion()
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const still = Boolean(systemReduced) || !animationsEnabled
  const force = useRef(tourForceFromUrl()).current

  const [marker, setMarker] = useState<TourMarker | null>(null)
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<TourAnswers>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [engine, setEngine] = useState<EngineView | null>(null)
  const [engineLoading, setEngineLoading] = useState(false)
  const [activate, setActivate] = useState<TourActivate>({ memory: true, skills: true, web: false })
  const [activateStart, setActivateStart] = useState<TourActivate | null>(null)
  const [activateReady, setActivateReady] = useState(false)
  const [imported, setImported] = useState<ImportSummary | null>(null)
  const [carry, setCarry] = useState<TourCarry | null>(null)
  const [sparked, setSparked] = useState(false)
  const [finale, setFinale] = useState(false)
  const [guardPreview, setGuardPreview] = useState(false)

  const dialogRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const beeRef = useRef<BeeGuideHandle>(null)
  const booted = useRef(false)

  useEffect(() => {
    void loadSetupGate()
    let alive = true
    void loadTourMarker().then((m) => {
      if (alive) setMarker(m)
    })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (booted.current || !marker) return
    if (!shouldOpenTour(marker, gate, force)) {
      if (gate.ready || force) booted.current = true
      return
    }
    booted.current = true
    setAnswers(marker.answers)
    setStep(force ? 0 : marker.step)
    setOpen(true)
  }, [marker, gate, force])

  const persist = useCallback(
    async (next: TourMarker) => {
      setMarker(next)
      try {
        await writeTourMarker(next)
      } catch {
        setError(t('tour.saveError'))
      }
    },
    [t],
  )

  const goTo = useCallback(
    (next: number, patch: Partial<TourAnswers> = {}) => {
      const nextAnswers = { ...answers, ...patch }
      const nextMarker = { ...(marker ?? emptyMarker()), step: next, answers: nextAnswers }
      setAnswers(nextAnswers)
      setStep(next)
      setError('')
      // Scene 5: the card edge lights up at every step change.
      if (!still) {
        setSparked(true)
        window.setTimeout(() => setSparked(false), 620)
      }
      void persist(nextMarker)
    },
    [answers, marker, persist, still],
  )

  const closeTour = useCallback(
    async (walked: boolean, skipped: boolean) => {
      setOpen(false)
      const base = marker ?? emptyMarker()
      const next: TourMarker = {
        ...base,
        walked,
        skipped,
        step: skipped ? base.step : TOUR_DESK_STEP,
        answers,
      }
      try {
        await writeTourMarker(next)
      } catch {
        /* closing is the user's act; a failed marker write costs a replay */
      }
    },
    [answers, marker],
  )

  /** The tour's exits: without an engine, record the skip so the gate does not bounce. */
  const leaveTour = useCallback(
    async (walked: boolean, skipped: boolean) => {
      if (!(gate.configured || engine?.model)) await skipSetupGate()
      await closeTour(walked, skipped)
    },
    [closeTour, engine?.model, gate.configured],
  )

  const finishTour = useCallback(async () => {
    if (!(gate.configured || engine?.model)) await skipSetupGate()
    if (still) {
      await closeTour(true, false)
      return
    }
    // Scene 7: the live bee flies from where it is into the header corner.
    setFinale(true)
    beeRef.current?.finale()
    window.setTimeout(() => void closeTour(true, false), 1300)
  }, [closeTour, engine?.model, gate.configured, still])

  useEffect(() => {
    if (!open) return
    dialogRef.current?.focus()
    const node = dialogRef.current
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        void leaveTour(true, true)
        return
      }
      if (event.key !== 'Tab' || !node) return
      const items = Array.from(
        node.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null)
      if (items.length === 0) {
        event.preventDefault()
        node.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) {
        event.preventDefault()
        node.focus()
        return
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, closeTour])

  useEffect(() => {
    if (open) titleRef.current?.focus()
  }, [open, step])

  useEffect(() => {
    if (step !== 2) return
    let alive = true
    setEngineLoading(true)
    void getSettings()
      .then((settings) => {
        if (!alive) return
        setEngine({ model: settings.provider?.model, endpoint: settings.provider?.endpoint })
      })
      .catch(() => {
        if (alive) setEngine(null)
      })
      .finally(() => {
        if (alive) setEngineLoading(false)
      })
    return () => {
      alive = false
    }
  }, [step])

  useEffect(() => {
    if (step !== 3 || activateReady) return
    let alive = true
    void Promise.all([getSettings(), getPlugins(), listSkills()])
      .then(([settings, plugins, skills]) => {
        if (!alive) return
        const memoryField = settings.deep
          ?.find((section) => section.key === 'memory')
          ?.fields.find((field) => field.key === 'memory.capture_enabled')
        const memory = memoryField ? Boolean(memoryField.value ?? memoryField.default) : true
        const all = [...plugins.public, ...plugins.personal]
        const web =
          all.find((plugin) => plugin.id === 'web-research' || plugin.name === 'web-research')
            ?.enabled ?? false
        const skillsOn = skills.skills.some((skill) => !skill.disabled)
        const next = { memory, skills: skillsOn, web }
        setActivate(next)
        setActivateStart(next)
      })
      .catch(() => {
        /* the defaults stay; only the memory switch is written on continue */
      })
      .finally(() => {
        if (alive) setActivateReady(true)
      })
    return () => {
      alive = false
    }
  }, [step, activateReady])

  const openEngineSetup = useCallback(() => {
    goTo(3)
    markSetupIntent()
    setOpen(false)
    window.location.hash = '#/setup'
  }, [goTo])

  const saveActivate = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const settings = await getSettings()
      const sections: Record<string, Record<string, string | number | boolean>> = {}
      for (const section of settings.deep ?? []) {
        const fields: Record<string, string | number | boolean> = {}
        for (const field of section.fields) {
          const value = field.value ?? field.default
          if (value !== null && value !== undefined) {
            fields[field.key] = value as string | number | boolean
          }
        }
        sections[section.key] = fields
      }
      sections.memory = { ...(sections.memory ?? {}), 'memory.capture_enabled': activate.memory }
      await saveSections(sections)
      if (activateStart && activate.skills !== activateStart.skills) {
        const skills = await listSkills()
        await Promise.all(
          skills.skills.map((skill) =>
            activate.skills ? enableSkill(skill.name) : disableSkill(skill.name),
          ),
        )
      }
      if (activateStart && activate.web !== activateStart.web) {
        await setPluginEnabled('web-research', activate.web)
      }
      goTo(4, { activate })
    } catch {
      setError(t('tour.saveError'))
    } finally {
      setBusy(false)
    }
  }, [activate, activateStart, goTo, t])

  const chooseFolder = useCallback(async () => {
    const bridge = (
      window as {
        __TAURI__?: {
          core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
        }
      }
    ).__TAURI__
    const invoke = bridge?.core?.invoke
    if (!invoke) return
    setBusy(true)
    setError('')
    try {
      // The shell records the pick and returns a one-time token; the path
      // itself never travels through the page or the request.
      const token = await invoke('pick_folder')
      if (typeof token !== 'string' || !token) return
      const response = await fetch(apiUrl('/api/import'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, apply: true }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = (await response.json()) as {
        applied?: { persona?: boolean; skills?: unknown[]; mcp_servers?: unknown[] }
      }
      const applied = data.applied ?? {}
      setImported({
        skills: Array.isArray(applied.skills) ? applied.skills.length : 0,
        servers: Array.isArray(applied.mcp_servers) ? applied.mcp_servers.length : 0,
        persona: applied.persona === true,
      })
      setCarry('imported')
      setAnswers((current) => ({ ...current, carry: 'imported' }))
    } catch {
      setError(t('tour.importError'))
    } finally {
      setBusy(false)
    }
  }, [t])

  // Scene 5/6: the guide flies to the new card on every step, and to the engine core
  // once the connection is green.
  useEffect(() => {
    if (!open || still) return
    const id = window.setTimeout(() => {
      const panel = dialogRef.current?.querySelector('[data-testid="tour-panel"]')
      beeRef.current?.flyToPanelPerch(panel ?? null)
    }, 60)
    return () => window.clearTimeout(id)
  }, [open, still, step])

  useEffect(() => {
    if (!open || still || step !== 2 || !(gate.configured || engine?.model)) return
    const core = dialogRef.current?.querySelector('[data-testid="tour-engine-core"]')
    beeRef.current?.flyToControl(core ?? null)
  }, [engine?.model, gate.configured, open, still, step])

  const clickStage = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (still) return
      const control = (event.target as HTMLElement).closest('[data-testid]')
      const id = control?.getAttribute('data-testid') ?? ''
      if (control && /^tour-(usage-|toggle-|guard-|continue|start|next|engine-)/.test(id)) {
        beeRef.current?.flyToControl(control)
      } else {
        beeRef.current?.flyTo(event.clientX, event.clientY)
      }
    },
    [still],
  )

  // The shell stays mounted behind the tour. Its resting actors step out of the
  // composed page for as long as the guide is the one figure on screen.
  useEffect(() => {
    if (!open) return
    document.body.classList.add('ephe-tour-open')
    return () => document.body.classList.remove('ephe-tour-open')
  }, [open])

  if (!open) return null

  const configured = gate.configured || Boolean(engine?.model)
  const question = step >= 1 && step <= TOUR_QUESTION_COUNT
  const eyebrow = question
    ? t('tour.step', { current: step, total: TOUR_QUESTION_COUNT })
    : step === TOUR_DESK_STEP
      ? t('tour.desk.eyebrow')
      : t('tour.greeting.eyebrow')

  const primary = (() => {
    if (step === 0) {
      return (
        <button
          type="button"
          className="tour-primary focus-ring"
          onClick={() => goTo(1)}
          data-testid="tour-start"
        >
          {t('tour.greeting.cta')}
        </button>
      )
    }
    if (step === 1) {
      return (
        <button
          type="button"
          className="tour-primary focus-ring"
          disabled={!answers.usage}
          onClick={() => goTo(2, { usage: answers.usage })}
          data-testid="tour-continue"
        >
          {t('tour.continue')}
        </button>
      )
    }
    if (step === 2) {
      if (!configured) return null
      return (
        <button
          type="button"
          className="tour-primary focus-ring"
          onClick={() => goTo(3, { engine: engine?.model })}
          data-testid="tour-continue"
        >
          {t('tour.continue')}
        </button>
      )
    }
    if (step === 3) {
      return (
        <button
          type="button"
          className="tour-primary focus-ring"
          disabled={busy}
          onClick={() => void saveActivate()}
          data-testid="tour-continue"
        >
          {busy ? t('tour.saving') : t('tour.continue')}
        </button>
      )
    }
    if (step === 4) {
      return (
        <button
          type="button"
          className="tour-primary focus-ring"
          onClick={() => {
            const choice = carry ?? 'fresh'
            setCarry(choice)
            goTo(TOUR_DESK_STEP, { carry: choice })
          }}
          data-testid="tour-next"
        >
          {carry === 'imported' ? t('tour.next') : t('tour.carry.fresh')}
        </button>
      )
    }
    return (
      <button
        type="button"
        className="tour-primary focus-ring"
        onClick={() => void finishTour()}
        data-testid="tour-finish"
      >
        {t('tour.desk.cta')}
      </button>
    )
  })()

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-title"
      tabIndex={-1}
      data-testid="first-run-tour"
      data-step={step}
      data-reduced={still ? 'true' : undefined}
      className={`tour-stage${still ? ' is-still' : ''}${finale ? ' is-finale' : ''}`}
      onPointerDown={clickStage}
    >
      {/* Scene 5 is the stage: the keyframe's forest behind the glass card. The bee is
          the live guide over it, never a bee baked into the backdrop. */}
      <img
        className="tour-stage-frame"
        src="/onboarding/scene-1-ignition.jpg"
        alt=""
        aria-hidden="true"
        draggable={false}
      />
      <div className="tour-stage-shade" aria-hidden="true" />
      <div className="tour-fireflies" aria-hidden="true" />
      <div className="tour-ground" aria-hidden="true" />
      <InteractiveBeeGuide ref={beeRef} still={still} size="clamp(13rem, 24vw, 20rem)" />

      <section
        className={`tour-panel${sparked ? ' is-sparked' : ''}`}
        data-testid="tour-panel"
        data-step={step}
      >
        <header className="tour-head">
          <span className="tour-eyebrow font-mono">{eyebrow}</span>
          <button
            type="button"
            className="tour-skip focus-ring"
            onClick={() => void leaveTour(true, true)}
            data-testid="tour-skip"
          >
            {t('tour.skip')}
          </button>
        </header>

        <div key={step} className="tour-body">
          {step === 0 && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.greeting.title')}
              </h2>
              <p className="tour-line">{t('tour.greeting.body')}</p>
            </>
          )}

          {step === 1 && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.usage.title')}
              </h2>
              <p className="tour-line">{t('tour.usage.hint')}</p>
              <div className="tour-cards" role="radiogroup" aria-label={t('tour.usage.title')}>
                {USAGE_OPTIONS.map(({ value, key, icon: Icon }) => {
                  const selected = answers.usage === value
                  return (
                    <button
                      key={value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      data-testid={`tour-usage-${value}`}
                      onClick={() => setAnswers((current) => ({ ...current, usage: value }))}
                      className={`tour-card focus-ring${selected ? ' is-selected' : ''}`}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      <span>{t(key)}</span>
                    </button>
                  )
                })}
              </div>
              <button
                type="button"
                className="tour-text-action"
                onClick={() => goTo(2)}
                data-testid="tour-skip-question"
              >
                {t('tour.usage.skip')}
              </button>
            </>
          )}

          {step === 2 && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.engine.title')}
              </h2>
              <div
                className="tour-engine-core"
                data-testid="tour-engine-core"
                data-state={engineLoading ? 'testing' : configured ? 'ok' : 'idle'}
                aria-hidden="true"
              >
                <img src="/onboarding/scene-6-engine.jpg" alt="" draggable={false} />
                <span className="tour-core-halo" />
              </div>
              {engineLoading ? (
                <p className="tour-line inline-flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  {t('tour.checking')}
                </p>
              ) : configured ? (
                <div className="tour-engine" data-testid="tour-engine-ready">
                  <p className="text-scale-ui text-foreground">
                    {t('tour.engine.configured', {
                      model: engine?.model ?? '—',
                      endpoint: engine?.endpoint ?? '—',
                    })}
                  </p>
                  <button type="button" className="tour-text-action" onClick={openEngineSetup}>
                    {t('tour.engine.change')}
                  </button>
                </div>
              ) : (
                <>
                  <p className="tour-line">{t('tour.engine.body')}</p>
                  <div className="tour-actions">
                    <button
                      type="button"
                      className="tour-primary focus-ring"
                      onClick={openEngineSetup}
                      data-testid="tour-engine-choose"
                    >
                      {t('tour.engine.choose')}
                    </button>
                    <button
                      type="button"
                      className="tour-ghost focus-ring"
                      onClick={() => {
                        void skipSetupGate()
                        goTo(3)
                      }}
                      data-testid="tour-engine-skip"
                    >
                      {t('tour.engine.skip')}
                    </button>
                  </div>
                </>
              )}
            </>
          )}

          {step === 3 && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.activate.title')}
              </h2>
              <p className="tour-line">{t('tour.activate.hint')}</p>
              <div className="tour-switches">
                <Toggle
                  checked={activate.memory}
                  onChange={(memory) => setActivate((current) => ({ ...current, memory }))}
                  label={t('tour.activate.memory')}
                  hint={t('tour.activate.memoryHint')}
                  testId="tour-toggle-memory"
                />
                <Toggle
                  checked={activate.skills}
                  onChange={(skills) => setActivate((current) => ({ ...current, skills }))}
                  label={t('tour.activate.skills')}
                  hint={t('tour.activate.skillsHint')}
                  testId="tour-toggle-skills"
                />
                <Toggle
                  checked={activate.web}
                  onChange={(web) => setActivate((current) => ({ ...current, web }))}
                  label={t('tour.activate.web')}
                  hint={t('tour.activate.webHint')}
                  testId="tour-toggle-web"
                />
              </div>
              <div className="tour-guard">
                <button
                  type="button"
                  className="tour-text-action tour-guard-toggle focus-ring"
                  aria-expanded={guardPreview}
                  aria-controls="tour-approval-preview"
                  onClick={() => setGuardPreview((value) => !value)}
                  data-testid="tour-guard-toggle"
                >
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('tour.guard.preview')}
                </button>
                {guardPreview && (
                  <div
                    id="tour-approval-preview"
                    className="tour-approval"
                    data-testid="tour-approval-card"
                    role="group"
                    aria-label={t('tour.guard.title')}
                  >
                    <p className="tour-approval-question">{t('tour.guard.question')}</p>
                    <p className="tour-approval-detail">{t('tour.guard.detail')}</p>
                    <div className="tour-approval-actions">
                      <button
                        type="button"
                        data-testid="tour-guard-allow"
                        onClick={() => setGuardPreview(false)}
                        className="tour-approval-allow"
                      >
                        {t('tour.guard.allow')}
                      </button>
                      <button
                        type="button"
                        data-testid="tour-guard-deny"
                        onClick={() => setGuardPreview(false)}
                        className="tour-approval-deny"
                      >
                        {t('tour.guard.deny')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.carry.title')}
              </h2>
              <p className="tour-line">{t('tour.carry.body')}</p>
              {imported ? (
                <p className="tour-imported" data-testid="tour-import-summary">
                  {t('tour.carry.imported', {
                    skills: imported.skills,
                    servers: imported.servers,
                    persona: imported.persona
                      ? t('tour.carry.personaYes')
                      : t('tour.carry.personaNo'),
                  })}
                </p>
              ) : (
                <div className="tour-actions">
                  {isDesktop() ? (
                    <button
                      type="button"
                      className="tour-primary focus-ring"
                      disabled={busy}
                      onClick={() => void chooseFolder()}
                      data-testid="tour-import"
                    >
                      {busy ? t('tour.saving') : t('tour.carry.choose')}
                    </button>
                  ) : (
                    <p className="tour-line">{t('tour.carry.pwaNote')}</p>
                  )}
                  <button
                    type="button"
                    className="tour-ghost focus-ring"
                    onClick={() => {
                      setCarry('fresh')
                      goTo(TOUR_DESK_STEP, { carry: 'fresh' })
                    }}
                    data-testid="tour-fresh"
                  >
                    {t('tour.carry.fresh')}
                  </button>
                </div>
              )}
            </>
          )}

          {step === TOUR_DESK_STEP && (
            <>
              <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title font-display">
                {t('tour.desk.title')}
              </h2>
              <p className="tour-line">{t('tour.desk.body')}</p>
              <p className="tour-desk-actions text-scale-ui text-ink-faint">
                {t('tour.desk.hint')}
              </p>
            </>
          )}
        </div>

        {error && (
          <p className="tour-error" role="status" aria-live="polite">
            {error}
          </p>
        )}

        <footer className="tour-foot">
          {step > 0 ? (
            <button
              type="button"
              className="tour-back focus-ring"
              onClick={() => goTo(step - 1)}
              data-testid="tour-back"
            >
              {t('tour.back')}
            </button>
          ) : (
            <span />
          )}
          {primary}
        </footer>
      </section>
    </div>
  )
}
