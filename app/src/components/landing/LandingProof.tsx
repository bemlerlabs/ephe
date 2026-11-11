import { useTranslation } from 'react-i18next'
import { LandingSection } from './LandingSection'
import { REPO_BLOB, STUDIES } from './landingFacts'

interface ProofItem {
  id: string
  valueKey: string
  labelKey: string
  bodyKey: string
  href: string
  /** A studied source is named in the locale; a repository file is named by its path. */
  sourceKey?: string
  sourcePath?: string
}

const ITEMS: readonly ProofItem[] = [
  {
    id: 'agents-md',
    valueKey: 'landing.proof.agentsMdValue',
    labelKey: 'landing.proof.agentsMdLabel',
    bodyKey: 'landing.proof.agentsMdBody',
    href: STUDIES.agentsMd.href,
    sourceKey: 'landing.proof.agentsMdSource',
  },
  {
    id: 'realm',
    valueKey: 'landing.proof.realmValue',
    labelKey: 'landing.proof.realmLabel',
    bodyKey: 'landing.proof.realmBody',
    href: STUDIES.realm.href,
    sourceKey: 'landing.proof.realmSource',
  },
  {
    id: 'accounts',
    valueKey: 'landing.proof.accountsValue',
    labelKey: 'landing.proof.accountsLabel',
    bodyKey: 'landing.proof.accountsBody',
    href: `${REPO_BLOB}core/engine_config.py`,
    sourcePath: 'core/engine_config.py',
  },
] as const

/**
 * The three numbers the page argues from. Two are other people's measurements, and the
 * study line says on which agent and how many runs. The page prints those figures; it does
 * not turn them into a percentage of its own.
 */
export function LandingProof() {
  const { t } = useTranslation()

  return (
    <LandingSection
      id="landing-proof"
      eyebrow={t('landing.proof.eyebrow')}
      title={t('landing.proof.title')}
      lede={t('landing.proof.lede')}
    >
      <div data-testid="landing-proof" className="grid gap-x-8 gap-y-6 sm:grid-cols-3">
        {ITEMS.map((item) => (
          <figure
            key={item.id}
            data-testid={`landing-proof-${item.id}`}
            className="border-t border-hairline pt-4"
          >
            <p className="font-display text-4xl leading-none tracking-tight text-foreground">
              {t(item.valueKey)}
            </p>
            <p className="mt-2 font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint">
              {t(item.labelKey)}
            </p>
            <p className="mt-3 text-ui-sm leading-relaxed text-ink-soft">{t(item.bodyKey)}</p>
            <figcaption className="mt-3">
              <a
                href={item.href}
                target="_blank"
                rel="noreferrer"
                className="focus-ring inline-flex rounded-sm font-mono text-ui-2xs text-ink-faint underline decoration-hairline underline-offset-4 transition-colors duration-fast hover:text-ink-soft"
              >
                {item.sourceKey ? t(item.sourceKey) : item.sourcePath}
              </a>
            </figcaption>
          </figure>
        ))}
      </div>
    </LandingSection>
  )
}
