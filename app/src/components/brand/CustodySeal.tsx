'use client'

/**
 * The four-eyes seal: the moth's two crimson ties, filled and still.
 *
 * The tie that pulses on the bar means "waiting for you"; here both are tied, so
 * the seal is the picture of a letter closed — it appears only where the record
 * carries the second signature, and it says nothing the record does not.
 */
import { useTranslation } from 'react-i18next'
import { PaperMothGlyph } from './PaperMothGlyph'

export function CustodySeal({ testId = 'custody-seal' }: { testId?: string }) {
  const { t } = useTranslation()
  return (
    <span
      data-testid={testId}
      data-sealed="true"
      className="inline-flex items-center gap-1.5 rounded-full border border-brand/40 bg-brand/10 px-2 py-0.5 text-ui-xs text-brand"
    >
      <PaperMothGlyph size="14px" testId={`${testId}-glyph`} />
      {t('custody.sealed')}
    </span>
  )
}
