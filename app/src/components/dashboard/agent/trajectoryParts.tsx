'use client'

import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, ChevronRight, FileStack } from 'lucide-react'
import type { TrajTurn, TurnDelta } from '@/lib/api'
import { fmtMs, fmtClock, fmtTokens, fmtSigned } from '@/lib/format'
import { intlLocale } from '@/lib/dateLocale'
import { trajectoryRoleTextClass, trajectoryRoleMarkerClass } from './trajectoryRoleStyles'

// ── P5-4: model trajectory — the numbered step timeline ───

/** When the turn happened, in the language of the surface: the call was pinned
 *  to en-US, so a German interface read the English date form. One helper for
 *  both tooltip sites, so the turn head and its steps never disagree. */
export function turnStamp(
  ts: number | null | undefined,
  language: string | undefined,
): string | undefined {
  if (ts == null) return undefined
  return new Intl.DateTimeFormat(intlLocale(language), {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(ts * 1000))
}
// P6/A3: a header row like ref-12 — six icon buttons, a summary line, search with
// a deferred value; the error case shows role=alert instead of a swallowed
// .catch, so an empty and a failed trajectory stay tellable apart.
export const TRAJ_ICON_BTN = 'p-1 rounded-md text-ink-faint hover:text-foreground hover:bg-surface'

// P6/A3: the backend caps from core/trajectory.py (20 turns / 60 steps) — from the
// turn cap upwards the header shows the truncated notice.
export const MAX_TURNS_NOTICE = 20

// P6/A6: section titles by role (the trajectory norm).
// Lookup is lowercase — the backend delivers the step types UPPERCASE.
export function trajectorySectionTitle(type: string): string {
  switch (type.toLowerCase()) {
    case 'tool_result':
    case 'file_result':
    case 'artifact':
      return 'TOOL RESULT OUTPUT'
    case 'reasoning':
    case 'thinking_start':
    case 'thinking_chunk':
    case 'thinking':
    case 'reflect':
    case 'revision':
      return 'ASSISTANT Reasoning'
    case 'user':
      return 'USER'
    case 'tool_call':
    case 'tool_start':
    case 'tool_done':
      return 'TOOL CALL'
    case 'usage':
      return 'USAGE'
    default:
      return 'ASSISTANT'
  }
}

// P6/A6: a section header above code blocks (the Ephe norm).
function TrajectorySectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-ui-xs uppercase tracking-wf-label text-ink-faint">{children}</p>
  )
}

export const clock = (ts: number | null) => (ts == null ? '' : fmtClock(ts))
export const liveDur = (turn: TrajTurn) =>
  turn.duration_ms ??
  (turn.ts ? Math.max(0, Math.round((Date.now() / 1000 - turn.ts) * 1000)) : null)

// P6/A5: sticky header like ref-12 — number padStart(2),
// on the right IN/OUT tokens + duration + clock from the usage step.
export function TurnHead({
  ti,
  turn,
  delta,
  fileCount = 0,
  onOpenFiles,
}: {
  ti: number
  turn: TrajTurn
  delta: TurnDelta | null | undefined
  /** A3 backwards: what this assignment left behind in the workbench. */
  fileCount?: number
  onOpenFiles?: (turnId: string) => void
}) {
  const { t, i18n } = useTranslation()
  const turnId = turn.turn_id ?? ''
  return (
    <div
      data-testid={`trajectory-turn-head-${ti}`}
      className="col-span-full sticky top-0 z-10 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-b border-border/50 bg-card/90 backdrop-blur-sm px-3 py-2"
    >
      <span className="size-5 font-mono text-ui-xs text-ink-faint">
        {String(ti + 1).padStart(2, '0')}
      </span>
      <span className="text-ui-xs font-semibold text-foreground/90 truncate">
        {turn.model || t('agentPanel.trajectoryTurn')}
      </span>
      {!!turnId && fileCount > 0 && onOpenFiles && (
        <button
          type="button"
          onClick={() => onOpenFiles(turnId)}
          data-testid={`trajectory-turn-files-${ti}`}
          title={t('agentPanel.turnFilesHint')}
          className="inline-flex flex-shrink-0 items-center gap-1 rounded-md border border-hairline px-1.5 py-0.5 font-mono text-ui-2xs text-ink-soft transition-colors hover:border-brand/40 hover:text-foreground"
        >
          <FileStack className="h-3 w-3" aria-hidden="true" />
          {t('agentPanel.turnFiles', { count: fileCount })}
        </button>
      )}
      {(() => {
        const usageStep = turn.steps.find((s) => s.usage)
        const parts: string[] = []
        if (usageStep?.usage) {
          parts.push(`IN ${fmtTokens(usageStep.usage.in ?? 0, i18n.language)}`)
          parts.push(`OUT ${fmtTokens(usageStep.usage.out ?? 0, i18n.language)}`)
          parts.push(fmtMs(usageStep.ms))
        } else if (liveDur(turn) != null) {
          parts.push(fmtMs(liveDur(turn) as number))
        }
        if (turn.ts != null) parts.push(clock(turn.ts))
        if (parts.length === 0) return null
        return (
          <span
            data-testid={`trajectory-turn-meta-${ti}`}
            title={turnStamp(turn.ts, i18n.language)}
            className="ml-auto font-mono text-ui-xs text-ink-faint"
          >
            {parts.join(' · ')}
          </span>
        )
      })()}
      {/* N5: the delta row (only with the switch active, from the 2nd turn on) */}
      {(() => {
        const d = delta
        if (!d || (d.din == null && d.dout == null)) return null
        return (
          <span
            data-testid={`trajectory-delta-${ti}`}
            className="ml-2 font-mono text-ui-xs text-ink-faint"
          >
            {`ΔIN ${d.din == null ? '–' : fmtSigned(d.din, i18n.language)} · ΔOUT ${
              d.dout == null ? '–' : fmtSigned(d.dout, i18n.language)
            }`}
          </span>
        )
      })()}
    </div>
  )
}

// P6/A6: the step rows of a turn — TYPE in the role colour, duration, copy,
// chevron, expandable IN/OUT sections with a ⤢ overlay.
export function TurnSteps({
  ti,
  turn,
  allExpanded,
  openSteps,
  openCode,
  activeStep,
  onStepClick,
  onToggleCode,
}: {
  ti: number
  turn: TrajTurn
  allExpanded: boolean
  openSteps: Set<string>
  openCode: Set<string>
  activeStep: string | null
  onStepClick: (stepKey: string) => void
  onToggleCode: (codeKey: string) => void
}) {
  const { i18n } = useTranslation()
  return (
    <ol className="col-start-2 grid grid-cols-[max-content_minmax(0,1fr)_auto] gap-x-2">
      {turn.steps.map((s) => {
        const stepKey = `${ti}-${s.n}`
        const open = allExpanded || openSteps.has(stepKey)
        // P6 text contents (ref-12): the USER/Reasoning/Output texts
        // sit in the text body — the USER text belongs in the
        // IN section (OUT stays empty), Reasoning/tool output in OUT.
        const isUserStep = s.type.toLowerCase() === 'user'
        const inText = isUserStep && s.text ? s.text : s.title
        const outText =
          s.text && !isUserStep
            ? s.text
            : s.usage
              ? `in ${s.usage.in} · out ${s.usage.out} · ${s.usage.model}`
              : s.state
        return (
          <Fragment key={s.n}>
            {/* P6/A6: a step row inside the subgrid — TYPE in the role colour,
                on the right the duration + full timestamp, copy and chevron. */}
            <li
              data-testid={`trajectory-step-${ti}-${s.n}`}
              data-trajectory-step={stepKey}
              data-active={activeStep === stepKey ? 'true' : undefined}
              data-active-step={activeStep === stepKey ? stepKey : undefined}
              onClick={() => onStepClick(stepKey)}
              className={`col-span-full grid min-h-8 cursor-pointer grid-cols-subgrid items-center border-l-2 px-3 hover:bg-surface ${trajectoryRoleMarkerClass(s.type)} ${
                s.n % 2 === 1 ? '' : 'bg-surface/30'
              }`}
            >
              <span className="font-mono text-ui-sm text-ink-faint text-right">{s.n}</span>
              <div className="col-span-2 flex min-w-0 flex-col gap-1.5 sm:flex-row sm:items-baseline">
                <span
                  data-testid={`trajectory-step-type-${ti}-${s.n}`}
                  className={`font-mono text-ui-sm uppercase tracking-wf-label shrink-0 ${trajectoryRoleTextClass(s.type)}`}
                >
                  {s.type}
                </span>
                <span className="text-ui-xs text-foreground/80 truncate min-w-0">{s.title}</span>
              </div>
              <span className="flex items-center gap-1 justify-self-end">
                <span
                  data-testid={`trajectory-step-meta-${ti}-${s.n}`}
                  title={turnStamp(turn.ts, i18n.language)}
                  className="font-mono text-ui-xs text-ink-faint"
                >
                  {fmtMs(s.ms)}
                </span>
                <button
                  type="button"
                  aria-label="copy"
                  data-testid={`trajectory-copy-${ti}-${s.n}`}
                  className="p-0.5 rounded text-ink-faint hover:text-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    void navigator.clipboard
                      ?.writeText(s.text || s.title || s.state || '')
                      ?.catch(() => undefined)
                  }}
                >
                  <Copy className="size-3" aria-hidden="true" />
                </button>
                <span data-testid={`trajectory-chevron-${ti}-${s.n}`}>
                  <ChevronRight
                    className={`size-3 text-ink-faint transition-transform ${open ? 'rotate-90' : ''}`}
                    aria-hidden="true"
                  />
                </span>
              </span>
            </li>
            {open && (
              <Fragment key={`detail-${stepKey}`}>
                <li aria-hidden="true" className="col-span-full h-px bg-border/50" />
                {(['in', 'out'] as const).map((dir) => {
                  const body = dir === 'in' ? inText : outText
                  const codeKey = `${stepKey}-${dir}`
                  const wide = openCode.has(codeKey)
                  return (
                    <li
                      key={dir}
                      data-testid={`trajectory-section-${ti}-${s.n}-${dir}`}
                      className="col-span-full rounded-lg border border-card-border px-2 py-1"
                    >
                      <TrajectorySectionTitle>
                        {trajectorySectionTitle(s.type)}
                      </TrajectorySectionTitle>
                      {body ? (
                        <div className="relative">
                          <pre
                            data-testid={`trajectory-code-${ti}-${s.n}-${dir}`}
                            className={`max-w-full overflow-auto whitespace-pre-wrap break-words rounded-md bg-surface px-2 py-1.5 text-ui-sm ${
                              wide ? 'max-h-none' : 'max-h-64'
                            }`}
                          >
                            {body}
                          </pre>
                          {/* P6/A6: floating ⤢-overlay right, centred
                              in the pre — opens to the pane height. */}
                          <button
                            type="button"
                            aria-label="expand"
                            data-testid={`trajectory-code-expand-${ti}-${s.n}-${dir}`}
                            className="absolute right-1 top-1/2 -translate-y-1/2 rounded bg-surface/90 px-1 text-ui-xs text-ink-soft hover:text-foreground"
                            onClick={() => onToggleCode(codeKey)}
                          >
                            ⤢
                          </button>
                        </div>
                      ) : (
                        <p
                          data-testid={`trajectory-section-empty-${ti}-${s.n}-${dir}`}
                          className="p-3 text-ui-sm text-foreground-subtlest"
                        >
                          –
                        </p>
                      )}
                    </li>
                  )
                })}
                <li aria-hidden="true" className="col-span-full h-px bg-border/50" />
              </Fragment>
            )}
          </Fragment>
        )
      })}
    </ol>
  )
}
