import { useTranslation } from 'react-i18next'
import { LandingSection } from './LandingSection'
import { COMPARISON_ROWS, REPO_BLOB } from './landingFacts'

/**
 * The six questions, answered from the checkout.
 *
 * Only Ephe's column is filled. A row for another tool would have to state what that
 * tool's documentation says, and this page has no measured source for those cells, so
 * the table carries the one column it can prove plus the path that proves it.
 */
export function LandingComparison() {
  const { t } = useTranslation()

  return (
    <LandingSection
      id="landing-comparison"
      eyebrow={t('landing.compare.eyebrow')}
      title={t('landing.compare.title')}
      lede={t('landing.compare.lede')}
    >
      <div className="border-t border-hairline">
        <table
          data-testid="landing-comparison"
          className="w-full table-fixed border-collapse text-left"
        >
          <caption className="sr-only">{t('landing.compare.title')}</caption>
          <thead>
            <tr className="border-b border-hairline">
              <th
                scope="col"
                className="w-24 py-2.5 pr-3 align-bottom font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint sm:w-44 sm:pr-4"
              >
                {t('landing.compare.question')}
              </th>
              <th
                scope="col"
                className="py-2.5 align-bottom font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint"
              >
                {t('landing.compare.ephe')}
              </th>
            </tr>
          </thead>
          <tbody>
            {COMPARISON_ROWS.map((row) => (
              <tr
                key={row.id}
                data-testid={`landing-row-${row.id}`}
                className="border-b border-hairline align-top"
              >
                <th
                  scope="row"
                  className="py-4 pr-4 text-ui-sm font-medium break-words text-foreground"
                >
                  {t(row.questionKey)}
                </th>
                <td className="py-4 text-ui-sm leading-relaxed break-words text-ink-soft">
                  {t(row.answerKey)}
                  <a
                    href={`${REPO_BLOB}${row.proofPath}`}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring mt-2 flex w-fit max-w-full rounded-sm font-mono text-ui-2xs break-words text-ink-faint underline decoration-hairline underline-offset-4 transition-colors duration-fast hover:text-ink-soft"
                  >
                    {row.proofPath}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </LandingSection>
  )
}
