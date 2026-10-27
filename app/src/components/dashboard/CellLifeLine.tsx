'use client'

/**
 * WP5 — the life line.
 *
 * It shows what the cell registry really knows about this session: which number it
 * has, how long its calls took on average, whether it is alive. It says nothing
 * when the registry knows nothing — and it does not vanish without a word: the
 * death runs through the same decay edge as the badge.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getCellLife, type CellLife } from '@/lib/api'

const POLL_MS = 5000
/** Must match `--ephe-decay-duration` in globals.css (380 ms + buffer). */
const DECAY_MS = 460

type Phase = 'silent' | 'alive' | 'dying' | 'gone'

export function CellLifeLine({ sessionId }: { sessionId: string }) {
  const { t, i18n } = useTranslation()
  const [phase, setPhase] = useState<Phase>('silent')
  const [life, setLife] = useState<CellLife | null>(null)
  const sawLife = useRef(false)
  const decay = useRef<number | undefined>(undefined)

  useEffect(() => {
    sawLife.current = false
    setPhase('silent')
    setLife(null)
  }, [sessionId])

  useEffect(() => {
    let cancelled = false
    const read = () => {
      // A hidden window does not ask for a life it cannot see.
      if (typeof document !== 'undefined' && document.hidden) return
      getCellLife(sessionId)
        .then((r) => {
          if (cancelled) return
          const cell = r.cell
          if (cell.alive) {
            sawLife.current = true
            setLife(cell)
            setPhase('alive')
            return
          }
          if (!sawLife.current) {
            // Never born: there is nothing to claim.
            setPhase('silent')
            setLife(null)
            return
          }
          setPhase('dying')
          decay.current = window.setTimeout(() => {
            if (!cancelled) setPhase('gone')
          }, DECAY_MS)
        })
        .catch(() => {
          if (!cancelled) setPhase(sawLife.current ? 'gone' : 'silent')
        })
    }
    read()
    const id = window.setInterval(read, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
      window.clearTimeout(decay.current)
    }
  }, [sessionId])

  if (phase === 'silent' || !life) return null

  if (phase === 'gone') {
    return (
      <span data-testid="cell-life-gone" className="text-ui-xs text-ink-faint">
        {t('chat.cellEvaporated')}
      </span>
    )
  }

  const ms = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 3 }).format(
    life.avg_ms ?? 0,
  )
  const resting = (life.idle_seconds ?? 0) >= POLL_MS / 1000
  const left = Math.max(0, Math.round(life.seconds_left ?? 0))
  const mins = Math.floor(left / 60)
  const secs = left % 60
  const leftText = mins > 0 ? `${mins}:${String(secs).padStart(2, '0')}` : `${secs}s`

  // A cell without a guest cannot carry a call. Reporting "0 ms/call · idle"
  // there was the false claim the QA pass found; the state is the whole answer.
  if (life.contained === false) {
    return (
      <span
        data-testid="cell-life-line"
        className={`text-ui-xs text-ink-faint font-mono truncate ${
          phase === 'dying' ? 'ephe-decay' : 'ephe-condense'
        }`}
      >
        <span data-testid="cell-life-sandbox-off">
          {t('chat.cellUncontained', { ordinal: life.ordinal ?? 0 })}
        </span>
      </span>
    )
  }

  return (
    <span
      data-testid="cell-life-line"
      className={`text-ui-xs text-ink-faint font-mono truncate ${
        phase === 'dying' ? 'ephe-decay' : 'ephe-condense'
      }`}
    >
      <span>{t('chat.cellLife', { ordinal: life.ordinal ?? 0, ms })}</span>
      {' · '}
      {/* Only the state word is an announcement — the remaining time shifts with
          every tick and would fill a live region at five-second intervals. That is
          why it stands as readable text, not as a title. */}
      <span aria-live="polite" data-testid="cell-life-state">
        {t(resting ? 'chat.cellResting' : 'chat.cellRunning')}
      </span>
      {' · '}
      <span data-testid="cell-life-left">{t('chat.cellLeft', { left: leftText })}</span>
    </span>
  )
}
