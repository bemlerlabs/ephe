'use client'

/**
 * R29 follow-up: what the agent actually read.
 *
 * The settings report over `GET /api/context/stages`: every stage of the
 * assembled prompt with its share, and under the workspace rules every file
 * the resolver saw with the status it reported. The route builds these stages
 * with the same resolver a run uses, so the figures here are the prompt, not a
 * reconstruction of it. A cap is shown where it was hit (a cut file, a file
 * without room), and the empty state says that the backend answered with no
 * stage instead of drawing an empty list.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Layers, Loader2, RefreshCw, ShieldCheck } from 'lucide-react'

import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { formatNumber } from '@/lib/dateLocale'
import {
  isKnownRuleStatus,
  loadContextReport,
  type ContextReport as Report,
} from '@/lib/api/contextReport'

/** Stage names come from the backend; a name without a label renders as itself. */
const STAGE_LABEL_KEYS: Record<string, string> = {
  identity: 'settings.context.stage.identity',
  persona: 'settings.context.stage.persona',
  tool_guidelines: 'settings.context.stage.toolGuidelines',
  custom_instructions: 'settings.context.stage.customInstructions',
  workspace_rules: 'settings.context.stage.workspaceRules',
  user_profile: 'settings.context.stage.userProfile',
  corrections: 'settings.context.stage.corrections',
  feedback: 'settings.context.stage.feedback',
  date: 'settings.context.stage.date',
}

type Load = { status: 'loading' } | { status: 'ready'; report: Report } | { status: 'error' }

export default function ContextReport() {
  const { t, i18n } = useTranslation()
  const [state, setState] = useState<Load>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    loadContextReport()
      .then((report) => {
        if (live) setState({ status: 'ready', report })
      })
      .catch(() => {
        if (live) setState({ status: 'error' })
      })
    return () => {
      live = false
    }
  }, [attempt])

  const reload = () => setAttempt((n) => n + 1)
  const number = (value: number, digits = 0) => formatNumber(value, i18n.language, digits)

  const stageLabel = (name: string) => {
    const key = STAGE_LABEL_KEYS[name]
    return key ? t(key) : name
  }

  const statusLabel = (status: string) => {
    if (isKnownRuleStatus(status)) return t(`statusBar.ruleStatus.${status}`)
    return status
  }

  const statusTone = (status: string) => {
    if (status === 'included')
      return 'border-status-success/40 bg-status-success/10 text-status-success'
    if (status === 'truncated')
      return 'border-status-warning/40 bg-status-warning/10 text-status-warning'
    if (status === 'denied' || status === 'unreadable')
      return 'border-status-danger/40 bg-status-danger/10 text-status-danger'
    return 'border-hairline bg-surface text-ink-faint'
  }

  const caps = state.status === 'ready' ? state.report.caps : null
  const hasRuleFiles =
    state.status === 'ready' && state.report.stages.some((stage) => stage.files.length > 0)
  const capLines: string[] = []
  if (caps) {
    if (!hasRuleFiles) capLines.push(t('settings.context.capsNoFiles'))
    else if (caps.truncatedFiles === 0 && caps.filesWithoutBudget === 0) {
      capLines.push(t('settings.context.capsNone'))
    } else {
      if (caps.truncatedFiles > 0) {
        capLines.push(
          t('settings.context.capsTruncated', {
            count: caps.truncatedFiles,
            chars: number(caps.truncatedChars),
          }),
        )
      }
      if (caps.filesWithoutBudget > 0) {
        capLines.push(t('settings.context.capsSkipped', { count: caps.filesWithoutBudget }))
      }
    }
  }

  return (
    <div className="space-y-3" data-testid="context-report">
      <PageHeader
        title={t('settings.context.title')}
        subtitle={t('settings.context.subtitle')}
        actions={
          <button
            type="button"
            onClick={reload}
            data-testid="context-report-refresh"
            aria-label={t('settings.context.refresh')}
            title={t('settings.context.refresh')}
            className="focus-ring inline-flex min-h-9 min-w-9 items-center justify-center rounded-lg text-ink-soft transition-colors hover:bg-surface hover:text-ink pointer-coarse:min-h-11 pointer-coarse:min-w-11"
          >
            <RefreshCw
              className={`h-4 w-4 ${state.status === 'loading' ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
          </button>
        }
      />

      {state.status === 'loading' && (
        <div data-testid="context-report-loading" className="flex h-24 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-brand/50" aria-hidden="true" />
        </div>
      )}

      {state.status === 'error' && (
        <div
          role="alert"
          data-testid="context-report-error"
          className="rounded-xl border border-status-danger/30 bg-status-danger/10 px-4 py-3"
        >
          <p className="flex items-start gap-2 text-scale-ui text-status-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">{t('settings.context.unreachable')}</span>
          </p>
          <button
            type="button"
            onClick={reload}
            data-testid="context-report-retry"
            className="focus-ring mt-2 inline-flex min-h-8 items-center rounded-lg border border-hairline px-2.5 py-1 text-scale-ui text-ink-soft transition-colors hover:bg-surface hover:text-ink pointer-coarse:min-h-11"
          >
            {t('settings.context.retry')}
          </button>
        </div>
      )}

      {state.status === 'ready' && state.report.stages.length === 0 && (
        <div
          data-testid="context-report-empty"
          className="rounded-xl border border-hairline bg-surface px-4 py-4"
        >
          <Layers className="h-5 w-5 text-ink-faint" aria-hidden="true" />
          <p className="mt-2 text-scale-ui text-ink">{t('settings.context.emptyTitle')}</p>
          <p className="mt-1 text-scale-data text-ink-faint">{t('settings.context.emptyBody')}</p>
        </div>
      )}

      {state.status === 'ready' && state.report.stages.length > 0 && (
        <>
          <div
            data-testid="context-report-total"
            className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-1"
          >
            <span className="font-mono text-scale-data tabular-nums text-ink">
              {number(state.report.totalChars)}
            </span>
            <span className="text-scale-data text-ink-faint">
              {t('settings.context.layersCount', { count: state.report.stages.length })}
            </span>
          </div>

          <SettingsGroup
            icon={Layers}
            title={t('settings.context.stagesTitle')}
            testid="context-report-stages"
          >
            {state.report.stages.map((stage) => {
              const share =
                state.report.totalChars > 0 ? (stage.chars / state.report.totalChars) * 100 : 0
              return (
                <div key={stage.name} data-testid={`context-report-stage-${stage.name}`}>
                  <SettingsRow
                    title={stageLabel(stage.name)}
                    description={t('settings.context.stageFigures', {
                      chars: number(stage.chars),
                      percent: number(share, 1),
                    })}
                    testid={`context-report-stage-row-${stage.name}`}
                  />
                  {stage.files.length > 0 && (
                    <ul
                      data-testid={`context-report-files-${stage.name}`}
                      className="space-y-1.5 px-4 pb-3"
                    >
                      {stage.files.map((file, index) => (
                        <li
                          key={`${file.name}-${index}`}
                          data-testid="context-report-file"
                          data-status={file.status || undefined}
                          data-reason={file.reason || undefined}
                          className="flex flex-wrap items-center gap-x-2 gap-y-1 text-scale-data"
                        >
                          <span
                            className="min-w-0 flex-1 truncate font-mono text-ink-soft"
                            title={file.name}
                          >
                            {file.name}
                          </span>
                          <span className="shrink-0 font-mono tabular-nums text-ink-faint">
                            {number(file.chars)}
                          </span>
                          {file.status && (
                            <span
                              data-testid={`context-report-badge-${file.status}`}
                              data-status={file.status}
                              title={file.reason || undefined}
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-ui-2xs ${statusTone(file.status)}`}
                            >
                              {statusLabel(file.status)}
                            </span>
                          )}
                          {file.reason && (
                            <span className="w-full font-mono text-ui-2xs text-ink-faint">
                              {t('settings.context.fileReason', { reason: file.reason })}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </SettingsGroup>

          <SettingsGroup
            icon={ShieldCheck}
            title={t('settings.context.capsTitle')}
            description={t('settings.context.capsHint')}
            testid="context-report-caps"
          >
            <div
              data-testid="context-report-caps-body"
              className="space-y-1 px-4 py-3 text-scale-data text-ink-soft"
            >
              {capLines.map((line) => (
                <p key={line} className="break-words">
                  {line}
                </p>
              ))}
            </div>
          </SettingsGroup>

          <p className="px-1 text-scale-data text-ink-faint" data-testid="context-report-note">
            {t('settings.context.readNote')}
          </p>
        </>
      )}
    </div>
  )
}
