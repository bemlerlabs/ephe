import { useTranslation } from 'react-i18next'
import { LandingSection } from './LandingSection'
import { IMPORT_COMMAND, IMPORT_ROWS, SWITCHING_DOC } from './landingFacts'

const STAYS = [
  'landing.migrate.history',
  'landing.migrate.engine',
  'landing.migrate.plugins',
] as const

/**
 * The migration story, taken from `docs/SWITCHING.md`: what `ephe import` detects, where
 * each artifact lands, and what does not come over. The rules file is the part that has
 * to travel by hand, so it is said rather than implied.
 */
export function LandingMigration() {
  const { t } = useTranslation()

  return (
    <LandingSection
      id="landing-migrate"
      eyebrow={t('landing.migrate.eyebrow')}
      title={t('landing.migrate.title')}
      lede={t('landing.migrate.lede')}
    >
      <pre
        tabIndex={0}
        className="max-w-2xl overflow-x-auto rounded-xl border border-hairline bg-surface/40 px-3 py-2.5 font-mono text-ui-xs break-words whitespace-pre-wrap text-foreground sm:whitespace-pre"
      >
        <code data-testid="landing-import-command">{IMPORT_COMMAND}</code>
      </pre>

      <div className="mt-7 grid gap-8 lg:grid-cols-2">
        <div>
          <h3 className="font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint">
            {t('landing.migrate.carries')}
          </h3>
          <dl data-testid="landing-import-rows" className="mt-3 border-t border-hairline">
            {IMPORT_ROWS.map((row) => (
              <div
                key={row.id}
                data-testid={`landing-import-${row.id}`}
                className="border-b border-hairline py-3"
              >
                <dt className="text-ui-sm break-words text-foreground">{t(row.artifactKey)}</dt>
                <dd className="mt-1 text-ui-xs leading-relaxed break-words text-ink-faint">
                  {t(row.landsKey)}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <h3 className="font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint">
            {t('landing.migrate.stays')}
          </h3>
          <ul data-testid="landing-stays" className="mt-3 border-t border-hairline">
            {STAYS.map((key) => (
              <li
                key={key}
                className="border-b border-hairline py-3 text-ui-sm leading-relaxed text-ink-soft"
              >
                {t(key)}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-ui-sm leading-relaxed text-ink-soft">
            {t('landing.migrate.rules')}
          </p>
          <a
            href={SWITCHING_DOC}
            target="_blank"
            rel="noreferrer"
            className="focus-ring mt-3 inline-flex rounded-sm text-ui-xs text-ink-faint underline decoration-hairline underline-offset-4 hover:text-ink-soft"
          >
            {t('landing.migrate.docLink')}
          </a>
        </div>
      </div>
    </LandingSection>
  )
}
