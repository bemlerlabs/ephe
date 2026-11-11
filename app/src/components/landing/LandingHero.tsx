import { useTranslation } from 'react-i18next'
import { REPO_URL } from './landingFacts'

/**
 * The first screen: what Ephe is, and the two doors a visitor needs.
 *
 * "Install in 60 seconds" scrolls to the command instead of navigating, because the
 * page is reached from an app route and the command is the next thing to read.
 */
export function LandingHero({ onJumpToInstall }: { onJumpToInstall: () => void }) {
  const { t } = useTranslation()

  return (
    <header>
      <p className="font-mono text-ui-2xs uppercase tracking-[0.18em] text-ink-faint">
        {t('landing.eyebrow')}
      </p>
      <h1
        data-testid="landing-title"
        className="mt-4 max-w-3xl font-display text-3xl leading-[1.06] tracking-tight text-foreground sm:text-5xl"
      >
        {t('landing.title')}
      </h1>
      <p className="mt-4 max-w-2xl text-ui-base leading-relaxed text-ink-soft">
        {t('landing.lede')}
      </p>
      <div className="mt-7 flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="landing-install-jump"
          onClick={onJumpToInstall}
          className="focus-ring forest-glow inline-flex h-12 items-center justify-center rounded-xl bg-brand px-6 text-ui-base font-medium text-black transition-colors duration-fast hover:bg-brand-glow"
        >
          {t('landing.primaryCta')}
        </button>
        <a
          data-testid="landing-source-link"
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="focus-ring glass-control inline-flex h-12 items-center rounded-xl px-6 text-ui-base font-medium text-foreground transition-colors duration-fast hover:bg-brand/10"
        >
          {t('landing.secondaryCta')}
        </a>
      </div>
    </header>
  )
}
