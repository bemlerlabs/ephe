/**
 * Duration formatting for the surfaces that show how long something took.
 * P6 A2 (DRY): delegates to the central format core `lib/format.ts`.
 * `formatDuration` keeps the full-second floor („0s“) the agent panels established;
 * `formatTurnDuration` adds the millisecond read the turn head has always shown
 * below a second. Both follow `chat.duration_format` (I6-3) from there up.
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

/**
 * The form of the turn head on the assistant bubble. Below a second it keeps the
 * millisecond read that head has always shown — a turn that ended in half a second
 * is an instrument fact, not „0s" — and from there up it follows
 * `chat.duration_format` like every other duration the product displays.
 */
export function formatTurnDuration(ms: number): string {
  return Math.floor(ms / 1000) === 0 ? fmtDurationUnits(ms) : formatDuration(ms)
}
