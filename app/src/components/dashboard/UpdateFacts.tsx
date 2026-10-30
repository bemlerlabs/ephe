/**
 * The two facts the update channel turns on: the commit this build runs and the
 * channel that answered. Their own module because UpdateDialog sits on the
 * 400-line wall, and a row that only appears when the answer carries it is a
 * self-contained decision.
 */
import { DetailRow } from './UpdateNotes'

export function UpdateFacts({
  commit,
  channel,
  commitLabel,
  channelLabel,
}: {
  commit?: string
  channel?: 'release' | 'main'
  commitLabel: string
  channelLabel: string
}) {
  return (
    <>
      {commit && (
        <DetailRow label={commitLabel} value={commit} mono testId="update-details-commit" />
      )}
      {channel && (
        <DetailRow label={channelLabel} value={channel} testId="update-details-channel" />
      )}
    </>
  )
}
