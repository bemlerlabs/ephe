/**
 * Ephe — Welcome Empty State (R26 redesign, mockup-faithful)
 *
 * Hero (2 lines) + model-status toast (from /api/health) + 4 glassy
 * action cards in a 2x2 grid with LIVE data (workspace projects from
 * /api/projects, recent artifacts from /api/artifacts). The cards fill the
 * main composer draft via onFillComposer — there is no second input here.
 *
 * Offline-first: every fetch fails silently into an honest static
 * fallback text — the cards never render fabricated numbers.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { Sparkles, Mail, Image as ImageIcon, Globe, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { markSetupIntent } from '@/lib/setupGate'
import { subscribeTourMarker, tourMarkerSnapshot } from '@/lib/firstRunTour'
import './WelcomeEmptyState.css'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import { engineStateOf, type EngineState } from '@/lib/engineState'
import EphemeralWordmark from './EphemeralWordmark'
import { EpheMark } from '@/components/shell/EpheMark'
import { HeroMark } from '@/components/shell/HeroMark'
import { CompanionActor, type CompanionHandle } from '@/components/shell/CompanionActor'
import {
  listProjects,
  listArtifacts,
  healthCheck,
  type ProjectSummary,
  type ArtifactEntry,
  type HealthInfo,
} from '@/lib/api'

interface WelcomeEmptyStateProps {
  /** Fills the main chat composer (bottom ChatInput) — cards never auto-send. */
  onFillComposer: (text: string) => void
}

interface LiveData {
  projects: ProjectSummary[] | null
  artifacts: ArtifactEntry[] | null
  health: HealthInfo | null
}

const CARD_ICONS = [Sparkles, Mail, ImageIcon, Globe] as const
const STARTER_CARD_BY_USAGE: Record<string, number> = { code: 0, documents: 1, research: 3 }

export default function WelcomeEmptyState({ onFillComposer }: WelcomeEmptyStateProps) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const companionEnabled = useDeepBool('appearance.companion_enabled', false)
  const companionSpecies = useDeepSelect('appearance.companion_species', 'fire_bee')
  const companionScale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const still = Boolean(reduceMotion) || !animationsEnabled
  const companionRef = useRef<CompanionHandle>(null)
  const [live, setLive] = useState<LiveData>({ projects: null, artifacts: null, health: null })
  // The tour's first answer decides which starter fits: code → the project card,
  // documents → the email card, research → the web card. A mix recommends nothing.
  // FirstRunTour owns the request; this surface only reads the answer it publishes.
  const tourMarker = useSyncExternalStore(subscribeTourMarker, tourMarkerSnapshot, () => null)
  const usage = tourMarker?.answers.usage
  const recommended = usage && usage !== 'mix' ? (STARTER_CARD_BY_USAGE[usage] ?? null) : null

  // A click on a card (or on the companion) turns the bee toward the card,
  // leaves a spark burst and fills the draft. It still never sends.
  const activateCard = useCallback(
    (index: number, degrees = 0) => {
      companionRef.current?.turnTo(degrees)
      companionRef.current?.burst()
      onFillComposer(t(`welcome.cards.${index}.prompt`))
    },
    [onFillComposer, t],
  )

  const loadHealth = useCallback(() => {
    healthCheck()
      .then((h) => setLive((s) => ({ ...s, health: h })))
      .catch(() => {
        /* offline → toast hidden */
      })
  }, [])

  useEffect(() => {
    let cancelled = false
    listProjects()
      .then((r) => {
        if (!cancelled) setLive((s) => ({ ...s, projects: r.projects }))
      })
      .catch(() => {
        /* offline → fallback desc */
      })
    listArtifacts({ limit: 12 })
      .then((r) => {
        if (!cancelled) setLive((s) => ({ ...s, artifacts: r.artifacts }))
      })
      .catch(() => {
        /* offline → fallback desc */
      })
    loadHealth()
    return () => {
      cancelled = true
    }
  }, [loadHealth])

  // I2: time-of-day greeting for the clean empty state (reference look).
  const hour = new Date().getHours()
  const greetingKey =
    hour >= 5 && hour < 11
      ? 'welcome.greetingMorning'
      : hour >= 11 && hour < 18
        ? 'welcome.greetingDay'
        : hour >= 18 && hour < 23
          ? 'welcome.greetingEvening'
          : 'welcome.greetingNight'

  // DD-06: the pill reflects one named engine state — a reachable engine without a
  // model is not "ready", and a refused key is not "offline".
  const engineState = engineStateOf(live.health)
  const pillText: Record<EngineState, string> = {
    checking: t('welcome.modelOffline'),
    unconfigured: t('welcome.modelOffline'),
    unreachable: t('welcome.modelOffline'),
    'key-refused': t('welcome.modelKeyRefused'),
    'no-model': t('welcome.modelNoModel'),
    ready: t('welcome.modelOnline'),
  }

  return (
    <m.div
      data-testid="panel-chat"
      initial={reduceMotion ? { opacity: 0 } : { filter: 'blur(10px)', opacity: 0, y: 20 }}
      animate={reduceMotion ? { opacity: 1 } : { filter: 'blur(0px)', opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0.15 : 0.35 }}
      className="relative flex flex-col items-center flex-1 min-h-0 overflow-y-auto px-4 py-3 sm:py-5 text-center"
    >
      {/* AI model-status toast. On sm+ it floats top-right as in the mockup;
          below sm it sits inline at the top so the engine state — and its next
          step — is not invisible on a phone (DD-10 parity). */}
      {live.health && (
        <m.div
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          data-testid="model-status-toast"
          className="mb-2 w-fit max-w-[calc(100%-2rem)] sm:mb-0 static sm:absolute sm:top-4 sm:right-4 float-surface px-3 py-2 text-left"
        >
          <p
            className={`text-ui-xs font-medium ${engineState === 'ready' ? 'text-status-success/90' : 'text-status-warning/90'}`}
            data-model-status={
              engineState === 'ready' ? 'up' : engineState === 'key-refused' ? 'refused' : 'down'
            }
            data-engine-state={engineState}
          >
            {pillText[engineState]}
          </p>
          <p className="text-ui-xs text-ink-soft" data-testid="model-status-line">
            {t('welcome.modelLabel')}:{' '}
            {/* An engine that named nothing has no model to print and no tier to put in
                parentheses; the em dash is the house mark for a fact the engine did
                not state, and the empty pair read as a malformed value. */}
            <span className="text-foreground/80">{live.health.active_model || '—'}</span>
            {live.health.active_tier ? ` (${live.health.active_tier})` : ''}
          </p>
          {/* First-run path: the state names its next step right here, so the
              welcome screen is never a dead end. One primary action per state. */}
          {engineState !== 'ready' && (
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              {engineState === 'unreachable' && (
                <button
                  type="button"
                  data-testid="welcome-engine-retry"
                  onClick={() => loadHealth()}
                  className="rounded inline-flex items-center text-ui-xs font-medium text-ink-soft hover:text-foreground transition-colors max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                >
                  {t('welcome.retry')}
                </button>
              )}
              <button
                type="button"
                data-testid="welcome-engine-setup"
                onClick={() => {
                  markSetupIntent()
                  window.location.hash = '#/setup'
                }}
                className="rounded inline-flex items-center gap-1 text-ui-xs font-medium text-brand hover:opacity-80 transition-opacity max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                {engineState === 'key-refused'
                  ? t('welcome.fixKey')
                  : engineState === 'no-model'
                    ? t('welcome.chooseModel')
                    : t('welcome.openSetup')}
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          )}
        </m.div>
      )}

      {/* my-auto wrapper: centres while there is room; on overflow the auto
          margins collapse → clean scrolling starting at the top (justify-center
          would push the hero past the top edge, where it cannot be scrolled to). */}
      <div className="my-auto flex w-full flex-col items-center">
        {/* The wordmark condenses in the empty state — inline, so the movement
            has SVG children, which an <img> does not own. */}
        {companionEnabled && companionSpecies !== 'minimal' ? (
          <CompanionActor
            ref={companionRef}
            species={companionSpecies === 'ember_spark' ? 'ember_spark' : 'fire_bee'}
            scale={companionScale}
            still={still}
            size="hero"
            testId="ephe-mark-hero"
            className="mb-1"
            onActivate={() => activateCard(recommended ?? 0)}
          />
        ) : companionSpecies === 'minimal' && companionEnabled ? (
          /* hero-size-exception: minimal — S3. 4rem would be the render, and `minimal`
             is the user's own choice of the quiet vector form; its shape lands in Wave 5. */
          <EpheMark state="condense" size="4rem" testId="ephe-mark-hero" className="mb-3" />
        ) : (
          <HeroMark size="4rem" testId="ephe-mark-hero" className="mb-3" />
        )}
        {/* I2 clean empty state (reference look): a time-of-day greeting, a
          subdued brand name, no tile/version line — the first impression stays
          calm, the composer carries the composition. */}
        <p
          data-testid="hero-greeting"
          className="ap-sketch-in stagger-1 text-ui-sm text-ink-faint mb-1.5"
        >
          {greetingKey ? t(greetingKey) : ''}
        </p>
        <h2
          data-testid="hero-brand"
          className="font-display hero-frost text-3xl sm:text-4xl font-semibold text-foreground/90 mb-1.5"
        >
          <EphemeralWordmark text={t('welcome.heroTitle')} />
        </h2>
        <p className="ap-sketch-in stagger-2 text-ui-sm text-ink-soft mb-4 sm:mb-5">
          {t('welcome.heroSub')}
        </p>

        {/* 4 action cards (2x2) with live data — icon tile + title + 1-3 lines.
          Mobile: 2 compact columns (everything stays reachable without scrolling),
          desktop exactly as in the mockup. */}
        {/* Natural-width pills, centered, wrapping as one flexible row: fixed grid
          columns truncated every title with an ellipsis at common widths. */}
        <div className="flex flex-wrap items-center justify-center gap-2 max-w-3xl w-full mb-4 sm:mb-5 shrink-0">
          {recommended !== null && (
            <p
              data-testid="welcome-recommended"
              className="welcome-recommended-label w-full text-ui-xs"
            >
              {t('welcome.recommended')}
            </p>
          )}
          {(recommended === null
            ? [0, 1, 2, 3]
            : [recommended, ...[0, 1, 2, 3].filter((i) => i !== recommended)]
          ).map((i) => {
            const Icon = CARD_ICONS[i]!
            const isRecommended = i === recommended
            return (
              <m.button
                key={i}
                data-testid={`welcome-card-${i}`}
                data-recommended={isRecommended ? 'true' : undefined}
                initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14, filter: 'blur(6px)' }}
                animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={
                  reduceMotion
                    ? { duration: 0.12, delay: i * 0.03 }
                    : { delay: 0.08 + i * 0.05, type: 'spring', stiffness: 300, damping: 26 }
                }
                whileHover={
                  reduceMotion
                    ? undefined
                    : {
                        y: -2,
                        scale: 1.015,
                        transition: { type: 'spring', stiffness: 400, damping: 20 },
                      }
                }
                whileTap={reduceMotion ? undefined : { scale: 0.99 }}
                className={`glass-control rounded-full px-3.5 py-1.5 welcome-card group flex items-center gap-2 shrink-0 max-lg:min-h-11${isRecommended ? ' welcome-card-recommended' : ''}`}
                onClick={(event) => {
                  // Deploy-check P2-1: a card FILLS the composer draft instead of
                  // firing an engine call on a stray click — the user stays in
                  // control and can edit before sending.
                  const rect = event.currentTarget.getBoundingClientRect()
                  const degrees = Math.max(
                    -38,
                    Math.min(38, (rect.left + rect.width / 2 - window.innerWidth / 2) / 20),
                  )
                  activateCard(i, degrees)
                }}
              >
                <Icon className="welcome-card-icon h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="text-ui-xs text-ink-faint group-hover:text-foreground/90 transition-colors truncate">
                  {t(`welcome.cards.${i}.title`)}
                </span>
              </m.button>
            )
          })}
        </div>
        {/* Owner feedback 2026-09-28: the ephemerides do NOT live on the
            welcome screen (too much for a first impression) — their own area sits
            in the settings hub (tab „Ephemeriden"). */}
      </div>
    </m.div>
  )
}
