import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'
import { StorageFootprint } from './StorageFootprint'
import CodebaseStatusBarPill from '../CodebaseStatusBarPill'
import CodebaseIndexDialog from '../CodebaseIndexDialog'

/**
 * The figures that used to sit in the visible status row — the raw task/MB
 * footprint, the free-of-window pair and the index state. They are still one
 * click away (the status pill opens this), but the row the reader looks at all
 * day now states only status, connection and the context remainder in percent.
 *
 * The index pill is mounted here on purpose: its status request runs when the
 * popover opens, not on every boot.
 */
export default function StatusDetails({
  remaining,
  window,
  tokenizer,
}: {
  remaining: number
  window: number
  tokenizer: string | null
}) {
  const { t, i18n } = useTranslation()
  const [codebaseOpen, setCodebaseOpen] = useState(false)
  return (
    <section
      data-testid="status-details"
      className="mt-2 space-y-1.5 border-t border-hairline pt-2"
    >
      <p className="text-ui-2xs uppercase tracking-wide text-ink-faint">
        {t('statusBar.detailsTitle')}
      </p>
      <p className="font-mono text-ui-xs tabular-nums text-ink-faint">
        {window
          ? t('statusBar.contextFreeOf', {
              free: formatNumber(remaining, i18n.language),
              window: formatNumber(window, i18n.language),
            })
          : `${formatNumber(remaining, i18n.language)} ${t('statusBar.contextFree')}`}
        {tokenizer === 'tiktoken-bpe' && (
          <span
            data-testid="statusbar-tokenizer-chip"
            className="ml-1.5"
            title={t('status.bpeExact')}
          >
            ·bpe
          </span>
        )}
      </p>
      <StorageFootprint />
      <CodebaseStatusBarPill onOpen={() => setCodebaseOpen(true)} />
      <CodebaseIndexDialog open={codebaseOpen} onClose={() => setCodebaseOpen(false)} />
    </section>
  )
}
