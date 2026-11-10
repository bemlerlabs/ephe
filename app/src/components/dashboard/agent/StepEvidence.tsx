'use client'

/**
 * #88 — the verdict a browser step already carries, put next to the page it describes.
 *
 * `core/browser.py` ends each action with a `STEP_EVIDENCE:` line: the numbers the document
 * changed by, and `observed` only when one of them moved. The audit row keeps it; the run
 * surface read the step's prose and left the verdict inside it, so a reader watching a page
 * had no way to tell a step the environment confirmed from one it merely did not argue with.
 *
 * What shows here is the verdict and the counts. The backend's reason sentence stays in the
 * trail: it is English prose typed by the server, and a German reader would meet it as a
 * leak. Numbers and one verdict word need no translation to be honest.
 */
import { useTranslation } from 'react-i18next'
import { CircleSlash, Eye } from 'lucide-react'
import {
  evidenceFacts,
  parseStepEvidence,
  signed,
  type EvidenceFact,
} from '@/lib/browserStepEvidence'

/** One key per fact the parser can emit. The record is total over the kind, so a fact
 *  arrives with a word or the build does not compile — a fallback string here would be a
 *  key no bundle carries and no reader ever sees. */
const FACT_WORD: Record<EvidenceFact['kind'], string> = {
  elements: 'chat.stepElements',
  characters: 'chat.stepCharacters',
  scrolled: 'chat.stepScrolled',
  checked: 'chat.stepChecked',
  address: 'chat.stepAddress',
  title: 'chat.stepTitle',
  focus: 'chat.stepFocus',
}

export function StepEvidence({ result }: { result: string | null | undefined }) {
  const { t } = useTranslation()
  const evidence = parseStepEvidence(result)
  if (!evidence) return null
  const facts = evidenceFacts(evidence)
  const observed = evidence.verdict === 'observed'

  return (
    <div
      data-testid="step-evidence"
      data-verdict={evidence.verdict}
      className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-hairline bg-canvas/40 px-2 py-1 text-ui-2xs"
    >
      <span className="flex items-center gap-1 text-ink-soft">
        {observed ? (
          <Eye className="h-3 w-3 text-status-ok" aria-hidden="true" />
        ) : (
          <CircleSlash className="h-3 w-3 text-status-warning" aria-hidden="true" />
        )}
        <span data-testid="step-evidence-verdict">
          {observed
            ? t('chat.stepObserved', { defaultValue: 'Read from the page' })
            : t('chat.stepUnproven', { defaultValue: 'No change the page showed' })}
        </span>
      </span>
      {facts.map((fact) => (
        <span
          key={fact.kind}
          className="font-mono text-ink-faint"
          data-testid={`step-evidence-${fact.kind}`}
        >
          {t(FACT_WORD[fact.kind], {
            delta: signed(fact.value),
            defaultValue: signed(fact.value),
          })}
        </span>
      ))}
    </div>
  )
}
