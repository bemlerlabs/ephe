import { useEffect, useState } from 'react'
import { BrainCircuit, ChevronRight, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDeepBool, useDeepSelect } from '@/lib/deepSettings'
import { audienceOf, proofText } from '@/lib/proofAudience'
import { fmtMs } from '@/lib/format'
import { formatDurationShort, formatThinkingLabel } from '@/lib/thinking'
import { classifyToolCall } from '@/lib/toolCardModel'
import type { ThinkingPhase } from '@/types'
import { ICONS, isToolError } from '@/lib/toolRound'
import { ToolCallDetails } from '../ToolCallDisplay'
import type { RoundEvent } from './calmRounds'

/**
 * UI-CHAT — one calm row per working round.
 *
 * A round is the thoughts and the calls that belong together. It renders as
 * exactly one line: tool name · duration · outcome, plus a quiet brain+seconds
 * when the thought is part of the call. The chevron opens the body, which holds
 * the reasoning text and every call detail (arguments, output, digest) — the
 * transcript never repeats a name or prints a "completed" suffix.
 */
export function RoundRow({
  events,
  streaming,
  defaultOpen = false,
  suppressWatch = false,
}: {
  events: RoundEvent[]
  streaming?: boolean
  defaultOpen?: boolean
  suppressWatch?: boolean
}) {
  const { t } = useTranslation()
  const detailsMode = useDeepSelect('chat.details_mode', 'expanded')
  const showCount = useDeepBool('chat.show_tool_count', true)
  const calls = events.filter((event) => event.kind === 'call').map((event) => event.call)
  const thoughts = events.filter((event) => event.kind === 'thought').map((event) => event.phase)

  const live = streaming !== false
  const running =
    live &&
    (calls.some((call) => call.status === 'pending') ||
      thoughts.some((phase) => phase.end === null))
  const failed =
    calls.some(isToolError) ||
    calls.some((call) => call.status === 'failed' || call.status === 'denied')
  const waiting = calls.some((call) => call.status === 'waiting')
  const total = calls.length
  const done = calls.filter((call) => call.status !== 'pending').length
  const family = calls[0] ? classifyToolCall(calls[0]).family : 'generic'
  const Icon = ICONS[calls[0] ? classifyToolCall(calls[0]).icon : 'wrench'] ?? ICONS.wrench

  const knownDurations = calls
    .map((call) => call.duration_ms)
    .filter((ms): ms is number => typeof ms === 'number')
  const durationMs =
    knownDurations.length > 0 ? knownDurations.reduce((sum, ms) => sum + ms, 0) : null

  // Live thought seconds tick like the thinking block, so the row is never a
  // frozen number while the model is still thinking.
  const liveThought = thoughts.some((phase) => phase.end === null)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!liveThought) return
    setNow(Date.now())
    const handle = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(handle)
  }, [liveThought])
  const thoughtMs = thoughts.reduce((sum, phase) => {
    const end = phase.end ?? now
    return sum + Math.max(0, end - phase.start)
  }, 0)

  // Failures and approvals open themselves; everything else waits for a click.
  const [open, setOpen] = useState(() => defaultOpen || failed || waiting)
  useEffect(() => {
    if (failed || waiting) setOpen(true)
  }, [failed, waiting])

  const outcome = running
    ? t('chat.rowWorking')
    : failed
      ? t('chat.rowFailed')
      : waiting
        ? t('chat.toolWaiting')
        : t('chat.roundOk')

  const thoughtLabel =
    thoughts.length === 1
      ? formatThinkingLabel(thoughtMs, t)
      : t('chat.thoughtForSecondsCount', {
          duration: formatDurationShort(thoughtMs),
          count: thoughts.length,
        })

  const hasBody = calls.length > 0 || thoughts.length > 0
  const tailSource = [...calls]
    .reverse()
    .map((call) => call.stdout)
    .find((tail) => !!tail)
  const tailLine = tailSource
    ? tailSource
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .slice(-2)
        .join(' ')
    : ''
  const groupMs = durationMs ?? 0
  const proof =
    !running && calls.length > 0
      ? proofText(audienceOf(detailsMode), { ok: !failed, ms: groupMs || null })
      : null

  return (
    <div
      data-testid={calls.length > 0 ? `tool-stream-row-${family}` : 'thought-row'}
      data-calm-row={calls.length > 0 ? 'tool' : 'thought'}
      className="max-w-full"
    >
      <button
        type="button"
        data-testid={running ? 'tool-stream-row-active' : undefined}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={
          calls.length > 0 ? `${calls.map((call) => call.name).join(', ')} Details` : thoughtLabel
        }
        className="group flex w-full min-w-0 items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-surface"
      >
        {running ? (
          <Loader2
            data-testid="tool-row-spinner"
            className="h-3 w-3 shrink-0 animate-spin text-brand"
            aria-hidden="true"
          />
        ) : calls.length > 0 ? (
          <Icon className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
        ) : (
          <BrainCircuit className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
        )}

        {calls.length > 0 ? (
          <>
            <span
              data-testid="round-tool-name"
              className="min-w-0 truncate font-mono text-ui-xs text-ink-soft group-hover:text-foreground/80"
              title={calls.map((call) => call.name).join(', ')}
            >
              {calls[0]?.name}
            </span>
            {showCount && total > 1 && (
              <span data-testid="round-count" className="shrink-0 text-ui-xs text-ink-faint">
                {running ? `${done}/${total}` : `${total}×`}
              </span>
            )}
            {durationMs !== null && (
              <span
                data-testid="round-duration"
                className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint"
              >
                {fmtMs(Math.round(durationMs))}
              </span>
            )}
            <span
              data-testid="tool-row-status"
              className={`shrink-0 text-ui-xs ${
                running
                  ? 'text-brand'
                  : failed
                    ? 'text-status-danger'
                    : 'text-ink-faint group-hover:text-ink-soft'
              }`}
            >
              · {outcome}
            </span>
            {thoughts.length > 0 && (
              <span
                data-testid="round-thought"
                aria-label={
                  thoughts.length === 1 ? formatThinkingLabel(thoughtMs, t) : thoughtLabel
                }
                title={thoughtLabel}
                className="inline-flex shrink-0 items-center gap-0.5 text-ui-2xs tabular-nums text-ink-faint"
              >
                <BrainCircuit className="h-3 w-3" aria-hidden="true" />
                {formatDurationShort(thoughtMs)}
              </span>
            )}
            {running && tailLine !== '' && (
              <span
                data-testid="tool-row-tail"
                className="min-w-0 line-clamp-1 font-mono text-ui-2xs text-ink-faint"
              >
                {tailLine}
              </span>
            )}
          </>
        ) : (
          <span
            data-testid="round-thought-label"
            className="min-w-0 truncate text-ui-xs text-ink-soft"
          >
            {thoughtLabel}
          </span>
        )}

        <ChevronRight
          className={`ml-auto h-3 w-3 shrink-0 text-ink-faint transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && hasBody && (
        <div
          className="mb-1 ml-2 mt-1 space-y-2 border-l border-hairline pl-2.5"
          data-testid="round-body"
        >
          {events.map((event, index) =>
            event.kind === 'thought' ? (
              <ThoughtDetail key={`thought-${index}`} phase={event.phase} />
            ) : (
              <div key={`call-${event.call.id}`} data-testid="round-call">
                {calls.length > 1 && (
                  <div
                    data-testid="round-call-head"
                    className="flex items-center gap-1.5 text-ui-2xs text-ink-faint"
                  >
                    <span className="font-mono text-ink-soft">{event.call.name}</span>
                    {event.call.duration_ms != null && (
                      <span className="tabular-nums">
                        {fmtMs(Math.round(event.call.duration_ms))}
                      </span>
                    )}
                    <span>
                      ·{' '}
                      {isToolError(event.call) || event.call.status === 'failed'
                        ? t('chat.rowFailed')
                        : t('chat.roundOk')}
                    </span>
                  </div>
                )}
                <ToolCallDetails tool={event.call} suppressWatch={suppressWatch} />
                {event.call.stdout ? (
                  <pre
                    data-testid="tool-stdout-tail"
                    className="mt-1 rounded bg-canvas border border-hairline px-2 py-1.5 font-mono text-ui-sm leading-relaxed text-ink-faint whitespace-pre-wrap break-all overflow-x-auto"
                  >
                    {event.call.stdout.split('\n').slice(-12).join('\n')}
                  </pre>
                ) : null}
              </div>
            ),
          )}
          {proof && (
            <div
              data-testid="tool-row-proof"
              className={`tabular-nums text-ui-2xs ${
                failed ? 'text-status-danger/90' : 'text-ink-faint'
              }`}
            >
              {t(proof.key, proof.values)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** The reasoning behind a round — one block per thought phase, in order. */
function ThoughtDetail({ phase }: { phase: ThinkingPhase }) {
  const { t } = useTranslation()
  const ms = Math.max(0, (phase.end ?? Date.now()) - phase.start)
  return (
    <div data-testid="round-thought-detail" className="space-y-0.5">
      <div className="text-ui-2xs uppercase tracking-wide text-ink-faint">
        {formatThinkingLabel(ms, t)}
      </div>
      <div
        data-testid="round-thought-text"
        className="whitespace-pre-wrap break-words text-ui-xs leading-relaxed text-ink-faint"
      >
        {phase.text || <span className="italic">{t('chat.thinkingEmpty')}</span>}
      </div>
    </div>
  )
}
