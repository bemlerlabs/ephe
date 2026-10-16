/**
 * Duration formatting for the live turn timer (parity with „Working for Xm Ys“).
 * P6 A2 (DRY): delegates to the central format core `lib/format.ts`.
 * Below 1s the full-second display („0s“) stays, as the turn timer established
 * it; from 1s the Ephe norm applies: at most 2 units, no 0s suffix.
 */
import { fmtClockDuration, fmtDurationUnits } from '@/lib/format'
import { deepSelect } from '@/lib/deepSettings'

export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  if (totalSeconds === 0) return '0s'
  // I6-3: `chat.duration_format` picks between the terse Ephe norm and the
  // clock form; with no register stored (backend unreachable) the norm stays.
  return deepSelect('chat.duration_format', 'compact') === 'clock'
    ? fmtClockDuration(totalSeconds * 1000)
    : fmtDurationUnits(totalSeconds * 1000)
}
