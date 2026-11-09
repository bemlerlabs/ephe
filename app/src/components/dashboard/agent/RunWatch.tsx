'use client'

/**
 * The run view: one page, large enough to follow, with pause, stop, and takeover.
 *
 * It sits outside the tool card. A browser step that is still running brings it up.
 * Takeover is the only mode in which a click on the picture reaches the page.
 * Hand-back returns the evidence line the agent has to read next.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserWatch } from './BrowserWatch'
import { parseStepEvidence } from '@/lib/browserStepEvidence'
import { pointerToViewport } from '@/lib/browserPointer'
import { postBrowserAct, postBrowserHold, type HoldAction } from '@/lib/browserRun'
import { requestRunStop } from '@/lib/runControl'
import type { WatchFrame } from '@/lib/browserWatch'

export function RunWatch({ session }: { session: string }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('running')
  const [evidence, setEvidence] = useState<string | null>(null)

  async function hold(action: HoldAction): Promise<void> {
    try {
      const result = await postBrowserHold(session, action)
      setMode(result.mode)
      if (result.evidence) setEvidence(result.evidence)
    } catch {
      // A hold the current mode refuses leaves the view where it is.
    }
  }

  async function onStop(): Promise<void> {
    try {
      await hold('stop')
    } finally {
      requestRunStop()
    }
  }

  async function onFramePointer(
    frame: WatchFrame,
    box: DOMRect,
    clientX: number,
    clientY: number,
  ): Promise<void> {
    if (mode !== 'takeover') return
    const point = pointerToViewport(
      frame,
      { left: box.left, top: box.top, width: box.width, height: box.height },
      clientX,
      clientY,
    )
    if (!point) return
    try {
      await postBrowserAct(session, { kind: 'click', x: point.x, y: point.y })
    } catch {
      // A click the page refuses stays on the picture. The mode does not change.
    }
  }

  const verdict = evidence ? parseStepEvidence(evidence)?.verdict : null

  return (
    <section
      data-testid="run-watch"
      data-session={session}
      data-mode={mode}
      className="mt-2 space-y-2"
    >
      <BrowserWatch
        session={session}
        large
        onFramePointer={(frame, box, x, y) => void onFramePointer(frame, box, x, y)}
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="run-watch-pause"
          className="rounded-md border border-hairline px-2 py-1 text-ui-xs text-ink-soft"
          onClick={() => void hold(mode === 'paused' ? 'resume' : 'pause')}
        >
          {mode === 'paused'
            ? t('chat.watchResume', { defaultValue: 'Resume' })
            : t('chat.watchPause', { defaultValue: 'Pause' })}
        </button>
        <button
          type="button"
          data-testid="run-watch-stop"
          className="rounded-md border border-hairline px-2 py-1 text-ui-xs text-ink-soft"
          onClick={() => void onStop()}
        >
          {t('chat.watchStop', { defaultValue: 'Stop' })}
        </button>
        <button
          type="button"
          data-testid="run-watch-takeover"
          className="rounded-md border border-hairline px-2 py-1 text-ui-xs text-ink-soft"
          onClick={() => void hold(mode === 'takeover' ? 'handback' : 'takeover')}
        >
          {mode === 'takeover'
            ? t('chat.watchHandback', { defaultValue: 'Hand back' })
            : t('chat.watchTakeover', { defaultValue: 'Take over' })}
        </button>
      </div>
      {verdict && (
        <p
          data-testid="run-watch-note"
          data-verdict={verdict}
          className="text-ui-2xs text-ink-faint"
        >
          {verdict === 'observed'
            ? t('chat.watchHeldObserved', { defaultValue: 'The page moved while you held it.' })
            : t('chat.watchHeldStill', {
                defaultValue: 'The page showed no change while you held it.',
              })}
        </p>
      )}
    </section>
  )
}
