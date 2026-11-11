/**
 * The page a visitor from another agent lands on: one command, the six decisions, the
 * two measurements that back the argument, and the import path. It is a route inside the
 * app shell, so it scrolls like the other pages and carries no second navigation.
 */
import { useTranslation } from 'react-i18next'
import {
  LandingComparison,
  LandingHero,
  LandingMigration,
  LandingProof,
  LandingTryIt,
  REPO_BLOB,
  REPO_URL,
} from '@/components/landing'

const FOOTER_LINKS = [
  { id: 'docs', labelKey: 'landing.footer.docs', href: `${REPO_BLOB}docs/README.md` },
  { id: 'source', labelKey: 'landing.footer.source', href: REPO_URL },
  { id: 'issues', labelKey: 'landing.footer.issues', href: `${REPO_URL}/issues` },
] as const

export default function LandingPage() {
  const { t } = useTranslation()

  const jumpToInstall = () => {
    document.getElementById('landing-install')?.scrollIntoView?.({ block: 'start' })
  }

  return (
    <div data-testid="landing-page" className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-4 pt-10 pb-24 sm:px-6">
        <LandingHero onJumpToInstall={jumpToInstall} />
        <LandingProof />
        <LandingComparison />
        <LandingTryIt />
        <LandingMigration />

        <footer className="mt-16 border-t border-hairline pt-6">
          <p className="max-w-2xl text-ui-xs leading-relaxed text-ink-faint">
            {t('landing.footer.license')}
          </p>
          <nav aria-label={t('landing.footer.nav')} className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
            {FOOTER_LINKS.map((link) => (
              <a
                key={link.id}
                data-testid={`landing-footer-${link.id}`}
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="focus-ring rounded-sm text-ui-xs text-ink-soft underline decoration-hairline underline-offset-4 hover:text-foreground"
              >
                {t(link.labelKey)}
              </a>
            ))}
          </nav>
        </footer>
      </div>
    </div>
  )
}
