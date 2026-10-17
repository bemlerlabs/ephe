'use client'

import { useTranslation } from 'react-i18next'
import type { SubagentDetail } from '@/lib/api'
import { LoadingRow } from '@/components/ui'
import { fmtMs } from '@/lib/format'

export function SubagentDetailBlock({
  backendId,
  detail,
  liveDur,
}: {
  backendId: string
  detail: SubagentDetail | null
  liveDur: number | null
}) {
  const { t } = useTranslation()
  return (
    <div data-testid={`subagent-expanded-${backendId}`} className="mt-2 pl-6 space-y-1">
      {detail ? (
        <>
          {detail.task && (
            <p
              data-testid={`subagent-prompt-${backendId}`}
              className="text-ui-sm leading-snug text-ink-soft line-clamp-3"
            >
              <span className="text-ink-faint">{t('agentPanel.subagentPrompt')} </span>
              {detail.task}
            </p>
          )}
          {detail.tool_calls.length > 0 && (
            <ol className="space-y-0.5">
              {detail.tool_calls.map((tc, i) => (
                <li
                  key={i}
                  data-testid={`subagent-step-${i}`}
                  className="flex items-baseline gap-2 text-ui-sm text-ink-soft"
                >
                  <span className="shrink-0 font-mono text-ink-faint tabular-nums">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono">
                    {tc.tool}
                    {tc.args_preview ? ` · ${tc.args_preview}` : ''}
                  </span>
                  <span
                    data-testid={`subagent-step-duration-${i}`}
                    className="shrink-0 text-right font-mono text-ink-faint tabular-nums"
                  >
                    {fmtMs(tc.ms)}
                  </span>
                </li>
              ))}
            </ol>
          )}
          {/* running: elapsed time live (ticking), finished: measured */}
          {liveDur != null && (
            <p data-testid={`subagent-worked-${backendId}`} className="text-ui-xs text-ink-faint">
              {t('agentPanel.subagentWorked', { time: fmtMs(liveDur) })}
            </p>
          )}
          {detail.report && (
            <div className="mt-1.5 space-y-1">
              <p className="font-mono text-ui-xs uppercase tracking-wf-label text-ink-faint">
                {t('agentPanel.subagentReport')}
              </p>
              <p
                data-testid={`subagent-report-${backendId}`}
                className="text-ui-sm leading-relaxed text-foreground/85 whitespace-pre-wrap"
              >
                {detail.report}
              </p>
            </div>
          )}
        </>
      ) : (
        <LoadingRow label={t('agentPanel.subagentLoading')} className="py-1" />
      )}
    </div>
  )
}
