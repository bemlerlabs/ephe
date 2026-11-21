'use client'

/**
 * #88 — the watched page, in the state it is actually in.
 *
 * The run surface needs one thing from a browser session: what is on the screen right now,
 * or the reason there is nothing to show. The four states below are the ones the transport
 * can prove (`app/src/lib/browserWatch.ts`), and each gets its own sentence because a pane
 * that only ever shows a picture would leave a reader guessing whether the run had stalled.
 *
 * The frame carries two coordinate spaces: the page's own viewport and the size the cast
 * was asked for. The picture is drawn in the cast space and the overlay in #87 has to be
 * placed in the viewport space, so both are read from the payload rather than assumed
 * equal.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleDot, Loader2 } from 'lucide-react'
import { watchBrowserSession, type WatchFrame, type WatchSnapshot } from '@/lib/browserWatch'

/** The newest frame, drawn at the aspect ratio the page it came from has. */
function WatchPicture({
  frame,
  alt,
  large,
  onFramePointer,
}: {
  frame: WatchFrame
  alt: string
  large: boolean
  onFramePointer?: (frame: WatchFrame, box: DOMRect, clientX: number, clientY: number) => void
}) {
  const ratio =
    frame.viewportWidth > 0 && frame.viewportHeight > 0
      ? `${frame.viewportWidth} / ${frame.viewportHeight}`
      : undefined
  return (
    <img
      src={`data:image/jpeg;base64,${frame.jpeg}`}
      alt={alt}
      data-testid="browser-watch-frame"
      data-viewport={`${frame.viewportWidth}x${frame.viewportHeight}`}
      data-cast={`${frame.castWidth}x${frame.castHeight}`}
      className={
        large
          ? 'max-h-[70vh] min-h-64 w-full rounded-md border border-hairline bg-canvas object-contain'
          : 'w-full max-h-64 rounded-md border border-hairline bg-canvas object-contain'
      }
      style={ratio ? { aspectRatio: ratio } : undefined}
      onClick={
        onFramePointer
          ? (event) =>
              onFramePointer(
                frame,
                event.currentTarget.getBoundingClientRect(),
                event.clientX,
                event.clientY,
              )
          : undefined
      }
    />
  )
}

function FrameProof({ frame }: { frame: WatchFrame }) {
  const { t } = useTranslation()
  const audit = frame.audit ?? null
  if (!audit) {
    return (
      <p
        data-testid="browser-watch-proof"
        data-audit="missing"
        className="text-ui-2xs text-ink-faint"
      >
        {t('chat.watchUnproven', { defaultValue: 'This frame has no audit row.' })}
      </p>
    )
  }
  return (
    <p
      data-testid="browser-watch-proof"
      data-audit="bound"
      data-kind={audit.kind}
      data-verdict={audit.verdict}
      className="font-mono text-ui-2xs text-ink-faint"
    >
      {t('chat.watchBound', {
        kind: audit.kind,
        tool: audit.tool,
        ts: audit.ts,
        defaultValue: '{{kind}} {{tool}} {{ts}}',
      })}
    </p>
  )
}

export function BrowserWatch({
  session,
  large = false,
  onFramePointer,
}: {
  session: string
  large?: boolean
  onFramePointer?: (frame: WatchFrame, box: DOMRect, clientX: number, clientY: number) => void
}) {
  const { t } = useTranslation()
  const [snapshot, setSnapshot] = useState<WatchSnapshot | null>(null)

  useEffect(() => watchBrowserSession(session, setSnapshot), [session])

  const phase = snapshot?.phase ?? 'connecting'
  const frame = snapshot?.frame ?? null
  const refusal = snapshot?.refusal ?? null

  return (
    <div
      data-testid="browser-watch"
      data-phase={phase}
      className="space-y-1.5 rounded-md border border-hairline bg-canvas/40 p-2"
    >
      <div className="flex items-center gap-2 text-ui-2xs text-ink-faint">
        {phase === 'casting' && (
          <CircleDot className="h-3 w-3 text-status-ok opacity-80" aria-hidden="true" />
        )}
        {phase === 'connecting' && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
        <span data-testid="browser-watch-state">
          {phase === 'refused' && refusal
            ? // The reader's own sentence, filled from the params the route sent; the
              // server's English is the fallback under it.
              t(`serverError.${refusal.code}`, {
                ...refusal.params,
                defaultValue: refusal.message,
              })
            : phase === 'connecting'
              ? t('chat.watchConnecting', { defaultValue: 'Opening the view…' })
              : phase === 'ended'
                ? t('chat.watchEnded', {
                    defaultValue: 'This browser session is no longer running.',
                  })
                : phase === 'unchanged'
                  ? t('chat.watchUnchanged', {
                      seconds: Math.round(snapshot?.ageS ?? 0),
                      defaultValue: 'The page has not changed for {{seconds}} s.',
                    })
                  : t('chat.watchLive', { defaultValue: 'Live — the page Ephe is working on' })}
        </span>
      </div>
      {frame && (
        <>
          <WatchPicture
            frame={frame}
            large={large}
            onFramePointer={onFramePointer}
            alt={t('chat.watchAlt', { defaultValue: 'The page Ephe is working on right now' })}
          />
          <FrameProof frame={frame} />
        </>
      )}
    </div>
  )
}
