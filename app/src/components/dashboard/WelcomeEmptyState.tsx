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
import { useEffect, useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { Sparkles, Mail, Image as ImageIcon, Globe, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { markSetupIntent } from '@/lib/setupGate'
import EphemeralWordmark from './EphemeralWordmark'
import { EpheMark } from '@/components/shell/EpheMark'
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

export default function WelcomeEmptyState({ onFillComposer }: WelcomeEmptyStateProps) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const [live, setLive] = useState<LiveData>({ projects: null, artifacts: null, health: null })

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
    healthCheck()
      .then((h) => {
        if (!cancelled) setLive((s) => ({ ...s, health: h }))
      })
      .catch(() => {
        /* offline → toast hidden */
      })
    return () => {
      cancelled = true
    }
  }, [])

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

  // DD-06: the pill must reflect the real engine state, not a flattering constant.
  const engineUp = Boolean(
    live.health &&
    (live.health.engine_online ?? live.health.dgx_online) &&
    live.health.status === 'ok',
  )
  // An engine that answers and refuses the credential is not an engine that is
  // down, and the difference is the action: one has a field to fill, the other has
  // nothing to do. Measured 2026-10-10: the refused case read as offline here.
  const keyRefused = Boolean(live.health?.engine_key_challenge)
  const pillText = keyRefused
    ? t('welcome.modelKeyRefused')
    : engineUp
      ? t('welcome.modelOnline')
      : t('welcome.modelOffline')

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
            className={`text-ui-xs font-medium ${engineUp ? 'text-status-success/90' : 'text-status-warning/90'}`}
            data-model-status={keyRefused ? 'refused' : engineUp ? 'up' : 'down'}
          >
            {pillText}
          </p>
          <p className="text-ui-xs text-ink-soft">
            {t('welcome.modelLabel')}:{' '}
            <span className="text-foreground/80">{live.health.active_model}</span> (
            {live.health.active_tier})
          </p>
          {/* First-run path: a down or refused engine names its next step right
              here, so the welcome screen is never a dead end. Same re-entry the
              composer chip offers, reachable from the first screen. */}
          {!engineUp && (
            <button
              type="button"
              data-testid="welcome-engine-setup"
              onClick={() => {
                markSetupIntent()
                window.location.hash = '#/setup'
              }}
              className="mt-1 rounded inline-flex items-center gap-1 text-ui-xs font-medium text-brand hover:opacity-80 transition-opacity max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              {t('welcome.openSetup')}
              <ArrowRight className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
        </m.div>
      )}

      {/* my-auto wrapper: centres while there is room; on overflow the auto
          margins collapse → clean scrolling starting at the top (justify-center
          would push the hero past the top edge, where it cannot be scrolled to). */}
      <div className="my-auto flex w-full flex-col items-center">
        {/* The wordmark condenses in the empty state — inline, so the movement
            has SVG children, which an <img> does not own. */}
        <EpheMark state="condense" size="4rem" testId="ephe-mark-hero" className="mb-3" />
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
          {[0, 1, 2, 3].map((i) => {
            const Icon = CARD_ICONS[i]!
            return (
              <m.button
                key={i}
                data-testid={`welcome-card-${i}`}
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
                className="glass-control rounded-full px-3.5 py-1.5 hover:bg-brand/10 group flex items-center gap-2 transition-colors shrink-0 max-lg:min-h-11"
                onClick={() => {
                  // Deploy-check P2-1: a card FILLS the composer draft instead of
                  // firing an engine call on a stray click — the user stays in
                  // control and can edit before sending.
                  onFillComposer(t(`welcome.cards.${i}.prompt`))
                }}
              >
                <Icon className="h-3.5 w-3.5 text-brand/80 shrink-0" aria-hidden="true" />
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
